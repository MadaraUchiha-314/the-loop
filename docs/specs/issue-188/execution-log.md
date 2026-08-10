---
type: execution-log
workItem: issue-188
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: an opt-in critic review of the locked design

> Append-only log for issue-188. Ticket:
> [#188](https://github.com/MadaraUchiha-314/the-loop/issues/188).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-10 | @MadaraUchiha-314 (out of band) | The owner assigned this ticket directly to a cloud session rather than through the daemon, so no checklist was posted on the ticket and no `the-loop execute` reply exists. The full process was run — no phase was declared away, and the harness declared none. `the-loop check issue-188` therefore still reports the pointer at this gate, honestly: the loop's own record of the selection is a comment that was never posted. |
| requirements-definition | 2026-08-10 |  | `requirements.md` locked — three requirements: the `optIn` marker, the checklist that offers it, the phase the loop ships with it. |
| design | 2026-08-10 |  | `design.md` locked. One marker across four layers; the load-bearing choice is expressing an unselected opt-in node as a skip with `via: not-selected`. |
| test-planning | 2026-08-10 |  | `testing-plan.md` locked — 13 rows, 6 `n/a` with reasons. |
| tasks-breakdown | 2026-08-10 |  | `tasks.md` locked — 7 tasks, DAG drawn. |
| implementation | 2026-08-10 |  | Tasks 1–6. |
| verification | 2026-08-10 |  | Plan executed; results and evidence recorded. |
| needs-review | 2026-08-10 |  | Self-review; awaiting the human gate on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-188-03nnes` | the whole work item (tasks 1–7) | open |

## Progress entries

### 2026-08-10 — spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** Read the ticket, the shipped graph, the selection hook and the declared-skip
  mechanism, then wrote and locked the four spec artifacts. The design question that took
  the time: the ticket asks for a phase that is *selectable* **and** *not on by default*,
  and the selection vocabulary had exactly one default. Settled on a second node marker
  (`optIn`) that implies `skippable`, so the new phase reuses the whole existing
  mechanism — routing, freezing, provenance, reporting — and differs only in which way the
  box starts.
- **Checkpoint/tests:** none yet (no code).
- **Next:** implement tasks 1–5.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** Tasks 1–5. `Node.opt_in`/`Node.description` with two compile-time refusals
  (`required`×`optIn`, an opt-in `skipSets` member); `GraphState.opt_ins`;
  `Runtime.selected()` plus the default-skip fold in `declared_skips()` and the
  *not selected* branch in `_skip_provenance`; the gate's third checklist section, third
  parse outcome, fuller confirmation and `optIn`-carrying frozen graph; the
  `design-critic-review` node with its four edges; the `## Design critic review` section in
  the shipped execution-log template; `graph.opt_ins_selected` in the event catalogue; and
  `graph show` printing `[opt-in]` in place of the weaker `[skippable]`.
- **Checkpoint/tests:** `uv run pytest cli/tests` — 1650 passed, 1 skipped. Two existing
  tests were updated rather than worked around: the shipped-sequence assertion in
  `test_graph_model.py` (the walked sequence is unchanged; the *declared* one gained a
  node) and the shipped-checklist assertion in `test_graph_skips.py` (an opt-in node must
  render unticked). **TDD note, honestly:** the model/graph edits for tasks 1 and 5 were
  written before their tests. The red→green transition was then established for real by
  stashing the whole production change and running the new tests against the unchanged
  runtime — 19 failed → 19 passed, recorded in `evidence/tests.md`.
- **Next:** task 6 (documentation), then verification.

### 2026-08-10 — documentation

- **Phase:** implementation (task 6)
- **Did:** `reference/reviewing.md` gained the design critic round (subject, prompt,
  where it is recorded, the `unavailable` rule); `reference/workflow.md` gained an
  *Opt-in phases* section beside declared skips; `SKILL.md` gained the sentence in the
  selection rule; `docs/capabilities/process-graph.md` and `review-loop.md` gained the
  behaviour and their history rows; `decision-071` was written and indexed. User-facing
  surfaces: `README.md`, `docs/guide/what-is-the-loop.md`, `docs/cli/commands/graph.md`
  and `docs/cli/state.md`. While in `graph.md`, corrected a statement that had gone stale
  before this change — it claimed ticking boxes in place does nothing, which the shipped
  hook has not done since PR #178's review.
- **Checkpoint/tests:** `make lint` — 0 errors over 504 markdown files.
- **Next:** verification.

### 2026-08-10 — verification

- **Phase:** verification
- **Did:** Executed every activity of `testing-plan.md` and recorded the results there;
  captured `evidence/tests.md`, `evidence/lint.md` and `evidence/walkthrough.md`. The
  walkthrough drives the **shipped** loop on a scratch work item both ways — unselected
  (routed around, reported *not selected*) and selected (walked, blocking on its own
  section) — and shows the rendered checklist and the recorded provenance.
- **Checkpoint/tests:** full suite 1650 passed / 1 skipped; `make lint format-check
  typecheck validate` clean.
- **Next:** the review chain, then the human gate on the PR.

## Verification results

> This work item kept `test-planning`, so the record lives in
> [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix rows it
> planned. This section stays as the template left it.

## Design critic review

> This work item did not select the opt-in `design-critic-review` phase — it is the work
> item that *introduces* it, so the node did not exist when its own design was written.
> Recorded here rather than left blank, because an empty gated section is never an answer.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | claude/opus-5 | new findings — three, all fixed: the checklist's opening sentence still said only "untick" with an opt-in section present; `graph show` printed `[skippable]` for an opt-in node (reads as on-by-default); the testing plan's T8/T10 `-k` expressions selected fewer tests than intended (`deleting_a_selection` carries no `opt_in` in its name) | this log |
| 2 | self | claude/opus-5 | zero (converged) — re-read the diff for the two facts that must not blur: `via: not-selected` never renders as a declaration, and a forged `optIns` entry can only add a review | this log |
| 3 | critic | — | **unavailable** — `reviews.critics[]` is empty in this repository's config, so no critic CLI is configured to run. Recorded as a stated gap, not a pass, per `reference/reviewing.md` | `.the-loop/harness-config.yaml` |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no built-in
  security-review skill was invoked from this session).
- **Outcome:** pass. The change adds no ingress, no credential, no network call and no new
  authorization path — the selection reply is parsed by the existing `_CHECK_LINE` regex,
  authorized by the existing `_authorized_comments` boundary, and matched against compiled
  node ids only. The new `optIns` map is agent-writable like the rest of `graph-state.json`
  and is filtered through the compiled graph on every read (`Runtime.selected`), so its
  widest possible abuse is causing an extra review to run: it can neither pass a gate nor
  excuse an artifact. Deleting an entry removes a review, never a gate, and `check` then
  reports *not selected* rather than `pass`. The one new string reaching a posted comment
  is the shipped graph's `description`, which no repository can supply. Abuse cases 1–3
  have negative tests (`evidence/tests.md` § T8); abuse case 4 (critic output carrying
  instructions) is the pre-existing documented rule in `reference/reviewing.md`.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier` (4).

## Final validation evidence

Acceptance criteria, against the record:

- **R1 (the graph can declare an off-by-default phase)** — `optIn` parsed and implying
  `skippable`, both compile refusals, the runtime default with no declaration present, the
  *not selected* report in both `check` modes, the recorded selection with provenance, the
  filtered read of a forged entry, and `optIn` in the frozen graph: `evidence/tests.md`
  §§ T1, T2, T8, T10 and `evidence/walkthrough.md` §§ 3–5.
- **R2 (the checklist offers them separately)** — the rendered checklist with its own
  unticked section and the node's description, the three-way parse (ticked / unticked /
  absent), and both confirmation lines: `evidence/tests.md` § T2 and
  `evidence/walkthrough.md` § 2.
- **R3 (the loop ships the design critic round)** — the node's position, markers and gate,
  the two loops that declare no opt-in node, and the gated template section:
  `evidence/tests.md` §§ T2, T12 and `evidence/walkthrough.md` § 1.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`process-graph.md`](../../capabilities/process-graph.md) | New *Opt-in phases* section (the marker, its compile refusals, the checklist contract, the recorded selection, the routing and reporting rule); `description` added to the node-field contract | `issue-188` row |
| [`review-loop.md`](../../capabilities/review-loop.md) | New *The design critic round* section — subject, opt-in default, its own gated log section, unchanged procedure, `stage: critic-review` | `issue-188` row |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/reference/reviewing.md` | The design critic round: what it reviews, how it differs from the `critic-review` node, the prompt's contents, where findings go, the `unavailable` rule |
| `skills/the-loop/reference/workflow.md` | *Opt-in phases — the other default*: the two markers side by side, the fail-closed direction, the one shipped phase, and that it is outer-loop only |
| `skills/the-loop/SKILL.md` | One sentence in the phase-selection rule — the same gate also offers what is not on by default |
| `skills/the-loop/templates/execution-log.md` | The `## Design critic review` section the node gates |
| `README.md` | The reviews sentence now says a work item can opt in to one more, reading the locked design |
| `docs/guide/what-is-the-loop.md` | Same, in the insists-on list |
| `docs/cli/commands/graph.md` | The checklist example gained an opt-in row and the two-defaults explanation; `show`'s flag list gained `opt-in` with an updated sample; **and** the stale claim that ticking in place does nothing was corrected |
| `docs/cli/state.md` | The portable `graph` record's node shape gained `optIn`, with what `skipped: true` means for such a node |
| `docs/decisions/decision-071.md` + `decisions.md` | The decision record and its index row |
