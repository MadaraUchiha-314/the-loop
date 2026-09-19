# the-loop — root task runner. RULE: all scripts run from the project root, and
# CI runs these same tools (via pre-commit). Targets are thin wrappers over the
# configured tooling so local == CI. the-loop declares `uv` as its Python package
# manager, so it uses `uv` here (uv workspace; deps pinned in uv.lock).

.PHONY: help install-dev check lint format format-check typecheck test validate pre-commit graph

help:
	@echo "targets: install-dev, check, lint, format, typecheck, test, validate, pre-commit, graph"

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

test:
	uv run --project cli python -m pytest -q cli

validate:
	uv run python scripts/validate_config.py

# Everything, the way CI runs it.
pre-commit:
	uv run pre-commit run --all-files --show-diff-on-failure

check: lint format-check typecheck validate test

# The knowledge graph's no-LLM half, the way .github/workflows/graphify.yml rehearses it
# on a pull request (issue-385): AST extraction for code, no doc extraction, no community
# naming. `uv tool install --with anthropic graphifyy` first. The committed graph.json and
# manifest.json are the baseline, so this re-extracts only what changed.
graph:
	GRAPHIFY_NO_BACKUP=1 graphify extract . --code-only
	GRAPHIFY_NO_BACKUP=1 graphify cluster-only . --no-label
