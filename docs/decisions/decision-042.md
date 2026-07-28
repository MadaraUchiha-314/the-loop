# Decision 042: CEL for edge conditions; dynamic gates decide facts, never destinations

- **Status:** proposed
- **Date:** 2026-07-27
- **Deciders:** @MadaraUchiha-314 (issue #109, PR #110)
- **Work item:** issue-109
- **Spec:** `docs/specs/issue-109/`
- **Extends:** [decision-041](decision-041.md) (the process graph). Accepts one new runtime
  dependency, in the posture [decision-038](decision-038.md) established when it retired the
  zero-dependency guarantee.

## Context

decision-041 made the-loop's PDLC an explicit graph. Its first draft gave edges a **closed
keyword vocabulary** (`gate.satisfied`, `gate.failed.retriable`, …). The owner rejected that
as too weak for the gates that actually matter:

> *"We should at least support CEL based expressions for conditional edges so that one can
> define dynamic edges for gates. For e.g. the approval gate after every step will need an
> LLM call to check if the user requested some changes or approved. It can't be static."*

Two distinct requirements are hiding in that sentence:

1. **Expressiveness.** Real conditions combine attempt counts, per-work-item tags, risk
   tiers and decision outcomes. A fixed keyword set means inventing a keyword per condition
   forever.
2. **Semantics.** "Did the human approve?" is a judgement over free-form English. No
   expression language answers it, no matter how expressive.

These pull in opposite directions. Expressiveness wants a richer *evaluator*; semantics wants
a *model*. The risk is that satisfying (2) hands routing to an LLM and gives back the
non-determinism issue #109 exists to remove.

There is also a constraint on *how* the model is invoked. The owner:

> *"Triggering claude/cursor through CLI and piping it through a tmux session is important
> because that lets the user take over and interact whenever required."*

So whatever makes these calls must not disturb the session a human may be watching.

## Decision

1. **Edge conditions are CEL expressions.** `when` is a CEL expression over a documented,
   typed context (`gate`, `attempts`, `maxAttempts`, `node`, `workItem.{tags,riskTier,skip}`,
   `decision.<id>`, `findings`, `approval`). CEL is
   [non-Turing-complete, side-effect-free and designed to be embedded](https://cel.dev/) —
   it cannot reach the filesystem, network, subprocesses or environment. That property is
   why it remains safe when user-defined graphs eventually arrive.
2. **Every expression is compiled at load time**, not at traversal time. A malformed
   expression fails before any work item is touched.
3. **Deterministic selection.** Outgoing edges are evaluated in declaration order and the
   first true one is taken; the ambiguity is recorded. **No true edge parks and escalates**
   rather than guessing.
4. **Dynamic gates: the LLM produces facts; CEL routes on them.** A node may declare a
   `decision` — a prompt plus a **JSON Schema** whose validated result is recorded in graph
   state and bound into the CEL context. The model answers a constrained question; the
   node's **declared** edges decide where that answer leads. *The model never returns a
   destination.*
5. **Structured output comes from the harness CLI.** Claude Code supports
   `claude -p … --output-format json --json-schema '<schema>'`, returning a validated result
   in `structured_output`. Cursor's CLI has `-p --output-format json` but no schema
   enforcement today, so its decisions embed the schema in the prompt, validate locally, and
   retry within a declared bound.
6. **A decision that cannot be resolved fails closed.** Invalid output after its retries →
   park and notify. Never assume an outcome.
7. **Policy outranks the model.** A decision can only *classify* a human response that has
   actually arrived. It can never satisfy an approval that `autonomy.tiers` or
   `security.review.humanSignOffMinTier` reserves for a human.
8. **Only authorized text is read.** A decision that reads human-authored text considers only
   text authored by a user in `routing.authorizedUsers` (`authz.is_authorized`). Everything
   else is not carefully handled — it is not read at all.
9. **Decision calls are side calls.** They run as fresh, short-lived headless processes at
   the cheapest model tier: never `--resume` of the work session, never pasted into tmux. The
   work stays in the session a human can attach to and take over; the decisions happen beside
   it.
10. **Dependency: a pure-Python CEL implementation** (`cel-python`) over the official
    wrapped-C++ binding, so wheels stay pure and installation needs no toolchain. Recorded as
    an open question in case the owner prefers upstream fidelity over install simplicity.

## Consequences

**Positive.**

- Gates that are inherently semantic (approval, "were changes requested?") become expressible
  without a keyword explosion or a regex that pretends English is structured.
- Determinism is preserved where it matters: the **set of reachable states stays fixed**.
  Judgement is confined to producing a value inside a closed enum, and every route out of
  that value is declared in the graph and reviewable in a diff.
- Per-work-item `tags` and `riskTier` become routing inputs, so one graph serves a typo fix
  and an auth change (`workItem.tags.exists(t, t == 'docs-only')`).
- The routing decision is auditable: graph state records the outcome, its inputs, the harness
  that produced it, and which expression selected the edge.
- `the-loop check` stays pure and cheap enough to run on every turn, because it reads the
  *recorded* decision instead of making a new one.

**Negative / accepted costs.**

- **One new runtime dependency.** Judged worth it: writing a bespoke expression evaluator
  means proving our own sandbox safe, which is strictly worse than adopting a language
  designed for exactly this.
- **A decision call costs a model invocation per dynamic gate.** Mitigated by the economy
  tier, a tiny prompt, and recording results so they are not recomputed.
- **Harness asymmetry.** Claude Code enforces the schema; Cursor validates and retries. The
  Cursor path is measurably weaker and is called out as an open question.
- **A new trust boundary.** Decisions read human-authored text, which on a public repository
  is attacker-reachable. This is the boundary that replaces the one decision-041's
  internal-graph change removed, and it carries the risk tier at **4**.
- **CEL is another language in the codebase** for maintainers to know.

## Alternatives considered

- **Keep the closed keyword vocabulary.** Rejected by the owner and on merit: every new
  condition needs a new keyword and a code change, and the approval gate remains impossible.
- **Let the model choose the next node directly** (return a node id). Rejected: it makes the
  reachable state set a model output, which is precisely the non-determinism issue #109
  exists to remove. Returning a *fact* into a declared expression gets the flexibility
  without the loss.
- **Keyword-match the approval comment** (`/approve`, `LGTM`). Rejected: brittle, and it
  pushes process onto reviewers instead of meeting them where they write.
- **Python expressions (`eval`) for conditions.** Rejected outright: arbitrary code
  execution, and unsafe the moment graphs become user-authored — which is the stated plan.
- **A general rules engine.** Rejected as heavier than the problem; CEL is the smallest thing
  that answers it.
- **Run decisions inside the resident tmux session.** Rejected on the owner's constraint:
  it would consume the session's context and interfere with a human mid-takeover.

## References

- `docs/specs/issue-109/requirements.md` (R2, R5, R6, R7) and `design.md` (§ Data models,
  § Security design).
- Claude Code — [CLI reference](https://code.claude.com/docs/en/cli-reference) and
  [running Claude Code programmatically](https://code.claude.com/docs/en/headless):
  `--output-format json` with `--json-schema` returns a validated `structured_output`.
- Cursor — [CLI output format](https://cursor.com/docs/cli/reference/output-format):
  `-p --output-format json|stream-json`, no schema enforcement.
- CEL — [cel-python (pure Python, Cloud
  Custodian)](https://github.com/cloud-custodian/cel-python); [Google's official
  CEL-expr-python](https://opensource.googleblog.com/2026/03/announcing-cel-expr-python-the-common-expression-language-in-python-now-open-source.html)
  (wraps the C++ implementation).
