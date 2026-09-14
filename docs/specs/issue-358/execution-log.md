---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#358"
phase: needs-review
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
| design | 2026-09-13 | | [`design.md`](design.md) — revision 6 after five rounds of the owner's review on PR #359 (model/effort split and availability in r2; three top-level sections, a flat `models[]`, and the-loop-owned effort normalization in r3); awaiting approval |
| test-planning | | | not started — downstream of an unapproved design |
| tasks-breakdown | | | not started |
| implementation | 2026-09-13 | | eight commits, one per reviewable chunk, on `claude/github-issue-358-eecbix`; scope includes R8 (spawn after the gate) |
| verification | 2026-09-13 | | [`testing-plan.md`](testing-plan.md) § Verification results; [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| needs-review | 2026-09-13 | | PR #359 updated; tier 4, so the owner's approval is the gate and the named security sign-off |
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

### 2026-09-13 — a model is not tied to a harness (revision 5)

- **Phase:** design (revision 5)
- **Decision recorded:** *"Let's not tie model to harness. Let's just keep it models … and the
  models will be like opus 5, fable 5.1, gpt 5.6 sol — use whatever naming convention each of the
  model providers follow."* Accepted, and it **retires an objection I had raised twice** rather
  than working around it: `models` is now a plain list of provider-named strings, and the
  `harness:` field revision 3 introduced is gone.
- **Why the objection dissolves.** I had argued that an untied list forces the-loop to *attribute*
  a name to a harness, and attribution is a guess (the decision-120 rule). What I had missed is
  that **R7's availability probe already replaces the guess with a measurement**: it asks each
  harness whether it can actually run a name and caches the answer, so the cache is a name ×
  harness matrix and resolution reads exactly one cell — this work item's harness, this name. A
  name the harness cannot run comes back `refused`, which R7 already defines as "not offered, never
  spawned". Nothing is attributed; the operator writes one flat list.
- **The deliberate asymmetry, now stated in the design:** a model *name* is the provider's
  identifier, so the-loop copies it verbatim and neither normalizes nor parses it; an effort
  *level* is a the-loop concept three harnesses spell differently, so the-loop owns that
  vocabulary. Opposite answers to "who owns the name", each for a stated reason.
- **Two things got smaller.** There is no declared-choice record left — a declaration carries
  nothing but a name — and there is no `args` escape hatch on a model: a harness with no
  `model_flag` is simply offered no model section rather than given a hand-written flag.
- **Checkpoint/tests:** `markdownlint-cli2` on the three files, clean. Still no code; the
  implementation hold has not been lifted.
- **Next:** the owner's approval of the design, and their answers on the effort enum, the verdict
  lifetime and the `harnesses[]` consolidation follow-up.
- **Blockers:** the implementation hold.

### 2026-09-13 — an optional model→harnesses link (revision 6)

- **Phase:** design (revision 6)
- **Decision recorded:** *"for each model, we can link it to supported harnesses."* Taken as an
  **optional** `harnesses:` on a model name, with one rule that keeps it from contradicting the
  probe: **a declaration may narrow, only the probe may confirm.**

  | | what it does | what it cannot do |
  |---|---|---|
  | a bare name | candidate for every declared harness | — |
  | `harnesses: [cursor]` | restricts the model to those harnesses, and probes only those | grant support the harness refuses |
  | the probe (R7) | the only thing that makes a name offerable | widen past a declared `harnesses:` |

- **Why it is worth having** even though the probe already measures the relation: it cuts the
  matrix from *models × harnesses* to what was declared, and it lets an operator keep an expensive
  model off a harness deliberately. Both are restrictions, which is the only thing a declaration
  is allowed to be here.
- **Rejected in the same breath:** treating a declared link as authoritative and skipping the probe
  for it — a declaration could then assert support that does not exist, and the failure would land
  in an unattended pane, which is the whole thing R7 exists to prevent.
- **Note on the artifacts:** revision 3's mandatory single `harness:` per row is not what came back.
  This is its optional, plural, non-authoritative descendant, and the rejected-alternatives table
  now distinguishes the two so a later reader does not read the history as a circle.
- **Checkpoint/tests:** `markdownlint-cli2` on the three files, clean. R2's criteria were renumbered
  (the old 3–10 became 5–12) and every cross-reference re-checked. Still no code.
- **Next:** the owner's approval of the design, and their answers on the effort enum, the verdict
  lifetime and the `harnesses[]` consolidation follow-up.
- **Blockers:** the implementation hold.

### 2026-09-13 — implementation and verification

- **Phase:** implementation → verification → needs-review
- **Did:** the seventeen tasks of [`tasks.md`](tasks.md), in eight commits so each is
  reviewable on its own — the adapter seam and the two new modules, the three config
  sections, **R8** (its own commit, widest blast radius), the gate's two sections, the
  effort-enum widening, resolution + recording + the drift net, the surfaces, the abuse
  table, and the docs. Ran every activity of the testing plan; recorded the results there
  and the raw evidence under [`evidence/`](evidence/).
- **Checkpoint/tests:** 3603 passed, 1 skipped (3539 before this work item). `ruff check`,
  `ruff format --check`, `pyright`, `markdownlint` and `validate_config.py` all clean — the
  same commands CI runs.
- **Three things the repository's own guards caught**, which is the part worth recording:
  an unregistered event type, an unclassified state path, and a schema keyword the
  hand-rolled validator did not know. The third was a real bug in the keyword guard — it
  descended into `examples`/`default`/`enum` and reported a sample object's field names as
  JSON Schema keywords — exposed because `harnesses` is the first section with
  object-valued examples.
- **Two things I got wrong and corrected in place:** the design claimed an OpenAPI edit
  that does not exist (`/api/v1/sessions` types its response as untyped objects, so the
  three record fields flow through without one), and a test expectation of mine asserted
  that `model-opus-5;rm -rf /` yields nothing — it yields `opus-5`, because the token
  grammar stops at the `;`. The test now asserts the property that matters: a row can only
  ever yield a name the operator declared.
- **One finding from writing the abuse tests**, not from the design: `harnesses:` on a model
  was enforced only where the checklist is rendered, so a hand-edited frozen record could
  have put a cursor-only model onto claude. Now enforced where the argv is built as well.
- **Next:** the owner's review of PR #359. Tier 4, so their approval is both the PR gate and
  the named security sign-off.
- **Blockers:** none.

### 2026-09-14 — the effort vocabulary, confirmed from both harnesses

- **Phase:** needs-review (a follow-up commit on the same PR)
- **Decision recorded:** the owner pasted Codex's reasoning picker as text (the screenshots
  could not be fetched from this session). It names **Low · Medium · High · Extra high**, with
  **Max and Ultra** behind a "More reasoning…" submenu. So the enum is now the **union** of the
  two harnesses' own vocabularies: `low | medium | high | xhigh | max | ultra`.
- **Two rows justify the whole normalisation**, and they are now the documented argument for
  it rather than an assertion:
  - `xhigh` — Claude spells it `xhigh`, Codex spells it *"Extra high"*. One concept, two
    spellings, which is precisely why an operator should not be writing per-harness flags.
  - `ultra` — Codex has it, Claude does not. A **union** rather than an intersection, so the
    level is offered where it exists and silently absent where it does not.
- **What I got right by refusing to guess:** the first revision invented three words; the
  second took Claude's five; this one has both harnesses' actual pickers. Had `_EFFORT_ARGS`
  been populated with a guessed flag at any point, the enum would have been wrong twice and
  the code would have been wrong with it.
- **Still not shipped:** no adapter has a mapping, because neither CLI exposes a
  thinking-effort flag. Codex has the richest set and no adapter at all; the mapping table is
  written down in `decision-124` and the config docs so that adding one is a table, not a
  redesign.
- **Checkpoint/tests:** full suite, `ruff`, `pyright`, `markdownlint`, `validate_config.py`.
- **Next:** the owner's approval.
- **Blockers:** none.

## Verification results

> Recorded in [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix
> rows it planned — this section stays as the template left it, which is the rule when a
> `testing-plan.md` exists.

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
| 5 | human (owner) | @MadaraUchiha-314 | a model is not tied to a harness → revision 5; the probe measures the matrix | [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359#discussion_r4000531271) |
| 6 | human (owner) | @MadaraUchiha-314 | link a model to supported harnesses → revision 6, as an optional narrowing that the probe still confirms | [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359#discussion_r4000724428) |
| 7 | human (owner) | @MadaraUchiha-314 | the real reasoning levels in Claude Code and Codex → the effort enum widened from three invented words to Claude's own five | [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359#issuecomment-5656065048) |
| 8 | self | the-loop | the abuse table written against the real path rather than a mock, which surfaced the narrowing gap; the OpenAPI claim re-checked against the actual contract and corrected | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist — [`evidence/security-review.md`](evidence/security-review.md).
- **Outcome:** **pass, with one finding fixed in the same PR.** The one new trust boundary —
  comment text reaching an argv — is designed out rather than mitigated: a reply yields a token
  that is a key into the operator's declared list, and the argv comes from `cli-config.yaml`
  plus the adapter's own flag. Seven abuse cases, each with a negative test against the real
  path. The finding: `harnesses:` on a model was enforced only where the checklist is rendered,
  so a hand-edited frozen record could have put a cursor-only model onto claude; it is now
  enforced where the argv is built too. Also audited: the probe's egress (a fixed prompt, off
  the delivery path, machine-local cache) and every fail-closed direction.
- **Human sign-off:** pending — risk tier 4 requires a named sign-off, which is the owner's
  approval of [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359).

## Final validation evidence

Mapped onto the acceptance criteria; the raw record is
[`testing-plan.md`](testing-plan.md) § Verification results.

| Requirement | Proved by |
|---|---|
| R1 an authorized human picks model and effort | `test_selection_choices.py` — rendering, per-section parsing, the confirmation naming both outcomes; `test_abuse_an_unauthorized_reply_freezes_nothing` |
| R2 the choices are the operator's, declared and closed | `test_modelchoice.py` (33 cases: the two shapes, malformed entries, narrowing, the enum, the merge) |
| R3 merged onto the operator's arguments, never a replacement | `test_the_merge_order_is_base_then_model_then_effort`, `test_the_operators_own_arguments_are_never_rewritten`, `test_a_frozen_choice_reaches_the_argv_in_order` |
| R4 the choice survives the session | `test_dispatcher_choice.py` — resolution at spawn, re-resolution on respawn, the drift net, and every fault path resolving to the operator's arguments |
| R5 a human can see what it is running on | `test_routing.py` round-trip + legacy record; the `Model` column; `test_models_cmd.py` |
| R6 a work item that chose nothing is unchanged | `test_a_work_item_that_chose_nothing_gets_the_shared_adapter_untouched`, `test_an_install_that_declared_nothing_behaves_exactly_as_before` |
| R7 a model the harness refuses is never offered or spawned | `test_modelprobe.py` (13 cases), `test_an_unavailable_model_is_withheld_from_the_checklist`, `test_a_model_the_harness_refuses_is_never_spawned_onto` |
| R8 the session is spawned after the gate | `test_spawn_gate_integration.py` (4 scenarios), `test_graphlink.py` (6 `on_arm` cases) |

## Capability docs

> Nothing is implemented, so no capability doc changes in this pass. The design names the
> three that change with the implementation: `interactive-sessions.md` (what a session is
> launched with), `process-graph.md` (the gate's questions) and `cli.md` (the `Model`
> column).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`interactive-sessions.md`](../../capabilities/interactive-sessions.md) | four new behaviour rules: no session while parked at a human start gate, the resolved launch arguments, the drift re-launch, and the three recorded fields with the `Model` column | issue-358 |
| [`process-graph.md`](../../capabilities/process-graph.md) | the gate's two new per-work-item questions and their fail-closed resolution; the deferred spawn and the narrowness of the deferral rule | issue-358 |
| [`cli.md`](../../capabilities/cli.md) | `the-loop models list\|check`, and the `Model` column on `sessions list` | issue-358 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/cli/harnesses-options.md`](../../config/cli/harnesses-options.md) | new page for the three top-level sections, with the two rules that carry the design (a declaration may narrow, only the probe may confirm; the-loop owns the effort vocabulary, the provider owns the model name) and the warning that no adapter has an effort mapping yet |
| [`docs/cli/commands/models.md`](../../cli/commands/models.md) | new page for `models list\|check`: the verdict table, the exit codes, and the warning that `check` runs your harness and may cost tokens |
| [`docs/cli/state.md`](../../cli/state.md) | the availability verdict cache — its shape, why it is machine-local, and that deleting it is safe |
| [`skills/the-loop/SKILL.md`](../../../skills/the-loop/SKILL.md) | the gate answers four non-phase questions now, and an armed work item with **no session** is normal — a session that reads the absence as a fault is the failure this had to pre-empt |
| [`skills/the-loop/reference/workflow.md`](../../../skills/the-loop/reference/workflow.md) | two new sections beside the `pr-sessions-*` one: the model/effort rows, and why the spawn now follows the gate |
| [`skills/the-loop/templates/cli-config.yaml`](../../../skills/the-loop/templates/cli-config.yaml) | all three sections, commented, with empty defaults so an upgrade changes nothing |
| [`docs/decisions/decision-124.md`](../../decisions/decision-124.md) | the five decisions this work item made, each with the review round that forced it |
