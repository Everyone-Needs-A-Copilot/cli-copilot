.PHONY: install test test-cov lint format format-check check e2e-health e2e-health-pytest clean

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

check: lint format-check test

e2e-health:
	python3 scripts/e2e_health.py

e2e-health-pytest:
	COPILOT_E2E_LIVE=1 pytest tests/e2e/test_cli_connectivity.py -m e2e -vv -rA --tb=short --color=yes

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf *.egg-info dist build .pytest_cache .coverage htmlcov
