# Capability: process-graph

> the-loop's PDLC as an executable **graph**: nodes are the steps, hooks are the checks and
> side effects that run at their boundaries, and declared edges route on hook outcomes.
> Prose describes the process; the graph *is* the process.

## What it is

The runtime under `cli/the_loop/graph/` plus the shipped loop definitions
(`cli/the_loop/graph/pdlc-work-item-loop.yaml` and `pdlc-pr-loop.yaml`), surfaced as
`the-loop check` and `the-loop graph`.
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
  and a terminal `complete`. Same vocabulary, same hooks, same runtime; a third,
  `pdlc-project-management-loop`, is anticipated by the naming and not yet shipped.
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
  - Where the **outer** loop's artifacts are iterated with humans SHALL be the project's
    declaration, `workflow.outerLoop.surface` (`issue` \| `pull-request`, default
    `pull-request`); the artifacts SHALL be committed files linked from the ticket in
    either case. The **inner** loop SHALL have no such setting: a pull request's loop is
    iterated on that pull request. WHEN a session enters a node THEN its assignment SHALL
    name the surface it is working on, and a cross-repo claim command SHALL carry
    `--pr-repo`.
  - The daemon SHALL drive each inner loop from its PR's **own session** (the
    `pullRequests[]` endpoint, `routing.tmux.sessionPerPr`): the endpoint's spawn enters
    the loop at `implementation`, its events advance it, and the work item's outer loop
    is NEVER advanced by a PR's events — the outer loop hears about inner ones only
    through the state files `await-inner-loops` reads. WHEN the PR **merges** THEN its
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
`mcp-call`.

- `validate-artifacts` SHALL check front matter, required sections and the security
  boundary mapping (`enforces-boundaries-from`) — the design's Security design section
  must answer every abuse case the requirements raised.
- `classify-feedback` SHALL turn a human's free-text review into one of the decisive
  outcomes via a schema-constrained harness call, and SHALL only accept feedback from
  **authorized authors**; anything indecisive keeps the gate `wait`ing rather than
  guessing (negative test: an unauthorized author's "lgtm" does not advance the node).
- `record-feedback` SHALL append approve-with-comments feedback to the artifact's own
  `## Review comments` section, append-only and attributed. An approval never silently
  discards a reviewer's suggestions, and the feedback travels with the document it
  concerns instead of living in a side-channel tracker.

### Testing is planned and verified as nodes (issue-163)

- **`test-planning`** SHALL sit between `design` and `design-approval` and produce
  `testing-plan.md`, gating on the artifact being locked and carrying non-empty
  **Test matrix**, **Verification environment**, **Evidence plan** and **Verification
  results** sections. Placing it *before* the human gate means **one approval covers
  `design.md` and the plan derived from it** — the plan gets human review without a stop
  of its own, and is still locked before the `tasks.md` that references its rows.
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
  milliseconds, receives events while it waits, runs an internal iterate-until-locked
  loop, and produces artifacts — none of which a hook's request/response shape can carry.
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

### What drives the graph (issue-113, issue-148)

- The graph SHALL be driven by the **ingress**, not only by a human at a terminal: the
  shared dispatcher — which both the webhook receiver and the poller feed — SHALL enter a
  work item's start node when a session is spawned for it (**every spawn enters** —
  issue-148 closed the gap where tmux-hosted spawns never entered), and SHALL advance
  it at most one node boundary when an event is delivered to an existing session.
- **The session drives it too** (issue-148): `the-loop graph complete <id>` is the
  node-completion claim. WHEN a claim arrives THEN the runtime SHALL evaluate the
  current node's exit chain and advance only when it passes; the claim SHALL carry no
  verdict and no event text. Claims name their node: a replay of a claim for a node the
  pointer has left SHALL be a recorded no-op, a claim for a node that is neither current
  nor past SHALL be refused naming the current node, and a claim on an item that never
  entered the graph SHALL be refused. Output is one JSON envelope; a refusal or block is
  a result, not a CLI error. Claims are recorded in the state's `completions` ledger.
- **Graph state is resolved before anything is delivered** (issue-148): the dispatcher
  SHALL resolve a read-only context — current node, phase, status, parked/blocked
  reason, gate messages, the node's `command` — before rendering any prompt, and SHALL
  render it into the `$graph_context` placeholder. A spawn prompt for a mid-graph item
  SHALL say *resume at the current node*; entering the graph (`on_spawn`, the write)
  SHALL still happen only after a successful spawn. Reads before the spawn, writes
  after it.
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
  the work item has no spec directory, or when `control.requireStartCommand` holds and
  nobody has started the item. **No input can move a work item forward**; inputs can only
  cause a move not to happen.
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
  and spawned but whose graph never moves is a question `the-loop events` must be able to
  answer; at `logger.debug` it could not.
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

## Design

[`docs/specs/issue-109/design.md`](../specs/issue-109/design.md) ·
[`decision-041`](../decisions/decision-041.md) ·
[`decision-042`](../decisions/decision-042.md) ·
[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[architecture](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-183 | Multi-repo topology named (2026-08-09): the outer loop runs in the repository the ticket was created in and each contributing repository gets one PR and one inner loop, whose state is qualified by repository (`pr-loops/<owner>__<repo>/pr-<n>/`) with the origin repo's shipped path unchanged; repository names are validated at the path boundary, never sanitized; a qualified cross-repo closing reference now routes to its work item; `execution-log.md` front matter takes `repos:` and `await-inner-loops` holds `implementation` until each declared repository has a finished loop (blocking on a malformed entry); `workflow.outerLoop.surface` declares where the OUTER loop's artifacts are iterated (`issue` \| `pull-request`), with the inner loop deliberately not configurable; graph verbs and the API gained `--pr-repo`/`prRepo` | [spec](../specs/issue-183/), [decision-069](../decisions/decision-069.md), [spec-workflow](spec-workflow.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/183) |
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
