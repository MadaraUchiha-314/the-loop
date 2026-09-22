---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#422"
status: in-review            # draft | in-review | approved — tier 3: a human approves the PR
approvedBy: []
severity: medium
collaborators: [engineer]
overrides: {}
riskTier: 3                  # the ticket estimated 1–2; deleting two files under `.the-loop/**` is a sensitive path, and the fix reaches one runtime call site (the Slack probe's cache path)
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: the suite writes into the checked-in `.the-loop/` when run from the repo root

> Phases 1–2 of 4 (bugfix+design → testing plan → tasks). Source:
> [issue-422](https://github.com/MadaraUchiha-314/the-loop/issues/422), split out of
> [#412](https://github.com/MadaraUchiha-314/the-loop/issues/412) /
> [#421](https://github.com/MadaraUchiha-314/the-loop/pull/421).

## Summary

Run from the repository root, the CLI suite rewrites the tracked
`.the-loop/portable/github-octo-repo-15.json`. That file and its `index.json` sibling are
themselves debris from an earlier run: `octo/repo#15` is the suite's fixture ref, and
the pair was committed in [#366](https://github.com/MadaraUchiha-314/the-loop/pull/366).

The ticket traced the resolution chain and placed the write at session shutdown. Neither
guess held. The write is **synchronous, inside one test's body**, and it is one of
**four** tests writing into the repository's `.the-loop/`. The other three write into
gitignored paths, so `git status` never showed them.

## Steps to reproduce

On `main` at `a754cea`, from the repository root:

```console
$ git status --porcelain .the-loop/
$ uv run --project cli python -m pytest -q cli
4517 passed, 1 skipped
$ git status --porcelain --ignored .the-loop/
 M .the-loop/portable/github-octo-repo-15.json
!! .the-loop/local/
!! .the-loop/logs/
```

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| the working tree after a root run | clean | one tracked record rewritten |
| the repository's `.the-loop/` after a root run | untouched | four tests write into it, three of them into ignored paths |
| `.the-loop/portable/` in version control | this repository's own work-item records, if any | two records for a repository that does not exist |

## Root cause

Found with a tracer that logs a stack for every write under either `.the-loop/`, then
confirmed by the guard below, which names the same four tests (method in
[`evidence/verification.md`](evidence/verification.md) § How the writers were found).
There are four writers, reached by two routes.

**Route A: a default relative to the working directory.** From `cli/` these writes land
in `cli/.the-loop/`, which `.gitignore` already listed as "test residue". From the root
they land in the repository's own tree.

| Test | Writes | Why |
|---|---|---|
| `test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph` | `portable/github-octo-repo-15.json`, `portable/index.json` (**tracked**) | `_dispatcher` builds `RoutingConfig(...)` without `portable_dir`, whose default is `".the-loop/portable"`. The one test in the module whose comment reaches `_apply_control` records a `contribute` control there. |
| `test_sessions_restart_integration.py::…test_no_declared_value_reaches_any_output_on_any_path` (4 cases) | `logs/events.jsonl` | `eventlog.configure(str(tmp_path / "events.jsonl"), enabled=True)` passes the path as the **`source`** argument, so the log keeps its default path. |
| `test_doctor_slack.py::test_doctor_slack_prints_all_three_sections_and_exits_zero_when_clean` | `local/slack-directory.json` | `probe_subscription` resolves a channel *name* through `SlackDirectory(token_env=…)` built with no CLI config, and a directory with no config falls back to `.the-loop/local/`. This is a **runtime** defect. `the-loop doctor slack`, `channels status --probe` and the listener's connect-time probe cache the workspace directory under whatever directory they are run from, not under `<state.root>/local/` as [`channels-options.md`](../../config/cli/channels-options.md) documents. |

**Route B: the ambient config file.** This is the route the ticket predicted.

| Test | Writes | Why |
|---|---|---|
| `test_api_health_integration.py::test_a_hosted_loop_that_ends_on_its_own_drops_its_lock_and_says_so` | `poll.pid` | `ingress._start_poller(config)` takes its pidfile from `poller_daemon.default_options()`, which re-reads the config **file** rather than the mapping it was handed. From the root, that file is this repository's `.the-loop/cli-config.yaml`, and `state.root: .the-loop` anchors on it (issue-339). |

Two of these tests were also **weaker than they read**, because what they asserted on
was never what the code wrote:

- The restart test's "no credential in any event record" check read
  `tmp_path/events.jsonl`, which never existed. `_sinks` treats a missing log as empty, so
  the event-log half of an abuse-case assertion passed without looking at anything.
- The health test waited on, and asserted, the lock at `tmp_path`'s `poll.pid`, while the
  poller held a different file. The "lock is released" assertion was true before the
  poller ever started.

### Why the ticket's bisection saw nothing

The ticket's plugin reported no change at any test boundary. The audit hook attributes the
write to the test's own `call` phase, so the write is not at shutdown. What went wrong in
that plugin was not reconstructed. The stack in the evidence is what the fix relies on.

## The fix

### 1. Give each writer the state root it should have had

- `test_graph_drive_integration._dispatcher` defaults `portable_dir` to
  `tmp_path / "portable"`.
- The restart test passes `source` and `path=` as the signature has them, and asserts the
  log is non-empty before searching it, so the check cannot go vacuous again.
- The health test writes its config mapping to a file under `tmp_path` and points
  `$THE_LOOP_CLI_CONFIG` at it. That is the file the poller reads, so the pidfile the test
  waits on is the poller's own.
- **Runtime:** `probe_subscription` and `report_subscription` gain an optional
  `cli_config`, passed to `SlackDirectory`. Their three callers already hold it and now
  pass it: `channels status --probe`, `doctor slack`, and the socket listener's
  connect-time probe. Left out, behaviour is unchanged. The doctor test asserts the cache
  lands in `<state.root>/local/`.

Not changed: `RoutingConfig.portable_dir`'s cwd-relative default and `default_options()`
re-reading the file. Both are how the daemons resolve state when run by an operator, and
in production the file and the mapping are the same config. Making either
config-anchored is a behaviour change to the daemons, outside this ticket. The guard
below is what stops a test from depending on them.

### 2. Remove the debris

`.the-loop/portable/github-octo-repo-15.json` and `.the-loop/portable/index.json` are
deleted. Nothing reads them: every other mention of `github-octo-repo-15` is an example in
prose or a fixture under `cli/tests/`. The pattern that tracks `.the-loop/portable/` stays.
The directory is for this repository's own work-item records, should it ever hold any.

### 3. A guard, so the next instance is not silent

`cli/tests/conftest.py` installs an **audit hook** (`sys.addaudithook`). It records every
write-mode `open`, `os.rename`/`os.replace`, `os.mkdir`, `os.remove`, `os.rmdir`,
`os.link` and `os.symlink` whose written path falls under a protected tree. For a link
that is the destination, never the target. A name given beside a `dir_fd` is relative to
that directory, so it is skipped rather than misread against the cwd. The protected trees
are the repository's own `.the-loop/` and the `.the-loop/` of the directory pytest was
started from. An autouse fixture fails the test that made the write, printing the path
and the stack. `pytest_sessionfinish` catches a write made after the last teardown.

Three choices worth stating:

- **An audit hook, not a before/after snapshot.** A snapshot names no test and no line.
  It also cannot tell the suite from a daemon an operator is running out of this
  checkout: `.the-loop/cli-config.yaml` is checked in precisely so it can be. The hook
  sees only the test process.
- **The cwd's tree too, not only the repository's.** CI runs from `cli/`, so guarding
  `cli/.the-loop/` is what makes CI enforce this. A cwd-relative writer trips the guard
  from either directory, instead of only from the one CI never uses.
- **Fail the test, do not block the write.** Raising inside the hook would make the write
  itself fail, and much of the dispatcher and channel code is fail-open: a broad
  `except` would swallow it and the test would pass. Recording and failing at teardown
  cannot be swallowed.

Limits: the hook does not see a test's subprocesses. A write from a background thread
that outlives its test is reported by the next test's teardown, with a stack that still
names the code. The first limit was checked once by hand. A `sitecustomize` tracer,
exported to every child that inherits the test's environment, found no subprocess
writer.

## What it costs

- One Python call per audited event for the whole suite. Measured from `cli/`, back to
  back on one machine: 185.05s without the hook, 180.81s with it. That is within
  run-to-run noise (§ T7 of the evidence).
- A test that writes into a protected tree now fails with a message naming
  `tmp_path` as the fix. That is the intent.
- `.gitignore`'s `cli/.the-loop/` entry now describes residue the suite no longer leaves.
  It stays, reworded, for checkouts that still carry the old directory.

## Acceptance criteria

1. WHEN the CLI test suite is run from the repository root THEN it SHALL leave the
   working tree clean (`git status --porcelain` reports nothing).
2. WHEN the suite is run from any working directory THEN no test SHALL write into the
   repository's checked-in `.the-loop/` state.
3. WHERE `.the-loop/portable/` holds records that exist only as test debris THEN they
   SHALL be removed from version control.
4. WHEN a test writes into the repository's `.the-loop/` or the working directory's
   `.the-loop/` THEN that test SHALL fail, naming the path and the code that wrote it.
5. WHEN a Slack channel is configured by name and the subscription probe resolves it THEN
   the directory cache SHALL be written under `<state.root>/local/`, not under the
   working directory.

AC1–AC3 are the ticket's, verbatim. AC4 is the ticket's optional step 3, made concrete.
AC5 is the runtime defect the guard surfaced.

## Security considerations

- **No credential moves.** The Slack change passes a config mapping the caller already
  holds to a constructor that already accepts it. The token is still read from the
  environment variable the channel config names, exactly as before. Only the cache
  file's path changes, and the cache holds names and ids, never a token.
- **The cache moves to where it was documented to be.** Before the fix, a probe run from
  a shared directory wrote the workspace's channel and user directory there. After it,
  the cache is under the operator's own state root. That is a small reduction in
  exposure.
- **An abuse-case assertion is restored, not weakened.** The restart test now checks the
  event log that the code actually writes, and it still passes: no declared value
  reaches the log on any of the four paths.
- **The guard reads nothing and writes nothing.** It inspects path arguments and keeps an
  in-memory list.
- **Sensitive path:** `.the-loop/**` (two files deleted), hence tier 3.
