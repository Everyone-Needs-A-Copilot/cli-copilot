"""Read CLI component locations from the publisher-verified current release.

This consumes release metadata; it does not create releases or authorize new
signers. A present but invalid pointer is an error, never a mirror fallback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def _repository_identity(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("repository identity is missing")
    if value.startswith(("/", "~")):
        path = Path(value).expanduser().resolve()
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            origin = result.stdout.strip()
            if origin and not origin.startswith(("/", "~")):
                return _repository_identity(origin)
        return str(path)
    if "://" in value:
        parsed = urlsplit(value)
        host, repository = parsed.hostname, parsed.path
    else:
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", value)
        if not match:
            raise ValueError("repository identity must be a URL or absolute checkout path")
        host, repository = match.groups()
    if host in {"github-work", "github-personal"}:
        host = "github.com"
    if not host or not repository.strip("/"):
        raise ValueError("repository identity is malformed")
    repository = repository.strip("/").removesuffix(".git")
    return host.lower() + "/" + (repository.lower() if host.lower() == "github.com" else repository)


class CentralRelease:
    def __init__(self, root: Path, rows: dict[str, dict]):
        self.root = root
        self.rows = rows

    @classmethod
    def current(cls) -> CentralRelease | None:
        home = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot").expanduser()
        pointer = home / "current"
        if not pointer.exists() and not pointer.is_symlink():
            return None
        if not pointer.is_symlink():
            raise ValueError("current must be a release symlink")
        root = pointer.resolve(strict=True)
        if root.parent != (home / "releases").resolve():
            raise ValueError("current points outside the release store")
        manifest = root / "release.json"
        if manifest.is_symlink():
            raise ValueError("release metadata must belong to the selected snapshot")
        data = json.loads(manifest.read_text())
        if (
            not isinstance(data, dict)
            or type(data.get("schema")) is not int
            or data["schema"] != 1
            or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-z]{1,40}", str(data.get("release", "")))
            or data["release"] != root.name
        ):
            raise ValueError("release schema or identity does not match current")
        components = data.get("components")
        if not isinstance(components, list):
            raise ValueError("release components must be a list")
        rows = {}
        fields = {"name", "tier", "kind", "version", "ref", "commit", "source", "path", "signer"}
        for row in components:
            if (
                not isinstance(row, dict)
                or set(row) != fields
                or not all(isinstance(value, str) for value in row.values())
            ):
                raise ValueError("release component is malformed")
            if row["name"] in rows:
                raise ValueError("release has duplicate components")
            rows[row["name"]] = row
        return cls(root, rows)

    def layer_root(self, entry: dict) -> Path:
        role = {"org": "organization", "dept": "department"}.get(entry["role"], entry["role"])
        tier = role
        if role == "foundation":
            name, tier = "cli-copilot", "framework"
        elif role == "department":
            unit = entry.get("unit")
            if not isinstance(unit, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", unit):
                raise ValueError("central department layer needs a valid unit")
            tier = "department-" + unit
            name = "cli/" + tier
        elif role in {"personal", "organization"}:
            name = "cli/" + role
        else:
            raise ValueError("central CLI layer has an unknown role")
        row = self.rows.get(name)
        kind = "live-link" if role == "personal" else "signed-tag"
        if (
            row is None
            or row.get("path") != name
            or row.get("tier") != tier
            or row.get("kind") != kind
        ):
            raise ValueError(f"{name}: missing or mismatched central component")
        source = entry["source"]
        if entry.get("activation", "always") != "always":
            raise ValueError(f"{name}: custom activation requires review")
        allowed = (entry.get("policy") or {}).get("allowed_signers")
        if kind == "signed-tag" and allowed is not None:
            if not isinstance(allowed, list) or row.get("signer") not in allowed:
                raise ValueError(f"{name}: selected signer is outside the layer policy")
        if source.get("subpath"):
            raise ValueError(f"{name}: custom subpaths are not a central CLI component")
        if source.get("ref", "main").removeprefix("refs/tags/") != str(
            row.get("ref", "")
        ).removeprefix("refs/tags/"):
            raise ValueError(f"{name}: manifest ref differs from the selected release")
        if _repository_identity(source["repo"]) != _repository_identity(row.get("source")):
            raise ValueError(f"{name}: manifest repository differs from the selected release")
        candidate = self.root / name
        selected = candidate.resolve(strict=True)
        if not selected.is_dir():
            raise ValueError(f"{name}: component is not a directory")
        if kind == "signed-tag":
            if selected != candidate or not selected.is_relative_to(self.root):
                raise ValueError(f"{name}: signed component escapes the release snapshot")
            if not re.fullmatch(r"[0-9a-f]{40}", str(row.get("commit", ""))) or not row.get(
                "signer"
            ):
                raise ValueError(f"{name}: signed component has no verified provenance")
        else:
            live_source = Path(row["source"]).expanduser()
            if (
                not live_source.is_absolute()
                or not candidate.is_symlink()
                or selected != live_source.resolve()
            ):
                raise ValueError(f"{name}: personal component is not its recorded live link")
        declared = source.get("path")
        if declared is not None:
            if not isinstance(declared, str) or not Path(declared).expanduser().is_absolute():
                raise ValueError(
                    f"{name}: source.path must be an absolute component or recorded source"
                )
            declared_path = Path(declared).expanduser().resolve()
            recorded_source = Path(row["source"]).expanduser()
            if declared_path != selected and not (
                recorded_source.is_absolute() and declared_path == recorded_source.resolve()
            ):
                raise ValueError(f"{name}: source.path does not match the selected component")
        return selected
