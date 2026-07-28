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

### Risk tier 4 — what that actually means here

This work item is **risk tier 4**, because gate classification reads human-authored text
(attacker-reachable on a public repository) and the-loop gains outbound integrations holding
credentials. Two rules in this repository's own `.the-loop/harness-config.yaml` then apply,
and because the jargon is easy to skim past, here is what each one concretely requires:

| Config | Says | In practice, for this work item |
|---|---|---|
| `autonomy.tiers: {"4": human-approves-pr}` | tier 4 may not self-complete | the loop can do everything up to "ready", but a human merges the PR |
| `security.review.humanSignOffMinTier: 4` | at tier ≥ 4 a **named** human approves the security review, recorded on the PR | someone writes, in a comment, that they have read the Security design section and accept it — with their name against it |

**It does not imply a security team.** "Named human sign-off" means the paper trail records
*who* accepted the security analysis, so the-loop cannot self-certify its own threat model.
For this repository that person is the owner. The practical deliverable is one comment on
the PR of the form *"security review read and accepted — @handle, <date>"*, recorded in the
execution log's Security review section.

The tier also raises the bar on this spec itself: the **Security considerations** section
below has to be specific and honest about new attack surface rather than asserting "no new
attack surface".

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
   **and** the review SHALL be appended to a `## Review comments` section of the artifact the
   gate approved — an approval SHALL NOT silently discard a reviewer's suggestions.
   *(Owner decision: the comments live in the generated document, not in a side-channel
   follow-up list.)*
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
   `classify-feedback`, `record-feedback` and `record-decision`.
2. WHEN `validate-artifacts` runs THEN it SHALL check existence, front-matter lock state and
   required sections of the node's declared outputs; WHEN the artifact has passed through a
   gate THEN a non-empty `## Review comments` section SHALL be one of those required
   sections, so a lost review is a blocking finding rather than a silent omission.
3. WHEN `record-feedback` runs THEN it SHALL append the review, attributed and dated, to the
   artifact's `## Review comments` section without rewriting earlier entries.
4. WHEN `lint-artifacts` runs THEN it SHALL run the configured markdown linter **and** verify
   that every mermaid block parses.
5. WHEN `set-phase-label` runs THEN it SHALL sync the ticket label for the node's `phase`.
6. WHEN `request-review` or any other commenting hook posts THEN the comment SHALL carry
   the-loop's self-authored marker.
7. WHEN `notify` runs THEN recipients SHALL resolve only through `notifications.events` →
   roles → `.the-loop/collaborators.yaml`.

### Requirement 6 — Integrations: two call planes, configurable transport

**User story:** As an operator, I want to choose how the-loop reaches GitHub, Slack and Jira
— and I want the agent left free to reach anything however it likes — so the-loop fits my
environment instead of dictating it.

1. WHEN the **agent** reaches an external service from inside its session THEN the-loop SHALL
   NOT constrain how — CLI, MCP or API are all the harness's and the operator's business.
   *(Owner: "anything that the LLM uses can be through CLI, MCP or API as LLM is free to do
   whatever it wants.")* Everything below governs **the-loop's own calls only**.
2. WHEN the-loop calls an external service THEN the transport SHALL be **configurable per
   integration** in the CLI config, supporting at least `api` and `cli` where both are
   meaningful, and `sdk` where an official one exists.
3. WHEN `transport: auto` is configured THEN resolution SHALL follow a documented order — a
   configured API token first, then an installed CLI binary — and WHEN neither is available
   the system SHALL fail closed naming **both** remedies.
4. WHEN an explicit transport is configured THEN it SHALL be honoured verbatim and SHALL fail
   rather than silently falling back to another.
5. WHEN the-loop notifies Slack THEN the default transport SHALL be the official `slack-sdk`,
   with a dependency-free raw `webhook` transport available as the alternative.
6. WHEN the-loop calls GitHub THEN both an `api` transport (stdlib HTTP + token) and a `cli`
   transport (the existing `gh` path, inheriting the operator's `gh auth`, including
   enterprise/SSO) SHALL be available; `auto` SHALL be the default.
7. WHEN the-loop updates Jira THEN an `api` transport SHALL be available, with a `cli`
   transport supported for parity.
8. WHEN a transport provider is registered THEN it SHALL **declare the operations it
   implements**.
9. WHEN the runtime loads THEN it SHALL verify that every operation the configured graph's
   hooks require is implemented by the configured transport, and SHALL fail **at load time**
   — naming the operation, the target and how to fix it — rather than failing mid-traversal.
10. WHEN a transport is swapped THEN the `HookResult` a hook returns SHALL be unchanged —
    transport SHALL affect how a side effect is performed, never whether a node advances.
11. WHEN an integration is unavailable except through MCP THEN the-loop SHALL perform the call
    by **delegating to the harness** with schema-constrained output, rather than implementing
    the MCP protocol itself.
12. WHEN an integration call fails THEN the hook SHALL record the failure and the runtime
    SHALL continue unless that hook is declared blocking — a channel outage SHALL NOT wedge
    the graph.
13. WHEN any integration is configured THEN its credentials SHALL come from environment or a
    secret store, never from the repository, graph state or logs.
14. WHEN the `cli` transport is used for GitHub THEN it SHALL reuse the existing `gh` code
    paths (`announce`, `comments`, `control`, `reactions`, `poller/github`) rather than
    replacing them — configurable transport turns the migration into an addition.

### Requirement 7 — Sessions

**User story:** As an operator watching a tmux session, I want to take over at any moment, so
automation never costs me the ability to intervene.

1. WHEN a work node runs THEN it SHALL run through the configured runner, including the
   resident tmux session, so a human can attach and take over.
2. WHEN a human takes over a session THEN the exit chain SHALL still evaluate against the
   artifacts that session produces.
3. WHEN a node declares `session: inherit` THEN it SHALL bind the previous node's session.
4. IF an inherited session has died THEN the system SHALL fall back to a fresh session seeded
   with the work item's artifacts (`requirements.md`, `design.md`, `execution-log.md`) as
   context, recording the fallback — it SHALL NOT block. *(Owner decision: those artifacts
   are enough to restart the session.)*
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

- **Dependencies: one, and it is free.** Edges route on hook outcomes only — no expression
  language (owner decision: *"Remove CEL"*) — and GitHub/Jira HTTP uses the standard library.
  The single addition is the **official `slack-sdk`**, which declares **zero required runtime
  dependencies** of its own, so the-loop's installed footprint grows by one package and no
  transitive tree.
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

All four earlier questions were **resolved by the owner on PR #110**; kept here as the paper
trail.

1. ~~Who provides the tier-4 named security sign-off?~~ → **Clarified, not delegated.** It
   means the paper trail records *who* accepted the security analysis, so the loop cannot
   self-certify its own threat model; for this repository that is the owner. See § *Risk tier
   4 — what that actually means here*.
2. ~~Approve-with-comments: mandatory follow-ups or advisory notes?~~ → **Neither — the
   comments go into the artifact.** A `## Review comments` section at the bottom of the
   generated doc (R4.5, R5.3). Better than both options offered: the feedback becomes part of
   the durable record, travels with the document it concerns, and is reviewable in the diff.
3. ~~`session: inherit` when the session has died?~~ → **Fall back to fresh**, seeded with
   `requirements.md` / `design.md` / `execution-log.md` (R7.4). Owner: *"artifacts… should be
   enough to restart the session."*
4. ~~Is CEL still wanted?~~ → **Removed.** Every edge routes on a hook outcome; a condition
   that would have needed an expression becomes a named hook. Zero new runtime dependencies.

Nothing now blocks tasks breakdown except phase approval itself.
