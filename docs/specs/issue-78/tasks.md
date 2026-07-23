---
type: tasks
phase: tasks-breakdown
workItem: issue-78
status: approved
approvedBy: ["@MadaraUchiha-314"]
collaborators: [engineer]
overrides: {}
---

# Tasks: derive the CLI version from package metadata

> Phase 3 of 3 (bugfix → design → tasks).

- [x] **T1 — Derive `__version__` from metadata.** In `cli/the_loop/__init__.py`, replace
  the hardcoded `"0.1.0"` with `importlib.metadata.version("the-loopy-one")`, falling back
  to a `0.0.0+unknown` sentinel on `PackageNotFoundError`. *(AC 1–3)*
- [x] **T2 — De-duplicate the webhook version.** In `cli/the_loop/webhook/server.py`, import
  `__version__` and build `server_version` from it instead of the hardcoded
  `"the-loop-gh-webhook/0.1.0"`. *(AC 4)*
- [x] **T3 — Regression tests.** In `cli/tests/test_cli.py`, assert `__version__` matches
  `importlib.metadata.version("the-loopy-one")`, is not `"0.1.0"`, and that `--version`
  prints `the-loop <version>`. *(AC 1–2)*
- [x] **T4 — Capability doc.** Record the derived-version behaviour and the fix in
  `docs/capabilities/cli.md` (current behaviour + history row).
- [x] **T5 — Gates.** `ruff check` / `ruff format --check`, `pyright`, and `pytest` all
  green.
