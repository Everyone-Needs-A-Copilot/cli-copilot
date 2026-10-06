---
paths:
  - "copilot_cli/services/**"
  - "copilot_cli/main.py"
  - "tests/test_services/**"
  - "docs/services/**"
---

# Adding a new service

1. Create `copilot_cli/services/<name>/` with `__init__.py`, `client.py`, and `commands.py`.
2. In `commands.py`, create a Typer sub-app and add its commands.
3. In `client.py`, implement the business logic.
4. Register it: a generic foundation service gets a `ServiceEntry` in `_BASE_SERVICES` in `copilot_cli/services/_loader.py` (this changes the fast-path contract, so update `tests/test_tier_inheritance_parity.py` deliberately); an org-specific service belongs in a tier overlay declared through `copilot.layers.yml`, not in this repo (see `docs/03-tier-inheritance.md`). `main.py` registers whatever `resolve_cli_services()` returns; do not hardcode `app.add_typer()` calls.
5. Add the service's health check to `_collect_health_checks()` in `copilot_cli/main.py`.
6. Add config fields to `copilot_cli/config/settings.py` if needed.
7. Add tests in `tests/test_services/test_<name>.py`.
8. Add docs in `docs/services/XX-<name>.md` and list it in `docs/services/00-service-index.md`.
