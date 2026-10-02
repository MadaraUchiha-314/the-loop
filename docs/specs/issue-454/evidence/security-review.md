---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#454"
---

# Security review: the CLI suite reads the machine it runs on

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)). This is a
> checklist read of the branch diff.

## Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `cli/tests/conftest.py` | `preflight_tmux` fixture and `PreflightTmux` helper | none (test only) |
| `cli/tests/test_core_repo.py`, `cli/tests/test_critics.py` | `shutil.which` fixed per test | none |
| `cli/tests/test_harness_gate.py` | canonical containment, four hostile refs, symlinked temp dir | none |
| `cli/tests/test_poll_daemon_integration.py`, `cli/tests/test_hosted_ingress_integration.py` | `_stat()` via `getsid`/`getpgid`; the daemon's PATH gets the stub | none |
| `docs/capabilities/testing-and-contracts.md`, `docs/specs/issue-454/**` | prose | none |

## Findings

**None.**

## Checklist

- **Runtime code.** Untouched. `runner.check_dependencies`, `critics.Critic.available` and
  the gate's `attempts_path` behave as before. The suite still runs them for real; only
  what they see is controlled.
- **The path-escape check is not weakened.** It now covers four hostile refs instead of
  one. It asserts the lexical parent and the canonical parent, so a work-item id embedded
  raw in the filename would still fail (`../../etc/passwd` would resolve to `/etc`). The
  symlink test adds a case the old assertion misread.
- **The tmux stub's reach.**
  - The stub lives under the requesting test's `tmp_path`.
  - It is prepended to the `environ` dict handed to the daemon subprocess, and never to
    the test process's own `os.environ`.
  - The log path is shell-quoted into the script (`shlex.quote`).
  - It runs nothing: it records its argv and exits 1.
  - Before this change these tests' daemons resolved the developer's real tmux, so the
    change shrinks what a test can touch.
- **The fixed `shutil.which` lookup.** It is patched through `monkeypatch`, so it unwinds
  per test. The patched function returns a stub path string and never executes anything.
- **Secrets.** None read, written or logged. The daemon tests already set a dummy
  `GH_TOKEN` and point at the loopback GitHub stub (issue-442); that is unchanged.
- **Sensitive paths.** None touched: not `**/*schema*`, `.the-loop/**`,
  `.github/workflows/**`, `**/auth/**`, `**/*secret*`, `**/*credential*`.
- **Supply chain.** No dependency added, removed or re-pinned; `uv.lock` untouched.
- **Risk tier.** 2. No named human security sign-off is required (that threshold is tier 4).

## Verdict

Passed, with no findings and nothing escalated.
