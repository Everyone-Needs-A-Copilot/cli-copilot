.PHONY: install-launcher install-launcher-dev check-launcher rollback-launcher install test test-cov lint format format-check check check-cli-docs e2e-health e2e-health-pytest clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

test-cov:
	pytest tests/ --cov=copilot_cli --cov-report=term-missing -m "not e2e"

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

check-cli-docs:
	python3 scripts/check-cli-guide.py CLI.md
	python3 -m unittest discover -s scripts/tests -p 'test_cli_contract.py'

check: check-cli-docs lint format-check test

e2e-health:
	python3 scripts/e2e_health.py

e2e-health-pytest:
	COPILOT_E2E_LIVE=1 pytest tests/e2e/test_cli_connectivity.py -m e2e -vv -rA --tb=short --color=yes

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf *.egg-info dist build .pytest_cache .coverage htmlcov

# Launcher resolving through ~/.copilot/current (see docs/ for the release pointer).
# Override HOME_DIR / BIN_DIR to target a sandbox.
install-launcher:
	python3 scripts/install-cli.py install $(if $(HOME_DIR),--home $(HOME_DIR)) $(if $(BIN_DIR),--bin-dir $(BIN_DIR))

install-launcher-dev:
	python3 scripts/install-cli.py install --dev . $(if $(HOME_DIR),--home $(HOME_DIR)) $(if $(BIN_DIR),--bin-dir $(BIN_DIR))

check-launcher:
	python3 scripts/install-cli.py check $(if $(HOME_DIR),--home $(HOME_DIR)) $(if $(BIN_DIR),--bin-dir $(BIN_DIR))

rollback-launcher:
	python3 scripts/install-cli.py rollback $(if $(HOME_DIR),--home $(HOME_DIR)) $(if $(STEPS),--steps $(STEPS)) $(if $(TO),--to $(TO))
