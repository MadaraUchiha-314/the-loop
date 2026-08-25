# Capability: process-graph

> the-loop's PDLC as an executable **graph**: nodes are the steps, hooks are the checks and
> side effects that run at their boundaries, and declared edges route on hook outcomes.
> Prose describes the process; the graph *is* the process.

## What it is

The runtime under `cli/the_loop/graph/` plus the shipped loop definitions
(`cli/the_loop/graph/pdlc-work-item-loop.yaml`, `pdlc-pr-loop.yaml`,
`pdlc-contribution-loop.yaml`, `pdlc-adhoc-loop.yaml` and `pdlc-review-loop.yaml`),
surfaced as `the-loop check` and `the-loop graph`.
It exists because before it, the PDLC was enforced only by prompts: there was no event
anywhere in the-loop meaning *"this node of the process completed"*, so there was nowhere
to hang a gate, a notification, or an advance (issue-109, [decision-041](../decisions/decision-041.md)).

There are exactly **two** runtime concepts and **one** contract between them.

## Current behaviour

### The graph

- The PDLC SHALL be declared as data — nodes and edges in
  `cli/the_loop/graph/pdlc-work-item-loop.yaml`, versioned and validated against its
  schema — and the runtime SHALL execute that declaration rather than re-deriving the
  process from prose.
- **The process is two loops** (issue-172, [decision-065](../decisions/decision-065.md)).
  The **outer** `pdlc-work-item-loop` walks a *work item* through the full PDLC, exactly
  as the single graph always did. The **inner** `pdlc-pr-loop` walks one *pull request*
  through the component-scoped subset that delivers it — starting at `implementation`
  (everything earlier is the work item's, decided once at the outer level), through
  verification and the same review chain, to the PR's own human gate (`pr-approval`)
  and a terminal `complete`. Same vocabulary, same hooks, same runtime; a
  `pdlc-project-management-loop` is anticipated by the naming and not yet shipped.
- **The third loop is the contribution loop** (issue-185,
  [decision-070](../decisions/decision-070.md)). `pdlc-contribution-loop` SHALL be
  walked instead of the outer loop when an authorized user arms a work item with the
  `contribute` control keyword — the-loop joining an **existing, in-progress** issue or
  PR as a contributor, with no assumption that any spec-chain artifact exists.
  - The loop SHALL NOT start until an authorized user's comment states a goal and at
    least one success criterion (`Goal:` + a `Success criteria:` bullet list); the
    `goal-definition` node is `required: true`, the parsed goal is frozen into
    `graph-state.json`'s decisions with provenance and confirmed in a comment, and
    unauthorized or self-authored text SHALL NOT be read at all.
  - Its planning nodes (`context-intake`, `scoped-plan`, `plan-approval`) SHALL author
    **one** artifact — `contribution.md` — in place of the four-file spec chain; its
    `verification` node SHALL block until every success-criterion checkbox is complete
    and `Verification results` is recorded (in the execution log when the plan was
    declared away). Every node but `goal-definition` and `phase-selection` is
    skippable (skip sets `plan` and `review-chain`).
  - A contribution has **no outer loop**, so it SHALL NOT be asked where to put one
    (issue-199). The `phase-selection` checklist SHALL omit the `outer-loop-on-pull-request`
    row for this loop, the token SHALL be ignored if a reply carries it anyway, the
    confirmation SHALL claim no surface, and the frozen record SHALL carry an **empty**
    surface — the fact "never asked", which is not the fact "the default was kept". The
    session's `$graph_context` SHALL likewise place its work on the work item without
    naming an outer loop.
  - Which loop a work item walks SHALL be recorded durably: `GraphState.loop`, written
    once at start from the compiled graph's name, resolved state-first (then the
    portable control record, then the default) by the daemon and every CLI verb. Only
    shipped loop names SHALL be honoured — an invented value in the agent-writable
    state file reads as the default, never as a graph choice.
  - The target repository need not have **adopted** the-loop (PR #187 review), and a
    contribution SHALL NOT adopt it (issue-193,
    [decision-073](../decisions/decision-073.md)): every other loop writes the built-in
    default into a repository that carries none, and this one deliberately does not —
    a guest does not install itself. WHEN it
    carries no `.the-loop/harness-config.yaml` THEN every harness-config read SHALL
    degrade to the built-in defaults (decision-044), the spec tree SHALL be kept out
    of the repository's history structurally (`Runtime.start` writes the spec root
    into the checkout's git exclude file — the contribution PR carries only the
    intervention), and the `publish-artifact` hook SHALL post `contribution.md`'s
    content to the thread at `plan-approval` and `human-approval` — the review surface
    such a repository offers. In an adopted repository the hook SHALL skip: the
    checked-in artifact is the surface, and no extra comment is posted.
- **The fourth loop is the ad-hoc loop** (issue-225,
  [decision-083](../decisions/decision-083.md)). `pdlc-adhoc-loop` SHALL be walked
  instead of the outer loop when an authorized user arms a work item with the `do`
  control keyword — a **tactical task that runs no PDLC process at all**. It is the
  answer to "does `contribute` fit an ad-hoc task?": it does not, because
  `pdlc-contribution-loop` is defined by the two `required: true` gates an ad-hoc task
  has no content for — a stated goal with success criteria, and a verification node that
  blocks until each is proved.
  - The loop SHALL declare exactly three walkable nodes — `work` (agent, phase
    `implementation`), `review` (human) and `complete` (phase `complete`) — plus the
    terminal `cleanup` and `escalated` nodes, with edges `work --pass--> review`,
    `review --more-work--> work` and `review --done--> complete`.
  - It SHALL declare **no** `produces` and **no** `validate-artifacts` entry (no spec
    chain, no `contribution.md`, no evidence tree), **no** `goal-definition` and **no**
    `phase-selection` node, and therefore **no** `skipSets` and no `skippable` or
    `required` node. The issue-177/179 invariant — every phase that does not run carries
    a named human's attribution — SHALL hold by construction rather than by gate: nothing
    is skipped because the loop declares nothing to skip, and arming with `the-loop do`
    IS that named, authorized, durably recorded declaration.
  - The `review` node SHALL classify the requester's reply through `classify-adhoc-reply`
    into exactly two outcomes. WHEN an authorized reply declares completion THEN the
    outcome SHALL be `done`; WHEN an authorized reply says anything else THEN it SHALL be
    `more-work` — the inverse of `classify-feedback`'s wait-until-decisive default, which
    is correct for a review gate and wrong for a conversational one. WHILE no authorized,
    non-self-authored reply exists the gate SHALL stay open. The **newest** authorized
    comment SHALL decide, so a done-word in the arming comment ("tell me when you're
    done") cannot end the item before any work has run. The hook SHALL reuse
    `feedback._authorized_comments`, so self-authored text is dropped before
    authorization is considered and an empty `authorizedUsers` reads nothing.
  - "Until the user closes the work item" SHALL need no new machinery: the existing
    close path (a closed issue, or a merged/closed PR) already ends the session
    (issue-94), and this loop inherits it.
  - It SHALL reuse the existing phase vocabulary (`implementation`, `complete`,
    `cleanup`), so adopting it changes no repository's `workflow.phases`.
  - Unlike a contribution, an ad-hoc item is **not a guest**: an unconfigured checkout
    SHALL be adopted exactly as the outer loop adopts it (issue-193). The harness config
    is what supplies the test and lint commands the ad-hoc session still runs.
  - Which non-default outer-path loop a recorded name selects SHALL be decided in exactly
    one place, `graph.model.resolve_outer_loop`, which returns `""` for the default, for
    the inner loop (addressed by pull-request number, never by name) and for anything
    invented — the fail-closed rule the state file's agent-writability demands, now
    localized instead of copied per reader.
- **The fifth loop is the review loop** (issue-279,
  [decision-101](../decisions/decision-101.md)). `pdlc-review-loop` SHALL be walked
  instead of the outer loop when an authorized user arms a thread with the `review`
  control keyword — the-loop as the **reviewer** of a change, never its author. Its
  product is judgement posted on the thread, so the session SHALL change no code: it
  commits nothing, pushes nothing and opens no pull request; a finding worth fixing is
  a new work item.
  - Typed on a pull request, the review SHALL bind to the **pull request's own ref** —
    control record, spawn and graph state alike — even when the PR links work items
    (the router's linked-first ordering is right for delivery and wrong for a review);
    on a plain issue the ordinary target stands.
  - The loop SHALL declare exactly four walkable nodes — `review-brief` (human,
    `required: true`), `review` (agent, phase `needs-review`, stage `critic-review`),
    `follow-up` (human) and `complete` — plus the terminal `cleanup` and `escalated`
    nodes, with edges `review-brief --briefed--> review --pass--> follow-up`,
    `follow-up --more-work--> review` and `follow-up --done--> complete`.
  - **No brief, no review.** The `review-brief` gate SHALL post a fill-in template
    (questions / angles / validations) idempotently — and not at all when the brief
    rode in on the arming comment — then freeze the newest authorized,
    non-self-authored brief into `graph-state.json`'s decisions with provenance and
    confirm it in a comment. Unauthorized or self-authored text SHALL NOT be read at
    all, and the gate SHALL re-read the whole thread because the arming comment is
    consumed by the control path.
  - Each `review` round SHALL answer every question, examine every angle and run every
    requested validation (or state why one could not run), posted as one self-marked
    comment. The `follow-up` gate SHALL reuse `classify-adhoc-reply` (decision-101):
    an authorized reply that declares completion is `done`, anything else is another
    round, silence keeps the gate open.
  - **A work item is reviewable too** (R8, PR #280): armed on a work item, the loop
    runs one review conversation across every pull request delivering it. The template
    SHALL additionally ask which pull requests the review spans, pre-filled with the
    ones the-loop detects — its own `pr-loops/` state first, then the provider's
    linked pull requests (`get-thread` / `linked-pulls` integration ops, best-effort)
    — and stated entries SHALL be normalized to composed refs, unparseable bullets
    dropped, the scope frozen with the brief. A brief with no pull requests reviews
    the work item itself; a pull-request list alone is not a brief.
  - It SHALL declare **no** `produces`, **no** `validate-artifacts`, **no**
    `phase-selection` and **no** skip vocabulary — arming with `the-loop review` IS
    the named, authorized, durably recorded declaration (the issue-177/179 invariant,
    held as the ad-hoc loop holds it) — and SHALL reuse the existing phase vocabulary
    (`needs-review`, `complete`, `cleanup`).
  - A review is a **guest** (`GUEST_LOOPS`, generalizing the contribution carve-out):
    it SHALL NOT adopt the repository it reviews in, and in an unadopted repository
    the spec tree (the graph-state cache) SHALL stay out of git via the existing
    `repoInitialized` seam.
- **Every work-item-level loop ends at a `cleanup` node** (issue-186). `pdlc-work-item-loop`,
  `pdlc-contribution-loop`, `pdlc-adhoc-loop` and `pdlc-review-loop` SHALL each declare a
  terminal `cleanup`
  node — phase
  `cleanup`, `actor: code`, entry chain `set-phase-label` + `log-entry` — that the-loop
  enters just **before** it releases the work item's local resources (its tmux sessions,
  its workspace checkout, its machine-local session record), so the teardown is a
  transition with a timestamp and a `loop:cleanup` label rather than a silent side
  effect. `pdlc-pr-loop` SHALL declare none: a pull request owns no checkout of its own.
  - It SHALL have **no inbound edge**, like `escalated`: it is not a node a work item
    walks into by satisfying a gate, so `complete` stays terminal (which
    `await-inner-loops` and the PR-merge path both read). Entering it from mid-walk — a
    work item closed unfinished — is legitimate and honest: the earlier nodes keep
    whatever they evaluated to, and `check --recompute` still reports every gate that
    never ran.
  - The move SHALL NOT be a `force`: no gate is bypassed and no verdict is claimed, so
    nothing is recorded as forced and no override announcement is posted. It is
    idempotent, and a no-op for a work item that never entered the graph.
  - It is the **one** graph action exempt from the start requirement, because a cleanup
    disarms the work item by the very command that asks for it — every other gate
    (the checkout-ownership proof, spec-directory containment) still applies.
  - The loops SHALL meet at exactly **one seam**: the outer `implementation` node's
    `await-inner-loops` exit hook. WHEN inner loops have been started under
    `docs/specs/<id>/pr-loops/` THEN the work item SHALL `wait` at `implementation`,
    naming the pending PRs, until every one of them reaches its `complete` node — "wait
    for tasks to be complete (inner loop start and finish)" — after which verification
    runs across all the PRs. WHEN none was ever started THEN the gate SHALL pass
    vacuously: a single-session work item behaves exactly as before issue-172.
  - Each inner loop's state SHALL live at
    `docs/specs/<id>/pr-loops/pr-<number>/graph-state.json` — beside the outer
    `graph-state.json`, checked in, a cache and never an authority. Artifacts SHALL
    resolve against the work item's **one** spec chain: a PR does not get a spec chain
    of its own. An unreadable inner state SHALL hold the outer gate (naming the PR),
    never release it.
- **The loops run in named places when the work spans repositories** (issue-183,
  [decision-069](../decisions/decision-069.md)). The **origin** repository is the one the
  ticket was created in (`ticketing.github`).
  - The outer loop SHALL walk in the origin repository, and the work item's one spec chain
    SHALL live there. WHEN a work item needs contributions in *n* repositories THEN *n*
    pull requests SHALL be raised — one per repository, each walking its own
    `pdlc-pr-loop` — and no implementation pull request SHALL be raised in the origin
    repository unless it is itself one of the *n*.
  - WHEN a pull request is in a repository other than the origin THEN its inner-loop state
    SHALL live at `docs/specs/<id>/pr-loops/<owner>__<repo>/pr-<n>/`, **in the origin
    repository's checkout**; WHILE it is in the origin repository the shipped
    `pr-loops/pr-<n>/` path SHALL be kept, so no work item in flight needs migrating.
  - IF a repository value reaching that layer is not `<owner>/<repo>` with each segment
    matching `[A-Za-z0-9._-]+` (never `.` or `..`) THEN the-loop SHALL raise rather than
    resolve a path from it — the value becomes a directory name and arrives from a payload
    or an operator's `--pr-repo`.
  - WHEN a pull request carries a closing reference qualified with another repository
    (`Closes <owner>/<repo>#<n>`, its URL form, or a `closingIssuesReferences` entry naming
    its repository) THEN routing SHALL map the event to the work item in **that**
    repository. This widens which work item an arrived event names — never which events
    arrive, nor which work items are armed.
  - WHEN `execution-log.md`'s front matter declares `repos: [<owner>/<repo>, …]` THEN
    `await-inner-loops` SHALL hold `implementation` until each declared repository has at
    least one inner loop **and** every started loop has reached `complete`; a declared
    repository with no loop SHALL be named in the wait. IF a declared entry is not a usable
    repository name THEN the gate SHALL **block** — waiting on it would wait forever. IF no
    repositories are declared THEN the gate SHALL behave exactly as it did before
    issue-183.
  - Where the **outer** loop's artifacts are iterated with humans SHALL be declared **per
    work item** at `phase-selection`, by the same authorized reply that freezes the phase
    selection: one extra checklist row (`outer-loop-on-pull-request`) whose resolved value
    is written to `graph-state.json` and to the portable record. IF it is unticked or
    absent THEN the surface SHALL be the **work item itself** — the default, because a
    work item only opens a pull request in the origin repository when its author asks for
    one. It SHALL NOT be a key in the harness config or the CLI config: one repository has
    both a one-repo bugfix and a three-repo migration (owner's call, PR #184). The
    artifacts SHALL be committed files linked from the ticket in either case, and the
    **inner** loop SHALL have no such choice: a pull request's loop is iterated on that
    pull request. WHEN a session enters a node THEN its assignment SHALL name the surface
    it is working on, and a cross-repo claim command SHALL carry `--pr-repo`.
  - The daemon SHALL drive each inner loop from its PR's **own session** (the
    `pullRequests[]` endpoint, `routing.tmux.sessionPerPr`): the endpoint's spawn enters
    the loop at `implementation`, its events advance it, and the work item's outer loop
    is NEVER advanced by a PR's events — the outer loop hears about inner ones only
    through the state files `await-inner-loops` reads. Which pull requests have a session to
    drive an inner loop from is the work item's own frozen `sessionPerPr` (issue-260),
    falling back to `routing.tmux.sessionPerPr` (issue-258): under
    `cross-repository` it is a pull request in **another** repository, so an inner loop is
    what a cross-repository contribution walks and a pull request in the work item's own
    repository has no second session — the work item walks its outer loop alone, the "one
    agent, one session" shape `await-inner-loops` already passes vacuously. `always`
    extends inner loops to same-repository pull requests that get a checkout of their own,
    and `never` collapses every one of them onto the outer loop. WHEN the PR **merges** THEN its
    loop SHALL be driven to `complete` as a **forced** transition (reason recorded; a
    force moves the pointer, never forges a verdict), because a merge is the PR's
    approval delivered as a state change. A PR closed WITHOUT merging SHALL keep its
    pointer where it was: abandoned is not finished, and the outer gate holding is the
    process noticing.
  - Every graph verb SHALL address either loop: `the-loop graph
    status|advance|complete|force|show --pr <n>` (and `pr` on the corresponding API
    bodies) selects the PR's inner loop; omitted, the work item's outer loop — the whole
    pre-issue-172 surface, unchanged. `--pr-repo <owner>/<repo>` (and `prRepo` on the API)
    qualifies `--pr` for a pull request outside the origin repository (issue-183); without
    `--pr` it SHALL be refused, because a repository does not identify a loop.
  - **The graph assigns, not just judges** (decision-065 D8). WHEN either loop enters a
    non-terminal agent node on the daemon path THEN the `deliver-assignment` entry hook
    SHALL push that node's assignment — where the item stands, what to produce, the
    exact claim command (`the-loop graph complete <id> [--pr <n>]`) — into the loop's
    bound session (`graph.assignment_delivered`), so the session is told its work
    rather than inferring it from the next GitHub event. The text is composed only from
    the-loop's own vocabulary — no payload reaches it. WHEN there is no delivery
    channel — a session's own `graph complete`, `the-loop check`, any CLI invocation —
    THEN the hook SHALL skip: the claim's JSON envelope already carries the same facts.
    A failed push SHALL be recorded (`graph.assignment_failed`) and SHALL never gate
    the node.
- The graph SHALL be **internal to the-loop**: it ships as package data inside the CLI —
  the thing that executes it, and where every hook it names is registered — and a consuming
  repository does not define or override it. A repo-local `.the-loop/graph.yaml` SHALL be
  ignored with a warning, so that user-authored graphs can be enabled later as a deliberate
  feature rather than arriving as an accidental one (R1.5).
- A **node** SHALL be one step of the process, with an ordered `entry` hook chain and an
  ordered `exit` hook chain. A node is **complete** when its exit chain all passes,
  **waiting** when a hook returns `wait`, and **blocked** when a hook returns `block`.
  No prose is parsed to decide this.
- A node MAY be declared `optional` (skipped when its artifact is absent — brainstorming)
  or `required` (never skippable, even by an optional-looking gate). Since issue-179 the
  outer loop declares `required` on exactly one node: `phase-selection`.
- A node MAY carry a one-line `description`, rendered beside its row on the
  phase-selection checklist. It is shipped-graph text — a repository cannot supply it —
  and it exists so a phase a reader has to guess at is not a phase they decline by default.

### Declared skips (issue-177, widened by issue-179)

The author of a work item — never the harness — decides which phases it walks
([decision-067](../decisions/decision-067.md)):

- A node MAY be declared `skippable: true` — the **fixed vocabulary** of what a human may
  skip. `required` and `skippable` on one node SHALL fail at compile time, as SHALL a
  skippable node without its own `on: skipped` edge: routing around a node is authored,
  never inferred.
- **In the outer loop that vocabulary is every node it walks** (issue-179,
  [decision-068](../decisions/decision-068.md)) — the spec chain, `test-planning`,
  `implementation`, `verification`, the review chain, `security-review` and
  `human-approval` — **except `phase-selection` and the terminals**. `phase-selection`
  SHALL remain `required: true` and unskippable: the loop can never walk past the act of
  choosing, which is what makes every omission attributable to a named human decided
  before any work starts. The floor is that one invariant, not a set of phases. The inner
  `pdlc-pr-loop` declares no skippable node and keeps `security-review` `required: true`.
- The graph MAY ship named `skipSets` (the outer loop ships `spec-chain` and
  `review-chain`); a member that is not a declared skippable node SHALL fail at compile
  time — a set cannot widen the vocabulary.
- **Only a human declares, at the loop's own first phase.** The outer loop SHALL start
  at `phase-selection`, a **human** node: its entry posts a checklist of the selectable
  phases on the ticket (idempotent — a second entry finds its own marker and does not
  re-post), and its exit SHALL wait until an **authorized** user (`authorizedUsers`, the
  boundary every other human gate uses) says the execute keyword
  (`routing.control.keywords.execute`, default `the-loop execute`).
  - The selection is **ticked in place** on the-loop's own comment; the authorized
    execute comment is what makes that tick state theirs. A checklist inside the execute
    comment itself SHALL win over the boxes. A selection with nothing unticked SHALL run
    the full process.
  - Unticked skippable phases become declared skips; a phase the reply never mentions is
    kept; an unticked **protected** phase SHALL be refused and named in the confirmation.
  - `execute` is a `routing.control` command like `start`, and carries the same
    named-actor authorization — but it touches no session, and the comment carrying it is
    still delivered, because the gate is what reads the selection.
  - **How many tmux+claude sessions this work item's pull requests get SHALL be chosen
    here too** (issue-260), on the same checklist and by the same signed reply: three rows
    — `pr-sessions-never`, `pr-sessions-cross-repository`, `pr-sessions-always` — with the
    deployment's `routing.tmux.sessionPerPr` rendered **pre-ticked**. Exactly one ticked
    row SHALL be the choice; none ticked, several ticked, an unreadable checklist and a
    token outside those three SHALL all resolve to that configured default. The resolved
    mode SHALL be written to `graph-state.json` and to the portable record
    (`graph.sessionPerPr`), named in the confirmation, and read by the daemon **per work
    item** in preference to the config key — which is therefore a default and not a
    verdict, for the same reason the surface is not a config key at all. The rows SHALL be
    offered by every loop that reaches this gate, the contribution loop included: unlike
    the surface, the question has a true answer there. A row SHALL never be read as a
    phase, whichever way it is ticked.
- **The selection freezes the graph.** WHEN the gate is answered THEN the resolved graph —
  every node with whether it is walked, and whether it was selectable — SHALL be recorded
  in `graph-state.json` and pushed to the work item's **portable session record**
  (`frozenGraph`, `graph.frozen`), so what the loop will walk is a recorded fact rather
  than a comment anyone can keep editing, readable without a checkout. A failed publish
  SHALL be recorded (`graph.frozen_publish_failed`) and SHALL NOT gate the selection —
  the checked-in state file is the authoritative copy.
- An operator MAY declare the same from a shell via `the-loop graph skip <id> --node
  <token> --reason <why>` — `force`'s sibling: reason required, audit comment posted,
  recorded as `graph.skips_declared` — and a token naming a node the pointer has already
  reached SHALL be refused: a skip is a plan, not an amnesty.
- A declaration SHALL never apply to a node already entered, whichever channel it came
  from, and SHALL be filtered through the compiled graph's `skippable` vocabulary on
  every read — so no hook can declare a skip the graph does not permit.
- **A skip routes and records; it never forges.** WHEN the pointer would enter a
  declared-skipped node THEN it SHALL take that node's `skipped` edge, run **none** of
  its hooks (no phase label, no assignment), record outcome `skipped`
  (`graph.node_skipped`), and land on the first non-skipped node. `the-loop check` —
  `--recompute` included — SHALL report the node as *skipped by declaration* with its
  provenance, never as `pass`. A declaration on a non-skippable node (a hand-edited
  state file) SHALL be inert everywhere and surfaced on the node it tried to touch.
- WHEN a later gate reads an artifact whose authoring node was declared-skipped and the
  artifact is **absent** THEN that slot SHALL be treated as a planned absence
  (`implementation`'s `tasks.md` re-gate after `tasks-breakdown` was skipped); an
  artifact that **exists** SHALL be gated normally regardless of declarations.
- **A kept gate SHALL keep a subject** (issue-179). A hook entry MAY declare
  `onlyWhenSkipped: <artifact>`, and SHALL then apply only while every named artifact is a
  *planned absence* — authoring node declared-skipped **and** absent on disk — reporting
  `skipped` with a reason otherwise. It reads only the runtime's filtered
  `skipped_artifacts`, so it SHALL only ever narrow a gate's applicability and can never
  widen what may be skipped. The shipped use is `verification`: with `test-planning`
  declared away and no `testing-plan.md`, it gates the shared `execution-log.md` for a
  non-empty **Verification results** section instead, and blocks until it is written —
  skipping the plan removes the document, never the verifying.

### Opt-in phases (issue-188)

The other default, at the same gate and by the same person
([decision-071](../decisions/decision-071.md)):

- A node MAY be declared `optIn: true` — **off unless an authorized human selects it**.
  It SHALL imply `skippable` (same vocabulary, same required `on: skipped` edge, same
  routing and reporting), and `required` × `optIn` SHALL fail at compile time. A
  `skipSets` member that is opt-in SHALL fail at compile time too: a set declares phases
  *away*, and an opt-in phase is already away.
- The phase-selection checklist SHALL render opt-in nodes **unticked**, in a section of
  their own that states they do not run unless ticked, with each node's `description`.
  Ticking one SHALL select it; leaving it unticked, or never naming it in the reply, SHALL
  leave it unselected. Every unreadable-input path SHALL resolve to *not selected* — the
  fail-closed direction for a phase that adds a review rather than gating one.
- A selection SHALL be recorded in `graph-state.json` as `optIns[<node>] = {via, token,
  by, at}` (`graph.opt_ins_selected`), filtered through the compiled graph on every read
  exactly as `skips` is, and never applied to a node the pointer already entered. The
  frozen graph SHALL carry `optIn` per node so the portable record distinguishes a phase
  nobody asked for from a phase somebody removed. The confirmation comment SHALL name the
  selected opt-in phases, or state that the offered ones were not selected.
- WHEN an opt-in node is not selected THEN the runtime SHALL route around it on its
  `skipped` edge, running none of its hooks, and `the-loop check` — `--recompute`
  included — SHALL report it as **not selected**, distinct from *skipped by declaration*
  (which names a human) and never as `pass`. A work item whose state predates the node
  SHALL therefore skip it rather than block on it.
- The shipped opt-in phase is **`design-critic-review`** (outer loop only), between
  `design` and `test-planning`: a different model reading the completed `design.md`
  against the requirements before the testing plan and task DAG derive from it (it is
  locked later, at `design-approval` — issue-281), gating the execution log's
  `Design critic review` section. See [review-loop](review-loop.md).
- An **edge** SHALL route on a hook **outcome** only (`on: pass`, `on: changes-requested`,
  …). There is no expression language: the LLM produces facts, declared edges route on
  them. That split is what makes judgement and determinism coexist.

### What a node `produces`

- A `produces` entry SHALL name an **artifact**, not a filename. It MAY accept several
  names separated by `|` — `produces: ["requirements.md|bugfix.md"]` — because one artifact
  can legitimately go by more than one name: a bug's phase-1 spec is called `bugfix.md`
  ([decision-045](../decisions/decision-045.md)).
- **Exactly one** accepted name may be present. None SHALL block with a message naming
  *every* accepted name, so an agent knows what it is allowed to write; more than one
  SHALL block as **ambiguous**, because two artifacts filling one slot have no defined
  source of truth and a gate that quietly picks one can approve the stale one.
- An artifact found under an alternative name SHALL be held to the **identical** standard —
  `locked`, `frontMatter`, `sections`, `checkmarks`. The name is what is flexible; the bar
  is not.
- An entry with an empty alternative (`a||b`, `|a`, `a|`) SHALL fail at **graph-compile
  time**, naming the node and the entry — every structural failure is a startup failure.
- The entry SHALL be reported verbatim by `the-loop graph show`, unsplit, so the output
  states what the graph declares rather than claiming two artifacts where it means one.
- `enforces-boundaries-from`'s `upstream` SHALL resolve the same way; when several accepted
  names are present their bodies are joined rather than one being chosen, so a boundary
  raised in either still has to be answered downstream.
- The names the graph gates, the names `.the-loop/manifest.yaml` tracks and the templates
  under `skills/the-loop/templates/` SHALL agree, enforced in both directions by
  `cli/tests/test_graph_parity.py` — including that a bundled template offers every section
  the node it is authored for requires.

### What a node `validates` (issue-167)

`produces` means *this node authored it*. A node that gates an artifact it did **not**
author — the six review-chain nodes each own one section of the shared
`execution-log.md` — declares it on the hook entry instead
([decision-063](../decisions/decision-063.md)):

```yaml
exit:
  - {hook: validate-artifacts, with: {validates: execution-log.md, sections: ["Security review (gate)"]}}
```

- `validates` SHALL be a **hook parameter**, not a node field: it describes one assertion,
  not the node's ownership, and only `validate-artifacts` reads it.
- It SHALL resolve through the **same** resolver as `produces`, so alternation, the
  absent-artifact block and the two-files-one-slot ambiguity block are identical for both
  and cannot drift apart. Every declared check (`locked`, `frontMatter`, `sections`,
  `checkmarks`) applies to a validated artifact exactly as to a produced one.
- A validated artifact that is **absent** SHALL block, naming the file. It is never a skip:
  the node asserted the file would be there.
- **A gate with nothing to read SHALL fail closed.** When a `validate-artifacts` entry
  declares any content check and resolves *no* artifact — neither `produces` nor
  `validates` — it SHALL `block`, and the block SHALL be **not retriable**: re-running a
  node cannot repair the graph that declared it, and a retriable block would burn
  `maxAttempts` before anyone was told.
- A node MAY gate **several** sections of the same artifact. `capability-docs` gates two
  (issue-174, [decision-066](../decisions/decision-066.md)): `## Capability docs` — the
  organized view of specs, for a reader who already uses the project — and
  `## Documentation` — the user-facing surface (`README.md`, the docs site, the
  operating-model skill), for a reader who does not yet. They stay separate rows because
  folding them together would lose which of the two was skipped, and they share a node
  because a second node would cost an edge, a `stage` key and a place in both loops' entry
  chains to read a file this one already opens. The node keeps its id and `stage`:
  `stage: capability-docs` is a public key in operators' `tokenEconomy.modelRouting.stages`
  and `thinkingEffort.stages` maps, so a rename would drop their configuration silently.
  The **inner** loop gates neither — a work item's documentation is decided once, at the
  outer level.
- `cli/tests/test_graph_parity.py`'s **P5** SHALL enforce all three questions against the
  shipped graph: every content gate resolves a target (P5a), every validated name is
  tracked by the manifest (P5b), and every section it demands exists in that artifact's
  bundled template (P5c).
- What this proves SHALL be stated rather than implied: the section check is **structural**,
  so a heading holding placeholder text passes it. The gate proves the *record exists*; the
  reviewer judges whether the review was any good.

Before this, those six nodes declared `sections:` and no artifact at all — so their
`validate-artifacts` resolved nothing, returned *skipped*, and (a skip not being a
decision) the chain passed straight through every one of them, `security-review`
included, however empty the log was.

### The hook contract

- Every hook SHALL have one signature — `(HookContext) -> HookResult` — where
  `HookResult` carries `status` (`pass|block|wait|skip`), the hook's name, ordered
  `messages`, free-form `data`, and `retriable`.
- Hooks SHALL be discovered through a name registry (`@hook("validate-artifacts")`),
  mirroring the CLI's existing `Command`/`@register` pattern, so the shipped graph refers
  to hooks by name and never by import path.
- A chain SHALL **short-circuit** on the first result that is neither `pass` nor `skip`.
  Aggregation is therefore the *hook's* job: a validating hook reports every finding in
  one result rather than failing on the first and hiding the rest — a gate that reveals
  problems one at a time is a gate people learn to route around.
- **A `skip` SHALL NOT be a decision** (issue-163): a hook that declines to run has said
  nothing about the node, so the chain continues past it and, if nothing objects, the
  node passes on the outcome `pass`. Short-circuiting on `skip` hid the hooks behind a
  skipping one and routed a chain ending in a skip on the outcome `"skip"`, for which no
  edge is declared — which is why `implementation` (whose chain ends in a `verify-tests`
  that is a no-op unless a command is bound) parked at `no_edge` instead of advancing.
- A hook that raises SHALL become a `block` with `retriable=False`, never a silent pass.
- Hook results SHALL carry secret **handles**, never secret values (R2.7).

### Shipped hooks

`validate-artifacts` · `lint-artifacts` · `verify-tests` · `set-phase-label` ·
`log-entry` · `request-review` · `notify` · `classify-feedback` · `record-feedback` ·
`lock-artifacts` · `mcp-call`.

- `validate-artifacts` SHALL check front matter, required sections and the security
  boundary mapping (`enforces-boundaries-from`) — the design's Security design section
  must answer every abuse case the requirements raised.
- `classify-feedback` SHALL turn a human's free-text review into one of the decisive
  outcomes via a schema-constrained harness call, and SHALL only accept feedback from
  **authorized authors**; anything indecisive keeps the gate `wait`ing rather than
  guessing (negative test: an unauthorized author's "lgtm" does not advance the node).
- `lock-artifacts` SHALL be the **only** thing that locks a gated artifact
  ([issue-281](https://github.com/MadaraUchiha-314/the-loop/issues/281)): on an approval
  outcome from the `classify-feedback` result of the **same chain run** it SHALL write
  `status: approved` and merge the approving authors into `approvedBy` — as a
  front-matter **splice** that preserves every other line and comment — and SHALL verify
  the write landed, blocking (fail closed) when it cannot. On any other outcome it SHALL
  skip, leaving the artifact untouched; an absent artifact is a planned absence, and an
  ambiguous slot blocks. It SHALL never declare an `outcome`, so the classifier alone
  routes the edge. Producing nodes SHALL NOT demand `locked:` — one gate, one human
  approval, and a node with no gate (`brainstorming`, `tasks-breakdown`) needs no human
  sign-off at all.
- `record-feedback` SHALL append approve-with-comments feedback to the artifact's own
  `## Review comments` section, append-only and attributed. An approval never silently
  discards a reviewer's suggestions, and the feedback travels with the document it
  concerns instead of living in a side-channel tracker. The block it writes SHALL pass the
  project's configured markdown linter — the attribution is `**@handle** wrote:`, emphasis
  plus trailing text, because emphasis alone on a line is what MD036 rejects, and a comment
  with **no** body becomes a single `**@handle** left no comment text.` line rather than a
  run of blank ones. The reviewer's body SHALL NOT be rewritten to that end: it is recorded
  verbatim, so a body that fails lint on its own merits is a human's edit to make, never
  the recorder's ([decision-089](../decisions/decision-089.md)).

### A repository's own hooks (issue-248)

> [decision-096](../decisions/decision-096.md) · [adding a hook](../cli/hooks.md)

- A repository SHALL be able to bring **hooks of its own** and attach them to boundaries the
  shipped graph already declares, by declaring `graph.hooks` in its
  [harness config](../config/harness-config.md): `modules[]` (a `path` to a `.py` file inside
  the repository, or an installed `module` dotted name) and `attach[]`
  (`hook`, `node`, optional `boundary` and `with`).
- A repository hook SHALL use the **same contract** as a shipped one —
  `(HookContext) -> HookResult`, the same `@hook` decorator, the same block-on-raise
  behaviour. There is one hook API, not two.
- Every repository hook SHALL be named `x-<something>`, and no shipped hook SHALL take such a
  name. The prefix says whose code is about to run and makes shadowing a shipped hook
  impossible.
- An attachment SHALL be **appended** to the node's chain. There SHALL be no way to remove,
  reorder or replace a shipped hook, so a shipped gate always runs — and short-circuits —
  first: a repository hook can add a constraint and never relax one.
- A repository hook SHALL NOT route. An `outcome` in its `data` SHALL be dropped and the drop
  logged, so it can neither classify a human gate nor select an edge; its influence on
  movement is its `status` alone.
- Repository hooks SHALL be resolved from a **per-repository table on the compiled graph**,
  never the process-global registry: a daemon walking two repositories that both define
  `x-house-rules` SHALL run each repository's own.
- A declaration that cannot be honoured SHALL **fail the graph load**, naming it — a missing,
  unreadable, raising or empty module, a name outside `x-`, a duplicate, an unknown node or
  boundary, or a `path` that escapes the repository (absolute, `..`, or a symlink out).
  Nothing SHALL degrade to "no hooks": a gate the repository asked for either runs or is
  loudly absent. (A repository *graph* file is still merely ignored — the-loop never promised
  to honour that one.)
- The modules run **inside the-loop's own process**, so `the-loop graph hooks` SHALL report
  what a repository declares **without importing any of it**, and
  `routing.graph.repoHooks: false` SHALL refuse the mechanism machine-wide, naming any
  repository whose hooks were refused.
- A module SHALL be imported once per process. The **graph itself stays the-loop's**: nodes,
  edges and loops are not repository-authorable, which is the half of issue-109's deferred
  item this does not deliver.

### Testing is planned and verified as nodes (issue-163)

- **`test-planning`** SHALL sit between `design` and `design-approval` and produce
  `testing-plan.md`, gating on the artifact carrying non-empty **Test matrix**,
  **Verification environment**, **Evidence plan** and **Verification results** sections
  (never on it being locked — issue-281). Placing it *before* the human gate means **one
  approval covers `design.md` and the plan derived from it** — the plan gets human
  review without a stop of its own, and `design-approval`'s `lock-artifacts` locks both
  before the `tasks.md` that references its rows.
  `design-approval` SHALL record feedback into **both** artifacts, because a reviewer's
  note about the test matrix belongs in the plan rather than filed under the design, and
  `changes-requested` SHALL return to `design`, which re-derives the plan. The results heading is gated at *planning* time deliberately:
  `validate-artifacts` treats an empty required section as a finding, so the heading is
  authored up front holding "not yet executed" and the verification node fills a section
  rather than inventing one.
- **`verification`** SHALL sit between `implementation` and `self-review` and re-declare
  the **same** artifact, gating on `checkmarks: complete` plus a non-empty **Verification
  results** section — the produce-then-re-gate shape `implementation` already uses for
  `tasks.md`. Re-declaring `produces` is what makes the gate run at all: a node that
  declares no artifacts gets a *skipped* `validate-artifacts`, which is a gate reporting
  success without running. WHEN `test-planning` was declared skipped and no plan exists
  THEN the same reasoning applies one level up (issue-179): the artifact gate takes its
  planned-absence branch, so `verification` SHALL gate the execution log's **Verification
  results** section instead (`onlyWhenSkipped:`), and SHALL still block until the results
  are written.
- Both nodes SHALL carry their own `phase`, so a work item's ticket label says
  `loop:test-planning` / `loop:verification` rather than hiding the state inside a
  neighbouring phase.
- The plan's content rules — which testing types are candidates, `n/a` **with a reason**,
  the declared-not-managed verification environment, committed and redacted evidence —
  live in [`reference/testing.md`](../../skills/the-loop/reference/testing.md) and the
  bundled template, not in the graph. The graph gates the *shape*; the reviewer judges the
  content.

### The human gate

- A human review/approval step SHALL be a **node**, not a hook. It lasts days rather than
  milliseconds, receives events while it waits, runs an internal iterate-until-approved
  loop, and locks the artifacts it approves — none of which a hook's request/response
  shape can carry alone.
- A gate node SHALL default to `session: inherit`: it reuses the harness session of the
  node that produced the artifact, so the reviewer's questions land in the context that
  wrote the thing. WHEN that session is gone THEN the gate SHALL fall back to a fresh
  session seeded with the checked-in artifacts — which is exactly the property
  [decision-027](decision-027.md) already relies on.

### Two call planes

- **Control plane** — the-loop's *own* calls to external services (labels, comments,
  notifications) SHALL go through declared integrations whose **transport is
  configurable** (`integrations.<provider>.transport: auto|api|cli|sdk`), so an operator
  picks what suits their environment rather than inheriting the-loop's taste.
- **Work plane** — calls the *agent* makes while doing the work SHALL be unconstrained:
  CLI, MCP or API, whatever the task needs. Constraining the work plane would be
  constraining the engineer.
- Integrations SHALL declare their capabilities and SHALL fail closed at load time when a
  configured transport cannot serve a required operation, rather than at the moment a
  gate needs it.
- WHEN a service is reachable only over MCP THEN the-loop SHALL reach it **by delegation
  to the harness** (`mcp-call`), because MCP is an agent protocol, not a daemon protocol
  ([decision-042](../decisions/decision-042.md)).

### Which ticket a control-plane call reaches (issue-194)

Every control-plane call needs a **work-item ref** (`github:OWNER/REPO#N`), and a graph
verb is not required to be given one. The ref SHALL be resolved in three tiers, and
nothing outside them SHALL be invented:

1. An explicit `--ref` (or `ref=` argument) SHALL always win.
2. Otherwise the ref SHALL be **derived** from `ticketing.github` in the repository's
   harness config plus the work-item id: `issue-<n>` in a repository declaring
   `<owner>/<repo>` yields `github:<owner>/<repo>#<n>`. This is the inverse of the
   ingress's own ref → id translation, and the two SHALL agree.
3. Otherwise the bare work-item id SHALL be used, exactly as before derivation existed.

- WHEN the work-item id is not `issue-<n>`, OR the config declares no owner/repo pair, OR
  either name is not a shape GitHub accepts, THEN the-loop SHALL derive **nothing**. A ref
  pointing at the wrong repository is worse than no ref, so "no ref" is the fail-closed
  direction.
- Before this, an omitted `--ref` reached the integrations as the bare id, where every
  operation raised `malformed work item ref` — so a work item parked at
  `phase-selection` with the checklist never posted, the phase label never set, and a
  clean `wait` on stdout.

### Degraded side effects are reported, never swallowed

Outbound hooks are **best-effort**: a GitHub outage records and continues rather than
wedging the graph (R6.12). That is unchanged. What changed is that the record now has a
reader.

- WHEN a hook returns `pass` carrying a non-empty `error`, THEN the runtime SHALL append
  one message naming the hook and the error to the `NodeReport` that `advance`, `start`
  and `cleanup` return, and SHALL emit a `warning`-level `graph.hook_degraded` event —
  the CLI surface for a human at a terminal, the event log for the daemon's operator.
- The node's status, its outcome, the edge taken and the pointer SHALL be exactly what
  they would have been. Surfacing a degradation SHALL NOT turn a passing chain into a
  blocked or parked one.
- A hook that declines to act SHALL NOT be reported: `post-phase-selection` finding its
  own marker returns `posted=False` with a *reason* and no error, and that is idempotency,
  not a failure.
- WHEN `graph force` or `graph skip` cannot post its audit comment, THEN the verb SHALL
  take effect and the failure SHALL appear in its result's `warnings`, which the CLI
  prints.

### What drives the graph (issue-113, issue-148)

- The graph SHALL be driven by the **ingress**, not only by a human at a terminal: the
  shared dispatcher — which both the webhook receiver and the poller feed — SHALL enter a
  work item's start node when a session is spawned for it (**every spawn enters** —
  issue-148 closed the gap where tmux-hosted spawns never entered), and SHALL advance
  it at most one node boundary when an event is delivered to an existing session.
  WHEN the start node a spawn enters is a **human** node THEN its exit chain SHALL be
  evaluated once, with the spawning event's comments attached (issue-199): the comment
  that spawns a session is often the one that answers the gate it lands on — the arming
  `the-loop contribute` carries the goal — and the control path consumes it rather than
  forwarding it, so no later event can deliver it. A contribution that states its goal up
  front SHALL therefore reach `phase-selection` without a second command. An **agent**
  start node SHALL NOT be evaluated at spawn (its chain reads artifacts the session has
  not been given a chance to write), and a **respawn** SHALL evaluate nothing: only an
  entry that actually moved the pointer.
- **The session drives it too** (issue-148): `the-loop graph complete <id>` is the
  node-completion claim. WHEN a claim arrives THEN the runtime SHALL evaluate the
  current node's exit chain and advance only when it passes; the claim SHALL carry no
  verdict and no event text. Claims name their node: a replay of a claim for a node the
  pointer has left SHALL be a recorded no-op, a claim for a node that is neither current
  nor past SHALL be refused naming the current node, and a claim on an item that never
  entered the graph SHALL be refused. Output is one JSON envelope; a refusal or block is
  a result, not a CLI error. Claims are recorded in the state's `completions` ledger.
- **A state-changing verb adopts an unconfigured repository; a read never does**
  (issue-193, [decision-073](../decisions/decision-073.md)). WHEN `graph complete`,
  `graph advance`, `graph force` or `graph skip` runs in a repository carrying no harness
  config THEN the-loop SHALL write its built-in default there before building the runtime,
  so the verb and the daemon read one configuration instead of two sets of defaults. WHEN
  `check`, `graph status` or `graph show` runs THEN nothing SHALL be written — the check
  operation is pure by contract, and asking a question must not dirty a CI checkout. A
  contribution adopts nothing, whichever verb is used.
- **Graph state is resolved before anything is delivered** (issue-148): the dispatcher
  SHALL resolve a read-only context — current node, phase, status, parked/blocked
  reason, gate messages, the node's `command` — before rendering any prompt, and SHALL
  render it into the `$graph_context` placeholder. A spawn prompt for a mid-graph item
  SHALL say *resume at the current node*; entering the graph (`on_spawn`, the write)
  SHALL still happen only after a successful spawn. Reads before the spawn, writes
  after it.
- **A work item that has not been placed yet SHALL still get a block** (issue-273). Because
  the read precedes the write, a fresh work item has no pointer at the one moment the
  auto-execute prompt is written — and an empty block is what let a spawned session walk
  straight into `requirements-definition`. The context SHALL then name the graph's `start`
  node with status `pending`, and the rendered block SHALL say the node has **not been
  entered**, that the session must not begin a phase, write an artifact, set a label or
  open a pull request, that the loop delivers the node's assignment when it enters it,
  and — when that node is a human node — that it is a gate for an authorized person and
  not the session's to answer or claim. It SHALL also tell the session to **say so on the
  work item** if no assignment arrives: an *event* prompt can carry a pending context too
  (a session predating the coupling, or one whose entry faulted), and there no assignment
  is coming, so the block must turn that into an escalation rather than a silent wait.
  A `pending` context is deliberately **not** a waiting human gate: nothing has been
  entered, so no event is handed to a gate on its account, and the consult-first ordering
  above is unchanged. Where there is no graph to read at all the block SHALL stay empty, so
  a deployment with `routing.graph.enabled: false` renders exactly what it did before.
- **A waiting human gate sees its input first** (issue-148): WHEN an event arrives for
  an item parked at a human-actor node THEN the dispatcher SHALL run `advance` (with
  the event's comments) **before** delivering, and the delivered prompt SHALL carry the
  gate's verdict; the graph SHALL NOT be advanced a second time for the same event.
  There are **no consume-only routes**: every event is still delivered — a gate speaks
  first, never instead. WHEN the gate cannot classify (unauthorized author, indecisive
  text, fault) THEN the event SHALL still be delivered with the gate still waiting.
- **Advancement fails closed; delivery fails open** (issue-148). No input — comment
  text, completion claim, payload — moves the pointer except through an exit chain over
  checked-in artifacts or `classify-feedback` on an authorized author's text. Any
  consultation fault delivers with the context unknown and records `graph.link_failed`.
- Graph state has **two writers** (the daemon's link and the session's claim), so the
  load→mutate→save window SHALL run under an advisory lock (`graph-state.lock`,
  stdlib `fcntl`, no-op where unavailable); a busy lock reports `busy` rather than
  blocking, and a lost update on the no-op fallback costs a re-evaluation, never a
  wrong pointer.
- WHEN a human gate is entered THEN the runtime SHALL resolve its session per
  `session: inherit` — the binding `on_spawn` records (session id, runner — always
  `"tmux"` since issue-156 — alive),
  flipped dead on close, re-recorded on respawn — and SHALL record the resolution as
  `graph.gate_session` (`inherited` or `fresh-with-artifacts`). The registry remains
  the dispatch authority.
- Entering the start node SHALL run its **entry chain**, which is what writes the
  `loop:<phase>` label and the execution-log checkpoint. Before this, no node was ever
  entered on the automated path, so those side effects never fired and the phase labels
  stayed unpopulated.
- An inbound event's comments SHALL be passed to the exit chain as `HookContext.event`,
  so a human-approval node's `classify-feedback` classifies the reply that just arrived.
  The link SHALL always pass a comment's **author** alongside its body and SHALL NOT
  filter by `authorizedUsers` itself — that decision belongs to `classify-feedback`
  alone, so there is exactly one place where it can be got wrong.
- The coupling SHALL be **best-effort and non-blocking**: any failure is logged as
  `graph.link_failed` and the event is still delivered. A hook that raises, hangs on a
  subprocess or fails an outbound call SHALL never cost a session spawn or a forwarded
  comment.
- The coupling SHALL skip — leaving the graph exactly where it is — when it is disabled
  (`routing.graph.enabled: false`), when the ref has no known spec-id convention, when
  the checkout is not the work item's own repository, or when
  `control.requireStartCommand` holds and nobody has started the item. **No input can
  move a work item forward**; inputs can only cause a move not to happen.
- **Starting a graph SHALL NOT require a spec directory** (issue-273). `<specDir>/<id>/`
  is created by the work the graph exists to gate, so requiring it before the graph may
  start is a chicken-and-egg for every work item that begins life as a plain ticket —
  and the node it holds back is `phase-selection`, the outer loop's one `required: true`
  node, whose entire job is to run before any spec exists. The `start` and `context`
  actions SHALL therefore proceed without it: `start` writes `graph-state.json` (creating
  the directory as it goes) and `context` is a pure read. `advance` and `clean` SHALL keep
  the requirement — neither can be the first thing that happens to a work item, so for
  them a missing directory still means the graph was never placed here, and keeping it
  there is what preserves the rule above.
- **Where the specs are is the work item's own repository's to declare** (issue-123,
  [decision-044](../decisions/decision-044.md)). On the ingress path the coupling SHALL
  resolve the spec directory from the checkout's `workflow.specDir` (default
  `docs/specs`), with `routing.graph.specDir` left as a deliberate override for a checkout
  that carries no harness config — not, as before, as a machine-scoped default that
  silently governed every watched repository. It SHALL resolve that directory **once** and
  use the same value for the skip decision and for the runtime it builds, so the directory
  gated on and the directory `graph-state.json` is written into cannot drift apart.
- That read SHALL happen only **after** `_checkout_belongs_to` has proved via the `origin`
  remote that the directory is the work item's own repository, and a declared value that
  is absolute or resolves outside the checkout SHALL be refused — a value read from a
  repository must not select a write target elsewhere on the operator's machine.
- A skip for want of a spec directory SHALL be recorded as `graph.skipped` in the event
  log (`work_item`, `action`, `reason`, `spec_dir`). A work item that is labelled, armed
  and delivered to but whose graph never moves is a question `the-loop events` must be
  able to answer; at `logger.debug` it could not. Since issue-273 the `action` on such a
  record can only be `advance` or `clean`.
- A chain's routing outcome SHALL come from the last hook that declared one explicitly,
  whether or not that hook blocked. A gate that classifies a review returns `pass`
  *carrying* its verdict, so reading the outcome only from a blocking result discarded it
  and parked every human-approval node with `no_edge`.

### State, recovery and the escape hatch

- Graph state SHALL be a **cache, not an authority**. `the-loop check --recompute`
  SHALL ignore stored state and derive each node's verdict from the checked-in artifacts
  alone, which is what makes the CI gate meaningful and drift discoverable.
- `the-loop graph force --to <node> --reason <why>` SHALL move a work item past its gates,
  exercisable by the authorized user running the-loop's CLI. It SHALL require a reason,
  SHALL record the override in four places (graph state, execution log, event log, and a
  marked ticket comment), and SHALL warn about every gate it bypassed.
- **A force moves the pointer. It never forges a verdict.** A bypassed gate keeps its real
  result, so `the-loop check --recompute` still reports it unmet after the force. An
  escape hatch that could rewrite history would be a way to launder an unmet gate into a
  met one.
- Every transition, every non-`pass` hook and every edge taken SHALL be recorded in the
  structured event log (`graph.*` event types; see [observability](observability.md)).
- **A gate that evaluated nothing SHALL NOT pass** (issue-238). Since the control-plane
  API answers a `repo` that does not resolve with a position-unknown report rather than an
  error — a checkout somebody cleaned up is expected state on that machine, see
  [control-plane](control-plane.md) — such a report carries no nodes, and therefore no
  *blocking* node. `the-loop check` SHALL fail it in **both** `--fail-on` modes, ahead of
  either rule, and SHALL say `UNREAD — <path> is not a directory` rather than render it as
  a work item with no phases. Otherwise a mistyped `--repo` would take `--fail-on block`,
  the automated-gate mode, straight to exit 0.

## Design

[`docs/specs/issue-109/design.md`](../specs/issue-109/design.md) ·
[`decision-041`](../decisions/decision-041.md) ·
[`decision-042`](../decisions/decision-042.md) ·
[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[architecture](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-281 | The gate became the locker (2026-08-25): `validate-artifacts` stopped demanding `locked: true` on any producing node — brainstorming, requirements-definition, design, test-planning, tasks-breakdown, and the contribution loop's scoped-plan gate shape only — and a new `lock-artifacts` hook on the approval nodes' exit chains (after `classify-feedback` and `record-feedback`) writes `status: approved` and merges the approving authors into `approvedBy` as a comment-preserving front-matter splice, verified after the write and failing closed. It consumes the classifier's verdict from the same chain run (never re-reading comments), skips on `changes-requested` or an absent artifact, and declares no outcome, so the classifier alone routes. This ends the double-ask the stacked layers produced: one human approval per gate, and no approval at all for nodes the graph gives no gate | [spec](../specs/issue-281/), [spec-workflow](spec-workflow.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/281) |
| issue-279 | A fifth shipped loop, `pdlc-review-loop` (2026-08-24): the-loop as a pull request's **reviewer**, never its author. Armed by a ninth control keyword (`the-loop review`) that — alone among the keywords — binds to the pull request itself rather than its linked ticket; gated by a `required: true` brief gate (`review-brief` posts a fill-in template, freezes an authorized reviewer's questions/angles/validations with provenance); each agent round answers the frozen brief in one self-marked comment; the `follow-up` gate reuses `classify-adhoc-reply`, so any authorized reply that is not "done" is another round. No `produces`, no `phase-selection`, no code changed by contract, and no adoption — the contribution loop's guest carve-out generalized to `GUEST_LOOPS` | [spec](../specs/issue-279/), [decision-101](../decisions/decision-101.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/279) |
| issue-273 | `phase-selection` stopped being routed around by default (2026-08-20): the ingress→graph coupling gated **every** graph action on `<specDir>/<id>/` already existing, so a work item minted as a plain ticket — no `/create-ticket`, no committed spec folder — had its graph declined at spawn (`graph.skipped`, `no-spec-dir`, twice) and its session walked into `requirements-definition` with the outer loop's one `required: true` node never having run: no checklist, no `the-loop execute`, no frozen graph, and nothing for `the-loop check` to attribute. `start` and `context` are now exempt (the directory is created by the work the gate holds back; `advance` and `clean` keep the check), and the read-before-spawn context of an unplaced work item renders its start node as `pending` — a block that names the gate and forbids beginning a phase before the node's assignment arrives, instead of the empty block that let the session start on its own | [spec](../specs/issue-273/), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/273) |
| issue-247 | The one hook that writes markdown into a checked-in artifact stopped writing markdown the project's own linter rejects (2026-08-16): `record-feedback`'s attribution gained trailing text (`**@handle** wrote:`), because emphasis alone on a line is precisely MD036's target — so every approval-with-comments had been leaving `design.md` and `testing-plan.md` failing `make lint`, and a session hand-editing the paper trail to unblock itself. A comment with an empty body now becomes one attribution line instead of a blank-line run (MD012). The reviewer's body stays verbatim, which is the other half of the rule: the harness fixes its own markdown and never a human's words, so a body that fails lint on its own merits is out of scope by decision rather than by omission | [spec](../specs/issue-247/), [decision-089](../decisions/decision-089.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/247) |
| issue-238 | A gate that read nothing stopped counting as a gate that passed: when `graph/check` began answering a non-resolving `repo` with a position-unknown report instead of raising, that report had no nodes and so no blocking node, and `the-loop check --fail-on block` — the automated-gate mode — would have exited 0 on a mistyped `--repo`. Both modes now refuse it ahead of either rule, and the row renders `UNREAD — <path> is not a directory` instead of `UNMET (at )` with nothing under it. Found by self-review of the control-plane fix, not by the fix's own tests | [spec](../specs/issue-238/), [control-plane](control-plane.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/238) |
| issue-260 | How many sessions a work item's pull requests get moved from the operator to the work item (2026-08-17): issue-258 gave the choice to `routing.tmux.sessionPerPr`, machine-wide — the same mistake issue-183 refused to make for `outer-loop-on-pull-request`, because one repository has both a one-repo bugfix and a three-repo migration and one daemon serves both. `phase-selection` now carries three rows (`pr-sessions-never` / `pr-sessions-cross-repository` / `pr-sessions-always`) with the deployment's configured value pre-ticked; exactly one ticked row is the choice, and none, several, an unreadable checklist or a token outside the vocabulary all resolve to that default. The resolved mode is frozen by the same signed `the-loop execute` into `graph-state.json` and the portable record (`graph.sessionPerPr`), and routing reads it there per work item ahead of the config key. Nothing else moved: the three modes mean what decision-092 said, decision-088 D2's tree requirement is untouched, the schema is unchanged, and a work item with no frozen mode routes exactly as before | [spec](../specs/issue-260/), [decision-093](../decisions/decision-093.md), [routing](../config/cli/routing-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/260) |
| issue-225 | The ad-hoc loop (2026-08-14): a fourth shipped graph, `pdlc-adhoc-loop`, walked when a requester wants a tactical task done and no PDLC process run — armed by the new `do` control keyword (`routing.control.keywords.do`), driven by `/the-loop:do-task`. Three walkable nodes (`work` -> `review` -> `complete`, with `review` routing back to `work` on `more-work`) and deliberately no `goal-definition`, no `phase-selection`, no `produces`/`validate-artifacts`, no `skipSets` and no review chain — the issue-177/179 attribution invariant holding by construction, because nothing is skipped when the loop declares nothing to skip. A new `classify-adhoc-reply` hook inverts the review gate's default (any authorized reply that is not a declaration of completion is more work; the newest comment decides; self-authored and unauthorized text is never read), and `graph.model.resolve_outer_loop` becomes the single fail-closed decision point the three copied "contribution or default" comparisons used to be | [spec](../specs/issue-225/), [decision-083](../decisions/decision-083.md), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/225) |
| issue-199 | A contribution is not asked where its outer loop goes, and does not wait for a second command (2026-08-10): `pdlc-contribution-loop` joins somebody else's in-progress work item and owns no outer loop, so `phase-selection` omits the `outer-loop-on-pull-request` row for it, ignores the token if a reply carries it, confirms no surface, and freezes an **empty** one — *never asked*, not *default kept* — with the session prompt placing the work on the thread instead of naming an outer loop; and a spawn now evaluates a **human** start node once with the spawning event attached, so the goal that rode in with `the-loop contribute` moves the item to `phase-selection` on its own (agent start nodes and respawns evaluate nothing) | [spec](../specs/issue-199/), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/199) |
| issue-194 | Outbound hooks stopped being dead and silent (2026-08-10): a graph verb with no `--ref` had been handing the bare work-item id to the integrations, where every operation raised `malformed work item ref` — so nothing was posted, no label was set, and the command printed a clean answer. The ref is now **derived** from `ticketing.github` plus the `issue-<n>` id (a new `graph/refs.py`, the inverse of the ingress's `spec_id_for`, refusing anything that does not validate rather than guessing), and a best-effort hook that records an `error` while passing is reported as a warning line on the `NodeReport` plus a `graph.hook_degraded` event — without changing any node's verdict or edge. `graph force`/`graph skip` report a failed audit comment in their `warnings`; `_split_ref`'s error names both remedies; `sideeffects.py` resolves its integration at call time, so the seam every test patches finally applies to it | [spec](../specs/issue-194/), [cli](cli.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/194) |
| issue-193 | An unconfigured repository is adopted, and a guest still is not (2026-08-10): the four state-changing graph verbs (`complete`, `advance`, `force`, `skip`) write the-loop's built-in default harness config into a repository carrying none, before the runtime is built — so `repoInitialized` is true on the very run that adopted it — while `check`/`status`/`show` write nothing, and `pdlc-contribution-loop` adopts nothing at all, keeping issue-185's spec-tree exclusion and thread publishing pointed at the repositories they were written for | [spec](../specs/issue-193/), [decision-073](../decisions/decision-073.md), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/193) |
| issue-188 | Opt-in phases, and the design critic round (2026-08-10): a second node marker, `optIn: true` — the mirror of `skippable`, implying it (same vocabulary, same `on: skipped` edge, same provenance) but **off unless an authorized human ticks it** at `phase-selection`; `required`×`optIn` and an opt-in `skipSets` member refused at compile time; a node `description` rendered beside its checklist row; selections recorded as `optIns` in `graph-state.json` (`graph.opt_ins_selected`), filtered through the compiled graph on every read, carried into the frozen graph per node, and named in the confirmation comment; an unselected opt-in node routed around and reported by `check` as *not selected* — never as a declaration, never as a pass — which also leaves every pre-issue-188 work item unblocked; the outer loop ships one such phase, `design-critic-review`, between `design` and `test-planning` | [spec](../specs/issue-188/), [decision-071](../decisions/decision-071.md), [review-loop](review-loop.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/188) |
| issue-186 | A terminal `cleanup` node in both work-item-level loops (2026-08-10): the-loop enters it — via `Runtime.cleanup`, a sibling of `start` rather than a `force` — immediately before releasing a work item's local resources, so the teardown carries a `loop:cleanup` label and an execution-log checkpoint. No inbound edge (`complete` stays terminal), none in `pdlc-pr-loop`, and the one graph action exempt from the start requirement | [spec](../specs/issue-186/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/186) |
| issue-185 | The contribution loop (2026-08-09): a third shipped graph, `pdlc-contribution-loop`, walked when the-loop is invited into an existing, in-progress work item as a contributor — armed by the new `contribute` control keyword (a spawn-arming sibling of `start`, `routing.control.keywords.contribute`); a required `goal-definition` gate (`post-goal-request`/`classify-goal` hooks) that refuses to start until an authorized human states a goal and success criteria, frozen into graph state with provenance; one lightweight `contribution.md` artifact (bundled template) in place of the four-file spec chain; verification gating on every criterion checkbox being met; `GraphState.loop` recording which loop a state walks, resolved state-first everywhere with non-shipped names failing closed to the default | [spec](../specs/issue-185/), [decision-070](../decisions/decision-070.md), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/185) |
| issue-183 | Multi-repo topology named (2026-08-09): the outer loop runs in the repository the ticket was created in and each contributing repository gets one PR and one inner loop, whose state is qualified by repository (`pr-loops/<owner>__<repo>/pr-<n>/`) with the origin repo's shipped path unchanged; repository names are validated at the path boundary, never sanitized; a qualified cross-repo closing reference now routes to its work item; `execution-log.md` front matter takes `repos:` and `await-inner-loops` holds `implementation` until each declared repository has a finished loop (blocking on a malformed entry); the surface the OUTER loop is collaborated on became a **per-work-item** choice at `phase-selection` (one extra checklist row, frozen by the same signed reply; default: the work item itself), deliberately not a config key anywhere, with the inner loop not configurable at all; graph verbs and the API gained `--pr-repo`/`prRepo` | [spec](../specs/issue-183/), [decision-069](../decisions/decision-069.md), [spec-workflow](spec-workflow.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/183) |
| issue-179 | Every phase is selectable (2026-08-08): the outer loop's skip vocabulary widened from the spec chain to **every node it walks** except `phase-selection` (which keeps `required: true` and is now the whole floor — the loop cannot walk past the act of choosing) and the terminals; `security-review` and `human-approval` traded their `required` markers to become declarable; ten new `on: skipped` edges and a second shipped set, `review-chain`, beside a `spec-chain` that now includes `test-planning`; `validate-artifacts` gained `onlyWhenSkipped:` so a *kept* gate keeps a subject — `verification` gates the execution log's `Verification results` when the plan was declared away, and blocks until it is written; the `phase-selection` checklist says what an empty protected list means | [spec](../specs/issue-179/), [decision-068](../decisions/decision-068.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/179) |
| issue-177 | Declared skips (2026-08-08): `skippable: true` fixes the vocabulary in the shipped graph (spec-chain nodes only; compile-refused on `required` nodes, on missing `skipped` edges, and on `skipSets` members outside it); the outer loop gained a first human node `phase-selection` where the-loop posts a phase checklist, the user ticks it in place, and an authorized `the-loop execute` (a `routing.control` command) freezes the selection — the resolved graph landing in both `graph-state.json` and the portable session record (the audited `graph skip` verb is the same declaration from a shell); the runtime routes around declared nodes without running their hooks and `check` reports them as *skipped by declaration* with provenance — never a pass; a forged declaration on a protected node is inert and surfaced; later gates treat a skipped author's absent artifact as planned; `deliver-assignment` announces a human gate instead of telling the session to claim it | [spec](../specs/issue-177/), [decision-067](../decisions/decision-067.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/177) |
| issue-174 | `capability-docs` gates two sections of the execution log instead of one — `## Documentation` joins `## Capability docs`, so a work item cannot complete having left the README or the docs site describing the process it replaced. No new node, no hook or runtime change; the inner loop gates neither | [spec](../specs/issue-174/), [decision-066](../decisions/decision-066.md), [documentation](documentation.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/174) |
| issue-172 | The process became two named loops (2026-08-07): `pdlc.yaml` renamed to `pdlc-work-item-loop.yaml` (unchanged content, plus the `await-inner-loops` gate on `implementation`), and `pdlc-pr-loop.yaml` added — one inner loop per PR, run in that PR's own session with state under `docs/specs/<id>/pr-loops/pr-<n>/`, merge driving it to `complete` as an audited force. Graph verbs gained `--pr`; P5 parity asserts over both loops; `deliver-assignment` makes the graph the initiator — entering an agent node pushes its assignment into the bound session | [spec](../specs/issue-172/), [decision-065](../decisions/decision-065.md), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/172) |
| issue-167 | Six gates stopped reporting success without running: `validate-artifacts` gained `validates:` for an artifact a node asserts against but did not author, so the six review-chain nodes gate their sections of the shared `execution-log.md`; a content gate that resolves no artifact now blocks (not retriable) instead of skipping; the bundled execution-log template gained the `Capability docs` section `capability-docs` had always demanded; P5 asserts all three against the shipped graph | [spec](../specs/issue-167/), [decision-063](../decisions/decision-063.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/167) |
| issue-163 | Testing became two nodes: `test-planning` produces `testing-plan.md` before the task DAG that references it, `verification` re-gates the same artifact after implementation and before the review chain; a `skip` stopped short-circuiting a chain, which is what had left `implementation` parking at `no_edge` | [spec](../specs/issue-163/), [decision-060](../decisions/decision-060.md), [testing-and-contracts](testing-and-contracts.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/163) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): every spawn is tmux-hosted, so "every spawn enters the graph" no longer needs a per-runner qualifier, and the gate-session binding's `runner` is always `"tmux"` | [spec](../specs/issue-156/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-148 | The graph went from observer to authority: `the-loop graph complete` (the node-completion claim — idempotent, node-named, never a verdict), `GraphContext` resolved read-only before every delivery and spawn, the `$graph_context` prompt block, consult-first ordering at human gates (no consume-only routes), `resolve_session` gained its caller (`graph.gate_session`), tmux spawns finally enter the graph, two-writer state locking, and P4 phase parity — `pdlc.yaml` defines the sequence, the prose renders it | [spec](../specs/issue-148/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/148) |
| issue-124 | `produces` names an artifact rather than a filename: `\|`-separated alternatives, one resolver shared by every hook that reads them, ambiguity fails closed, malformed entries fail at compile; `enforces-boundaries-from` resolves `upstream` the same way, which turned a security gate that had been silently skipping for every bug work item into one that runs; graph ↔ manifest ↔ template parity is now a test | [spec](../specs/issue-124/), [decision-045](../decisions/decision-045.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/124) |
| issue-123 | The daemon stopped taking `specDir` from the operator's machine: `routing.graph.specDir` defaults to unset, so the work item's own `workflow.specDir` wins; the gate and the runtime resolve one value; the checkout's ownership is proved before its config is read; an escaping value is refused; and the skip is recorded as `graph.skipped` instead of a debug line | [spec](../specs/issue-123/), [decision-044](../decisions/decision-044.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/123) |
| issue-113 | Wired the ingress to the graph: `Runtime.start()`, the `GraphLink` seam in the shared dispatcher, `HookContext.event` finally written, the `routing.graph` config block, and the chain-outcome fix that lets a passing gate's verdict reach its edges | [spec](../specs/issue-113/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/113) |
| issue-109 | Established the capability: the two-concept graph (node + hook), the `HookResult` contract, the shipped PDLC graph, ten hooks, configurable integration transports, `the-loop check`/`graph`, and the forced-transition escape hatch | [spec](../specs/issue-109/), [decision-041](../decisions/decision-041.md), [decision-042](../decisions/decision-042.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/109) |
