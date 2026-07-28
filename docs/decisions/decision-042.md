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

8. **The rule: prefer the vendor's official SDK where one exists; where none does, weigh a
   community SDK against the number of endpoints actually used.** Raised by the owner on
   PR #110 (*"github doesn't have python SDK?"*, *"are we using slack python sdk? if not, we
   should"*). Note the starting point: the-loop calls GitHub through the **`gh` CLI** today
   in five modules, so this is a migration whichever transport wins.
9. **Slack: adopt the official `slack-sdk`.** Its `slack_sdk.webhook.WebhookClient` is how an
   incoming webhook is *properly* called — retry with exponential backoff, proxy support, SSL
   context — and it declares **zero required runtime dependencies**. The earlier
   "webhook *or* SDK" framing was a false dichotomy: the SDK is the client for the webhook.
10. **GitHub: thin REST over stdlib HTTP — because there is no official SDK to adopt.**
    GitHub's own documentation lists every Python library as third-party and not maintained
    by GitHub; official Octokit covers JS/Ruby/.NET only. The community options cost
    `pynacl` + `requests` + `pyjwt[crypto]` + `urllib3` (PyGithub, including a compiled
    extension used only for secrets encryption the-loop never performs) or
    `anyio` + `httpx` + `hishel` + `pydantic` + schemas (githubkit), to wrap roughly ten
    endpoints — against a current total runtime footprint of `pyyaml`. If an SDK is taken
    anyway, **githubkit** is the better choice: typed and generated from GitHub's OpenAPI
    spec, so it does not drift. Auth: `GH_TOKEN`/`GITHUB_TOKEN`, falling back to one
    `gh auth token` call **purely as a credential source**.
11. **Jira: thin REST with an API token** — Atlassian publishes no official Python SDK
    either, so the GitHub reasoning applies unchanged.
12. **All integrations are hooks** behind one `Integration.call` interface, so swapping
    GitHub for Jira is swapping which hooks a node declares, not a code path through the
    runtime.
13. **Credentials come from environment or a secret store** — never the repository, graph
    state or logs. `HookContext` carries handles, not values.

    *On MCP:*

14. **When a capability is only reachable via MCP, delegate to the harness.** MCP is a
    protocol for *agents* to call tools: it assumes a model-driven client with a session. the-loop
    already spawns Claude Code / Cursor, both of which are MCP clients with the operator's
    servers configured. An `mcp-call` hook asks the harness — headless, schema-constrained
    output — to perform the call and return the result. the-loop never implements the
    protocol; the harness is the client, which is what it is for.
15. **Implementing a minimal MCP client in the CLI stays on the shelf.** It is feasible
    (stdio JSON-RPC is simple) but adds protocol code, server lifecycle management and
    credential handling to a daemon, for capability reachable via (14). Revisit only if
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
  (13) and enumerated in `requirements.md` § Security considerations.
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
- **`gh` CLI as the GitHub transport** (the status quo — five modules use it today).
  Rejected: a binary dependency with version drift and shell quoting, for an HTTP call the
  standard library makes anyway. Kept only as an optional credential source.
- **A GitHub Python SDK** (PyGithub or githubkit). Rejected on dependency weight, not on
  quality: five or six transitive packages — one compiled — to wrap ~10 endpoints, against a
  current footprint of one. Revisit if the endpoint surface grows substantially.
- **Hand-rolling the Slack webhook call.** Rejected once the owner pointed at the official
  SDK: `slack-sdk` is free in dependency terms and already solves retry, backoff and proxy
  handling correctly.
- **A Slack OAuth app.** Rejected as disproportionate to posting a notification; the official
  SDK's webhook client gives the ergonomics without the app.
- **Implementing MCP in the CLI.** Deferred, not rejected — see (15).

## References

- `docs/specs/issue-109/requirements.md` (R4, R6), `design.md` (§ Tool access, § Edges,
  § The human gate node).
- Claude Code — [CLI reference](https://code.claude.com/docs/en/cli-reference),
  [headless mode](https://code.claude.com/docs/en/headless): `--output-format json` with
  `--json-schema` returns a validated `structured_output`.
- Cursor — [CLI output format](https://cursor.com/docs/cli/reference/output-format):
  `-p --output-format json`, no schema enforcement.
