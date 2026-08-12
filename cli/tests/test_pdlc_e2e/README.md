# The PDLC end-to-end scenario suite (issue-217)

One work item per scenario, driven ticket → complete through the **real**
runtime: the shipped `pdlc-work-item-loop`, the shipped hooks, real artifact
gates over real files in a throwaway git checkout. The "agent" is playback —
each scenario's manifest scripts what the agent hands the process (artifacts,
comments, completion claims), and the assertions are about **process
conformance**: phases in order, labels advancing, artifacts locked before
implementation, events in order, skips recorded as skips.

Fakes sit only at transport seams (the `integrations.resolve` labels/comments
provider, the event log path, the ask/reply comment poster and tmux runner) —
authorization, loop-prevention filtering and every gate run production code.

## Adding a scenario

1. Create `scenarios/<name>/scenario.yaml` plus its `artifacts/` fixtures.
2. Add one named test in `../test_pdlc_e2e_integration.py` decorated
   `@covers("<name>")`, with the repo's Gherkin docstring. (The tests live
   beside — not inside — this directory because `the-loop scenarios` discovery
   is pinned to `cli/tests/test_*_integration.py`.)

`test_every_scenario_directory_has_a_named_test` fails until both halves
exist, so a fixture set can never be silently skipped.

## The manifest

```yaml
name: my-scenario          # must equal the directory name by convention
description: one line
tier: 3                    # informational; riskTier lives in the fixtures
workItem: issue-42         # spec dir name; the ref derives as github:e2e/e2e#42
steps: [ ... ]             # the scripted agent, in order
expect: { ... }            # asserted after the last step
```

The run always begins with `Runtime.start` (the work item enters the graph at
`phase-selection`); every scenario's first step is therefore the authorized
selection reply.

## Steps (a closed vocabulary — playback, never code)

| Step | Meaning |
|------|---------|
| `comment: {author, body \| fixture, marked?}` | a comment arrives at the current gate (`Runtime.advance` with the event attached). `marked: true` stamps the production self-authorship marker. |
| `emit: {artifact, fixture}` | the agent "produces" an artifact: `artifacts/<fixture>` is copied to the spec dir as `<artifact>`. |
| `complete: {node, status?}` | the session's completion claim (`Runtime.complete`). `status` defaults to `pass`; set `block`/`wait` when the claim is expected to be refused. |
| `advance: {}` | a bare nudge (`Runtime.advance` with no event). |
| `ask: {question}` | the agent escalates (`core.sessions.ask_session`). |
| `reply: {text, actor, sessionMissing?}` | the operator answers (`core.sessions.reply_session`). `sessionMissing: true` asserts the fail-closed refusal instead of delivering. |
| `inner-loop: {pr, node, repo?}` | an inner PR loop's pointer stands at `node` (writes `pr-loops/…/graph-state.json`). |
| `fail-github: {ops}` / `restore-github: {}` | the named integration operations raise / recover. |
| `expect: {…}` | a mid-run checkpoint (same keys as the final `expect`). |

An unknown step kind, a missing manifest field, or a step naming an absent
fixture refuses the scenario **naming the file and field** — never a silent
skip.

## Expectations

| Key | Asserts |
|-----|---------|
| `finalNode` / `currentNode` | where the pointer stands |
| `completed` | whether `graph.completed` was emitted |
| `parked` | whether the run is parked awaiting input |
| `nodes` | the **exact** walked sequence, derived from events; `<node>~` marks a routed-around skip, so a skip can never satisfy an expectation written for a pass |
| `labels` | the **exact** ordered label trail (`set-labels` calls), as GitHub would have seen it |
| `events` | an **ordered subsequence** of `{event, field: value, …}` matchers — unrelated events are permitted between matches, so new event types don't break scenarios |
| `lockedBeforeImplementation` | the named artifacts carried `status: approved` at the moment `implementation` was entered |
| `executionLogSections` | the named `##` sections exist and are non-empty in the work item's execution log |
| `executionLogEntries` | the named nodes' `log-entry` checkpoints appear in the execution log, in order — the log mirrors the walk |

Divergences report the first mismatch (index, expected, found) plus the
observed trace.

## Fixtures

Plain markdown copied verbatim. They must satisfy the shipped gates they meet:
locked front matter (`status: approved`), the sections each node's
`validate-artifacts` demands, `trust boundary` / `abuse case` markers answered
in the design (`enforces-boundaries-from`), ticked checkboxes where
`checkmarks: complete` gates. Fixture markdown is linted like every other
markdown file in the repo.
