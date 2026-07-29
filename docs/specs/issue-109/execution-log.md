---
type: execution-log
workItem: issue-109
phase: tasks-breakdown        # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress           # in-progress | complete
---

# Execution Log: making the-loop deterministic (issue #109)

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in the ticketing system in sync with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-07-26 | @MadaraUchiha-314 (PR #110, 2026-07-27) | Phase 0 entered: the ticket is explicitly exploratory, so the loop started at the root artifact. Two review rounds (Cursor hook correction; graph architecture). **Locked** on *"let's go ahead with the requirements and design"*. |
| requirements-definition | 2026-07-27 | @MadaraUchiha-314 (PR #110, 2026-07-28) | `requirements.md` derived from the locked brainstorm; **rewritten 2026-07-28** for the nodes+hooks simplification. 9 requirements in EARS, threat-model-lite, risk tier **4** (explained in-doc rather than asserted). All open questions now resolved. |
| design | 2026-07-27 | @MadaraUchiha-314 (PR #110, 2026-07-28) | `design.md` derived from the requirements; **rewritten 2026-07-28** from a fresh slate. Two concepts (node, hook) + one contract (`HookResult`), human gate as a node with `session: inherit`, opinionated integrations, MCP by delegation, no expression language. Decisions `041` and `042`. |
| tasks-breakdown | 2026-07-28 | *(pending — this PR)* | `tasks.md` derived from the locked specs: **36 tasks in five vertical slices**, each independently mergeable. Slice A alone delivers the drift report this work item started from. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#110](https://github.com/MadaraUchiha-314/the-loop/pull/110) | Phase 0 — `brainstorm.md` + this log | open |

## Progress entries

### 2026-07-26 — Phase 0 brainstorm drafted

- **Phase:** brainstorming
- **Did:**
  - Read the operating model (`CLAUDE.md`, `.the-loop/harness-config.yaml`,
    `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/automation.md`) and the
    CLI's session machinery (`webhook/dispatcher.py`, `harness/base.py`,
    `harness/claude_code.py`, `runner.py`) to answer the ticket's mechanical questions
    from the code rather than from memory.
  - Measured the non-determinism the ticket describes against this repo's own checked-in
    specs (34 spec folders): 24/34 carry `tasks.md`, 25/34 carry `execution-log.md`,
    15/28 `requirements.md` and 16/33 `design.md` are still `status: draft` despite the
    work having shipped, and **0 of 25** execution logs reach `phase: complete` while 22
    sit at `needs-review` — against 15 issues labelled `loop:complete`. The two mirrors of
    the phase state machine disagree on 22 work items, unnoticed.
  - Confirmed the completion-signal question from the harnesses' documented behaviour:
    Claude Code's `Stop` hook and `Notification` matchers (`agent_needs_input`,
    `permission_prompt`, `idle_prompt` vs `agent_completed`) already distinguish
    "waiting for a human" from "turn finished"; headless `-p --output-format json` makes
    the question moot by exiting with a terminal result object.
  - Wrote `docs/specs/issue-109/brainstorm.md`: problem + evidence, constraints, the
    ticket's mechanical questions answered, seven options (A–G) with the rejected
    alternatives and *why*, two mermaid sketches, seven open questions, and a
    verify-first-orchestrate-second working hypothesis.
- **Checkpoint/tests:** documentation-only change — no code touched. Markdown lint is the
  applicable gate (`tooling.lint.markdown`): `npx markdownlint-cli2@0.18.1
  "docs/specs/issue-109/*.md"` → 0 errors. CI (`checks`) green on PR #110. No
  unit/integration surface exists for this phase.
- **Next:** owner feedback on the seven open questions (scope, gate hardness, Claude-first
  enforcement, verification-vs-orchestration, resident-vs-per-step sessions, strictness of
  "no extra steps", retrofit policy). When answered, set `status: approved` + `approvedBy`
  on `brainstorm.md`, advance the label to `loop:requirements-definition`, and derive
  `requirements.md` from the locked brainstorm.
- **Context:** no reset — single-phase, single-window work.
- **Blockers:** the brainstorm cannot be locked without the owner's answers; raised as a
  ticket comment (paper trail).

### 2026-07-26 — Cursor hook coverage corrected (owner review finding)

- **Phase:** brainstorming
- **Did:** @MadaraUchiha-314 challenged the claim that in-session enforcement would be
  Claude-first, pointing at Cursor's documented `stop` hook. Re-checked against Cursor's
  hook documentation: the finding is right, and the correction is stronger than a fix —
  **Option C is cross-harness.** Cursor's `stop` fires at the end of *each agent turn*, and
  while it cannot block completion the way Claude Code's `Stop` can (exit 2 /
  `decision: "block"`), it returns a `followup_message` that Cursor **auto-submits as the
  next user turn** — closing exactly the same enforcement loop by a different mechanism.
  Corrected the completion-signal matrix, added a **continuation matrix**, rewrote Option
  C's pro/con, the cross-harness constraint, the mermaid edge (`Cursor degrades to D` →
  both harnesses enforce in-session), open question 3, the hand-off, and the references.
  One consequence worth flagging: the runaway-protection asymmetry runs the *other* way —
  Cursor caps auto-followups natively (configurable `loop_limit`, hard max 5) while Claude
  Code caps nothing, so the attempt cap is required on the **Claude** path.
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1 "docs/specs/issue-109/*.md"` →
  0 errors.
- **Next:** unchanged — the remaining six open questions still gate locking the brainstorm.
  Open question 3 is narrowed from "is Claude-first acceptable?" to a five-minute
  experiment: does `stop` fire in the `cursor-agent` **CLI** surface (what the-loop drives)
  or only in the IDE? Reports conflict; run it before requirements lock.
- **Blockers:** unchanged.

### 2026-07-26 — architecture redirected to a graph model (owner direction)

- **Phase:** brainstorming
- **Did:** @MadaraUchiha-314 named the real defect on PR #110: *"there's no clear
  definition and hooks around logical 'node' boundaries… the hooks provided by the agent
  harnesses are too fine grained and lack the appropriate details to figure out which phase
  of the-loop we are in"* — and asked for a **graph** of the-loop's nodes with an
  orchestration layer determining the edges (static now, dynamic later), plus an answer on
  whether this is the literature's "graph engineering".
  - **Accepted and designed.** Added § *Architecture: the-loop as a graph* — five layers:
    graph data (nodes/edges with `produces`/`requires`/`gate`/`actor`/`stage`/`notify` and
    `when` edges, cycles first-class), graph state (checked-in `currentNode` + attempts),
    **node-lifecycle hooks** (`onEnter`/`onExit`/`onGateFail`/`onAwaitHuman`/`onEscalate`),
    transports (orchestrated / resident-session tick / event-driven / CI backstop), and
    bounded dynamic edges (the agent *selects among declared* edges, never invents one).
  - **Confirmed the critique against this repo's own numbers.** 23 of 26 execution logs
    sit at `phase: needs-review`, and `needs-review` is a single label covering six
    distinct nodes (self-review, critic-review, security-review, evidence, capability-docs,
    reviewer-briefing). The drift is not uniform — **it concentrates exactly where node
    granularity runs out.** This is now the strongest single piece of evidence in the
    brainstorm, and it argues the owner's case rather than the earlier draft's.
  - **Corrected my own framing.** The earlier draft treated a harness `Stop` event as if it
    were a node boundary. It is not: it fires many times per node and carries no phase.
    New principle recorded — **harness hooks are a clock, not a state machine**; they say
    *when* to look, the graph says *what we are looking at*. This rescues the hook work as
    a transport rather than discarding it.
  - **Answered the literature question: yes, and the term is current.** The lineage is
    prompt engineering → **flow engineering** (AlphaCodium, 2024) → **graph engineering**
    (2026): explicit workflow graphs modelled as state machines, canonical representation
    being the stateful directed graph with typed nodes, conditional edges and persistent
    checkpoints, cycles treated as a feature. Recommended adopting the *model and
    vocabulary* while **implementing rather than importing** — the-loop's nodes are harness
    CLI subprocesses and its checkpoints are checked-in files, neither of which an
    in-process graph library serves.
  - Re-cast options A–G as layers of the architecture (nothing discarded), resolved open
    question 4 (orchestration, per the owner), and opened questions 8–11 (node granularity,
    where graph state lives, graph vs `workflow.phases`, bounding dynamic edges).
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1 "docs/specs/issue-109/*.md"` →
  0 errors.
- **Next:** owner review of the architecture, then questions 1, 2, 7, 8, 9, 10 before the
  brainstorm can be locked. Question 4 is now closed.
- **Blockers:** unchanged — the brainstorm stays `status: draft`.

### 2026-07-27 — brainstorm locked; requirements and design derived

- **Phase:** brainstorming → requirements-definition → design
- **Did:**
  - **Locked `brainstorm.md`** (`status: approved`, `approvedBy: @MadaraUchiha-314`) on the
    owner's *"let's go ahead with the requirements and design"* (PR #110).
  - **`requirements.md`** — 10 requirements in EARS covering the declared graph (R1),
    durable graph state (R2), pure gate evaluation (R3), node-lifecycle hooks and
    notifications (R4), the orchestrated transport (R5), resident/event transports (R6),
    the repository-boundary hard gate (R7), bounded recovery (R8), backwards compatibility
    (R9) and observability (R10). Risk tier set to **4**: the change touches
    `autonomy.sensitivePaths` (`**/*schema*`), so `autonomy.tiers` gives `human-approves-pr`
    and `security.review.humanSignOffMinTier: 4` additionally requires a **named human
    security sign-off** before completion.
  - **Threat-model-lite written, not waved away.** This work item *does* add attack surface.
    Four boundaries enumerated with six abuse cases: config→process execution (a node
    carrying free-form argv would be arbitrary command execution), **agent→graph state**
    (the subject of the gate can write the gate's bookkeeping), gate-result→harness input
    (prompt-injection surface), and node-events→external channels.
  - **`design.md`** — the five layers as components (`the_loop/graph/{model,gates,state,
    runtime,notify}.py` plus two commands and per-harness hook wrappers), closed
    vocabularies for gate predicates and edge conditions, the `graph-state.json` schema, an
    error-handling table, a security design mapping every boundary to its mechanism and
    negative test, and a requirement→scenario testing matrix. UI/UX: N/A (CLI).
  - **Two design calls worth flagging to the reviewer.** (1) `command` is a **closed enum**,
    not a string to execute — the runtime builds the argv itself, which closes the largest
    new attack surface at the data model rather than with validation. (2) **Graph state is a
    cache, not an authority** — `--recompute` derives completion from artifacts alone and the
    CI gate always uses it, so an agent editing its own scorecard cannot pass a gate.
  - **`decision-041`** recorded and indexed: model the process as a graph with node-lifecycle
    hooks, harness hooks as a clock, implement rather than import. It also closes the "open
    design question" that has sat unanswered at the end of `reference/workflow.md`.
  - Seven brainstorm open questions resolved as **explicit assumptions** in a table at the
    top of `requirements.md`, each stated so this phase's review can override it — rather
    than silently absorbed (`reference/workflow.md`: keep moving, log the assumption).
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1` over the changed markdown → 0 errors;
  `uv run python scripts/validate_config.py` → config still valid (no schema change yet —
  the schema lands with implementation).
- **Deviation, authorized:** the-loop's rule is that a downstream artifact is derived only
  from a *locked* upstream one. The owner directed requirements **and** design in one pass,
  so both are drafted together and reviewed in the same PR. Recorded here and in
  `design.md`'s header rather than passed over; if the requirements review changes anything
  material, the design is revised before tasks.
- **Next:** owner review of `requirements.md` and `design.md`. On approval, set both to
  `status: approved`, advance to `loop:tasks-breakdown` and derive `tasks.md`. Three open
  questions want answers first: the closed command vocabulary vs. operator-defined commands,
  `graph-state.json` vs. execution-log front-matter, and who provides the tier-4 security
  sign-off.
- **Blockers:** phase approval for requirements and design (`requireHumanReviewPerPhase`).

### 2026-07-27 — specs revised: internal graph, CEL edges, dynamic gates (owner direction)

- **Phase:** design
- **Did:** second owner direction on PR #110 — make the graph internal, use CEL for
  conditional edges, support LLM-decided approval gates, per-work-item tags/skips, YAML
  lifecycle hooks, and keep tmux as the seat of the work. `requirements.md` and `design.md`
  rewritten; `decision-041` amended; `decision-042` added.
  - **The security model inverted, and it's a net win.** Making the graph internal *removes*
    the largest boundary outright — no repository-supplied declaration can reach an
    invocation, so config→process execution is gone rather than mitigated. But dynamic gates
    *add* a new primary boundary: a decision call reads human-authored text, which on a
    public repository anyone can write. Risk tier stays **4**, now for a better-founded
    reason. The closed `command` and hook-action vocabularies are **retained anyway** — they
    cost nothing now and are the mechanisms that will make user-defined graphs safe later.
  - **Resolved the central tension with "the LLM produces facts; CEL routes."** A dynamic
    gate never picks the next node. It answers a schema-constrained question; the validated
    result binds into the CEL context; the node's **declared** edges route. Judgement where
    judgement is needed, reachable state set still fixed — which is the whole point of #109.
  - **Verified the harness question from primary sources rather than assuming.** Claude Code
    supports `-p --output-format json --json-schema '<schema>'`, returning a validated
    `structured_output` — exactly the mechanism needed. Cursor's CLI has
    `-p --output-format json` but **no schema enforcement**, so its decisions embed the
    schema, validate locally and retry within a bound. That asymmetry is a documented open
    question, not papered over.
  - **Honoured the tmux constraint as a design rule.** Work nodes run through the normal
    runner (attachable, take-over-able); decision calls are separate short-lived headless
    processes — never `--resume` of the work session, never pasted into tmux — so automation
    never costs the human their intervention surface.
  - **Bounded per-work-item skipping before it could become the new hole.** `tags`/`skipNodes`
    come only from checked-in front-matter (never a comment or payload), and nodes marked
    `required: true` — the security-review gate, mandated human approvals — are unskippable
    regardless. Skipping is the obvious way to reintroduce step-skipping, so the bound lives
    in the data model rather than in convention.
  - **Closed hook-action vocabulary, no shell.** YAML selects and parameterises typed actions;
    it never supplies a command line. This is what lets the hooks surface eventually be
    user-authored without becoming remote code execution.
  - Accepted **one** new runtime dependency (pure-Python CEL) in decision-038's posture,
    reasoning that adopting a language designed to be embedded beats proving a bespoke
    evaluator safe ourselves.
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1` over the changed markdown → 0 errors;
  `uv run python scripts/validate_config.py` → all configs VALID.
- **Next:** owner review of the revised requirements and design. Four open questions want
  answers: the tier-4 security sign-off, which CEL implementation, how far `skipNodes` goes
  beyond the `required` set, and the Cursor decision path. On approval → `loop:tasks-breakdown`.
- **Blockers:** phase approval for requirements and design.

### 2026-07-28 — broken mermaid fixed; a rule-without-an-evaluator found

- **Phase:** design
- **Did:** @MadaraUchiha-314 reported that the design.md architecture diagram would not
  render — *"Lexical error on line 31. Unrecognized text."* Reproduced locally: backticks
  inside mermaid node labels. Fixed every backticked label
  across `brainstorm.md` and `design.md`, and simplified a sequence-diagram message
  containing `|`, `{}` and `[]`.
  - **Built a validator rather than eyeballing it.** Extracted every fenced mermaid block and
    ran it through the real parser (`@mermaid-js/mermaid-cli`, `--no-sandbox`). All 5 blocks
    in this work item's artifacts now parse.
  - **Then ran it over the rest of the repository — and found three already-merged broken
    diagrams:** `docs/specs/issue-21/design.md`, `issue-32/design.md`,
    `issue-86/design.md` (42 blocks pass, 3 fail). `userInteraction.diagramFormat: mermaid`
    is written as a **RULE** and is enforced by nothing, so broken diagrams shipped. That is
    this work item's thesis reproduced in miniature, on a rule nobody would have guessed was
    drifting.
  - **Turned the finding into design.** Added `diagramsRender` to the gate predicate
    vocabulary in `design.md` — one parser invocation, and the cheapest possible
    demonstration that a declared rule wants a mechanical evaluator.
  - **Did not fix the three merged specs.** They belong to closed work items and are outside
    issue-109's scope; reported to the owner with an offer instead of silently widening this
    PR.
- **Checkpoint/tests:** mermaid validation 5/5 blocks OK in this work item's artifacts;
  markdownlint 0 errors; config validation VALID.
- **Next:** unchanged — phase approval for requirements and design.
- **Blockers:** unchanged.

### 2026-07-28 — architecture simplified to nodes + hooks (owner direction, fresh slate)

- **Phase:** design
- **Did:** owner asked to *"simplify the concepts… a graph with entry and exit hooks, and
  then each of these validations that we want are hooks that are chained together"*, and to
  *"delete any bias that might have crept in till now, start with a fresh slate"*.
  `requirements.md` and `design.md` rewritten from scratch; `decision-041` and `-042`
  rewritten to match.
  - **Collapsed five layers into two concepts + one contract.** Node (a step, with `entry`
    and `exit` hook chains) and Hook (fixed signature), with `HookResult`
    (`pass | block | wait | skip`, plus `messages`, `data`, `retriable`) deciding movement.
    The separate lifecycle-event system, action vocabulary and per-edge expression language
    are **gone** — each was a subsystem where a hook would do.
  - **This is what finally answers the ticket's sharpest question cleanly.** A node is
    complete when its exit hooks all pass; waiting when one returns `wait`; blocked when one
    returns `block`. The earlier drafts circled this; the hook contract states it in one line.
  - **Answered the node-vs-hook question the owner asked.** Recommendation: the human gate is
    a **node**, on five grounds — it lasts days, it *receives* events while open, it has an
    internal loop (partial review, approve-with-comments), it produces artifacts, and every
    other PDLC step is a node. A hook is a function that runs and returns; modelling a
    multi-day event-receiving state as one means inventing suspend-and-resume, which is a
    node with extra steps. Its behaviour is still all hooks.
  - **Turned the owner's session observation into one field.** Gate feedback concerns the
    *previous* node's artifacts, so a gate node declares `session: inherit` and reuses the
    producing session — the reviewer's "this section is thin" reaches the agent that wrote
    it, context intact. One enum value rather than a new concept.
  - **Modelled iterative review properly.** The gate re-runs its exit chain on every inbound
    event and stays open on indecisive feedback; approve-with-comments is a distinct outcome
    that advances *and* carries follow-ups forward, so an approval never silently swallows a
    reviewer's suggestions.
  - **Made chain semantics do the right thing for feedback quality.** First non-`pass`
    short-circuits, but aggregation is the *hook's* job — `validate-artifacts` returns every
    unmet requirement in one result, so the agent gets the full list in one round instead of
    discovering failures one at a time.
  - **Took the opinionated tool decisions.** GitHub **REST over stdlib HTTP** rather than the
    `gh` CLI (no binary dependency, no version drift, no shell quoting, works in a bare
    container) — with `gh auth token` retained *purely as a credential source*, which keeps
    `gh`'s auth ergonomics without depending on it at call time. Slack **incoming webhooks**.
    Jira **REST + token**. All are ordinary hooks behind one interface.
  - **Answered the MCP open question.** MCP is a protocol for *agents* to call tools — it
    assumes a model-driven client with a session, so a daemon speaking it is against its
    grain. Recommendation: **delegate through the harness** (already an MCP client with the
    operator's servers configured) via an `mcp-call` hook with schema-constrained output;
    keep a minimal stdio JSON-RPC client on the shelf. Costs one invocation, avoids owning a
    protocol and its server lifecycle.
  - **Simplified routing.** `on: <outcome>` covers most edges now that hook results are
    typed; an optional `when:` handles the compound minority. Whether that is CEL or named
    compound-condition hooks is now an open question rather than a default — a real
    reduction from "an expression on every edge".
  - Carried forward the `diagramsRender` finding as part of `lint-artifacts`.
- **Checkpoint/tests:** markdownlint 0 errors; all 4 mermaid blocks in the rewritten
  `design.md` parse (validated with `@mermaid-js/mermaid-cli`).
- **Next:** owner review of the rewritten requirements and design. Four open questions:
  the tier-4 security sign-off; whether approve-with-comments follow-ups are mandatory or
  advisory; `session: inherit` fallback when the session has died; and whether CEL is still
  wanted for compound edges.
- **Blockers:** phase approval for requirements and design.

### 2026-07-28 — four open questions resolved by the owner

- **Phase:** design
- **Did:** owner answered all four open questions on PR #110; specs and `decision-042`
  updated. **No open questions remain** — only phase approval stands between this and tasks.
  - **"Tier-4 named security sign-off — what is this? I don't understand this."** Fair
    challenge: I had been repeating config jargon. Added § *Risk tier 4 — what that actually
    means here* to `requirements.md`, spelling out what each of the two config rules
    concretely requires and, importantly, what it does **not** mean — there is no implied
    security team. "Named sign-off" means the paper trail records *who* accepted the security
    analysis, so the loop cannot self-certify its own threat model; here that is the owner,
    and the deliverable is one attributed comment on the PR.
  - **Approve-with-comments → the comments go in the artifact.** Owner: *"approval and
    comments can be a section in the final artifact… a comments section at the bottom of each
    doc."* This is a better answer than either option I offered (mandatory vs advisory
    follow-ups): the feedback becomes part of the durable, checked-in record, travels with
    the document it concerns, and shows up in the PR diff. Added a `record-feedback` hook and
    made a non-empty `## Review comments` section a required check on any gated artifact, so
    a lost review blocks rather than passing silently.
  - **`session: inherit` fallback confirmed** — fall back to a fresh session seeded with
    `requirements.md` / `design.md` / `execution-log.md`, never block.
  - **CEL removed.** Every edge now routes on a hook outcome; a condition that would have
    wanted an expression becomes a named hook (`is-docs-only` → `docs-only | pass`). This
    lands the architecture on **zero new runtime dependencies** and removes the last place
    where two mechanisms did one job. Two successive drafts had reached for an expression
    language; the hook contract already expressed it.
- **Checkpoint/tests:** markdownlint 0 errors; all 4 mermaid blocks parse; config VALID.
- **Next:** phase approval for `requirements.md` and `design.md`. On approval → set both
  `status: approved`, advance to `loop:tasks-breakdown`, derive `tasks.md`.
- **Blockers:** phase approval only.

### 2026-07-28 — integration transport made configurable; two call planes named

- **Phase:** design
- **Did:** owner direction on PR #110 — *"How to interface with external services should be
  configurable. We should support SDK+API and CLI… Anything that the LLM uses can be through
  CLI, MCP or API as LLM is free to do whatever it wants."* `requirements.md` R6 rewritten,
  `design.md` § Tool access rewritten, `decision-042` revised.
  - **Named the boundary the comment draws.** Two call planes: the-loop's **control plane**
    (its own hook calls — deterministic, auditable, credentialed, configurable) and the
    agent's **work plane** (unconstrained — CLI, MCP, API, whatever the harness has). the-loop
    does not police the work plane: it would buy nothing, since the agent is already trusted
    to write code, and it would break the session-takeover property the tmux runner exists
    for. Everything in the integrations design now applies to the control plane only.
  - **Transport is configurable per integration** (`api` / `cli` / `sdk` in `cli-config.yaml`,
    since the daemon makes these calls — decision-032). `auto` resolves token → binary and
    **fails closed naming both remedies**; an explicit transport is honoured verbatim and
    fails rather than silently degrading, because a configured choice that quietly falls back
    is worse than an error.
  - **This fixes the migration story, which is the part I had wrong.** Two rounds ago I
    proposed replacing `gh` with REST outright. But the-loop already reaches GitHub through
    `gh` in five modules, with `ghBinary` configured in three places — so a mandated
    transport meant a risky big-bang rewrite *and* threw away working code. Configurable
    transport turns it into **keeping `gh` as the `cli` provider and adding `api` beside it**:
    additive, reversible, and it preserves `gh auth`'s enterprise/SSO inheritance for
    operators who want it. The earlier recommendations survive as **defaults**, not mandates.
  - **Added the discipline the flexibility needs.** N transports × M operations is a matrix
    that would rot silently, so providers **declare the operations they implement** and the
    runtime verifies at **load time** that the configured graph's hooks are all satisfiable —
    failing at startup, naming the operation and both fixes, rather than three nodes deep. One
    shared contract suite runs against every provider so `api` and `cli` are *verified*
    equivalent, not assumed. And `HookResult` stays transport-independent by construction:
    swapping transport changes how a side effect happened, never whether a node advances.
- **Checkpoint/tests:** markdownlint 0 errors; 4/4 mermaid blocks parse.
- **Next:** phase approval for requirements and design.
- **Blockers:** phase approval only.

### 2026-07-28 — orchestrator runtime specified; configs reconciled

- **Phase:** design
- **Did:** owner asked two things on PR #110 — *"what technology takes the graph definition,
  compiles it and runs it? Can we add that detail in the design.md?"* and *"can we reconcile
  the configs across cli-configs and harness-configs to follow this integration pattern?"*
  Both were real gaps: the design said "thin Python, no framework" without ever describing the
  runtime, and the integrations block was designed without applying it backwards.
  - **Added § The orchestrator: what actually runs the graph.** The answer is no engine —
    ~600 lines of plain Python — and the more useful half is that **the-loop already has this
    pattern in production**: `commands/base.py` is `Command` + `@register` + `_REGISTRY` +
    `iter_commands()`, and the hook registry is the same shape, so a new hook is a new module
    exactly as a new sub-command is. Specified what "compile" means (parse → validate →
    resolve hook/edge names → index edges by `(from, outcome)` → freeze), with the point that
    **every structural failure becomes a startup failure** rather than a surprise three nodes
    into a traversal. Runtime is a synchronous state machine; three drivers (`run`, the
    daemon, `check`) all call the same chain code, which is what keeps `check` honest — CI
    runs the runtime, not a reimplementation.
  - **Resolved a dependency question honestly.** `scripts/validate_config.py` uses
    `jsonschema`, but as a dev dependency behind `try/except ImportError`. Since the graph
    ships with the plugin and is validated in the-loop's own CI, the runtime needs only cheap
    structural checks — **no new runtime dependency**. Runtime schema validation earns its
    cost only if user-authored graphs arrive.
  - **Named what we are deliberately not using and why** — LangGraph (assumes in-process
    callables and serialized checkpoints; ours are subprocesses and checked-in files),
    Temporal/Airflow/Prefect (a scheduler, worker pool and database for a machine that
    advances a few times a day), a rules engine (removed with CEL), `asyncio` (every wait is a
    subprocess or a human, and the dispatcher already handles concurrency).
  - **Reconciled the configs, which removes duplication that already exists.** `ghBinary: gh`
    is declared **three times** in `cli-config.yaml` (`control`, `reactions`, `announce`) plus
    the poller — every feature redeclaring its transport. Now three layers with no overlap:
    **what** (harness-config: which events, which ticketing system) · **who**
    (collaborators.yaml: role → person → address) · **how** (cli-config `integrations`:
    transport + credentials). This *preserves* decision-032 rather than undoing it — per-repo
    intent stays in the harness config, daemon mechanics in the CLI config; the change is that
    intent now references a provider **by name** instead of restating how to reach it.
    Migration is non-breaking: a legacy `ghBinary` keeps working as an override with a
    deprecation warning, same posture as the `config.yaml` → `harness-config.yaml` rename.
  - Added R6a (config reconciliation) and R6b (the graph runtime) to `requirements.md`.
- **Checkpoint/tests:** markdownlint 0 errors; **5/5** mermaid blocks parse.
- **Next:** phase approval for requirements and design.
- **Blockers:** phase approval only.

### 2026-07-28 — config change made breaking, migrated by /upgrade

- **Phase:** design
- **Did:** owner overruled my non-breaking proposal — *"Let's make breaking changes. /upgrade
  should be able to handle it."* Agreed, and it is the better call: carrying `ghBinary` as a
  shadow override would have preserved exactly the duplication the reconciliation exists to
  remove, leaving two ways to say one thing. The legacy keys are now **removed**.
  - **Checked the claim before relying on it.** `/the-loop:upgrade-the-loop` is documented as
    reconciling files and **migrating schemas**, is idempotent and non-clobbering, supports
    `--dry-run`, and has **already performed a rename migration of exactly this shape**
    (`config.yaml` → `harness-config.yaml`, issue-82). So "/upgrade handles it" is a
    verifiable property of an existing tool, not an aspiration.
  - **Specified four properties that make the break safe**, since a breaking change is only
    as good as its migration: version the schema so detection is exact rather than
    key-sniffing; **fail closed and loudly** — a config still carrying a removed key makes the
    runtime refuse to start, naming the key, its replacement and the exact command, because
    silently ignoring a value the operator deliberately set would change their behaviour
    without telling them; make the migration a deterministic, idempotent, previewable key
    move that *reports* what it changed; and **test it both ways**.
  - The test point is the thesis eating its own cooking: *"/upgrade handles it"* is precisely
    the kind of claim that drifts into being false, so it gets a fixture — old config in,
    expected config out — plus a test asserting the runtime **refuses** an un-migrated config.
  - Rewrote R6a (now 8 criteria) and the design's migration paragraph; noted in `decision-042`.
- **Checkpoint/tests:** markdownlint 0 errors; 5/5 mermaid blocks parse.
- **Next:** phase approval for requirements and design.
- **Blockers:** phase approval only.

### 2026-07-28 — specs locked; escape hatch specified; tasks derived

- **Phase:** design → tasks-breakdown
- **Did:** owner: *"Go ahead with implementation. One thing I would also focus is how do we
  add commands that can force the-loop from one step/phase to the other overriding all the
  checks… an escape hatch exercisable by the authorized user running the-loop's CLI."*
  - **Locked `requirements.md` and `design.md`** (`status: approved`, `approvedBy`), advanced
    the phase to `tasks-breakdown`.
  - **Specified the escape hatch (R10 + design section) before deriving tasks**, because it
    changes what gets built. `the-loop graph force --work-item X --to <node> --reason "..."`.
    The design rule that keeps it honest: **a force moves the pointer, it never forges a
    verdict.** The transition is recorded as `forced` and the bypassed gate keeps its real
    evaluation, so `check --recompute` still reports it unmet — the operator gets unblocked,
    nobody gets misled. An override that also marked the gate satisfied would make every
    guarantee in the design worth only as much as the operator's discipline.
  - **Authorization is shell access, deliberately not a comment keyword** — comments are
    attacker-reachable on a public repository, a shell is not. `--reason` is required.
  - **Bypassing a `required` gate is allowed**, and that is the considered call: an operator
    with shell access can already edit artifacts, rewrite state and push, so refusing buys
    nothing except a worse workaround that leaves *no* trace. The real control is that the
    bypass is **loud and permanent** — four audit records, an explicit warning naming the
    guarantee waived, and a `--recompute` that keeps telling the truth afterwards.
  - **Derived `tasks.md`: 36 tasks across five vertical slices**, each independently
    mergeable and each leaving the repo working. Sequenced so **Slice A alone is useful** —
    it produces the drift report over the 34 existing spec folders that motivated the whole
    work item — and so nothing later is wasted if priorities shift. Every task names its
    dependencies, its requirements and the test that proves it; security-relevant tasks name
    the **negative** test.
- **Checkpoint/tests:** markdownlint 0 errors; 6/6 mermaid blocks parse across the specs.
- **Next:** begin Slice A (hook contract → registry → chain → validators → `check`), TDD per
  `tdd.mode: standard`.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (Claude Code) | Trimmed speculation not grounded in the repo or the harnesses' documented behaviour; every claim in the evidence table re-derived from the checked-in specs. | this PR |
| 2 | human | @MadaraUchiha-314 | **Finding accepted and fixed** — the Cursor `stop` hook does exist; the "Cursor degrades to CI-only" framing was wrong. See the 2026-07-26 entry below. | [PR #110 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 3 | human | @MadaraUchiha-314 | **Direction accepted** — model the process as a graph of nodes with an orchestration layer determining edges; harness hooks are too fine-grained and phase-blind to be node boundaries. Architecture added; options re-cast as its layers. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 4 | human | @MadaraUchiha-314 | **Brainstorm locked** — *"let's go ahead with the requirements and design"*. Phase advanced; both artifacts derived. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 12 | human | @MadaraUchiha-314 | **Approved requirements + design; go ahead with implementation.** Also asked for a force/override escape hatch exercisable by the authorized CLI user — specified as R10 before deriving tasks. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 11 | human | @MadaraUchiha-314 | **Make it a breaking change** — remove the legacy per-feature keys rather than shadowing them; `/the-loop:upgrade-the-loop` performs the migration. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 10 | human | @MadaraUchiha-314 | **Runtime + config reconciliation** — specify what compiles and runs the graph (no engine; the existing `Command`/`@register` pattern), and apply the integration pattern across both config files, removing triplicated `ghBinary`. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 9 | human | @MadaraUchiha-314 | **Transport made configurable** — support SDK+API and CLI per integration so operators choose; the agent's own calls left unconstrained (CLI/MCP/API). Turns the `gh` migration into an addition rather than a rewrite. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 8 | human | @MadaraUchiha-314 | **All four open questions resolved** — sign-off explained (not delegated); approve-with-comments recorded as a `## Review comments` section in the artifact; `session: inherit` falls back to fresh; **CEL removed** (zero new dependencies). | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 7 | human | @MadaraUchiha-314 | **Simplification accepted, fresh slate** — collapse to nodes + entry/exit hooks with one `HookResult` contract; everything (validation, labels, Slack, Jira) is a hook; opinionated integrations; MCP question answered. Human gate recommended as a **node**. Specs and both decisions rewritten. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 6 | human | @MadaraUchiha-314 | **Direction accepted** — graph internal to the-loop (user-defined graphs a future feature); CEL expressions for conditional edges; LLM-decided approval gates; per-work-item tags/skips; YAML lifecycle hooks; tmux preserved for takeover. Specs rewritten; `decision-042` added. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 5 | self | the-loop (Claude Code) | Checked the derived artifacts against the phase gates: EARS throughout, Security considerations non-empty and specific, every requirements-phase trust boundary enforced in `design.md` § Security design, testing strategy mapping every requirement to a named Gherkin scenario. Risk tier raised 3 → 4 on the `**/*schema*` sensitive-path rule rather than left at the default. | this PR |

## Security review (gate)

- **Mechanism:** n/a for this phase — the change is a checked-in markdown artifact; no
  code, no dependency, no configuration, no execution path. The security question belongs
  to `requirements.md`'s **Security considerations** section, where the options that
  actually carry a trust boundary (a `Stop` hook that can block a turn; a CI gate that can
  block a merge; an orchestrator that invokes a harness) will be threat-modelled.
- **Outcome:** deferred to the requirements phase (recorded, not skipped).
- **Human sign-off:** n/a — risk tier below `security.review.humanSignOffMinTier`.

## Capability docs

None affected. This work item has produced no behaviour change yet; the capability docs
(`docs/capabilities/spec-workflow.md`, `cli.md`) are updated in the PR that implements
whatever the locked requirements ask for.

## Final validation evidence

Not applicable at Phase 0. The deliverable is the brainstorm artifact itself; its
acceptance is the owner locking it (`status: approved` + `approvedBy`).
