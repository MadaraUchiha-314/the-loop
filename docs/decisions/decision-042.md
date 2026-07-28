# Decision 042: route on hook outcomes; the-loop owns its integrations; MCP by delegation

- **Status:** proposed
- **Date:** 2026-07-28 (revised; first drafted 2026-07-27)
- **Deciders:** @MadaraUchiha-314 (issue #109, PR #110)
- **Work item:** issue-109
- **Spec:** `docs/specs/issue-109/`
- **Extends:** [decision-041](decision-041.md) (nodes and hooks).
- **Bounded by:** [decision-030](decision-030.md) — the language stays Python. The
  observation that GitHub's official SDK exists for JavaScript prompted *"should we move the
  whole project to node/bun + typescript?"* on PR #110; decision-030 had already analysed
  exactly that and is re-affirmed there, so this record chooses a transport, not a runtime.

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

8. **Two call planes.** the-loop's **control plane** — the calls its own hooks make — is
   governed here. The agent's **work plane** is not: *"anything that the LLM uses can be
   through CLI, MCP or API as LLM is free to do whatever it wants."* the-loop does not police
   how the harness reaches services; doing so would buy nothing (the agent is already trusted
   to write code) and would break the takeover property the tmux runner exists for.
9. **Transport is configurable per integration, not decided once by us.** Owner direction:
   *"How to interface with external services should be configurable. We should support
   SDK+API and CLI, so people can choose based on what the-loop implements."* `api` and `cli`
   where both are meaningful; `sdk` where an official one exists. `transport: auto` resolves
   in a documented order (token → binary) and **fails closed naming both remedies** when
   neither is present; an explicit transport is honoured verbatim and fails rather than
   silently degrading.
   *This also fixes the migration story.* the-loop reaches GitHub through the **`gh` CLI**
   today in five modules, with `ghBinary` already a configured value in three places. Making
   transport a choice turns a risky big-bang rewrite into **keeping what works as the `cli`
   provider and adding `api` beside it**.
10. **The rule for defaults: prefer the vendor's official SDK where one exists; where none
    does, weigh a community SDK against the number of endpoints actually used.** Raised by
    the owner (*"github doesn't have python SDK?"*, *"are we using slack python sdk? if not,
    we should"*). These are now *defaults*, not the only option.
11. **Slack default: the official `slack-sdk`.** Its `slack_sdk.webhook.WebhookClient` is how
    an incoming webhook is *properly* called — retry with exponential backoff, proxy support,
    SSL context — and it declares **zero required runtime dependencies**. The earlier
    "webhook *or* SDK" framing was a false dichotomy: the SDK is the client for the webhook.
12. **GitHub default: `auto`, preferring thin REST over stdlib HTTP — because there is no
    official SDK to adopt.**
    GitHub's own documentation lists every Python library as third-party and not maintained
    by GitHub; official Octokit covers JS/Ruby/.NET only. The community options cost
    `pynacl` + `requests` + `pyjwt[crypto]` + `urllib3` (PyGithub, including a compiled
    extension used only for secrets encryption the-loop never performs) or
    `anyio` + `httpx` + `hishel` + `pydantic` + schemas (githubkit), to wrap roughly ten
    endpoints — against a current total runtime footprint of `pyyaml`. If an SDK is taken
    anyway, **githubkit** is the better choice: typed and generated from GitHub's OpenAPI
    spec, so it does not drift. Auth: `GH_TOKEN`/`GITHUB_TOKEN`, falling back to one
    `gh auth token` call **purely as a credential source**.
13. **Jira default: thin REST with an API token** — Atlassian publishes no official Python
    SDK either, so the GitHub reasoning applies unchanged; a `cli` transport is supported for
    parity.
14. **Providers declare their capabilities, and the runtime checks them at load time.**
    Transports are not equally capable, and pretending otherwise is how this design would
    rot. A graph needing an operation the configured transport lacks **fails at startup**,
    naming the operation, the target and both fixes — not mid-traversal. One **shared
    contract test suite** runs against every provider, so `api` and `cli` are verified to
    behave identically rather than assumed to.
15. **Transport never changes the verdict.** The `HookResult` a hook returns is
    transport-independent by construction: swapping transports changes how a side effect was
    performed, never whether a node advances.
16. **All integrations are hooks** behind one `Integration.call` interface, so swapping
    GitHub for Jira is swapping which hooks a node declares, not a code path through the
    runtime.
17. **Credentials come from environment or a secret store** — never the repository, graph
    state or logs. `HookContext` carries handles, not values.

    *On MCP:*

18. **When a capability is only reachable via MCP, delegate to the harness.** MCP is a
    protocol for *agents* to call tools: it assumes a model-driven client with a session. the-loop
    already spawns Claude Code / Cursor, both of which are MCP clients with the operator's
    servers configured. An `mcp-call` hook asks the harness — headless, schema-constrained
    output — to perform the call and return the result. the-loop never implements the
    protocol; the harness is the client, which is what it is for.
19. **Implementing a minimal MCP client in the CLI stays on the shelf.** It is feasible
    (stdio JSON-RPC is simple) but adds protocol code, server lifecycle management and
    credential handling to a daemon, for capability reachable via (18). Revisit only if
    delegation latency ever matters — which for notification-shaped calls it will not.

## Consequences

**Positive.**

- Routing reads as a state machine rather than a rules engine: `on: approved` says what it
  means, and there is no second language to learn, version or sandbox.
- Gates understand real review behaviour — partial, approving-with-comments, rejecting-with-
  comments — instead of forcing reviewers into a keyword protocol.
- Determinism is preserved where it matters: judgement is confined to producing a value in a
  closed enum, and every route out of that value is declared.
- Operators pick the transport that fits their environment: `gh auth` (including enterprise
  SSO) where that is the path of least resistance, a token where a bare container is.
- The existing `gh` code becomes the `cli` provider instead of being deleted, so adopting the
  API transport is additive and reversible rather than a one-way migration.
- The MCP answer costs nothing to build and keeps a protocol implementation out of the
  daemon.

**Negative / accepted costs.**

- the-loop now makes outbound HTTP calls and holds credentials — new surface, mitigated by
  (17) and enumerated in `requirements.md` § Security considerations.
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
- **A single mandated transport per target** (the earlier draft: GitHub REST only, `gh`
  rejected outright). Superseded by the owner: mandating one transport ignores that `gh auth`
  is genuinely the better path in some environments and a token in others, and it would have
  thrown away five working modules. `gh` is now the `cli` provider, not a rejected option.
- **A GitHub Python SDK** (PyGithub or githubkit). Rejected on dependency weight, not on
  quality: five or six transitive packages — one compiled — to wrap ~10 endpoints, against a
  current footprint of one. Revisit if the endpoint surface grows substantially.
- **Hand-rolling the Slack webhook call as the only option.** Superseded: `slack-sdk` is the
  default because it is official, dependency-free and already solves retry/backoff/proxy —
  but a raw `webhook` transport remains available for operators who want no dependency at all.
- **Constraining how the agent reaches external services.** Rejected: the work plane is the
  harness's and the operator's business, and policing it would break session takeover.
- **A Slack OAuth app.** Rejected as disproportionate to posting a notification; the official
  SDK's webhook client gives the ergonomics without the app.
- **Implementing MCP in the CLI.** Deferred, not rejected — see (19).

## References

- `docs/specs/issue-109/requirements.md` (R4, R6), `design.md` (§ Tool access, § Edges,
  § The human gate node).
- Claude Code — [CLI reference](https://code.claude.com/docs/en/cli-reference),
  [headless mode](https://code.claude.com/docs/en/headless): `--output-format json` with
  `--json-schema` returns a validated `structured_output`.
- Cursor — [CLI output format](https://cursor.com/docs/cli/reference/output-format):
  `-p --output-format json`, no schema enforcement.
