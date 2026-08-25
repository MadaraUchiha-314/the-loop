---
type: testing-plan
phase: test-planning
workItem: "issue-281"
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: lock artifacts at the approval gate

## Test matrix

| Type | In scope? | What it proves |
|------|-----------|----------------|
| unit | yes | `lock-artifacts` locks on approval, skips on `changes-requested`/no classification/absent artifact, blocks on ambiguity and unwritable files, preserves front-matter comments, records `approvedBy` |
| integration (graph) | yes | both shipped graphs compile with the new chains; producing nodes pass with `status: draft`; approval gates flip the status; parity tests (P1–P5) still hold |
| e2e (scenario suite) | yes | fixtures emitted **unlocked** reach `implementation` locked with exactly one approval per gate (regression for AC 1.5); `gate-rejection` blocks on a missing section instead of a missing lock |
| contract | n/a | no API/CLI surface changes |
| UI/visual | n/a | no UI |
| performance | n/a | a per-gate file splice is negligible |
| security/abuse-case | yes | unit: an unauthorized or self-marked comment still cannot reach a lock (covered by existing `classify-feedback` tests + new lock tests running behind it) |
| accessibility | n/a | no UI |
| migration | n/a | no state or config format change |
| manual | n/a | the automated walk covers the observed interaction end to end |

## Verification environment

Single repository, no external services: `uv run pytest` in `cli/`, plus `ruff`,
`pyright` and `markdownlint` per `.the-loop/harness-config.yaml`. The e2e suite is
hermetic (fake integration transport).

## Evidence plan

Test run output captured to `docs/specs/issue-281/evidence/` as markdown (commands +
raw output in fenced blocks).

## Verification results

Recorded at the `verification` node — see `evidence/test-run.md`.

| Activity | Command | Outcome | Evidence |
|----------|---------|---------|----------|
| unit + integration + e2e | `uv run pytest` (cli/) | pass | `evidence/test-run.md` |
| lint | `uv run ruff check` | pass | `evidence/test-run.md` |
| type check | `uv run pyright` | pass | `evidence/test-run.md` |
| markdown lint | `markdownlint` (changed docs) | pass | `evidence/test-run.md` |

## Review comments
