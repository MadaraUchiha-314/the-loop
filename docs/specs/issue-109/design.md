---
type: design
phase: design
workItem: issue-109
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Design: the-loop as a graph of nodes with entry/exit hooks

> Phase 2 of 3. Derives from [`requirements.md`](requirements.md).
>
> **Rewritten from a fresh slate** on the owner's direction (PR #110): *"I want to simplify
> the concepts here… a graph with entry and exit hooks, and then each of these validations
> that we want are hooks that are chained together… delete any bias that might have crept in
> till now."* Anchored on that comment and on the original bullets in
> [issue #109](https://github.com/MadaraUchiha-314/the-loop/issues/109).
>
> **Sequencing note.** the-loop derives a downstream artifact only from a *locked* upstream
> one; the owner directed requirements and design in one pass, so both are reviewed together.

## Overview

**There are exactly two runtime concepts, and one contract.**

| Concept | What it is |
|---|---|
| **Node** | A step of the PDLC. A place the work item *is*. Has `entry` hooks and `exit` hooks. |
| **Hook** | A unit of work with a fixed signature, chained in order at a node boundary. |
| **HookResult** | The contract every hook returns. It is what decides whether the work item moves. |

Everything else is an instance of those. Validating that an artifact exists is a hook.
Linting an artifact is a hook. Updating a GitHub label is a hook. Posting a review request,
messaging Slack, updating Jira — hooks. There is no separate "action vocabulary", no
"lifecycle event system", no "gate subsystem". One shape, used everywhere.

This directly answers the ticket's sharpest question — *how does the CLI know a step is
complete, versus waiting for the user?*

> **A node is complete when its exit hooks all pass. It is waiting when one returns `wait`.
> It is blocked when one returns `block`.** No prose is parsed, ever.

## The two-concept model

```mermaid
flowchart LR
    subgraph N["Node"]
        EH["entry hooks<br/>(in order)"] --> W["the work<br/>(harness session, or a human)"] --> XH["exit hooks<br/>(in order)"]
    end
    XH -->|"all pass"| NEXT["next node"]
    XH -->|"block + feedback"| W
    XH -->|"wait"| PARK["stay in this node,<br/>re-run exit hooks on the next event"]
```

- **Entry hooks** prepare the node: set the phase label, open the execution-log entry, post
  the "review please" comment, select the model tier, notify.
- **The work** is either a harness session (agent nodes) or a human (gate nodes).
- **Exit hooks** decide whether the node is done: artifacts exist, front-matter is locked,
  markdown lints, diagrams render, review rounds happened, the human approved.

## The hook contract

The owner asked for the signature and the output to be defined. This is the load-bearing
piece of the whole design.

```python
def hook(ctx: HookContext) -> HookResult: ...
```

### `HookContext` (input — everything a hook may see, nothing more)

| Field | Meaning |
|---|---|
| `work_item` | ref, id, tags, risk tier, spec directory |
| `node` | id, phase, actor, the node's own config block |
| `boundary` | `entry` or `exit` |
| `repo` | absolute path to the checkout |
| `artifacts` | resolved paths of the node's declared inputs/outputs |
| `session` | the harness session bound to this node (id, runner, cwd) — may be `None` |
| `event` | the event that triggered this evaluation (a comment, a CI result, a tick) |
| `results` | the `HookResult`s of hooks already run in this chain |
| `config` | harness config + resolved secrets handles (never raw secrets) |

### `HookResult` (output — the contract)

```python
@dataclass
class HookResult:
    status: Literal["pass", "block", "wait", "skip"]
    hook: str                      # which hook produced this
    messages: list[Message]        # human/agent-readable findings, in priority order
    data: dict                     # structured output other hooks and edges may read
    retriable: bool = True         # may the harness try again, or is this terminal?
```

| `status` | Meaning | Effect on the chain |
|---|---|---|
| `pass` | this hook is satisfied | continue to the next hook |
| `block` | a requirement is unmet | **stop the chain**; the node does not advance; `messages` go back to the harness as its next input |
| `wait` | nothing is wrong, but we cannot proceed yet (a human has not replied) | park the node; re-run the exit chain on the next inbound event |
| `skip` | this hook does not apply to this work item | continue, recorded |

**Chain semantics.** Hooks run in declared order and the first non-`pass` short-circuits.
Aggregation of many findings is the *hook's* job, not the chain's: `validate-artifacts`
returns every unmet requirement in one `HookResult` so the agent gets the complete list in a
single round rather than discovering them one at a time. This is why `messages` is a list.

**Feedback to the harness.** A `block` is not just a stop — its `messages` are rendered into
the agent's next input, so the loop is *do → check → repair → check*. The rendering is
the-loop's own text plus paths and hook names; never untrusted payload text.

```mermaid
sequenceDiagram
    participant RT as the-loop runtime
    participant H as harness session
    participant HK as exit hook chain
    RT->>H: run the node
    H-->>RT: turn ends (exit code, or stop-hook tick)
    RT->>HK: run exit hooks in order
    HK-->>RT: block — "design.md has no Security design section"
    RT->>H: feedback as the next input
    H-->>RT: turn ends
    RT->>HK: run exit hooks again
    HK-->>RT: pass
    RT->>RT: take the edge, enter the next node
```

## Is the human gate a node or a hook?

The owner asked directly. **It is a node.** Five reasons, in the order that convinced me:

1. **Duration.** A hook is a function that runs and returns; a human gate is a state you
   *sit in*, for days. Expressing that as a hook means inventing a suspend-and-resume
   return — which is a node, with extra steps.
2. **It receives events.** Comments, reviews and CI results arrive *while in* the gate. A
   node is a delivery target; hooks fire at boundaries and are gone.
3. **It has an internal loop.** Approve-with-comments, changes-requested, partial reviews
   arriving over hours. That is a state machine, and nodes are what the-loop uses for those.
4. **It produces artifacts** — the review thread, the recorded decision, the execution-log
   review row. Nodes produce; hooks check.
5. **Symmetry.** Every other step of the PDLC is a node, and `needs-review` is already a
   declared phase. A gate-as-hook would be the one special case.

**But the owner's instinct about session binding is exactly right, and it becomes one field
rather than a new concept.** The feedback at a gate is about the artifacts the *previous*
node produced, so the gate node declares:

```yaml
- id: design-approval
  actor: human
  session: inherit        # reuse the producing node's harness session
```

`session: inherit` means the gate does not start a fresh conversation — it reuses the
session that produced the artifacts, so when the reviewer says *"this section is thin"*, the
agent that wrote it still has the context to fix it. That is the whole reason the binding
matters, and it costs one enum value.

### The human gate node, in detail

```mermaid
stateDiagram-v2
    [*] --> waiting: entry hooks<br/>(comment asking for review, label, notify)
    waiting --> waiting: feedback arrives but is not decisive<br/>(partial review, a question, unclear)
    waiting --> approved: classified approved
    waiting --> approved_with_comments: classified approved, with follow-ups
    waiting --> changes_requested: classified changes requested
    approved --> [*]: advance
    approved_with_comments --> [*]: advance;<br/>comments recorded in the artifact
    changes_requested --> [*]: return to the producing node,<br/>feedback becomes its next input
```

Four behaviours the owner called out, and how each is served:

- **Iterative feedback in parts.** The gate stays in `waiting` and re-runs its exit chain on
  *every* inbound event. It only transitions when the classification is decisive; an
  ambiguous or partial comment returns `wait`, not a guess.
- **Approved with comments — the comments land *in the artifact*.** Owner decision:
  *"approval and comments can be a section in the final artifact that's generated… a comments
  section at the bottom of each doc like design, requirements, etc."* So a
  `record-feedback` exit hook appends the review to a **`## Review comments`** section of the
  artifact the gate approved, and the work item advances. This is a better answer than the
  mandatory-vs-advisory framing the question offered: the feedback becomes part of the
  durable, checked-in record rather than a side-channel to-do list, it travels with the
  document it is about, and it is reviewable in the PR diff like everything else. Nothing is
  silently swallowed, and nothing needs a separate follow-up mechanism to track.
- **Rejected/changes-requested with comments.** Returns to the producing node with the
  comments as that node's next input — which works precisely because of `session: inherit`.
- **Tied to the previous node's session.** As above.

The recorded section is append-only and attributed:

```markdown
## Review comments

### 2026-07-28 — @reviewer — approved with comments
- The Security design section should name the fail-closed behaviour explicitly.
- Consider splitting the error-handling table by severity.
```

`validate-artifacts` treats this section as a required part of any artifact that has passed
through a gate, so a lost review is a blocking finding rather than a silent omission.

**Classifying the reply.** "Did they approve?" is judgement over English, so one exit hook
(`classify-feedback`) asks the harness with a schema-constrained prompt and returns the
outcome in `data`. Two rules keep this from becoming a hole:

- Only text from an **authorized** author is read at all.
- The classification is a *fact*, not a destination — edges route on it, and every
  destination is declared in the graph.

## Edges

Routing is deliberately boring, because the hooks did the work:

```yaml
edges:
  - {from: design, to: design-approval, on: pass}
  - {from: design-approval, to: tasks, on: approved}
  - {from: design-approval, to: tasks, on: approved-with-comments}
  - {from: design-approval, to: design, on: changes-requested}
  - {from: implementation, to: reviewer-briefing, on: docs-only}   # from a named hook
```

**Every edge routes on a hook outcome. There is no expression language** (owner decision:
*"Remove CEL"*). A condition that would have needed an expression becomes a **named hook**
that returns the outcome — `is-docs-only` inspects the work item and returns
`docs-only` or `pass`. That keeps one mechanism instead of two, drops the dependency
entirely, and makes every condition unit-testable like any other hook.

Two earlier drafts sat on this: the first put an expression on *every* edge, the second kept
one for a "compound minority". Both were a second language for something the hook contract
already expresses. The named-hook form is strictly simpler and strictly more testable.

## Default hooks the-loop ships

All three the owner named, plus the validators the PDLC needs. Each is an ordinary hook
implementing the same signature.

| Hook | Boundary | Purpose |
|---|---|---|
| `set-phase-label` | entry | GitHub/Jira label for the current phase |
| `request-review` | entry (gate nodes) | post the review/approval comment, marked as the-loop's own |
| `notify` | entry / on wait | Slack (and any configured channel) for the roles in `notifications.events` |
| `log-entry` | entry, exit | append the execution-log checkpoint |
| `validate-artifacts` | exit | the node's declared outputs exist, are locked, carry required sections — **all findings in one result** |
| `lint-artifacts` | exit | markdownlint, and `diagramsRender` (mermaid actually parses) |
| `verify-tests` | exit | the node's declared test command passed |
| `classify-feedback` | exit (gate nodes) | schema-constrained classification of an authorized human's reply |
| `record-feedback` | exit (gate nodes) | append the review to the artifact's `## Review comments` section |
| `record-decision` | exit (gate nodes) | persist the outcome and its inputs to graph state |

`lint-artifacts` earns `diagramsRender` from an incident in this very PR: a reviewer caught
a diagram that would not render, and checking the whole repository then found **three more
already merged** (`issue-21`, `issue-32`, `issue-86` designs). `diagramFormat: mermaid` is
written as a RULE and enforced by nothing. A rule with no hook drifts — which is this work
item's thesis, demonstrated on a rule nobody thought to check.

## Tool access: two call planes, and a configurable transport

### The boundary first

Owner direction on PR #110: *"Anything that the LLM uses can be through CLI, MCP or API as
LLM is free to do whatever it wants."* That draws a line worth making explicit, because the
two sides have opposite requirements:

| | **Control plane** — the-loop's own calls | **Work plane** — the agent's calls |
|---|---|---|
| Who calls | hook implementations in the CLI | the harness, inside a session |
| Examples | sync a label, post the review request, notify Slack, record feedback | anything the agent decides it needs to read or do |
| Requirement | deterministic, auditable, credentialed, testable | *unconstrained* |
| Transport | **configurable** (below) | CLI, MCP, API — whatever the harness has |

**the-loop does not police the work plane.** The agent's MCP servers, its `gh`, its network
access are the operator's business and the harness's concern. Constraining them would buy
nothing (the agent is already trusted to write code) and would break the takeover property
the tmux runner exists for. Everything below is about the **control plane only**.

### Transport is configurable per integration

Owner direction: *"How to interface with external services should be configurable. We should
support SDK+API and CLI, so people can choose based on what the-loop implements for these
platforms."* This replaces the earlier draft's single opinionated answer per target, and it
is better for a reason worth stating: **the-loop already has a working CLI transport.**
`announce.py`, `comments.py`, `control.py`, `reactions.py` and `poller/github.py` all shell
out to `gh` today, and `ghBinary` is already a configured value in three places. Making
transport a choice turns a risky big-bang migration into **keeping what works as one
provider and adding another beside it**.

```yaml
# cli-config.yaml — the daemon makes these calls, so they live with the daemon's
# config (decision-032), not the per-repo harness config.
integrations:
  github:
    transport: auto                 # auto | api | cli
    api:
      tokenEnv: [GH_TOKEN, GITHUB_TOKEN]
      baseUrl: https://api.github.com     # or an enterprise host
    cli:
      binary: gh                    # the existing setting, unchanged
  slack:
    transport: sdk                  # sdk | webhook
    urlEnv: THE_LOOP_SLACK_WEBHOOK_URL
  jira:
    transport: api                  # api | cli
    api: {baseUrl: "", tokenEnv: THE_LOOP_JIRA_TOKEN}
    cli: {binary: jira}
```

**`auto` resolves in a stated order** and never guesses silently: use `api` when a token is
present; else `cli` when the binary is on `PATH`; else fail closed, naming *both* fixes
("set `GH_TOKEN`, or install `gh`"). An explicit `api`/`cli` is honoured verbatim and fails
rather than falling back — a configured choice that silently degrades is worse than an error.

### What each transport is worth

| Target | `api` | `cli` | `sdk` |
|---|---|---|---|
| **GitHub** | stdlib HTTP, no dependency, works in a bare container, needs a token | inherits the operator's `gh auth` (incl. enterprise/SSO), needs `gh` installed — **what the-loop does today** | none exists officially; `githubkit` is the pick if ever wanted |
| **Slack** | raw webhook POST, no dependency | not meaningful — Slack's CLI is for app development, not posting | **`slack-sdk`**, official, **zero required dependencies**, brings retry/backoff/proxy/SSL |
| **Jira** | REST + API token | community CLIs exist; supported for parity | none official |

So the earlier recommendations survive as **defaults**, not as the only option: GitHub
defaults to `auto` (which prefers `api`), Slack defaults to `sdk`, Jira to `api`.

### The part that needs discipline: capabilities

Transports are not equally capable, and pretending otherwise is how this design would rot.
Every provider **declares the operations it implements**, and the runtime checks that
declaration **at load time** against the operations the configured graph's hooks actually
need:

```python
class Integration(Protocol):
    operations: frozenset[str]                     # what this provider can do
    def call(self, op: str, **params) -> dict: ...
```

- A graph needing `add-reaction` with a transport that lacks it **fails at startup**, naming
  the operation, the target and the two ways to fix it — not mid-run, three nodes deep.
- One **shared contract test suite** runs against every provider for every operation, so
  `api` and `cli` are verified to behave identically rather than assumed to.
- The `HookResult` a hook returns is transport-independent by construction, so swapping
  transports cannot change whether a node advances — only how the side effect was performed.

This is the real cost of the flexibility and it should be named: N transports × M operations
is a matrix, and the contract suite is what keeps it honest.

### Reconciling the configs behind one integration pattern

The `integrations:` shape is worth applying backwards, because the duplication it removes
already exists. `ghBinary: gh` is declared **three separate times** in `cli-config.yaml`
(under `control`, `reactions` and `announce`) and again inside the poller — every feature
redeclaring its own transport. That is exactly what one integrations block fixes.

**Three layers, each answering one question, with no overlap:**

| Layer | File | Answers | Example |
|---|---|---|---|
| **What** | `harness-config.yaml` (per repo) | which events matter, which ticketing system | `notifications.events`, `ticketing.system: github` |
| **Who** | `collaborators.yaml` (per repo) | role → person → channel address | `approver: @handle`, their Slack id |
| **How** | `cli-config.yaml` (daemon) | transport + credentials | `integrations.github.transport: auto` |

This respects [decision-032](../../decisions/decision-032.md) rather than undoing it:
per-repo *intent* stays in the harness config, daemon *mechanics* stay in the CLI config.
The change is that intent now **references a provider by name** instead of redeclaring how
to reach it.

```yaml
# cli-config.yaml — declared ONCE
integrations:
  github: {transport: auto, api: {...}, cli: {binary: gh}}
  slack:  {transport: sdk, urlEnv: THE_LOOP_SLACK_WEBHOOK_URL}

webhooks:
  ghWebhook:
    routing:
      control:   {}          # no ghBinary — uses integrations.github
      reactions: {enabled: true, started: eyes, completed: hooray, error: confused}
      announce:  {enabled: true}
```

```yaml
# harness-config.yaml — names providers, never transports
ticketing:
  system: github             # already a provider name; now it means one
notifications:
  events:
    phase-approval-pending: [approver]   # WHAT + WHO; HOW comes from cli-config
```

**Migration is non-breaking.** An existing `ghBinary` key keeps working, resolved as an
override of `integrations.github.cli.binary`, with a deprecation warning naming the
replacement. Nothing an operator has today stops working on upgrade — the same posture the
`config.yaml` → `harness-config.yaml` rename took.

### What if MCP is the only available route?

The owner's open question, and it deserves a straight answer: **MCP is a protocol for
*agents* to call tools.** It assumes a model-driven client with a session; a daemon
speaking it is against its grain. Two options:

1. **Delegate through the harness (recommended default).** the-loop already spawns Claude
   Code / Cursor, and both are MCP clients with the operator's servers already configured.
   An `mcp-call` hook asks the harness — headless, schema-constrained output — to perform
   the call and return the result. the-loop never implements the protocol; the harness is
   the client, which is what it is for.
2. **Implement a minimal MCP client** (stdio JSON-RPC) in the CLI. Feasible — stdio
   transport is simple — but it adds protocol code, server lifecycle management and
   credential handling to a daemon, for capability we can already reach via (1).

**Recommendation: ship (1), keep (2) on the shelf.** Delegation costs one harness
invocation, reuses machinery that already exists, and keeps the-loop out of a protocol whose
lifecycle it would otherwise have to own. Revisit if the delegation latency ever matters,
which for notification-shaped calls it will not.

## Architecture

```mermaid
flowchart TB
    subgraph plugin["Shipped with the plugin"]
        PDLC["graph/pdlc.yaml — nodes, hooks, edges"]
        SCHEMA["graph.schema.json"]
        PDLC -. validated in CI .-> SCHEMA
    end

    subgraph core["the_loop.graph"]
        MODEL["model.py — load and validate"]
        RT["runtime.py — enter node, run chain, take edge"]
        HOOKS["hooks/ — the registry"]
        STATE["state.py — graph-state.json"]
        MODEL --> RT
        HOOKS --> RT
        STATE --> RT
    end

    subgraph impl["Hook implementations (all one signature)"]
        VAL["validate-artifacts<br/>lint-artifacts<br/>verify-tests"]
        GH["set-phase-label<br/>request-review"]
        SLACK["notify"]
        CLS["classify-feedback"]
    end

    subgraph integ["Integrations (the-loop is the caller)"]
        GHAPI["GitHub REST"]
        SLACKW["Slack webhook"]
        JIRA["Jira REST"]
        MCPD["mcp-call — delegated to the harness"]
    end

    subgraph sess["Sessions"]
        WORK["work nodes — harness session,<br/>tmux attachable, human can take over"]
        GATE["gate nodes — session: inherit"]
    end

    PDLC --> MODEL
    RT --> HOOKS
    HOOKS --> impl
    GH --> GHAPI
    SLACK --> SLACKW
    GH --> JIRA
    CLS --> MCPD
    RT --> WORK
    RT --> GATE
    RT --> EVT["eventlog JSONL"]
```

## The orchestrator: what actually runs the graph

The owner asked what technology takes the graph definition, compiles it and runs it. The
honest answer is **no engine at all** — roughly 600 lines of plain Python — and the more
useful answer is that **the-loop already has this exact pattern in production**.

### It is the pattern already used for CLI commands

`the_loop/commands/base.py` defines a `Command` base class, a `@register` decorator, a
module-level `_REGISTRY` and an `iter_commands()` accessor; dropping a module under
`commands/` makes a new sub-command exist. The hook registry is the same shape:

```python
# the_loop/graph/hooks/__init__.py — the same idea as commands/base.py
@hook("validate-artifacts")
def validate_artifacts(ctx: HookContext) -> HookResult: ...
```

New behaviour is a new module under `graph/hooks/`, exactly as a new sub-command is a new
module under `commands/`. Nothing to learn that the codebase does not already teach.

### What "compiling" means here

| Stage | Mechanism | Failure mode |
|---|---|---|
| **Parse** | `yaml.safe_load` of the shipped `pdlc.yaml` | malformed YAML → startup error |
| **Validate** | structural checks against the graph's declared shape | unknown field / missing `id` → startup error |
| **Resolve** | every hook name looked up in the registry; every edge endpoint looked up in the node table | unknown hook or node → startup error, naming it |
| **Index** | edges keyed by `(from_node, outcome)`; hook chains frozen into tuples | ambiguous edge → startup warning, first-declared wins |
| **Freeze** | the result is an immutable `Graph` dataclass | — |

"Compile" therefore means *resolve + validate + index, once, at load*. The point is that
**every structural failure is a startup failure**, never a surprise three nodes into a
traversal at 2am.

*On JSON Schema:* `scripts/validate_config.py` already validates against JSON Schema using
`jsonschema`, but as a **dev/CI dependency** (imported behind a `try/except ImportError`).
The graph ships with the plugin and is validated in **the-loop's own CI**, so the runtime
needs only the cheap structural checks above — **no new runtime dependency**. If
user-authored graphs ever arrive, that is when runtime schema validation earns its cost.

### The runtime is a state machine, not a scheduler

```python
def advance(repo: Path, work_item: str) -> Outcome:
    graph  = load_graph()                     # cached; compiled once per process
    state  = GraphState.load(repo, work_item) # or reconstruct from artifacts
    node   = graph.node(state.current_node)
    result = run_chain(node.exit, ctx)        # first non-pass short-circuits
    state.record(node, result); state.save()  # persist BEFORE the side effect
    return take_edge(graph, node, result.outcome)
```

No async, no event loop, no task queue, no database. One work item advances at a time — and
that is free, because the existing dispatcher already serialises per session with a FIFO
queue and a concurrency semaphore. Persistence is `json.dump` to a checked-in file.

### Three drivers, one entry point

```mermaid
flowchart LR
    RUN["the-loop run<br/>one-shot: advance until wait or done"] --> ADV["advance()"]
    DAEMON["gh-webhook / poll daemon<br/>event-driven: a comment or CI result arrives"] --> ADV
    CHECK["the-loop check<br/>pure: evaluate, never advance"] --> EVAL["run_chain() only"]
    ADV --> EVAL
    EVAL --> STATE[("graph-state.json")]
```

All three call the same code, which is what keeps `check` honest: the thing CI runs is the
thing the runtime runs, not a reimplementation of it.

### What we are deliberately not using

| Not used | Why |
|---|---|
| LangGraph / LlamaIndex Workflows | assume in-process Python callables and serialized checkpoints; the-loop's nodes are **subprocess invocations of harness CLIs** and its checkpoints are **checked-in files** |
| Temporal / Airflow / Prefect | a scheduler, a worker pool and a database for a state machine that advances a handful of times a day, on one operator's repos |
| A rules/expression engine | removed with CEL — a hook outcome is a name |
| `asyncio` | every wait is either a subprocess or a human; concurrency is already handled by the dispatcher |

The load-bearing constraint is the one from [decision-030](../../decisions/decision-030.md)
and [decision-005](../../decisions/decision-005.md): the-loop stays thin Python that
subprocess-drives official CLIs. A graph runtime that is 600 lines of dataclasses, a
registry and a `while` loop honours that; one that pulls a workflow engine does not.

## Data models

### A node

```yaml
- id: design
  phase: design                    # the label hooks sync
  actor: agent                     # agent | human
  produces: [design.md]
  command: create-design           # closed enum of the-loop's own commands
  stage: design                    # model tier
  entry: [set-phase-label, log-entry]
  exit:
    - {hook: validate-artifacts, with: {locked: true, sections: ["Security design"]}}
    - {hook: lint-artifacts}
    - {hook: log-entry}

- id: design-approval
  actor: human
  session: inherit                 # the owner's observation, as one field
  entry: [set-phase-label, request-review, notify]
  exit:
    - {hook: classify-feedback, with: {outcomes: [approved, approved-with-comments, changes-requested]}}
    - {hook: record-feedback, with: {into: design.md, section: "Review comments"}}
    - {hook: record-decision}
```

The artifact templates gain a `## Review comments` section so the shape exists before the
first review lands. That is an implementation task, not a runtime concern.

### `graph-state.json`

Per work item, checked in — `currentNode`, per-node attempts and outcomes, recorded hook
results and decisions, the bound session id, and the parked reason. It is a **cache, not an
authority**: `the-loop check --recompute` re-runs the validating hooks against the artifacts
and CI always uses it, so an agent editing its own scorecard cannot pass a gate.

## How this answers issue #109's original bullets

| Original question | Answer |
|---|---|
| "make the top level workflow programmatic" | The graph is data; the runtime walks it. |
| "each step needs a clear output artifact to pass on" | `produces`, checked by `validate-artifacts`. |
| "how do we make sure each step is not fresh context" | Work nodes bind a session; gate nodes `inherit` it. Fresh context is a per-node choice, not a global mode. |
| "can the CLI orchestrate deterministically, one or many sessions" | Yes — the runtime owns ordering; sessions are per-node and declared. |
| "how does session management work" | Existing registry/ControlStore, unchanged; nodes bind to session ids. |
| "how do we recover from failure modes" | `block` + `messages` → the harness repairs; bounded attempts then escalate. |
| **"how does the CLI know a step is complete vs waiting for input"** | **Exit hooks: all `pass` = complete; any `wait` = waiting; any `block` = needs repair.** |
| "will this consume a lot of tokens" | Hooks are code, not model calls — only `classify-feedback` invokes a model, at the economy tier. |

## Error handling

| Failure | Response |
|---|---|
| Graph or hook config invalid | refuse to advance anything; report at load time |
| Unknown hook name | load-time validation failure |
| Hook raises | treat as `block`, `retriable=False`, escalate — never as `pass` |
| Hook times out | `block`, retriable, bounded by the node's attempts |
| Same `block` message twice consecutively | escalate to a human (mirrors `escalateOnRepeatFinding`) |
| `classify-feedback` returns invalid output after retries | `wait` — never assume an outcome |
| Unauthorized author's text | not read; stay `wait` |
| Graph state unparseable | reconstruct by re-running validators; warn; keep the file |
| Session died mid-node | existing respawn-and-resume; re-enter the **same** node |
| Notification hook fails | record and continue — a Slack outage must not wedge the graph |

## Security design

- **Untrusted text → gate outcome (primary boundary).** Only authorized authors' text is
  read; the classification schema is a closed enum; the outcome is a fact, not a
  destination; and policy outranks the model — a classification can never satisfy an
  approval that `autonomy.tiers` or `security.review.humanSignOffMinTier` reserves for a
  human. Untrusted text is never echoed into feedback rendered back to the harness.
- **Hooks are code, not configuration.** YAML names a hook from a registry and passes typed
  params. There is no shell hook, no `exec`, no argv from configuration — so the graph
  (shipped with the plugin today, user-authored later) can never become code execution.
- **Agent → graph state.** State is a cache; `--recompute` re-derives from artifacts and CI
  always uses it.
- **Secrets.** Tokens and webhook URLs come from env or a secret store, never the repo,
  never graph state, never logs. `HookContext` carries handles, not values.
- **Least privilege.** Validation hooks are read-only. Integration hooks hold only the
  scopes their operation needs. `the-loop check` makes no network call and no model call.
- **Fail closed.** Unknown hook, invalid config, unevaluable condition, no matching edge,
  invalid classification, missing collaborator — all stop advancement and report.
- **New surface, stated:** outbound HTTP to GitHub/Slack/Jira, a model call for
  classification, and a new state file. Risk tier **4**; a named human security sign-off is
  required before completion.

## Testing strategy

Unit tests for every hook (they are pure functions of `HookContext` — this is the main
payoff of the contract). Integration tests with Gherkin docstrings under
`cli/tests/test_*_integration.py`.

| Area | Integration scenario |
|---|---|
| Chain semantics | *A blocking exit hook stops the chain and its messages reach the harness as the next input* |
| Aggregation | *validate-artifacts reports every unmet requirement in one result rather than one per round* |
| Human gate | *A partial review comment leaves the gate waiting rather than advancing* |
| Approve-with-comments | *An approval carrying suggestions advances the node and carries the follow-ups forward* |
| Session inheritance | *A changes-requested outcome returns to the producing node in the same harness session* |
| Authorization | *An unauthorized comment is not read by classify-feedback and the gate stays waiting* |
| Lint hook | *A design artifact with an unparseable mermaid block blocks the node* |
| Integrations | *A Slack webhook failure records and continues without wedging the graph* |
| Recompute | *CI fails a work item whose graph-state claims a node complete that the artifacts contradict* |

## Trade-offs & decisions

- **Two concepts, not five.** Costs some expressive precision; buys an architecture that
  fits on one page and one extension point instead of several. → `decision-041` (revised).
- **Human gate as a node, not a hook.** Costs the neatness of "everything is a hook"; buys
  correct modelling of a multi-day, event-receiving, iterative state.
- **`session: inherit` rather than a new binding concept.** One enum value expresses the
  owner's observation that gate feedback belongs to the previous node's session.
- **Every edge routes on a hook outcome; no expression language.** Costs a hook per
  non-trivial condition; buys one mechanism instead of two, **zero new runtime
  dependencies**, and conditions that are unit-testable like everything else.
  → `decision-042` (revised).
- **Official SDK where one exists; thin REST where none does.** Slack's `slack-sdk` is
  official and has **zero required dependencies**, so adopting it is free and buys
  retry/backoff/proxy handling. GitHub has **no** official Python SDK, and the community
  options cost five or six transitive dependencies (PyGithub even a compiled one) to wrap
  ~10 endpoints — a poor trade against a current footprint of exactly `pyyaml`. Migrating
  the five modules that use `gh` today is the real work either way.
- **MCP by delegation to the harness.** Costs one harness invocation per call; buys not
  owning a protocol implementation and its server lifecycle.
- **Hooks are registered code, never shell.** Costs operator extensibility today; buys a
  YAML surface that can safely become user-authored later.

## Open questions

**None outstanding.** All four were resolved by the owner on PR #110 and are folded into the
design above — see `requirements.md` § Open questions for the record of what each was and how
it was answered: the meaning of the tier-4 sign-off, review comments recorded *in the
artifact*, `session: inherit` falling back to a fresh session seeded with the artifacts, and
**CEL removed** in favour of routing on hook outcomes.

The only thing between this design and `tasks.md` is phase approval.
