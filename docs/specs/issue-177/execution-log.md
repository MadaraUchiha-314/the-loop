---
type: execution-log
workItem: issue-177
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: declared skips — the author decides which phases a work item walks

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-177/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-08 | pending (PR) | the ticket's constraint is the spine: the LLM never decides a skip |
| design | 2026-08-08 | pending (PR) | graph declares *may*, human declares *is*, runtime records and never forges — decision-067 |
| test-planning | 2026-08-08 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-08 | pending (PR) | 8 tasks: T1 → T2/T3 → T4 → T5/T6 → T7 → T8 |
| implementation | 2026-08-08 | — | T1–T7 |
| verification | 2026-08-08 | — | T8; every activity ran |
| needs-review | 2026-08-08 | pending | 3 self-review rounds (round 1 found the snapshot-once hole); critic round unavailable (none configured) |
| design (revisited) | 2026-08-08 | @MadaraUchiha-314 (PR #178 review) | owner rejected the label channel; rebuilt around a `phase-selection` first phase answered by `the-loop execute` — decision-067 § Reversal |
| verification (re-run) | 2026-08-08 | — | every activity re-executed against the rebuilt channel |
| needs-review (again) | 2026-08-08 | pending | 3 further self-review rounds on the rebuild |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#178](https://github.com/MadaraUchiha-314/the-loop/pull/178) | the whole work item — T1–T8 | open |

## Progress entries

### 2026-08-08 — spec chain written

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** wrote `requirements.md`, `design.md`, `testing-plan.md`, `tasks.md`. The
  strategy answers the ticket's three constraints in one shape: the *vocabulary* of
  skippable phases is fixed in the shipped graph (so the harness cannot widen it), the
  *selection* is a human act (ticket labels snapshotted at graph entry, or an audited
  `graph skip` verb), and the *record* is a declaration with provenance that `check`
  reports as a skip, never a pass. Rejected: harness-inferred skips (the ticket's own
  veto), front-matter channels (agent-writable), per-lane alternative graphs (parity
  burden), a config toggle (a knob without safety).
- **Checkpoint/tests:** none — no code yet.
- **Next:** T1, test-first.

### 2026-08-08 — implementation

- **Phase:** implementation
- **Did:** T1–T7. `Node.skippable` + `Graph.skip_sets` + `expand_skip_tokens()` with the
  three compile validations; `GraphState.skips` (additive); skip routing in
  `start`/`advance` (including the pointerless CLI path), provenance-carrying reports in
  both `status()` modes with forged declarations inert and surfaced;
  `declare_skips()`/`_announce_skips()` beside `force`; the one-time label snapshot;
  `HookContext.skipped_artifacts` and the planned-absence tolerance in
  `validate-artifacts`; the shipped graph's six markers, six `skipped` edges and
  `skipSets.spec-chain`; `graph skip` through CLI → core → API → the authored OpenAPI
  contract; three new documented event types (the routing event is `graph.node_skipped`
  because `graph.skipped` already means the ingress declining to touch a graph —
  issue-123's vocabulary kept intact). Docs folded in the same PR: workflow reference,
  SKILL rule, capability doc, decision-067, `graph` command page, init's label step.
- **Checkpoint/tests:** `pytest -q` → 1453 passed, 1 skipped (baseline 1423/1); `ruff`,
  `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py` clean.
- **Next:** T8 — execute the testing plan, commit evidence.

### 2026-08-08 — verification

- **Phase:** verification
- **Did:** T8. Ran every activity of the testing plan and committed the record:
  red→green for the new suite (collection-level red, shipped-vocabulary red, and the
  laundering-regression red with the guard weakened), the shipped-graph audit, the
  label-snapshot semantics, the operator/contract surface, the full regression battery,
  and the ticket's own scenario as a walkthrough — one `loop:skip:spec-chain` label on a
  temp work item became six provenance-carrying skips, the pointer landed on
  `test-planning` (which still blocks for its missing plan), and a forged skip on
  `security-review` stayed inert and surfaced. One process note for the record: while
  capturing the guard-weakened red, a careless `git checkout --` restored `runtime.py`
  to HEAD and discarded the uncommitted skip implementation; it was rebuilt from the
  reviewed design immediately and the full battery re-run green before the checkpoint
  commit — the checkpoint-then-capture order is the learning.
- **Checkpoint/tests:** `testing-plan.md` § Verification results; evidence under
  [`evidence/`](evidence/).
- **Next:** self-review rounds, then the PR briefing.

### 2026-08-08 — owner review replaces the declaration channel; rebuild

- **Phase:** design (revisited) → implementation → verification
- **Did:** the owner rejected the label channel on the PR — *"A label is not the right
  way to go about it since it breaks the authorization principle of the loop … A label
  needs to be created in all the repo etc and is tedious. Can we add a reply comment to
  the work item … with all the phases … and the user can choose which stages are
  required? This is the 'first phase'"*, plus *"Once the user has chosen, then the user
  can say `the-loop execute` … to start the graph execution."* Rebuilt accordingly: the
  outer loop now **starts** at a human node `phase-selection` whose entry posts a phase
  checklist (idempotent via its own marker, listing the executing loop's skippable
  phases and the whole never-skippable floor) and whose exit reads an authorized reply
  carrying `the-loop execute`, yielding the unticked skippable phases as declared skips
  and refusing any protected phase by name. The label snapshot is gone from the runtime;
  `hooks/selection.py` is new; `HookContext` gained `graph` and `decisions`;
  `deliver-assignment` now *announces* a human gate rather than telling the session to
  claim it (the loop opens on one); `/the-loop:init` creates no skip labels;
  `workflow.phases` gained `phase-selection` in both configs for P4 parity. The
  compile-checked vocabulary, the routing, the never-forge reporting and the tamper
  filter are unchanged — only the channel moved. `the-loop execute` is deliberately the
  gate's own vocabulary rather than a `routing.control` command: `start` arms the item,
  `execute` answers this gate.
- **Checkpoint/tests:** `pytest -q` → 1459 passed, 1 skipped; `ruff`,
  `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py` clean.
- **Next:** self-review of the rebuild, then update the PR briefing.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (agent) | **new finding — the label snapshot was once-by-convention, not once-by-construction.** The snapshot ran whenever `state.current_node` was empty, and on the CLI path a fresh item can sit *blocked at its first node with the pointer still unset* (a block neither enters nor exits a node) — so every `advance` there re-read the labels, and a `loop:skip:*` label applied mid-block would have been honoured: exactly the laundering R2.2 forbids, one path over. Fixed by enforcing "once" inside `_snapshot_label_skips` itself (untouched state only: no pointer AND no node records), with a regression test that fails against the weakened guard (red recorded in `evidence/tests.md`). | this PR |
| 2 | self | the-loop (agent) | zero (converged) — swept the remaining consumers for the same class of hole: `complete()` claims on skipped nodes land in the existing already-past/not-current handling; `force` onto a declared-skipped node deliberately wins over the declaration (an operator override outranks a plan — consistent with force's contract); `validates:` targets (the shared execution log) are authored by no node and can never enter `skipped_artifacts`; `graph-state.json` field docs live only in the capability doc, which was updated. Stopped per `reviews.stopOnNoNewFindings`. | this PR |
| 3 | self (final battery) | the-loop (agent) | zero — full suite, lint, types, markdown and config validation all clean after the round-1 fix and the runtime rebuild; walkthrough re-run against the shipped graph. | [`evidence/`](evidence/) |
| 4 | self (rebuild) | the-loop (agent) | **new findings — two, both caught by the tests being written first.** (a) `_phase_rows` re-loaded the **shipped** graph instead of reading the one the runtime is executing, so the checklist would have listed the outer loop's phases even for an inner PR loop, and validated replies against a vocabulary the pointer does not use; fixed by carrying the compiled graph on `HookContext` (`ctx.graph`). (b) The module's `from ..integrations import resolve` bound the name locally, so the integration seam every other caller and every test patches silently did not apply here — fixed with a call-time resolver, and the reason written into the docstring so it is not re-introduced. | this PR |
| 5 | self (rebuild) | the-loop (agent) | **new finding — the checklist under-reported the floor.** The always-runs list was filtered by `n.phase`, and most of the review chain (`security-review`, `human-approval`, `evidence`, …) carries no phase label — so the person deciding how light a work item gets to be was shown four protected phases instead of ten. Widened to every non-skippable, non-terminal node. | this PR |
| 6 | self (rebuild) | the-loop (agent) | **new finding, found by running the walkthrough — `check --recompute` reported every work item as stuck.** `check` passes no event by design, so the new first node's gate had nothing to classify and returned `wait` forever; with the gate now first, that made *every* recompute report read "UNMET (at phase-selection)" — the honest-status tool rendered useless. Fixed by recording the answer as a durable decision (`GraphState.decisions`, surfaced to hooks as `ctx.decisions`) that the gate honours, which is the same posture already taken for the skips themselves: a recorded human input, not the state file scoring itself. Pinned by a test asserting the gate reads `pass` in both `status` modes after a selection. | this PR |
| 7 | critic | — | **unavailable** — `reviews.critics: []`; no critic harness is configured in this repository, so no critic round could run. Does not count toward `criticReviewCount`; the human PR review is the backstop. | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist, cross-checked against `design.md` § Security design
  (`security.review.mechanism: auto`; no built-in security-review skill in this session's
  toolchain was applicable to a CLI/graph change of this shape). **Re-run in full after
  the rebuild** — the first pass's subject (the label channel) no longer exists.
- **Outcome:** **pass.** The new attack surface is the selection channel, and every
  boundary the requirements named is enforced where the design said it would be. *Who may
  declare* — the gate reads only `authorizedUsers`, through the same
  `_authorized_comments` reader the review gates use, which drops the-loop's own
  self-marked comments **before** authorization is even considered: the harness cannot
  answer its own gate even though it posts with the operator's credentials. The rejected
  label channel is itself a security improvement in reverse — it would have substituted
  GitHub's triage permission for the loop's own boundary. *What may be declared* — the
  vocabulary is compile-validated package data (`required`×`skippable` refused,
  `skipSets` cannot widen it, repo-supplied graphs already ignored), and
  `declared_skips()` re-applies the filter on every read, so a hook returning
  `declaredSkips` gains nothing and `security-review`/`human-approval` are structurally
  out of reach. *When* — a declaration only ever applies to a node still ahead of the
  pointer, on both channels. *Injection* — the checklist and confirmation are composed
  from the-loop's own vocabulary plus node ids from the compiled graph; the reply is
  parsed by a strict line regex into ids that must match that vocabulary, so no
  attacker-authored text becomes a destination. Deliberately **not** read: the checkboxes
  of the-loop's own comment, since GitHub reports that a comment was edited but never by
  whom. Tamper posture is stated rather than implied: a forged declaration on a protected
  node is inert and surfaced (tested, and shown in the walkthrough); a forged declaration
  on a skippable node is the accepted residual — detectable via its uncorroborated
  off-repo trail and bounded by the never-skippable floor, the same trust model as
  `graph-state.json` itself. Every failure yields *fewer* skips, and with no reply at all
  nothing runs.
- **Human sign-off:** effective risk tier **4** (set in `requirements.md` front-matter:
  the change alters process-gate semantics), so `security.review.humanSignOffMinTier: 4`
  applies — **pending: the owner's PR review is the sign-off**, requested in the PR
  briefing.

## Final validation evidence

Every acceptance criterion is proved by a committed artifact under
[`evidence/`](evidence/); the per-activity record is in
[`testing-plan.md`](testing-plan.md) § Verification results.

- **The vocabulary is fixed and validated** (R1.1–R1.6) — compile-refusal tests for
  `required`×`skippable`, missing `skipped` edges and out-of-vocabulary set members; the
  shipped-graph audit pinning exactly six skippable nodes, the exact `spec-chain` set,
  the unmarked floor and the clean PR loop: [`evidence/tests.md`](evidence/tests.md).
- **Only a human declares, and only up front** (R2.1–R2.12) — the selection-gate tests
  (posted once and naming the executing loop's phases; waits without an authorized
  `the-loop execute`; an unauthorized reply ignored; provenance recorded and the loop
  proceeding; a protected phase refused and named; `execute` with no list running
  everything; an outage leaving the gate waiting; an answered gate staying answered for
  `check`) and the verb tests (reason required; protected/unknown/entered/past tokens
  refused; audit comment recorded): [`evidence/tests.md`](evidence/tests.md),
  [`evidence/walkthrough.md`](evidence/walkthrough.md).
- **A skip routes and records, never forges** (R3.1–R3.5) — routing tests (no hooks run
  on skipped nodes; landing node's entry runs), both `status` modes reporting
  provenance, the tamper case inert and surfaced, and the planned-absence tolerance that
  still gates a present artifact: [`evidence/tests.md`](evidence/tests.md),
  [`evidence/walkthrough.md`](evidence/walkthrough.md).
- **The ticket's scenario works** — the checklist, an unauthorized reply changing
  nothing, an authorized reply producing six recorded skips and one refused protected
  phase, `test-planning` still gating:
  [`evidence/walkthrough.md`](evidence/walkthrough.md).
- **Nothing else moved** — 1459 passed, 1 skipped (baseline 1423/1); `ruff`,
  `ruff format --check`, `pyright`, `markdownlint` and `validate_config.py` clean:
  [`evidence/tests.md`](evidence/tests.md),
  [`evidence/lint-and-types.md`](evidence/lint-and-types.md).

## Documentation

> Which user-facing documentation this work item changed — gated by `capability-docs`
> since issue-174. A work item that changed none says so with the reason.

| Doc | What changed |
|---|---|
| [`docs/cli/commands/graph.md`](../../cli/commands/graph.md) | the new `## The first phase: phase-selection` section (what the checklist is, ticking in place, what `the-loop execute` freezes) and the `skip` verb; `graph show` now prints the `skippable` flag |
| [`docs/config/cli/routing-options.md`](../../config/cli/routing-options.md) | `control.keywords.execute` — the configurable keyword, and why it is a control command that touches no session |
| [`docs/cli/state.md`](../../cli/state.md) | the portable record's new `graph` section: the frozen node list, why it is portable rather than local, and what is lost if deleted |
| [`skills/the-loop/reference/workflow.md`](../../../skills/the-loop/reference/workflow.md) | § Declared skips — the three-party split and the start→select→execute→walk sequence |
| [`skills/the-loop/SKILL.md`](../../../skills/the-loop/SKILL.md) | the operating rule: skips are declared by humans, and a session never answers the gate |
| [`commands/init.md`](../../../commands/init.md) | states that **no** skip labels are created (the rejected channel would have needed seven per repo) |

The README and the docs-site front page are unchanged: this work item adds a phase to a
process both already describe at a level that does not enumerate phases.

## Capability docs

> Which living capability docs this work item changed, and the history row that traces the
> behaviour back to it. Updated **in the same PR** as the change — a ready-to-ship gate
> item (`workflow.capabilitiesDir`).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) | new § Declared skips: the `skippable` vocabulary and its three compile refusals, `skipSets`, the `phase-selection` first phase (authorized reply + `the-loop execute`, reply-only reading, refusal of protected phases) with the operator verb beside it, route-and-record semantics (`graph.node_skipped`, provenance in both `check` modes, tamper inert-and-surfaced), and the planned-absence rule for later gates | issue-177 · [decision-067](../../decisions/decision-067.md) |

`docs/cli/commands/graph.md` (the `skip` verb and the `skippable` flag in `show`),
`skills/the-loop/reference/workflow.md` § Declared skips, `skills/the-loop/SKILL.md`
(the never-self-skip rule) and `commands/init.md` (which now states that **no** skip
labels are needed) changed in the same PR; they are reference/skill pages rather than capability docs, listed here
for the reviewer's completeness.
