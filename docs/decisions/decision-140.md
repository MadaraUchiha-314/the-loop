# Decision 140: the coding harness reaches GitHub through `the-loop`'s verbs — service first, in-process otherwise

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-09-30
- **Work item:** [issue-447](https://github.com/MadaraUchiha-314/the-loop/issues/447)
- **Deciders:** MadaraUchiha-314 (the ask), the-loop (design)
- **Refines:** [decision-139](decision-139.md) (D7, "the agent's `gh` is untouched",
  is superseded for the work item's lifecycle; the daemon's own client is unchanged) ·
  [decision-078](decision-078.md) (`ask` runs in-process) ·
  [decision-058](decision-058.md) (the service is the CLI's execution path)

## Context

Decision-139 removed `gh` from every process of the-loop's, and left the agent's own
session alone. That session still used `gh`, or a GitHub MCP server, to read its ticket,
comment, open, inspect and merge its pull request, and open tickets. So every session
still needed a `gh` login or a token of its own, and the `PostToolUse` hook parsed `gh`'s
output to learn which pull request had been opened.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Seven verbs over the existing client:** `comment`, `ticket show\|create`, `pr create\|status\|threads\|merge`, plus `sessions link-pr --discover`. Core lives in `core.github_ops`, with a route and an MCP tool for each. | These are exactly the GitHub acts the skill tells the agent to perform on a work item. Each is one named operation with a contract, not a pass-through. |
| D2 | **`harness_routed`: through the service when one answers `/health`, otherwise in-process on `integrations.github.api.tokenEnv`, with a stderr note. It never auto-starts a service.** | The verbs' only state is GitHub's. What the service adds is the daemon's token, so the session holds none. In a cloud checkout there is no daemon, and an auto-started service would only copy the session's `GH_TOKEN` into a second process. `ask` already runs in-process for the same reason. The note keeps the fallback from being the silent kind decision-058 forbids. |
| D3 | **Work-item and pull-request scoped routes, never a generic `/github` proxy.** | A proxy would grant every call the token can make, say nothing in the contract, and put the merge gate out of reach. |
| D4 | **`pr merge` is gated by `routing.mergeOnApproval`, read from the executing process's config.** It checks no approval of its own. | The policy lives in one place, and routed through the service it is the daemon's. A session cannot bring a policy along. The graph's `human-approval` node decides approval, which GitHub's `reviewDecision` does not capture: this repository's owner approves by comment. |
| D5 | **`comment` publishes `comment.agent` with `record: true`.** | The ledger stamps the marker and the envelope centrally. The room hears the comment once, and the ingress drops the enveloped copy. A new event type would split one stream subscribers already understand. |
| D6 | **`pr create` links what it opens. The hook becomes trigger-agnostic** (a push or any PR-creating call runs `link-pr --discover`) and parses no output. | The owner's scope addition on the ticket. The primary path needs no hook, and the hook becomes a safety net that knows nothing of `gh`. |
| D7 | **A verb addresses github.com and the operator's own host only** (`ghhost.github_host`); any other host is a caller mistake, refused before a request. | A host-shaped string in a ref or URL would otherwise make the service send the daemon's token to that host (`base_for` derives `https://<host>/api/v3` against the public default). Found in self-review. |

## Consequences

**Good.** A session needs neither `gh` nor, where a daemon runs, a token. The marker
can no longer be forgotten on any comment the loop posts. The merge policy is enforced by
code instead of by prompt. A PR opened by hand or by MCP is still recorded.

**Costs, accepted.** A second exception to "the service is the only execution path"
(D2). One more GitHub request after every `git push` in a hooked session (idempotent).
Seven routes and seven MCP tools to keep in the contract. Closing a ticket and resolving
a review thread stay the harness's own acts, since no verb covers them yet.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Route like every core verb (`routed`: auto-start, fail closed) | Breaks every cloud session, which has no daemon to hold a token. |
| Always in-process, like `ask` | Every session would need a token even where the daemon already holds one. That is the problem the ticket names. |
| A generic `/github` proxy route or MCP tool | D3. |
| Check GitHub's `reviewDecision` before merging | D4. It refuses merges the loop's own gate approved. |
