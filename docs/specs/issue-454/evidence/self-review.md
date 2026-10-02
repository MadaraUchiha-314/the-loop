---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#454"
---

# Self-review: the CLI suite reads the machine it runs on (issue-454)

> The review policy is the defaults: `selfReviewCount: 3` and
> `stopOnNoNewFindings: true`. No `cli-config.yaml` declares critics in this cloud
> checkout, so the critic rounds are **unavailable** and do not count toward
> `criticReviewCount` (`reference/reviewing.md` § Running a critic round). Round 3 found
> nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (scope read) | new findings | (a) The first idea for tmux was `skipif(shutil.which("tmux") is None)`. Rejected: a recording stub showed the 11 daemon/ingress tests never run tmux, so a skip would hide them on exactly the hosts the ticket is about. Replaced with the `preflight_tmux` stub and a teardown tripwire. (b) The first count in `bugfix.md` said eleven tests need tmux. The red run showed eight (seven poller, one ingress). The fixture serves all eleven in the two modules. Corrected | `bugfix.md` § The fix; `verification.md` § T6 |
| 2 | self (mechanism read) | new findings | (c) A canonical comparison alone (`resolve()` on both sides) could pass a regression where the path is built outside the temp dir but resolves into it. Added the lexical assertion `path.parent == gettempdir()` beside the canonical one. (d) The symlink test could pass vacuously if the alias were not in effect. It now asserts first that the old, mixed comparison *would* fail there. (e) The stub's log path was interpolated into a shell script in single quotes. Now `shlex.quote`d | `test_harness_gate.py`; `conftest.py` |
| 3 | self (adversarial read) | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | — |

## Questions asked of the diff, and their answers

- **Is the escape check still a check?** Yes. In a mutation run, `attempts_path` was
  changed to embed the raw work-item id. All four parametrised cases and the symlink test
  failed. See `verification.md` § T2 mutation.
- **Does the detachment check still discriminate?** Yes. `_stat()` was run with `/proc`
  hidden, so `ppid` came from `ps`, against an attached and a detached `sleep`.
  `sid == pgid != getpgid(0)` was false for the first and true for the second, and both
  branches returned identical dictionaries. See `verification.md` § T4.
- **Is `os.getsid` safe to call on another process on macOS?** Yes. XNU's `getsid`
  returns the target's session ID for any existing PID; the only error is `ESRCH`. Linux
  does the same. The daemon is alive when it is called, and the test asserts that first.
- **Could the stub hide a real tmux regression?** Not one these tests were ever
  checking. They assert detachment, the pidfile lock, the log, idempotence and stop. The
  preflight's own refusal is covered by `runner.check_dependencies`'s unit tests, which
  are unchanged. The tripwire fails any test here that starts to run tmux.
- **Did anything else in the suite depend on the host?** A full run with stub `claude`,
  `codex`, `cursor-agent`, `aider`, `ttyd` and `gemini` on PATH, before the fix, failed
  only the two critic tests. The final matrix run (stubs, a symlinked `TMPDIR` and no tmux
  together) is recorded in `verification.md` § T7.

## What a reviewer should push on

The one judgement is **stub tmux, don't skip** (`bugfix.md` § The fix, row 4). The ticket
asks to "keep required tmux available for tests that genuinely exercise it". None of
these do, and the tripwire enforces that. If a reviewer would rather the poller tests run
against real tmux where it exists, that is a one-line change to the fixture, and it
brings back the host dependency the ticket asked to remove.
