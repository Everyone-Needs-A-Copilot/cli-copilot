"""Pydantic Settings - loads all credentials from project root .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource

from copilot_cli.config.layers import CliLayer, load_tier_overlay, resolve_cli_layer_chain
from copilot_cli.config.secrets_ladder import resolve_secret


def _find_env_file() -> Path:
    """Walk up from CWD to find the nearest .env file.

    Resolution order:
    1. COPILOT_ENV_FILE environment variable (explicit override)
    2. Walk up from CWD, stopping at project root markers
    3. Standard machine-agnostic user config locations ($HOME-relative, so they
       are identical on every machine and carry no hardcoded absolute paths).
       This is what lets a hook or script running in any project subdirectory
       find the shared copilot config without a baked path.
    4. Fall back to .env in current directory
    """
    import os

    # 1. Explicit override
    explicit = os.environ.get("COPILOT_ENV_FILE")
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p

    # 2. Walk up from CWD
    current = Path.cwd()
    root_markers = {".git", "pyproject.toml", ".mcp.json", "package.json"}
    for parent in [current, *current.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
        # Stop at any project root marker
        if any((parent / marker).exists() for marker in root_markers):
            return parent / ".env"

    # 3. Standard user config locations (portable across machines)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    standard = [
        Path(xdg) / "copilot" / ".env" if xdg else Path.home() / ".config" / "copilot" / ".env",
        Path.home() / ".copilot-cli" / ".env",
    ]
    for candidate in standard:
        if candidate.is_file():
            return candidate

    # 4. Fallback
    return Path(".env")


# --- Deferred (per-field, on-first-read) secret resolution -------------------
#
# `requires_secret` is declared per SERVICE, but a `Settings` model carries
# every service's fields at once. Resolving all of them while the model is
# being BUILT therefore coupled every command to every other service's
# credentials: one absent secret (a `research` key) aborted `copilot cloudflare
# ...`, `copilot uspto ...`, and everything else, because none of them can be
# invoked without a `Settings` instance existing first.
#
# The fix is to move resolution from build time to READ time, so a secret is
# resolved by -- and only by -- the code that actually reads its field. What
# changes is exclusively *when* the ladder runs; a genuinely-needed,
# genuinely-missing secret still raises `SecretResolutionError` the moment its
# field is read, which is the point at which the caller was going to use the
# value anyway. Nothing here can hand back `""` or `None` for a declared
# secret: the field is REMOVED from the instance so ordinary attribute lookup
# misses it and `__getattr__` (the only way to observe it) either returns a
# real ladder-resolved value or raises.
#
# The plan is keyed by model class because it is a pure function of (model
# fields, resolved layer chain), both process-global. Two dicts, not one,
# because they answer different questions and conflating them reintroduces
# staleness: `_PENDING` is a strict one-construction handoff (written by
# `SecretRefSource.__call__`, consumed by the very next `model_post_init`),
# which is what lets `model_post_init` tell "this construction had a layered
# chain" from "this construction took the manifest-absent fast path" and drop a
# previous construction's plan in the latter case.
_PENDING_SECRET_SOURCE: dict[type[BaseSettings], SecretRefSource] = {}
_LAZY_SECRET_PLAN: dict[type[BaseSettings], tuple[SecretRefSource, frozenset[str]]] = {}


class SecretRefSource(PydanticBaseSettingsSource):
    """Resolver for declared `requires_secret: <NAME>` refs -- the single place
    a secret *value* enters a `Settings` model in the layered path, via the
    credential ladder (`secrets_ladder.resolve_secret`). Only engaged when
    `settings_customise_sources` builds the layered source tuple (i.e. a
    `copilot.layers.yml` with `product: cli` entries resolves); the
    manifest-absent fast path never constructs this class.

    A field only resolves through this source if some tier's
    `cli.overlay.yml` declares it in `requires_secret` (matched
    case-insensitively: `USPTO_CLI_API_KEY` -> `uspto_cli_api_key`). Every
    other field is left untouched here, falling through to the tier `.env`
    sources ahead of it in the tuple.

    As a settings SOURCE this contributes nothing (`__call__` returns `{}`):
    it registers a deferral plan instead, and `LazySecretSettings` calls
    `get_field_value` back on first read of each declared field. Staying in
    the source tuple is what keeps `.env`/env-var precedence intact for free
    -- this source sits LAST, so a tier that supplies a declared secret through
    a higher-precedence source still wins and that field is never deferred at
    all (`model_post_init` checks `model_fields_set`).

    Fail-closed by construction: a declared secret that misses every ladder
    rung raises `SecretResolutionError` (via `resolve_secret`) instead of
    silently leaving the field at its `""` default -- see `secrets_ladder.py`
    and red-team §6.3 ("no silent no-op"). Deferring resolution moves *when*
    that raise happens (first read, not model build) and never *whether* it
    happens, so the field is never observable as an empty default.

    A declared secret may also carry a per-name routing hint (`cli.overlay.
    yml`'s mapping-form `requires_secret: [{name, from}]`, parsed by
    `layers.load_tier_overlay` into `TierOverlay.all_requires_secret_hints()`)
    -- threaded through to `resolve_secret`'s `prefer` param below. The hint
    is a pure ladder-rung filter (see `secrets_ladder._RUNG_SUBSET_FOR_HINT`):
    it never changes *whether* a name resolves through this source, only
    which rungs are consulted while resolving it.
    """

    def __init__(self, settings_cls: type[BaseSettings], chain: list[CliLayer]):
        super().__init__(settings_cls)
        self._chain = chain
        # Parsing every tier's overlay is itself deferred: a construction that
        # never reads a declared secret must not pay for reading the YAML that
        # declares them. `_collected` is the memo, `None` until first need.
        self._collected: tuple[set[str], dict[str, str]] | None = None

    @property
    def _secret_names(self) -> set[str]:
        return self._collect()[0]

    @property
    def _secret_hints(self) -> dict[str, str]:
        return self._collect()[1]

    def _collect(self) -> tuple[set[str], dict[str, str]]:
        if self._collected is None:
            self._collected = self._collect_secret_names(self._chain)
        return self._collected

    @staticmethod
    def _collect_secret_names(chain: list[CliLayer]) -> tuple[set[str], dict[str, str]]:
        names: set[str] = set()
        hints: dict[str, str] = {}
        for layer in chain:
            overlay = load_tier_overlay(layer.overlay_path)
            names.update(overlay.all_requires_secret())
            # Nearest tier wins on a hint conflict, same as every other
            # nearest-wins fold in this module -- `chain` is already
            # highest-precedence-first, so first-seen-per-name wins here.
            for name, hint in overlay.all_requires_secret_hints().items():
                hints.setdefault(name, hint)
        return names, hints

    def deferrable_field_names(self) -> frozenset[str]:
        """This model's field names that some tier declared `requires_secret`.

        Per-class and instance-independent (`model_fields` x the chain's
        declarations), which is why it is safe to cache in `_LAZY_SECRET_PLAN`
        alongside the source. Whether a given INSTANCE actually defers one of
        these is decided per-instance in `model_post_init`, from that
        instance's `model_fields_set`.
        """
        return frozenset(
            name for name in self.settings_cls.model_fields if name.upper() in self._secret_names
        )

    def get_field_value(self, field, field_name: str) -> tuple[object, str, bool]:
        env_name = field_name.upper()
        if env_name not in self._secret_names:
            return None, field_name, False
        prefer = self._secret_hints.get(env_name)
        return resolve_secret(env_name, self._chain, prefer=prefer), field_name, False

    def __call__(self) -> dict[str, object]:
        """Contribute no values; hand this model's deferral plan forward.

        The `issubclass` guard is a fail-closed backstop, not a formality: a
        model that reaches this source without inheriting `LazySecretSettings`
        has nothing to perform the deferred read, so its declared secrets would
        silently sit at their `""` defaults -- precisely the silent no-op the
        ladder exists to prevent. Refusing loudly at build time keeps that
        mistake impossible to ship.
        """
        if not issubclass(self.settings_cls, LazySecretSettings):
            raise TypeError(
                f"{self.settings_cls.__name__} declares `requires_secret` fields but does "
                "not inherit `LazySecretSettings`; deferred secrets would never resolve"
            )
        _PENDING_SECRET_SOURCE[self.settings_cls] = self
        return {}


class LazySecretSettings(BaseSettings):
    """Base for settings models whose declared secrets resolve on FIRST READ.

    Pairs with `SecretRefSource` to give `requires_secret` per-service
    resolution: a declared secret this instance received from no
    higher-precedence source is dropped from the instance, so reading it is
    the event that runs the credential ladder. A command that never touches
    another service's field never resolves -- or fails on -- that service's
    credential.

    Subclasses need only inherit this; their `settings_customise_sources`
    stays exactly as it was. The chain is never re-resolved here -- it arrives
    on the `SecretRefSource` the subclass's own `settings_customise_sources`
    already built, so each model keeps its own manifest gating (and its own
    tests' `resolve_cli_layer_chain` patching) as the single source of truth.
    """

    def model_post_init(self, context: object, /) -> None:
        super().model_post_init(context)
        source = _PENDING_SECRET_SOURCE.pop(type(self), None)
        if source is None:
            # Manifest-absent fast path: no layered chain resolved for this
            # construction, so nothing is declared and nothing may be deferred.
            # Dropping any earlier plan is what stops a previous, layered
            # construction of this same class from leaking its chain into this
            # one.
            _LAZY_SECRET_PLAN.pop(type(self), None)
            return

        deferrable = source.deferrable_field_names()
        _LAZY_SECRET_PLAN[type(self)] = (source, deferrable)
        for name in deferrable:
            # `model_fields_set` is exactly "some source supplied this".
            # `SecretRefSource` supplies nothing and sits last, so a name in
            # this set came from a HIGHER-precedence source (env var, a tier
            # `.env`) and must keep that value -- same precedence the eager
            # source got from its position in the tuple.
            if name not in self.model_fields_set:
                self.__dict__.pop(name, None)

    def __getattr__(self, name: str) -> object:
        """Resolve a deferred secret at its point of use.

        Only reached for attributes ordinary lookup missed, which for a
        declared secret means `model_post_init` deferred it. Resolution is
        memoized into the instance so the ladder runs at most once per name
        per process -- matching the old eager behaviour, and keeping rung 4's
        one-time interactive paste from re-prompting on every read.
        """
        plan = _LAZY_SECRET_PLAN.get(type(self))
        if plan is not None:
            source, deferrable = plan
            if name in deferrable:
                value, _key, _is_complex = source.get_field_value(None, name)
                self.__dict__[name] = value
                # Record it as source-provided, which is what it is: eager
                # resolution left these in `model_fields_set`, and this module
                # already treats that set as "provided vs. left at default"
                # (see `services/infisical/core/config.load_settings`).
                self.__pydantic_fields_set__.add(name)
                return value
        return super().__getattr__(name)


class TierConfigSource(PydanticBaseSettingsSource):
    """Surfaces ONE tier's committed `cli.overlay.yml` `adopt[].config` AND
    `provides[].config` blocks as a settings source -- the config-inheritance
    counterpart to `SecretRefSource`. This is what lets non-secret
    store/service config (e.g. `infisical_workspace_id`) inherit down-tier
    from a committed overlay instead of only ever living in that tier's
    local `.env`. `provides[].config` (ADR-001) works identically to
    `adopt[].config` -- same shape, same fold -- so a tier's own
    `provides:`-declared service can also ship its non-secret config in the
    committed overlay, not just an `adopt:`-declared one.

    Unlike `SecretRefSource` (which spans the whole chain), one instance
    covers exactly one layer, so `settings_customise_sources` can interleave
    it immediately AHEAD of that SAME layer's `DotEnvSettingsSource` in the
    source tuple -- giving a tier's committed `config:` precedence over its
    OWN `.env`, while a NEARER tier's `.env` still outranks a FARTHER tier's
    `config:` because nearest-wins is preserved by source ORDER, not by
    anything in this class.

    Overlay config keys are already lowercase field-name-shaped (e.g.
    `infisical_base_url`, matching the field name exactly, matched
    case-sensitively here); a key that isn't an actual `Settings` field
    simply never matches any `field_name` iterated in `__call__` below --
    belt-and-suspenders alongside `extra="ignore"`.
    """

    def __init__(self, settings_cls: type[BaseSettings], layer: CliLayer):
        super().__init__(settings_cls)
        self._config = self._collect_config(layer)

    @staticmethod
    def _collect_config(layer: CliLayer) -> dict[str, str]:
        """Fold this layer's `adopt[].config` then `provides[].config`,
        `dict.update` (last-write-wins) within each list and across the two.

        Same-tier adopt-vs-provides collision rule (ADR-001, an authoring
        edge case -- both blocks live in the same tier's single overlay
        file): **provides wins**. `provides` is processed after `adopt`,
        matching the canonical `adopt:` -> `provides:` -> `override:`
        declaration order documented at the top of this module, so a later
        block in the same file naturally overrides an earlier one -- the
        same last-write-wins reading `dict.update` already gives adopt
        entries against each other. `provides` config is also arguably the
        more specific declaration: it belongs to a service the tier itself
        implements, vs. `adopt`'s tuning of a shared base service.
        """
        overlay = load_tier_overlay(layer.overlay_path)
        merged: dict[str, str] = {}
        for adopt in overlay.adopt:
            merged.update(adopt.config)
        for provide in overlay.provides:
            merged.update(provide.config)
        return merged

    def get_field_value(self, field, field_name: str) -> tuple[object, str, bool]:
        if field_name not in self._config:
            return None, field_name, False
        return self._config[field_name], field_name, False

    def __call__(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field, field_name)
            if value is None:
                continue
            result[key] = self.prepare_field_value(field_name, field, value, is_complex)
        return result


class Settings(LazySecretSettings):
    model_config = SettingsConfigDict(
        env_file=str(_find_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer the CLI tier chain into settings resolution -- gated
        entirely behind `resolve_cli_layer_chain()` (design doc §1.2, D5).

        No manifest resolves (or none of its entries are `product: cli`)
        -> returns the IDENTICAL source tuple as pre-Phase-1, so
        `_find_env_file()` (baked into `model_config.env_file` above) is
        reached completely unchanged and `COPILOT_ENV_FILE` keeps working
        exactly as it always has. This is the back-compat fast path the
        parity fitness test gates.
        """
        chain = resolve_cli_layer_chain()
        if chain is None:
            return (init_settings, env_settings, dotenv_settings, file_secret_settings)

        # ---- LAYERED PATH: highest precedence FIRST (personal ... foundation) ----
        # Per tier, a `TierConfigSource` is interleaved immediately AHEAD of
        # that SAME tier's `DotEnvSettingsSource` -- so a tier's committed
        # `cli.overlay.yml` config outranks its OWN `.env`, while a NEARER
        # tier's `.env` still outranks a FARTHER tier's `config:` (nearest-
        # wins preserved by list order, not by pairing). Do NOT hoist every
        # tier's config ahead of every tier's `.env` -- that would invert
        # nearest-wins across tiers.
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        for layer in chain:
            sources.append(TierConfigSource(cls, layer))
            sources.append(DotEnvSettingsSource(cls, env_file=layer.env_path))
        sources.append(SecretRefSource(cls, chain))
        return tuple(sources)

    # --- Git ---
    git_user_name: str = "copilot"
    git_user_email: str = "dev@example.com"

    # --- Docker ---
    docker_socket: str = "/var/run/docker.sock"

    # --- Shell ---
    shell_scripts_path: str = ""
    shell_timeout: int = 3600

    # --- PostgreSQL ---
    # nocodb_database_url / n8n_database_url are example *logical database
    # names* for the generic multi-DB feature (like formbricks_database_url,
    # which has never had a matching CLI service) -- unrelated to any
    # `copilot <service>` adapter of the same name.
    database_url: str = ""
    nocodb_database_url: str = ""
    n8n_database_url: str = ""
    formbricks_database_url: str = ""

    # --- Filesystem ---
    allowed_volumes: str = "/tmp"
    max_file_size_mb: int = 500

    # --- Monitoring ---
    cpu_alert_threshold: int = 80
    memory_alert_threshold: int = 85
    disk_alert_threshold: int = 90

    # --- USPTO ---
    uspto_cli_base_url: str = ""
    uspto_cli_api_key: str = ""
    uspto_tsdr_base_url: str = "https://tsdrapi.uspto.gov"

    # --- Skills ---
    skill_paths: str = ""  # Comma-separated additional skill search paths

    # --- Database backups / transfers ---
    backup_dir: str = "~/copilot-backups"

    # --- General ---
    log_level: str = "info"

    def get_allowed_volumes(self) -> list[str]:
        return [v.strip() for v in self.allowed_volumes.split(",") if v.strip()]

    def get_backup_dir(self) -> Path:
        """Return ``backup_dir`` as an expanded ``Path``. Does not create it."""
        return Path(self.backup_dir).expanduser()

    def get_database_configs(self) -> dict[str, str]:
        """Return map of database name -> connection URL."""
        configs: dict[str, str] = {}
        if self.nocodb_database_url:
            configs["nocodb"] = self.nocodb_database_url
        if self.n8n_database_url:
            configs["n8n"] = self.n8n_database_url
        if self.formbricks_database_url:
            configs["formbricks"] = self.formbricks_database_url
        if self.database_url:
            configs["main"] = self.database_url
        return configs


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
