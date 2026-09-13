---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#358"
phase: design
status: in-progress
---

# Execution Log: per-work-item model choice, answered at the phase-selection gate

> Append-only log for issue-358. Ticket:
> [#358](https://github.com/MadaraUchiha-314/the-loop/issues/358).

## How this session ran the loop

One cloud session, spec only. The ticket proposed a **label**-to-args map; the owner
[disagreed on that mechanism](https://github.com/MadaraUchiha-314/the-loop/issues/358#issuecomment-5654002784)
— labels are not the-loop's authorization boundary — named the phase-selection lifecycle
as the venue instead, and asked three open questions. Mid-session the owner added: *"don't
proceed with implementation until i approve the design."*

So this pass authors `requirements.md` and `design.md` and stops. They are presented
**together** for one review: no authorized `the-loop execute` reaches a cloud session, so
neither `phase-selection` nor `requirements-approval` can be answered here, and the owner's
review is the human decision the loop records — the same way issue-352 and issue-354 ran.
No code is written, no testing plan and no task DAG are derived, because both would be
downstream of a design that has not been approved.

**Risk tier 4** — the change touches `**/*schema*` (`cli-config.schema.json`) and assembles
the argv of an unattended agent from an authorized human's reply. Tier 4 means the owner
approves the pull request and a named human signs off the security review.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-13 | — | recorded, not answered — no authorized `execute` reaches a cloud session |
| requirements-definition | 2026-09-13 | | [`requirements.md`](requirements.md) — six requirements, six abuse cases |
| design | 2026-09-13 | | [`design.md`](design.md) — revision 4 after three rounds of the owner's review on PR #359 (model/effort split and availability in r2; three top-level sections, a flat `models[]`, and the-loop-owned effort normalization in r3); awaiting approval |
| test-planning | | | not started — downstream of an unapproved design |
| tasks-breakdown | | | not started |
| implementation | | | **blocked by the owner's instruction** until the design is approved; scope now includes R8 (spawn after the gate) |
| verification | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#359](https://github.com/MadaraUchiha-314/the-loop/pull/359) | the spec pass (requirements + design), revision 2 after review | open |

## Progress entries

### 2026-09-13 — the spec pass

- **Phase:** requirements-definition → design
- **Did:** read the ticket and the owner's objection, `CLAUDE.md`, the skill and
  `reference/workflow.md`. Traced the three mechanisms the design reuses:
  `graph/hooks/selection.py` (the gate, its authorization, its freeze), `prsessions.py`
  with `dispatcher._tmux_for` (the per-work-item override the frozen record already
  carries), and `harness/base.py` with `harness/__init__.py` (`model_flag`,
  `oneshot_argv(prompt, model)`, `build_adapters`). Read `channels/kickoff.py` and
  `repos.py` for the declared-closed-set precedent (decision-120/122), `critics[]` and
  decision-123 for where executable configuration lives, `sessions/registry.py` and
  `commands/sessions_cmd.py` for the visibility surface. Wrote the requirements (six
  requirements, six abuse cases) and the design (two mermaid diagrams, the three open
  questions answered, four rejected alternatives).
- **Checkpoint/tests:** `markdownlint-cli2` on the three new files. No code changed, so
  no test suite applies to this pass.
- **Next:** the owner's approval of the design. On approval: `testing-plan.md`, then
  `tasks.md`, then implementation in the order the design's component table lists.
- **Blockers:** the owner's instruction to hold implementation until the design is
  approved.

### 2026-09-13 — the owner's review, and revision 2

- **Phase:** design (revision 2)
- **Decision recorded:** the owner reviewed PR #359 with five points. Four are folded into
  the artifacts: **model and effort are two independent inputs** (the coupled `opus-deep`
  shape would have made the operator declare the cross product), **a model the harness will
  not accept** is now requirement 7 — probe with the harness's own cheapest invocation, cache
  the verdict, withhold a refused choice from the checklist, fall back visibly, re-probe once
  on a dead session — the declarations stay **per harness** (a flat list would make the-loop
  attribute an id to a harness, which is a guess), and the keys were renamed from
  `harnessModels` to `models` with `effort` beside it — still under `routing` at that point,
  which the owner's second round then corrected.
- **The fifth is architectural.** *"Why do we start a session before the phase selection is
  complete? … We ideally shouldn't."* Verified in the code: `dispatcher._spawn_tmux` spawns
  and *then* calls `graphlink.on_spawn`, and the checklist is posted by the **daemon's** own
  github integration, not by the agent — so nothing about phase selection needs a session to
  exist. The current order's stated reason is "a failed spawn must not leave a labelled ticket
  pointing at a node nobody stands on", which entering the graph on the *arming* preserves.
  Answered in `design.md` § *Why a session exists before the gate, and why it should not* and
  proposed as a **prerequisite work item**, because it changes the spawn contract for every
  work item; R4.3's re-launch keeps this work item correct under either ordering.
- **Checkpoint/tests:** `markdownlint-cli2` on the three files, clean. Still no code.
- **Next:** the owner's decision on the prerequisite ticket, and approval of the design.
- **Blockers:** the owner's instruction to hold implementation until the design is approved.

### 2026-09-13 — the owner's second round, and revision 3

- **Phase:** design (revision 3)
- **Decision recorded:** the owner rejected the *shape* of revision 2's declaration on three
  counts, and each correction makes the design smaller:
  1. **Three top-level sections** — `harnesses`, `models`, `effort` — not one nested map under
     `routing`. `routing` configures how an event reaches a session; which harnesses an instance
     has and what they can run is installed-tooling configuration, which is where `repositories`
     and `critics[]` already live.
  2. **A flat `models[]` whose rows name a harness.** My earlier objection to a
     harness-independent list was that the-loop would have to *attribute* an id to a harness — a
     guess. A `harness:` field on the row removes the guess without nesting, and `critics[]` has
     had exactly this shape since issue-108.
  3. **the-loop normalizes effort.** Revision 2 had the operator hand-writing
     `["--thinking-effort", "high"]` per harness, which was worse than the coupling it replaced.
     The enum is now the-loop's (`low | medium | high`), the translation is
     `adapter.effort_args(level)`, and a level a harness cannot express is simply not offered
     there.
- **The one thing this design cannot settle from the codebase**, stated as such rather than
  papered over: no adapter has an effort flag today, so the per-harness mapping table is read
  from each harness CLI's own `--help` at implementation and validated by the same probe R7
  applies to models. A spec does not invent a flag.
- **Scope held.** `harnesses[].args` takes over from `routing.harnessArgs.<harness>` behind the
  warn-never-fail shim issue-156 and issue-348 established, because R3's merge is onto it. The
  other three per-harness keys (`harnessTrust`, `harnessPlugins`, `defaultHarness`) belong in
  `harnesses[]` by the same argument and are a named follow-up, not this work item.
- **Checkpoint/tests:** `markdownlint-cli2` on the three files, clean. Still no code.
- **Next:** the owner's approval of the design, and their answers on the effort enum, the verdict
  lifetime, the prerequisite ordering ticket and the `harnesses[]` consolidation follow-up.
- **Blockers:** the owner's instruction to hold implementation until the design is approved.

### 2026-09-13 — the spawn order folded in as R8

- **Phase:** design (revision 4)
- **Decision recorded:** asked whether to raise the spawn-order reorder as a prerequisite ticket
  and whether this work item should wait for it, the owner answered **"implement in this same
  PR."** So it is in scope as **requirement 8**: the graph is entered when a work item is armed,
  the spawn is **deferred** while the pointer is parked on a start node that is a human gate, and
  the session is spawned when the gate is answered — already carrying the frozen model. R4.3's
  re-launch drops to a safety net for a choice changed *after* the gate and for sessions launched
  before this change.
- **The seam:** `graphlink.on_spawn` does two things today — enter the graph and bind the session —
  and they split into `on_arm` (start, evaluate a human start gate with the arming event attached,
  report whether the pointer is parked) and `on_spawn` (bind only).
- **Claim struck.** I had written that the reorder spends "no tmux session and no checkout" on an
  unconfigured work item. Verified against `graphlink._guarded`: the checkout is validated and the
  pointer is written under the checkout's spec directory, so the workspace must be prepared before
  the graph can be entered. Deferral saves the harness session and the tmux session, not the
  clone — no regression either way, since the checkout already precedes the checklist today.
- **The deferral rule is deliberately narrow** — only while the pointer has never advanced past a
  human-gate start node — so nothing mid-graph, no inner PR loop and no existing `_guarded` skip
  path can be stranded by it. The blast radius (the arming path, `on_spawn`'s idempotency, the
  issue-199 hand-off, announce/conversation-open, and every test that assumes an armed item has a
  session) is recorded as this work item's largest cost.
- **Checkpoint/tests:** `markdownlint-cli2` on the three files, clean. Still no code — the owner's
  hold on implementation until the design is approved has not been lifted, and "implement in this
  same PR" answers *where the change belongs*, not *start now*; confirmation requested on the
  thread.
- **Next:** the owner's approval of the design, and their answers on the effort enum, the verdict
  lifetime and the `harnesses[]` consolidation follow-up.
- **Blockers:** the implementation hold.

## Verification results

> Not applicable to this pass: nothing is implemented. The `verification` node will record
> against `testing-plan.md`, which is derived once the design is approved.

## Design critic review

> The opt-in `design-critic-review` phase was not selected — no authorized reply reached
> this session to select it. The owner's own review is the gate this design waits on.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | the requirements' five reporter properties re-checked against the design's components; the merge order, the fail-closed table and the abuse-case table re-read against `_tmux_for`'s existing behaviour | — |
| 2 | human (owner) | @MadaraUchiha-314 | new findings → all five addressed in revision 2 | [PR #359 review](https://github.com/MadaraUchiha-314/the-loop/pull/359) |
| 3 | human (owner) | @MadaraUchiha-314 | new findings on the declaration's shape → all three addressed in revision 3 | [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359#discussion_r4000531271) |
| 4 | human (owner) | @MadaraUchiha-314 | the spawn-order change is to land in this PR → R8 | [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359#discussion_r4000541107) |

## Security review (gate)

- **Mechanism:** the-loop checklist, at the requirements and design phases (the gated
  sections of both artifacts).
- **Outcome:** the one new trust boundary — comment text reaching an argv — is designed out
  rather than mitigated: a reply yields a token that is a key into the operator's declared
  list, and the argv comes from `cli-config.yaml`. Six abuse cases, each with a named
  negative test in the testing strategy.
- **Human sign-off:** pending — risk tier 4 requires a named human sign-off, which is the
  owner's review of this spec and of the implementation PR that follows it.

## Final validation evidence

Pending implementation.

## Capability docs

> Nothing is implemented, so no capability doc changes in this pass. The design names the
> three that change with the implementation: `interactive-sessions.md` (what a session is
> launched with), `process-graph.md` (the gate's questions) and `cli.md` (the `Model`
> column).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| — | none in this pass; three named for the implementation pass | — |

## Documentation

| Document | What changed |
|----------|--------------|
| — | none in this pass. The implementation pass documents the three new top-level sections (`harnesses`, `models`, `effort`) in the CLI configuration reference under `docs/config/cli/`, notes the `routing.harnessArgs` deprecation in `routing-options.md`, updates the phase-selection section of the operating model, and extends `skills/the-loop/templates/cli-config.yaml`. |
