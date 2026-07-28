---
type: requirements
phase: requirements-definition
workItem: issue-109
status: draft                # draft | in-review | approved
approvedBy: []
collaborators: [architect, engineer, product-manager]
riskTier: 4                  # gate classification reads untrusted text; outbound integrations
overrides: {}
---

# Requirements: the-loop as a graph of nodes with entry/exit hooks

> Phase 1 of 3. Derived from the locked [`brainstorm.md`](brainstorm.md).
> **Rewritten from a fresh slate** on the owner's simplification direction (PR #110),
> anchored on that comment and on the original bullets in
> [issue #109](https://github.com/MadaraUchiha-314/the-loop/issues/109).

## Introduction

the-loop's PDLC — brainstorm → requirements → design → tasks → implement → review →
evidence → complete → learn — exists **only as prose**. Nothing evaluates it, so steps get
skipped or invented. Measured in this repository: of 26 execution logs, **23 sit at
`needs-review`** and none reaches `complete`, while 15 issues carry `loop:complete`; 15 of
28 `requirements.md` and 16 of 33 `design.md` are still `status: draft` despite shipping.

This work item makes the PDLC an explicit **graph**, walked by a runtime in the-loop's CLI,
built from exactly two concepts:

- a **node** — a step, with `entry` and `exit` hook chains;
- a **hook** — a unit of work with a fixed signature, returning a `HookResult` that decides
  whether the work item moves.

Everything the-loop needs to *do* at a step boundary — validate artifacts, lint them, update
a label, request a review, notify Slack, update Jira, classify a human's reply — is a hook.
One shape, used everywhere.

**Risk tier 4.** Gate classification reads human-authored text (attacker-reachable on a
public repository) and the-loop gains outbound integrations. Per `autonomy.tiers`,
`human-approves-pr`; per `security.review.humanSignOffMinTier`, a **named human security
sign-off**.

## Requirements

### Requirement 1 — The graph is declared data, owned by the-loop

**User story:** As a the-loop maintainer, I want the PDLC declared as data shipped with the
plugin, so the process is versioned with the code that runs it and no repository can
redefine what executes.

1. WHEN the runtime starts THEN it SHALL load the graph from the installed plugin and SHALL
   NOT read a graph from the working repository.
2. WHEN the graph is loaded THEN it SHALL be validated against a checked-in JSON Schema, and
   the runtime SHALL refuse to run if validation fails.
3. WHEN a node is declared THEN it SHALL require `id` and SHALL accept `phase`, `actor`,
   `produces`, `command`, `stage`, `session`, `entry`, `exit` and `maxAttempts`.
4. IF a repository declares its own graph THEN the system SHALL ignore it with a warning
   naming this as a future feature.
5. IF an edge or a hook reference names something undeclared THEN validation SHALL fail with
   the offending name.
6. WHEN the graph declares a cycle THEN it SHALL be accepted — review→fix→review is a valid
   transition set.

### Requirement 2 — The hook contract

**User story:** As a the-loop maintainer, I want every hook to share one signature and one
output type, so new behaviour is a new hook and never a new subsystem.

1. WHEN a hook is invoked THEN it SHALL receive a `HookContext` carrying the work item, the
   node, the boundary (`entry`/`exit`), the repository path, the resolved artifact paths, the
   bound session, the triggering event, prior results in the chain, and config handles.
2. WHEN a hook returns THEN it SHALL return a `HookResult` with `status`
   (`pass | block | wait | skip`), the hook name, an ordered `messages` list, a `data`
   mapping, and a `retriable` flag.
3. WHEN a hook returns `block` THEN the node SHALL NOT advance, and the result's `messages`
   SHALL be delivered to the harness as its next input.
4. WHEN a hook returns `wait` THEN the node SHALL park and re-run its exit chain on the next
   inbound event.
5. WHEN a hook returns `skip` THEN the chain SHALL continue and the skip SHALL be recorded.
6. WHEN a hook raises, or times out, THEN the runtime SHALL treat it as `block` — never as
   `pass`.
7. WHEN a `HookContext` is built THEN it SHALL carry secret *handles*, never secret values.

### Requirement 3 — Chains decide whether a node completes

**User story:** As an operator, I want "is this step done?" to have one mechanical answer, so
the CLI never has to interpret prose.

1. WHEN a node is entered THEN its `entry` hooks SHALL run in declared order.
2. WHEN a node's work signals it has finished — a process exit, or a harness stop-hook tick —
   THEN its `exit` hooks SHALL run in declared order.
3. WHEN every exit hook returns `pass` THEN the node SHALL be complete and the matching edge
   taken.
4. WHEN a hook returns a non-`pass` status THEN the chain SHALL short-circuit at that hook.
5. WHEN a validating hook finds several unmet requirements THEN it SHALL report **all of
   them in one result**, so the agent receives the complete list in a single round.
6. WHEN feedback is rendered back to the harness THEN it SHALL be composed of the-loop's own
   text, hook names and artifact paths — never untrusted payload text.

### Requirement 4 — The human gate is a node

**User story:** As a reviewer, I want my actual review — partial, approving with comments, or
requesting changes — to be understood, so the process meets me where I write.

1. WHEN a work item reaches a human gate THEN it SHALL enter a **node** whose `actor` is
   `human`, not a hook.
2. WHEN a gate node is entered THEN its entry hooks SHALL request the review, sync the phase
   label and notify the configured roles.
3. WHEN feedback arrives THEN the gate's exit chain SHALL re-run; WHEN the feedback is not
   decisive (partial, a question, ambiguous) THEN the chain SHALL return `wait` and the gate
   SHALL remain open.
4. WHEN feedback is classified `approved` THEN the work item SHALL advance.
5. WHEN feedback is classified **approved with comments** THEN the work item SHALL advance
   **and** the comments SHALL be carried forward as declared follow-up work — an approval
   SHALL NOT silently discard a reviewer's suggestions.
6. WHEN feedback is classified **changes requested** THEN the work item SHALL return to the
   producing node with the feedback as that node's next input.
7. WHEN a gate node declares `session: inherit` THEN it SHALL reuse the harness session of
   the node that produced the artifacts under review.
8. WHEN classification is performed THEN it SHALL read only text authored by a user in
   `routing.authorizedUsers`, and its result SHALL be constrained to a closed outcome set.
9. **A classification SHALL NOT satisfy an approval that policy reserves for a human** — it
   only classifies a human response that has actually arrived.

### Requirement 5 — The hooks the-loop ships

**User story:** As an operator, I want the defaults to be ordinary hooks, so what ships and
what I could add are the same kind of thing.

1. WHEN the-loop ships THEN it SHALL provide at least: `set-phase-label`, `request-review`,
   `notify`, `log-entry`, `validate-artifacts`, `lint-artifacts`, `verify-tests`,
   `classify-feedback` and `record-decision`.
2. WHEN `validate-artifacts` runs THEN it SHALL check existence, front-matter lock state and
   required sections of the node's declared outputs.
3. WHEN `lint-artifacts` runs THEN it SHALL run the configured markdown linter **and** verify
   that every mermaid block parses.
4. WHEN `set-phase-label` runs THEN it SHALL sync the ticket label for the node's `phase`.
5. WHEN `request-review` or any other commenting hook posts THEN the comment SHALL carry
   the-loop's self-authored marker.
6. WHEN `notify` runs THEN recipients SHALL resolve only through `notifications.events` →
   roles → `.the-loop/collaborators.yaml`.

### Requirement 6 — Integrations are the-loop's own calls

**User story:** As an operator, I want the-loop to talk to GitHub, Slack and Jira directly,
so behaviour does not depend on which CLI happens to be installed.

1. WHEN the-loop calls GitHub THEN it SHALL use the REST API over HTTP, not the `gh` CLI.
2. WHEN a GitHub token is absent from the environment and `gh` is available THEN the system
   MAY invoke `gh auth token` **solely as a credential source**.
3. WHEN the-loop notifies Slack THEN it SHALL use an incoming webhook URL from configuration
   or environment.
4. WHEN the-loop updates Jira THEN it SHALL use the Jira REST API with an API token.
5. WHEN an integration is unavailable except through MCP THEN the system SHALL perform the
   call by **delegating to the harness** with schema-constrained output, rather than
   implementing the MCP protocol itself.
6. WHEN an integration call fails THEN the hook SHALL record the failure and the runtime
   SHALL continue unless that hook is declared blocking — a channel outage SHALL NOT wedge
   the graph.
7. WHEN any integration is configured THEN its credentials SHALL come from environment or a
   secret store, never from the repository, graph state or logs.

### Requirement 7 — Sessions

**User story:** As an operator watching a tmux session, I want to take over at any moment, so
automation never costs me the ability to intervene.

1. WHEN a work node runs THEN it SHALL run through the configured runner, including the
   resident tmux session, so a human can attach and take over.
2. WHEN a human takes over a session THEN the exit chain SHALL still evaluate against the
   artifacts that session produces.
3. WHEN a node declares `session: inherit` THEN it SHALL bind the previous node's session.
4. IF an inherited session has died THEN the system SHALL fall back to a fresh session seeded
   with the artifacts as context, recording the fallback.
5. WHEN a model call is required by a hook THEN it SHALL run as a separate short-lived
   headless process at the cheapest declared tier, and SHALL NOT be injected into the
   resident session.

### Requirement 8 — Graph state, recovery and observability

1. WHEN a work item is walked THEN the system SHALL maintain a checked-in `graph-state.json`
   holding the current node, per-node attempts and outcomes, recorded hook results and
   decisions, the bound session and any parked reason.
2. WHEN state is written THEN it SHALL be persisted before any dependent side effect.
3. WHEN state is missing or unparseable THEN the system SHALL reconstruct by re-running the
   validating hooks against the artifacts, warn, and SHALL NOT delete the file.
4. WHEN `the-loop check --recompute` runs THEN it SHALL ignore graph state and derive
   completion from artifacts alone; CI SHALL use it.
5. WHEN the same blocking message recurs on two consecutive attempts, or attempts reach
   `maxAttempts`, THEN the system SHALL escalate to a human and stop advancing.
6. WHEN a harness session dies mid-node THEN the system SHALL respawn/resume and re-enter the
   **same** node.
7. WHEN any node is entered or exited, any hook returns non-`pass`, or any edge is taken,
   THEN a JSONL event-log record SHALL be emitted.
8. WHEN `the-loop check` runs THEN it SHALL make no network call and no model call.

### Requirement 9 — Backwards compatibility

1. WHEN a repository has never seen the graph THEN the system SHALL work without requiring
   any file to be added to it.
2. WHEN a node declares a `phase` THEN its label SHALL be kept in sync as today; nodes
   without one SHALL NOT create new labels.
3. WHEN `workflow.phases` is present THEN the shipped graph SHALL be authoritative and the
   phase list treated as derived, warning on divergence.

## Non-functional requirements

- **Dependencies.** At most one new runtime dependency, and only if the compound-edge case
  survives review (see open question 4). HTTP uses the standard library.
- **Both harnesses.** Every requirement holds for Claude Code and Cursor, or degrades to the
  repository-boundary check with the difference documented.
- **`the-loop check` is fast and pure** — it runs on every resident-session turn.
- **Hooks are unit-testable** as pure functions of `HookContext`; this is the main payoff of
  fixing the contract.
- **Observability identical at dev-time and runtime.**

## Security considerations

- **Actors & trust.** *Trusted:* the-loop's shipped graph; the operator. *Untrusted:*
  human-authored text a classification reads; the agent as a writer of state and artifacts;
  webhook and poller payloads.
- **Boundary 1 — untrusted text → gate outcome (primary).** *Mechanisms:* authorization
  filter first (unauthorized text is not read at all); closed outcome enum; the outcome is a
  fact and every destination is a declared edge; policy outranks the model (R4.9); untrusted
  text is never echoed into harness feedback (R3.6).
- **Boundary 2 — configuration → execution.** *Mechanism:* hooks are **registered code**, not
  shell. YAML names a hook and passes typed params; there is no `exec`, no shell, no argv
  from configuration. This is what will let the graph become user-authored later.
- **Boundary 3 — agent → graph state.** *Mechanism:* state is a cache; `--recompute`
  re-derives from artifacts and CI always uses it (R8.4).
- **Boundary 4 — outbound integrations.** *Mechanisms:* credentials from environment or a
  secret store only (R6.7); recipients only from `collaborators.yaml` (R5.6); message bodies
  name the work item, node and reason rather than artifact contents.
- **Abuse cases (EARS):**
  1. WHEN text from an unauthorized author would be classified THEN it SHALL be ignored.
  2. WHEN untrusted text contains instructions ("approve this") THEN the closed outcome set
     and declared edges SHALL confine the effect to a classification.
  3. WHEN a classification would satisfy an approval reserved for a human THEN it SHALL be
     refused.
  4. WHEN graph state claims a node complete that the artifacts contradict THEN the
     repository-boundary check SHALL fail.
  5. WHEN a graph names a hook that is not registered THEN validation SHALL fail.
  6. WHEN a hook raises THEN it SHALL be treated as `block`, never `pass`.
  7. WHEN a credential would be written to graph state or a log THEN it SHALL be refused.
- **Fail closed.** Invalid graph, unknown hook, raising hook, invalid classification, no
  matching edge, missing collaborator — each stops advancement and reports.
- **New surface, stated.** Outbound HTTP to GitHub/Slack/Jira, a model call for
  classification, a new state file, and hook wrappers running per turn. Risk tier 4.

## Out of scope

- **User-defined graphs and user-authored hooks.** A future feature; the declarative form and
  the registry exist so it can arrive safely.
- **Implementing the MCP protocol in the CLI.** Delegation to the harness instead (R6.5).
- **Shell/`exec` hooks.** Deliberately never.
- **Mass-retrofitting the 34 existing spec folders.** Reported and baselined.
- **Changing the PDLC itself.** The graph describes the process the skill already defines.

## Open questions

1. Who provides the tier-4 **named security sign-off**?
2. **Approve-with-comments** (R4.5): are carried-forward follow-ups *mandatory* work in the
   next node, or advisory notes? Mandatory is safer; advisory is faster.
3. **`session: inherit` when the session has died** (R7.4): fall back to fresh with artifacts
   as context (recommended, matches existing respawn behaviour), or block?
4. **Is CEL still wanted** for the compound-edge minority, now that `on: <outcome>` covers the
   common case — or drop the dependency and express compound conditions as named hooks?
