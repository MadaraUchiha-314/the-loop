# Decision 042: route on hook outcomes; the-loop owns its integrations; MCP by delegation

- **Status:** proposed
- **Date:** 2026-07-28 (revised; first drafted 2026-07-27)
- **Deciders:** @MadaraUchiha-314 (issue #109, PR #110)
- **Work item:** issue-109
- **Spec:** `docs/specs/issue-109/`
- **Extends:** [decision-041](decision-041.md) (nodes and hooks).

## Context

decision-041 makes the PDLC a graph of nodes with entry/exit hook chains. Three questions
it does not answer, all raised by the owner on PR #110:

1. **How do edges decide?** An earlier draft put a CEL expression on every edge; a second
   kept one for a "compound minority". With hooks returning a typed `HookResult`, a condition
   is a *name*, not a formula.
2. **Who calls GitHub, Slack and Jira?** the-loop is now the orchestrator rather than the
   harness, so the choice of transport is its own:

   > *"Given we are changing the architecture significantly and the-loop is now in control
   > (as opposed to claude/cursor), we can take an opinionated choice on certain tools…
   > basically we are not bound by CLI or mcp."*

3. **What if MCP is the only route?** The owner's explicit open question.

There is also a semantic problem no transport choice solves: *"did the reviewer approve?"*
is judgement over free-form English. A gate that keyword-matches `LGTM` pushes process onto
reviewers instead of meeting them where they write — and the owner was explicit that gate
feedback is iterative, may be approval *with* comments, and must be reacted to dynamically.

## Decision

### Routing

1. **Edges route on hook outcomes.** `on: <outcome>` names a value a hook produced —
   `pass`, `approved`, `approved-with-comments`, `changes-requested`. This covers the
   overwhelming majority of transitions.
2. **There is no expression language.** Owner decision on PR #110: *"Remove CEL."* A
   condition that would have wanted an expression becomes a **named hook** returning the
   outcome — `is-docs-only` inspects the work item and returns `docs-only` or `pass`. One
   mechanism instead of two, **zero new runtime dependencies**, and every condition is
   unit-testable like any other hook.
3. **No matching edge parks and escalates** rather than guessing.

   *On human feedback:*

4. **Classification is a hook that produces a fact, never a destination.**
   `classify-feedback` asks the harness with a schema-constrained prompt and returns a closed
   outcome in `data`; the node's **declared** edges do the routing. Judgement where judgement
   is needed; the reachable state set stays fixed and reviewable in a diff.
5. **Indecisive feedback keeps the gate open.** A partial review, a question or an ambiguous
   comment returns `wait`. The gate transitions only on a decisive classification, which is
   how iterative multi-comment review is served without guessing.
6. **Approved-with-comments records the review *in the artifact*.** Owner decision: the
   comments become a `## Review comments` section at the bottom of the generated document
   (design, requirements, …), appended by a `record-feedback` hook, and the work item
   advances. The feedback joins the durable record rather than a side-channel to-do list,
   travels with the document it concerns, and is reviewable in the diff. `validate-artifacts`
   then requires that section on any gated artifact, so a lost review blocks.
7. **Only authorized authors' text is read at all**, and **policy outranks the model**: a
   classification can only classify a human response that actually arrived; it can never
   satisfy an approval that `autonomy.tiers` or `security.review.humanSignOffMinTier`
   reserves for a human.

   *On integrations:*

8. **GitHub: the REST API over stdlib HTTP, not the `gh` CLI.** No binary dependency, no CLI
   version drift, no shell quoting, structured errors, and it works in a bare container.
   Auth from `GH_TOKEN`/`GITHUB_TOKEN`; when absent and `gh` is installed, shell out once to
   `gh auth token` **purely as a credential source** — `gh`'s auth ergonomics without
   depending on `gh` at call time.
9. **Slack: incoming webhooks.** A URL in config or environment. No OAuth app, no scope
   negotiation, no token refresh — the right weight for posting a notification.
10. **Jira: REST API with an API token**, for the same reasons as GitHub.
11. **All integrations are hooks** behind one `Integration.call` interface, so swapping
    GitHub for Jira is swapping which hooks a node declares, not a code path through the
    runtime.
12. **Credentials come from environment or a secret store** — never the repository, graph
    state or logs. `HookContext` carries handles, not values.

    *On MCP:*

13. **When a capability is only reachable via MCP, delegate to the harness.** MCP is a
    protocol for *agents* to call tools: it assumes a model-driven client with a session. the-loop
    already spawns Claude Code / Cursor, both of which are MCP clients with the operator's
    servers configured. An `mcp-call` hook asks the harness — headless, schema-constrained
    output — to perform the call and return the result. the-loop never implements the
    protocol; the harness is the client, which is what it is for.
14. **Implementing a minimal MCP client in the CLI stays on the shelf.** It is feasible
    (stdio JSON-RPC is simple) but adds protocol code, server lifecycle management and
    credential handling to a daemon, for capability reachable via (13). Revisit only if
    delegation latency ever matters — which for notification-shaped calls it will not.

## Consequences

**Positive.**

- Routing reads as a state machine rather than a rules engine: `on: approved` says what it
  means, and there is no second language to learn, version or sandbox.
- Gates understand real review behaviour — partial, approving-with-comments, rejecting-with-
  comments — instead of forcing reviewers into a keyword protocol.
- Determinism is preserved where it matters: judgement is confined to producing a value in a
  closed enum, and every route out of that value is declared.
- No dependency on which CLIs happen to be installed; the-loop's outbound behaviour is the
  same in a developer shell and a bare CI container.
- The MCP answer costs nothing to build and keeps a protocol implementation out of the
  daemon.

**Negative / accepted costs.**

- the-loop now makes outbound HTTP calls and holds credentials — new surface, mitigated by
  (12) and enumerated in `requirements.md` § Security considerations.
- A model call per gate classification. Mitigated by the cheapest tier, a tiny prompt, and
  recording the result so it is not recomputed.
- Harness asymmetry: Claude Code enforces an output schema
  (`-p --output-format json --json-schema`); Cursor's CLI has `-p --output-format json` but
  no schema enforcement, so its classifications embed the schema, validate locally and retry
  within a bound. The Cursor path is measurably weaker and is called out as an open question.
- MCP delegation means an MCP-only integration costs a harness invocation rather than an
  HTTP request.
- Dropping `gh` as the call transport loses its niceties (pagination helpers, auth refresh);
  the credential-source fallback recovers the part that mattered.

## Alternatives considered

- **An expression language on edges** (CEL, on every edge or on a compound minority).
  Rejected by the owner and on merit: it is a second mechanism for something the hook
  contract already expresses, and it would have been the work item's only new dependency.
- **Letting the model choose the next node** (return a node id). Rejected: it makes the
  reachable state set a model output, which is the non-determinism issue #109 exists to
  remove.
- **Keyword-matching approvals** (`/approve`, `LGTM`). Rejected: brittle, and it pushes
  process onto reviewers rather than meeting them where they write.
- **`gh` CLI as the GitHub transport.** Rejected: a binary dependency with version drift and
  shell quoting, for an HTTP call the standard library makes anyway. Kept only as an optional
  credential source.
- **A Slack OAuth app.** Rejected as disproportionate to posting a notification.
- **Implementing MCP in the CLI.** Deferred, not rejected — see (14).

## References

- `docs/specs/issue-109/requirements.md` (R4, R6), `design.md` (§ Tool access, § Edges,
  § The human gate node).
- Claude Code — [CLI reference](https://code.claude.com/docs/en/cli-reference),
  [headless mode](https://code.claude.com/docs/en/headless): `--output-format json` with
  `--json-schema` returns a validated `structured_output`.
- Cursor — [CLI output format](https://cursor.com/docs/cli/reference/output-format):
  `-p --output-format json`, no schema enforcement.
