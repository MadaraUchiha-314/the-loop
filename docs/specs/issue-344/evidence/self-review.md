---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#344"
---

# Self-review: programmatic hooks around the lifecycle of a work item's delivery

> The `self-review` node's proof, per `reference/reviewing.md`. Critic rounds: no critic
> is configured in this environment (`critics: []` in this repository's CLI config, and no
> harness CLI on the container's `PATH`), so they are recorded **unavailable** and do not
> count toward the operator's `criticReviewCount`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) — the whole diff re-read against the requirements, the design's decision table and the security table | new findings | 4 found, 4 fixed |
| 2 | self (this session) — the tests, the docs and the spec re-read for parity with the code | new findings | 3 found, 3 fixed |
| 3 | `make check`, twice — the whole suite under load | new findings | 1 found (a race the wiring introduced), 1 fixed |
| 4 | self (this session) | zero (converged) | the fix re-read; the racy test 10/10 green, 0/8 red on the base before the fix was needed |
| critic 1–3 | — | **unavailable** | no critic configured in this environment |

## Round 1 findings

**S1 — a respawn and a pull request's session reported the daemon's default harness to
the hooks, not their own.** `_before_launch` and `_refuse_launch` read
`self.config.default_harness`; a record spawned on `cursor` would have told the hook
`claude`. **Fixed**: `_before_launch(…, harness=)` takes the session's or record's harness
and `_refuse_launch` reports `launch.harness`.

**S2 — the graph start fired `phase_changed` for a start node with no phase.** The
channel publish already skipped an empty phase (`_lifecycle` returns on `not phase`), so a
hook would have seen a "phase change" from `""` to `""`. **Fixed**: `Runtime.start` asks
the hooks only when the start node has a phase; the shipped loops all do.

**S3 — the test suite could have loaded a developer's own hooks.** The hermetic fixture
`reset()` the process-wide runner, so the first call site in any test would have configured
it lazily from the resolved CLI config — on a developer's machine, `~/.the-loop/cli-config.yaml`,
`hooks:` included. **Fixed**: the fixture installs an **empty** runner (the same posture
`_hermetic_eventlog` takes for the log); the tests of the lazy path reset it themselves.

**S4 — three unused imports in the integration test.** Caught by `make lint`. **Fixed.**

## Round 2 findings

**F1 — the terminal-node scenario expected `terminal=True` one advance too early.** The
runtime fires the terminal `phase_changed` when the terminal node is *claimed* (its exit
chain evaluated), not when it is entered — the same moment `graph.completed` is emitted.
**Fixed in the test**, and the docs say "when a terminal node is reached" for the label
change and "the claim on the terminal node" in the test's own words; the design table says
"a terminal node is reached", which is the `graph.completed` moment. No code change.

**F2 — the design named a test file that already exists for another subject.**
`test_lifecycle_cmd.py` tests `the-loop start|stop|status`. **Fixed**: the command's tests
are `tests/test_hooks_cmd.py`; the testing plan and tasks name that file.

**F3 — the schema used `exclusiveMinimum`, which the in-house validator does not
implement** (`test_the_schemas_use_no_keyword_the_validator_ignores`). **Fixed**: the
parser enforces "a positive number" and the description says so; the keyword is gone.

## Round 3 finding

**R1 — the `work_item_start` mark raced a control command on the same record.**
`test_pre_existing_control_comments_are_applied_in_thread_order` (issue-119) went red in 3
of 5 runs on the branch and 0 of 8 on the base: the dispatch worker's `mark_started` and
the poller thread's `record(stop)` each read the portable record, set their own section
and wrote the whole file back, so the worker's write could carry a stale `control: start`
over the `stop`. `WorkItemStore.write_section` had always been an unlocked
read-modify-write; the closure stamp on the worker already shared that exposure with a
control command on the ingress thread, but nothing had hit it. **Fixed** in the store, not
the caller: one `RLock` per record directory, shared by every store built over it in the
process (the dispatcher's, the poller's, a test's), around the read-modify-write.
Cross-process writers are as they were. Pinned by
`test_concurrent_section_writes_do_not_clobber_each_other` (two threads, two sections,
two hundred writes each) and by the racy test at 10/10.

**R2 — a wait-on-the-attempt test went deterministic red.**
`test_a_raising_opener_never_fails_the_spawn` (issue-317) observed the tmux spawn and read
the registry the same instant; the registration is the dispatch's *outcome*, written a
fraction of a millisecond later. The suite's own `--dispatch-lag` (issue-251) exists to
find this shape — the base commit fails the same test under lag — and the extra work this
change puts on the worker before the spawn shifted the scheduling enough to expose it on
every plain run of the file. **Fixed as the repository prescribes**: the test waits on the
outcome (`_wait(lambda: registry.find_by_work_item(REF) is not None)`). Two more tests
in the file fail under lag on the base too (`…opens_the_conversation_once_before_the_checkout`,
`…without_an_opener_opens_nothing`); they pass plainly and are left as they are — not this
change's.

## What the reviewer looked for and did not find

- **A path by which a session or a repository declares a hook.** `read_declaration` reads
  the operator's CLI config only; a `path` resolves against that file's directory
  (`config_base_dir`), never a checkout; the state file and the control record carry no
  hook. Tested by `test_a_path_resolves_against_the_config_file_not_the_cwd`.
- **A path by which a hook's answer changes a fact.** `Context.apply` and
  `copy_decisions_from` copy decision fields only; a remote result's facts and unknown keys
  are dropped. Tested by `test_apply_copies_decisions_only` and
  `test_a_result_may_change_decisions_only` (against a live server).
- **A path by which a hook failure reaches a dispatch, an advance or an ask.**
  `Runner.run` catches everything and the `_run` body catches per executor; the remote
  client turns every transport error into `HookFailure`. Tested by
  `test_a_raising_hook_never_reaches_the_caller` and
  `test_the_runner_never_raises_even_when_the_context_is_odd`.
- **A change in behaviour with no hooks declared.** The whole suite (4831 before this work
  item's tests were added) passes unchanged; the two regressions the wiring surfaced were
  the state-portability classification of the new `lifecycle` section and its row in
  `docs/cli/state.md` — both additions, no behaviour.

No finding is left open.
