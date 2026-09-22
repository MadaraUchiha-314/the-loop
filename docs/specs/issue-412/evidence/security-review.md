---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#412"
---

# Security review: four `test_instance.py` tests read the machine they run on

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)).
> Run with the harness's built-in `security-review` skill over the branch diff, plus the
> checklist below against the specific seam this change touches.

## Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `cli/tests/test_instance.py` | one autouse fixture, `monkeypatch.setenv` | none — test-only |
| `Makefile` | `test:` target string, header comment | none — developer task runner |
| `docs/capabilities/testing-and-contracts.md` | prose | none |
| `docs/specs/issue-412/**` | prose | none |

No shipped code path changed. `cli/the_loop/` is untouched, so nothing here alters what a
spawned session receives, what the daemon resolves, or what reaches tmux.

## Findings

**None.**

## Checklist

- **Secrets.** The fixture's value is `tmp_path / "cli-config.yaml"` — a pytest-owned
  directory, unique per test. No token, credential, hostname or home-directory path is
  read, written, logged or committed. The file is never created, so nothing is put on disk
  at all.
- **The variable being set is itself sensitive-adjacent.** `$THE_LOOP_CLI_CONFIG` points at
  a config the daemon trusts, so *writing* it deserves a second look. It is set through
  `monkeypatch`, which unwinds at the end of each test, and only inside the test process —
  it is never exported to a child, and `_env_flags` is not reached by any test in this
  module (all spawns go through `_Probe`, which records argv and runs nothing).
- **The export path is unchanged.** `_cli_config_export()` and `default_cli_config_path()`
  keep their behaviour exactly; the fix pins the *input*, not the logic. In particular the
  absolutization and the "empty ⇒ not exported" rule from issue-393 (B6/R3) still hold and
  are still covered by `test_tmux_runner.py`, which asserts both directions. Had the fix
  stubbed `_cli_config_export`, that coverage would have been the thing weakened; it was
  not.
- **No weakened assertion.** The four tests assert the same argv they always did. The
  change removes an *inherited* third flag from the environment, not an expectation from
  the test — the abuse-case test among them
  (`test_only_the_configured_name_reaches_tmux_and_the_comment`, A6: only the validated
  config name is interpolated, never event text) still asserts exactly what it did, and
  now actually gets to assert it on every machine rather than on one.
- **Sensitive paths.** The change touches none of `**/*schema*`, `.the-loop/**`,
  `.github/workflows/**`, `**/auth/**`, `**/*secret*`, `**/*credential*`. The `Makefile` is
  not a sensitive path, and the CI workflow is deliberately *not* edited: the local target
  moved to CI's command, not the reverse, so no change to what runs on a runner.
- **Supply chain.** No dependency added, removed or re-pinned; `uv.lock` untouched.
- **Risk tier.** 2, unchanged from the ticket's own estimate — no escalation trigger fired,
  so the autonomous review suffices and no named human security sign-off is required
  (that threshold is tier 4).

## Verdict

Passed, with no findings and nothing escalated. The change narrows what the test suite
reads from the machine it runs on, which is a small reduction in ambient trust rather than
an increase.
