---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#407"
---

# Documentation: the release leaves `uv.lock` a version behind (issue-407)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/release-publishing.md` | three bullets in *Current behaviour*: the lockfile re-resolved into the same bump commit with the tag moved onto it; `uv sync --locked` on every PR; the uv version pinned in the workflows and bounded by `required-version` | issue-407 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `.github/workflows/release.yml` | the `Fold the refreshed uv.lock into the bump commit` step, with the comment explaining why it amends rather than adding a commit and why the tag moves with it; the uv pin and why this job in particular needs one |
| `.github/workflows/ci.yml` | `uv sync --locked` and the comment naming what a bare `uv sync` hid; the uv pin |
| `.github/workflows/the-loop-gate.yml` | the uv pin, pointing at the other two |
| `pyproject.toml` | `[tool.uv] required-version` with the reason (the uv that writes the committed lockfile decides its text); `scripts` added to pyright's `cli/tests` extra paths, with the reason |
| `scripts/check_version_lockstep.py` | module docstring: why `uv.lock` is checked here and cannot be a `version_files` entry; `check_uv_lock`'s own docstring |
| `cli/tests/test_version_lockstep.py` | module docstring: the two drifts the one script now covers |

No user-facing document changes: nothing in the CLI's behaviour, configuration or
commands moves. The spec chain under `docs/specs/issue-407/` is the record.

## Reviewer briefing

The PR body carries it: what broke, the three-part fix, what a contributor has to do
(`uv self update` if their uv is below the window), and where the proof is.
