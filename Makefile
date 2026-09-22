# the-loop — root task runner. RULE: every target is invoked from the project
# root, and runs the SAME command CI runs (via pre-commit) — targets are thin
# wrappers over the configured tooling so local == CI. Where a hook needs another
# working directory, the target changes into it too and says so; a parity that is
# claimed but not kept is worse than none (issue-412). the-loop declares `uv` as
# its Python package manager, so it uses `uv` here (uv workspace; deps pinned in
# uv.lock).

.PHONY: help install-dev check lint format format-check typecheck test validate pre-commit

help:
	@echo "targets: install-dev, check, lint, format, typecheck, test, validate, pre-commit"

install-dev:
	uv sync

lint:
	uv run ruff check cli hooks
	npx --yes markdownlint-cli2@0.18.1 "**/*.md"

format:
	uv run ruff format cli hooks

# CI parity: pre-commit runs `ruff format`, so `check` must catch format drift too.
format-check:
	uv run ruff format --check cli hooks

typecheck:
	uv run pyright cli

# CI parity: byte-for-byte the pre-commit `pytest` hook's entry, `cd cli` included.
# The hook runs from cli/ so pytest's rootdir, `pythonpath` and `testpaths` come
# off cli/pyproject.toml without an editable install. Running the same tests from
# the repo root is NOT the same command: anything the-loop resolves relative to the
# working directory (./.the-loop/cli-config.yaml above all) resolves elsewhere, and
# `make check` went red on a tree CI called green (issue-412). Change both or
# neither.
test:
	cd cli && uv run python -m pytest -q

validate:
	uv run python scripts/validate_config.py

# Everything, the way CI runs it.
pre-commit:
	uv run pre-commit run --all-files --show-diff-on-failure

check: lint format-check typecheck validate test
