.PHONY: install test unit integration demo schemas lint clean

install:
	uv venv --python 3.12
	VIRTUAL_ENV=$(PWD)/.venv uv pip install --python $(PWD)/.venv/bin/python -e ".[dev]"

test:
	.venv/bin/python -m pytest

unit:
	.venv/bin/python -m pytest tests/unit -q

integration:
	.venv/bin/python -m pytest tests/integration -q

# Everything except the Lean-backed assertions, for a machine with no Mathlib.
test-no-lean:
	.venv/bin/python -m pytest -m "not lean" -q

demo:
	.venv/bin/pipeline demo --fresh

schemas:
	.venv/bin/python scripts/gen_schemas.py

clean:
	rm -rf .pytest_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
