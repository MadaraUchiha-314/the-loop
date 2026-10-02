---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#454"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the CLI suite reads the machine it runs on

> Derived from [`bugfix.md`](bugfix.md). Planned at `test-planning`, results recorded at
> `verification`. See [`evidence/verification.md`](evidence/verification.md).

## What "proved" means here

The defect is in the tests, so the proof is a **host matrix**. The suite runs on a Linux
host that is made to look like the operator's Mac in each respect the ticket names:

- a harness CLI installed;
- the temp dir behind a symlink;
- no tmux on PATH.

First the original tests run under those conditions, and they must fail with the
ticket's failures (red). Then the fixed tests run under the same conditions, and they
must pass with no new skips (green).

The BSD `ps` column cannot be produced on Linux. So the proof for defect 3 is different:
`_stat()` is run with `/proc` hidden, against an attached and a detached child, to show
that the `ps` branch agrees with `/proc` and that the detachment check still tells the two
apart.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (critic availability) | yes | `available` follows the test's `shutil.which`, both branches, on any host (R1.1, R1.2) | `test_core_repo.py`, `test_critics.py` |
| T2 | Unit (gate containment) | yes | four hostile refs land directly in the temp dir, compared lexically and canonically; a symlinked temp dir is in effect and containment holds through it (R2.1–R2.3) | `test_harness_gate.py` |
| T3 | Integration (daemon detach) | yes | the detachment, pidfile and log assertions pass with `getsid`/`getpgid` (R3.1, R3.2) | `test_poll_daemon_integration.py` |
| T4 | Probe (`_stat` without `/proc`) | yes | the `ps -o ppid=` branch agrees with `/proc`; `sid == pgid != getpgid(0)` is false for an attached child and true for a detached one (R3.1, R3.2) | scratch script, output in evidence |
| T5 | Probe (tmux tripwire) | yes | a test that runs the stub fails at teardown naming the call; resolving it alone passes (R4.2) | scratch test, output in evidence |
| T6 | Red (host matrix, old tests) | yes | the original five modules fail under stub harnesses + symlinked `TMPDIR` + no tmux, with the ticket's failures (R5) | `git show HEAD:` copies |
| T7 | Green (host matrix, full suite) | yes | the full suite passes under the same conditions with no new skip (R4.1, R5.1, R5.2) | `cd cli && pytest -q -rs` |
| T8 | Regression (normal host) | yes | `make test`'s command passes on this host as is | `cd cli && uv run python -m pytest -q` |
| T9 | Static | yes | `ruff check`, `ruff format --check`, `pyright cli`, `markdownlint` on the docs touched | `make lint`, `make format-check`, `make typecheck` |
| T10 | macOS host run | n/a — no macOS host in this cloud checkout; T2's symlink case, T4 and T6 reproduce each macOS cause on Linux | | |
| T11 | Contract (OpenAPI), e2e, UI, performance, migration | n/a — no runtime code, route or behaviour changed | | |
| T12 | Security / abuse case | yes | the path-escape check still fails an id embedded raw; the stub reaches only the daemon subprocess's PATH | review + T2, T5 |

## Scenarios & requirement trace

| Row | Acceptance criterion | Case |
|-----|----------------------|------|
| T1 | R1.1, R1.2 | `installed ∈ {False, True}` → `available == installed`; `cursor-gpt` false and `claude-opus` true in one `critic list` |
| T2 | R2.1–R2.3 | `../../etc/passwd`, `github:o/r#1`, `/etc/passwd`, `a/../../b`; alias → `parent != resolve().parent`, `parent == alias`, `resolve().parent == real` |
| T3 | R3.2 | `stats["sid"] == stats["pgid"] != os.getpgid(0)`, pidfile lock held, log receiving `poll:` |
| T6 | R5 | the four ticket failures, plus seven poller tests and one ingress test refused by the tmux preflight |
| T7 | R5.1, R5.2 | `0 failed`; the skip list is the one skip the suite had before |

## Verification environment

- Linux, Python 3.11, `uv` 0.12.22, `uv sync`. Run from `cli/`, as `make test` and the
  pre-commit hook do (issue-412).
- Host conditions are built in the session scratchpad: stub `claude`, `codex`,
  `cursor-agent`, `aider`, `ttyd`, `gemini`; a PATH of `/usr/bin` symlinks minus `tmux`; and
  `TMPDIR` set to a symlink to a real directory.
