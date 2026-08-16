# Decision 091: an asynchronous test waits on the outcome, and the suite carries a lag to prove it

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-251](https://github.com/MadaraUchiha-314/the-loop/issues/251)
- **Deciders:** maintainer (via ticket); harness (proposal)

## Context

Five integration tests in this repository have now failed for the same reason: each waited
for one event and then depended on a **different** one, written a step later by a
dispatcher worker thread. They failed about one run in three, and only when something slow
ran before them —
[the ticket measured it](https://github.com/MadaraUchiha-314/the-loop/issues/251): 15/15
passes in isolation, 1 failure in 6 after a file that did nothing but burn ~16 seconds of
wall-clock.

[PR #244](https://github.com/MadaraUchiha-314/the-loop/pull/244) fixed three of them,
because a red CI on that PR was that PR's problem whoever's defect it was, and wrote the
lesson into three code comments. Two more were still in the suite when this work item
swept for them — which is the argument this decision turns on: a lesson in a comment is not
a mechanism.

The reason the shape keeps being written is structural, not careless. A dispatch is two
events:

- the **attempt** — `tmux.spawn` / `tmux.deliver`, which the `FakeTmux` double records, so
  it is the one a test can see immediately;
- the **outcome** — `registry.register` / `touch` / `save_endpoint`, `deduper.discard`,
  `eventlog.emit`, `announcer.announce`, `graphlink.on_spawn`, all of which happen
  afterwards on the worker thread, and all of which carry what the dispatch *means*.

The visible one is the wrong one, and nothing in the suite made that discoverable.

## Decision

**A test waits on the state its next line depends on, and this repository ships a way to
prove it did.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — wait on the outcome, not the attempt** | a test that depends on a background write waits on **that write**; the attempt survives as an ordinary assertion underneath | The two events are ordered by the code under test, not by the scheduler. Stated as a RULE in `reference/testing.md`, so the harness reads it before it writes an async test. |
| **D2 — a fixed `time.sleep` before a positive assertion is a defect** | delete it and wait on the signal; sleeps guarding a *negative* assertion stay | There is no correct sleep value, only values that are unlucky less often. The negative case is a different construct — it can only produce a false pass, never an intermittent failure. |
| **D3 — ship `pytest --dispatch-lag=<seconds>`** | an opt-in pytest option that delays every dispatcher write following a spawn or delivery | This is a happens-before property: reading the test cannot decide it, and moving time can. Under lag a mis-waited test fails **every** run. It is what found the two remaining instances after 190 wait sites had been read by hand. |
| **D4 — off by default, unwound per test** | `lag <= 0` patches nothing; when on, the patches go through `monkeypatch` | The suite's normal cost must not change, and a lagged class must not survive into the next test. |
| **D5 — not a standing CI gate** | the lagged run is documented and targeted, not wired into every PR | Nine minutes against two, for a property that changes only when async tests are added. Making it a gate is a CI-budget decision for the maintainer, not one to take inside a bugfix. |

## Consequences

- **The sweep is repeatable.** "Has this class of bug come back?" is now a command with an
  answer, not a reading exercise. The next work item that adds an async test can check its
  own work in one run.
- **The rule reaches the harness, not just this repository.** `reference/testing.md` ships
  in the plugin, so every project the-loop works in gets the attempt/outcome distinction;
  the `--dispatch-lag` flag itself is this repository's implementation of it, and other
  projects need their own equivalent seam list.
- **Test doubles are now a design surface.** `FakeTmux` records the attempt because that
  is what a runner double naturally records; a double that also exposed the outcome would
  not need this discipline. That is not a change worth making now, but it is where the
  next improvement lives if a sixth instance appears.
- **A failure under lag is a lead, not a verdict.** A test can fail under a half-second
  lag for honest reasons (a genuine timeout pushed past its budget). The control is the
  same test at lag 0.

## Alternatives considered

- **Only write the rule down.** This is what PR #244 did, in three comments at the sites it
  fixed. Two more instances were still there. A convention people mean to follow is not the
  same as one a command checks.
- **A lint rule over the test sources.** A checker for "waits on `tmux.delivers`, then
  asserts on the registry" would have caught the three instances PR #244 fixed and
  **neither** of the two found here — both of which fail on what they *do* next, not on
  what they assert — while firing on the many correct sites that wait on the attempt and
  then assert on the attempt.
- **Give `Dispatcher` a `quiesce()`/idle barrier for tests.** `dispatcher.stop()` already
  is one (sentinel at the tail of each queue, then join), and most of the suite uses it.
  A second barrier would be production API existing for tests, and it would let a test go
  on waiting for the wrong signal while still passing — which teaches nothing.
- **Raise the sleeps.** Trades a flaky suite for a slow one and keeps the defect.
- **Run every test under lag, always.** The lag would then be the suite's normal cost
  (nine minutes against two) for a property that is stable between changes.
