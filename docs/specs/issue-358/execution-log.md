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
| design | 2026-09-13 | | [`design.md`](design.md) — awaiting the owner's approval before anything is implemented |
| test-planning | | | not started — downstream of an unapproved design |
| tasks-breakdown | | | not started |
| implementation | | | **blocked by the owner's instruction** until the design is approved |
| verification | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| — | the spec pass (requirements + design) | open |

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
| — | none in this pass. The implementation pass changes `docs/config/cli/routing-options.md` (the `harnessModels` key), the phase-selection section of the operating model, and `skills/the-loop/templates/cli-config.yaml`. |
