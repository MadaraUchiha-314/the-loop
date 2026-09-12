# Capability: token economy

> The-loop's opinion on **token/cost reduction** — guidance the skill follows in every
> session, never a setting — so an inherently iterative, verbose harness spends fewer
> tokens **without** spending less rigor. Single source of truth for the capability's
> current behaviour; the raw specs under `docs/specs/issue-37/` are the historical record.

## What it is

the-loop iterates (brainstorm → 3-phase spec → implement → self/critic review → evidence →
fold-in → briefing), is verbose by design (a `SKILL.md` + ten `reference/*.md` + rich
templates), and hosts each work item as a resident tmux TUI whose window only grows across
the item's events. That makes it token-hungry. This capability packages the field's token-reduction
practices (Anthropic context engineering, the caveman/ponytail projects, loop-engineering
guidance) as `reference/token-economy.md`: a stage table for thinking effort and
verbosity, a phase → reference loading map, and the practices that keep verbose work out
of the main window. Every work item the loop runs follows it. Nothing here is configured
— until issue-352 the same levers were a `tokenEconomy` block in the harness config, and
the rule was made fixed because it is the same in every repository.

## Current behaviour

All statements are **advisory**: the guidance informs how the loop works and **never gates
a merge**. The rigor floor — validation, error handling, security, accessibility,
test-first discipline, the paper trail, review depth — is never traded for tokens.

- The loop SHALL follow `reference/token-economy.md` in every session; it SHALL NOT read a
  token-economy setting from the harness config, because there is none.
- **Model:** the harness runs whatever model the operator chose. There is no routing table
  and no per-stage tier; where a harness cannot switch models programmatically nothing is
  lost, because nothing asked it to.
- **Thinking effort:** the loop SHALL follow the guidance's stage table — reasoning-heavy
  stages (brainstorm/requirements/design/critic-review) think hard, mechanical stages
  (evidence, capability-docs, reviewer-briefing, status, learnings) do not bill reasoning
  tokens.
- **Output verbosity:** the loop SHALL keep its own **narration** concise (drop filler,
  prefer fragments) and SHALL NEVER compress code, commands, diffs, errors, paper-trail
  comments, the reviewer briefing, specs, decisions or capability docs — so the
  educate-the-reviewer mandate is preserved.
- **Progressive disclosure:** a step SHALL load only the reference doc(s) its phase needs
  (the loading map in `reference/token-economy.md`).
- **Sub-agent delegation:** verbose work (tests, doc fetches, log/file scans) SHOULD run in
  a fresh-context sub-agent that returns a summary.
- **Compaction:** long runs SHALL checkpoint durable state to `execution-log.md` and
  compact/reset the window preserving the spec + open threads, leaning on the-loop's
  filesystem-as-memory — the boundaries are the fixed context rule (clear at a phase
  boundary, compact after each task, never clear mid-task; [spec-workflow](spec-workflow.md)).
- **Telemetry:** the loop SHALL parse token/cost usage best-effort from each harness's JSON
  output (`DispatchResult.usage`) and surface it per dispatch/work item, so the guidance is
  tuned against a real baseline. The loop SHALL set **no headline reduction target** until
  it has measured one.
- **Prior art:** the loop expresses caveman's (output compression) and ponytail's
  (generation minimalism) techniques **natively**; neither plugin is vendored or registered
  ([decision-005](../decisions/decision-005.md): no bundled runtime). The harness discovers
  whatever tools it has itself.

## Design

Pointers, not copies:

- Guidance & loading map: [`skills/the-loop/reference/token-economy.md`](../../skills/the-loop/reference/token-economy.md).
- Generation-side rung: [`skills/the-loop/reference/minimalism.md`](../../skills/the-loop/reference/minimalism.md).
- Telemetry parsing: `cli/the_loop/harness/base.py` (`Usage`, `usage_from_output`) with
  per-dispatch logging in `cli/the_loop/webhook/dispatcher.py`.
- Resident-session interplay (the tmux-hosted TUI amortizes context across a work item's
  events; the window is managed inside the session):
  [`interactive-sessions`](interactive-sessions.md) and `docs/specs/issue-32/`.
- Research digest & rejected alternatives: [`docs/specs/issue-37/brainstorm.md`](../specs/issue-37/brainstorm.md).

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-352 | The `tokenEconomy` block left the harness config (2026-09-12): the levers are guidance, never configured — the harness runs the operator's model (no routing table), thinking effort and verbosity follow the reference's stage table, and disclosure, sub-agent delegation, compaction and telemetry are practices, not switches. `externalTools` left with it; caveman/ponytail are implemented natively, not registered | [spec](../specs/issue-352/), [decision-123](../decisions/decision-123.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/352) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): the cost model inverted — the resident TUI amortizes context across a work item's events instead of re-priming per event, and window growth is managed inside the session (compaction/clears). | [spec](../specs/issue-156/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-37 | Introduced the token-economy capability: `tokenEconomy` config (model routing, thinking effort, output verbosity, progressive disclosure, sub-agents, compaction, telemetry), the `token-economy.md` reference, best-effort usage telemetry in the CLI, and registration of caveman/ponytail. | [spec](../specs/issue-37/), PR #41 |
