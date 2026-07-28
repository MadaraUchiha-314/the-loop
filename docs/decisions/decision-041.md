# Decision 041: model the-loop's PDLC as a graph of nodes with entry/exit hooks

- **Status:** proposed
- **Date:** 2026-07-28 (revised; first drafted 2026-07-27)
- **Deciders:** @MadaraUchiha-314 (issue #109, PR #110)
- **Work item:** issue-109
- **Spec:** `docs/specs/issue-109/`
- **Answers:** the "open design question" left dangling at the end of
  `skills/the-loop/reference/workflow.md` § *Predictability & guarantees*.
- **Builds on:** [decision-004](decision-004.md) (the Kiro 3-phase spec — the graph
  formalizes the artifact chain it defines), [decision-027](decision-027.md)
  (checkpoint-then-reset — graph state is that checkpoint made explicit),
  [decision-005](decision-005.md) / [decision-038](decision-038.md) (dependency posture).

## Context

Issue #109: *"The current workflow of the-loop is only enforced through documentation and
prompts written in SKILL.md… how do we make these top level workflow more programmatic?"*

The PDLC is described in prose and enforced by nothing. Measured against this repository's
own checked-in specs: of 26 execution logs, **23 sit at `phase: needs-review`** and none
reaches `complete`, while 15 issues carry the `loop:complete` label — the two mirrors of the
same state machine disagreeing on 22 work items, unnoticed. 15 of 28 `requirements.md` and
16 of 33 `design.md` are still `status: draft` despite having shipped.

The owner's diagnosis located the defect precisely: **there is no event anywhere in the-loop
that means "this node of the process completed."** Harness hooks fire on *harness* lifecycle
— many times per node, carrying no phase — and a label is a state, not a transition. So
there was nowhere to hang a gate, a notification, or an advance.

The drift confirms it rather than merely coexisting with it: `needs-review` is one label
covering at least six distinct pieces of work (self-review, critic-review, security review,
evidence, capability-doc fold-in, reviewer briefing). **The drift concentrates exactly where
node granularity runs out.**

An earlier draft of this decision reached for more machinery than the problem needs — layers,
a separate lifecycle-event system, a distinct action vocabulary, an expression on every edge.
The owner cut it back:

> *"I want to simplify the concepts here. I want a graph with an entry and exit hooks, and
> then each of these validations that we want are hooks that are chained together. Each hook
> has a signature and the default features that we want are implemented using the same hooks
> pattern."*

That is a better architecture, and this record reflects it.

## Decision

1. **Two runtime concepts: node and hook.** A **node** is a step of the PDLC — a place the
   work item *is*. It declares `entry` and `exit` hook chains. A **hook** is a unit of work
   with a fixed signature, run in declared order at a boundary. There is no third concept.
2. **One contract: `HookResult`.** Every hook returns
   `{status, hook, messages[], data{}, retriable}` where status is
   `pass | block | wait | skip`. This is what decides movement:
   - all exit hooks `pass` → the node is **complete**, take the edge;
   - any `block` → **do not advance**, and the result's `messages` become the harness's next
     input, so the loop is do → check → repair → check;
   - any `wait` → **park**, re-running the exit chain on the next inbound event.
   This is the direct answer to the ticket's sharpest question — *how does the CLI know a
   step is complete versus waiting for the user?* No prose is parsed, ever.
3. **Everything is a hook.** Validating artifacts, linting them, verifying tests, syncing a
   GitHub label, requesting a review, notifying Slack, updating Jira, classifying a human's
   reply. The defaults the-loop ships are ordinary hooks, so what ships and what could later
   be added are the same kind of thing.
4. **Chains short-circuit; hooks aggregate.** The first non-`pass` stops the chain. Reporting
   several findings at once is the *hook's* job — `validate-artifacts` returns every unmet
   requirement in one result, so the agent gets the complete list in one round instead of
   discovering them one at a time. That is why `messages` is a list.
5. **The human gate is a node, not a hook.** It lasts days, it *receives* events while open,
   it has an internal loop (partial reviews, approve-with-comments, changes-requested), and
   it produces artifacts. A hook is a function that runs and returns; expressing a multi-day
   event-receiving state as one means inventing suspend-and-resume — which is a node with
   extra steps. Its *behaviour* is still all hooks.
6. **A gate node binds the producing node's session** (`session: inherit`). Feedback at a
   gate is about the artifacts the previous node produced, so the reviewer's *"this section
   is thin"* should reach the agent that wrote it, with its context intact. The owner's
   observation, expressed as one enum value rather than a new concept.
7. **Hooks are registered code, never shell.** YAML names a hook from a registry and passes
   typed params. No `exec`, no shell, no argv from configuration — which is what will let the
   graph safely become user-authored later.
8. **The graph ships with the plugin.** Repositories do not define or override it for now; a
   repo-supplied graph is ignored with a warning. It stays fully declarative precisely so
   user-defined graphs can arrive as a *distribution* change rather than a rewrite.
9. **Graph state is a cache, not an authority.** `graph-state.json` is checked in per work
   item, but `the-loop check --recompute` re-runs the validating hooks against the artifacts
   and CI always uses it — so an agent editing its own scorecard cannot pass a gate.

## Consequences

**Positive.**

- Both halves of issue #109 become decidable: a skipped step is a blocking hook, an invented
  step is an undeclared transition.
- The architecture fits on a page: one extension point instead of several, and new behaviour
  is a new hook rather than a new subsystem.
- Hooks are pure functions of a context object, so the interesting logic is unit-testable
  without a harness, a network or a session.
- The six nodes hiding inside `needs-review` become addressable — gateable, notifiable, and
  visible in graph state — which is where the measured drift lives.
- `notifications.events` and `collaborators.yaml` stop being inert configuration.
- Reviewers are met where they write: approve-with-comments and partial review are modelled
  outcomes rather than states the process cannot express.

**Negative / accepted costs.**

- A new checked-in state file per work item, and a hook registry to version.
- Repositories lose the ability to shape their own process for now — the price of removing
  the config-to-execution surface.
- The gate's classification reads human-authored text, which on a public repository is
  attacker-reachable. This is the primary remaining risk; it carries the tier at **4** and
  requires a named human security sign-off.
- "Everything is a hook" is not quite true — the human gate is a node — so there are two
  shapes to learn rather than one. Judged worth it: the alternative mis-models a multi-day
  wait.

## Alternatives considered

- **Stricter prompts.** The status quo; the drift table is what it produces.
- **Harness hooks as the enforcement mechanism.** Rejected on the owner's diagnosis: too
  fine-grained and phase-blind to *be* node boundaries. Retained only as a trigger for
  running the exit chain.
- **The earlier layered design** (separate lifecycle-event system, action vocabulary,
  expression on every edge). Rejected by the owner as unnecessarily complex; superseded by
  the node/hook pair above.
- **The human gate as a hook.** Rejected for the five reasons in `design.md`; principally
  that it must receive events while open.
- **Importing a graph framework.** Rejected: those assume in-process callables and
  serialized checkpoints, where the-loop has CLI subprocesses and checked-in files that
  survive a machine change and are reviewable in a PR diff.
- **Parsing the agent's prose for "step complete".** Rejected outright — it reintroduces the
  non-determinism the issue exists to remove.

## References

- `docs/specs/issue-109/brainstorm.md` (locked), `requirements.md`, `design.md`.
- [decision-042](decision-042.md) — edge routing and the classification of human feedback.
