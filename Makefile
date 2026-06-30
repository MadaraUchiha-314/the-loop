# the-loop — root task runner. RULE: all scripts run from the project root, and
# CI runs these same tools (via pre-commit). Targets are thin wrappers over the
# configured tooling so local == CI.

.PHONY: help install-dev check lint format typecheck test validate pre-commit

help:
	@echo "targets: install-dev, check, lint, format, typecheck, test, validate, pre-commit"

install-dev:
	pip install -e ./cli[dev] pre-commit pyright jsonschema pyyaml

lint:
	ruff check cli
	npx --yes markdownlint-cli2 "**/*.md"

format:
	ruff format cli

typecheck:
	pyright cli

test:
	cd cli && python -m pytest -q

validate:
	python scripts/validate_config.py

# Everything, the way CI runs it.
pre-commit:
	pre-commit run --all-files --show-diff-on-failure

check: lint typecheck validate test
