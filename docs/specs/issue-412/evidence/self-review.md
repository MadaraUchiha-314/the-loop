---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#412"
---

# Self-review: four `test_instance.py` tests read the machine they run on (issue-412)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`,
> `stopOnNoNewFindings: true`; `the-loop critic list` reports "No critics configured", so
> the critic rounds are **unavailable** and do not count toward `criticReviewCount`
> (`reference/reviewing.md` § Running a critic round). The self-review read the change
> adversarially in three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (scope read) | new findings | (a) the fixture was first written suite-wide in `conftest.py` — running the full suite failed **14** tests in `test_poll_status.py`, `test_poll_command.py` and `test_lifecycle_cmd.py`, because the config path's parent anchors the state root, so pinning it moved the root out from under tests that `chdir` and write their own config. Narrowed to `test_instance.py`, and the reasoning recorded rather than discarded | `bugfix.md` § Defect 1, `verification.md` § The suite-wide variant |
| 2 | self (mechanism read) | new findings | (b) my first-round justification ("the cwd branch reads ambient state") was **wrong as stated** — a test that chdirs to its own `tmp_path` and writes a config there controls the lookup completely and is already hermetic. The rule in `docs/capabilities/testing-and-contracts.md` was rewritten from "pin it everywhere" to "pin **or** control it, and do not pin wholesale"; (c) considered `monkeypatch.setattr(runner_mod, "_cli_config_export", lambda: "")` (the seam `test_tmux_runner.py` uses) and rejected it: that stubs out the very function whose export the argv assertion is about, so the test would stop covering the issue-393 absolutization. Pinning the *input* keeps both running for real | capability doc, `bugfix.md` § Defect 1 |
| 3 | self (adversarial read) | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |

## Questions asked of the diff, and their answers

- **Does the fixture hide the bug rather than fix it?** No. `default_cli_config_path()` and
  `_cli_config_export()` both still execute; they resolve branch 2 to a path that is not a
  file and return `""` through the real "empty ⇒ not exported" rule. A stub would have
  hidden it; a pinned input does not.
- **Is autouse too broad for the module?** It covers ~63 tests, only 5 of which spawn. The
  cost is one `setenv` per test; the benefit is that the next argv test added here inherits
  the pinning rather than the bug. Judged the right trade and written down in
  `bugfix.md` § What it costs.
- **Does `tmp_path` in an autouse fixture collide with tests that use `tmp_path` themselves?**
  `test_describe_instance_merges_declared_session_and_control_sources` takes `tmp_path` and
  builds a state root under it. It shares the same directory, but the fixture only names a
  path and never creates it, so nothing is added to what that test sees — confirmed by the
  test passing in all four environments.
- **Was the Makefile changed in the safer direction?** Yes. The hook is what CI runs, so the
  local target moved onto it. Editing the hook instead would have changed CI's behaviour to
  settle a local-only complaint, and `.github/workflows/**` is a sensitive path.
- **Does the negative control prove the fix?** Yes — T5 re-ran the four tests on a stashed
  tree in the same environments and got 4 failed / 59 passed, so T1's green is a change in
  the tests' behaviour, not a suite that never had the bug.
- **Is AC2 actually established, or only asserted?** Established by running the *whole*
  suite, in both working directories, with `~/.the-loop/cli-config.yaml` present — the
  state that makes a contributor's machine red. See `verification.md` T2/T3.

## What a reviewer should push on

The judgement call is the **scope** of the fix: module-scoped pinning plus a written rule,
rather than a suite-wide fixture. The suite itself rejected the wider option (finding (a)),
and the narrower one leaves the same shape possible in another module — which is why the
rule went into the capability doc instead of only into code. If a reviewer would rather
have a mechanism than a rule, the conversation to have is whether `default_cli_config_path`
should grow an explicit test-mode seam, which is a change to shipped code and a different
work item.
