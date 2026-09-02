# Decision 104: a ref minted from configuration carries the resolved GitHub host, and every outbound call reads the host off the ref

- **Status:** proposed
- **Date:** 2026-09-02
- **Work item:** [issue-311](https://github.com/MadaraUchiha-314/the-loop/issues/311)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (design)
- **Refines:** [decision-048](decision-048.md) (a work item's host lives in its ref,
  unwritten for github.com), [decision-042](decision-042.md) (integrations: transport is
  a choice; `gh` inherits the operator's auth)

## Context

Issue-130 put the host into the ref for work items that arrive through an event. Two
families of code never learned about it: refs the **graph mints from `ticketing.github`**
(no host, so github.com), which is where the Slack link for a pending decision comes
from; and **`gh` calls that pass `owner/repo` alone**, which go wherever `gh` happens to
point rather than where the work item is. The owner asked for an audit and for the host
to come from the CLI config or from `gh` itself.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **One resolver, five tiers:** `integrations.github.host` → the host of `api.baseUrl` when it is not the public API → `$GH_HOST` → the `origin` remote of the repository at hand → `github.com`. | The config file is the declaration the-loop documents and validates; `GH_HOST` and the remote are `gh`'s own answers, in `gh`'s own order; nothing a remote says outranks what the operator wrote down. |
| D2 | **The host enters at minting, as a separate argument.** `derive_ref`/`ref_for` take `host`; the `owner/repo` slug contract is unchanged. | A ref's meaning must not depend on the machine reading it (the portable record travels); the explicit host in the ref is decision-048's answer and this keeps it. Smuggling a host into the slug would make one validation accept two shapes. |
| D3 | **Every outbound call reads the host off the ref** through one helper (`--hostname` for `gh api`, `[host/]owner/repo` for `--repo`), written only when the host is not the default. | github.com deployments stay byte-identical; a call site cannot forget the host because it never spells it. |
| D4 | **The API transport derives `https://<host>/api/v3` only when `baseUrl` is the public default.** | An explicit `baseUrl` is the operator's and is honoured verbatim (decision-042); a hosted ref against the default base is the case nobody configured and the one worth deriving. |
| D5 | **`routing.workspace.defaultHost` stays.** | It names a directory, has an explicit key, and the payload's `html_url` wins over it; folding it in would change a documented key for no behaviour. |

## Consequences

**Good.** The Slack link, the ask's link, the portable record's URL, the reviewer's
pull-request list, every comment, reaction, poll read and integration call agree with the
work item's host. A github.com deployment sees no change in any string. Enterprise poll
sources can say `ghe.corp/owner/repo`.

**Costs, accepted.** One more optional key; one `git config` read per in-session graph
command; the-loop's own homes (self-diagnosis, the marketplace, the dashboard origin)
still live on github.com, which is a fact about the-loop and not the operator's GitHub.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| A configurable `DEFAULT_GITHUB_HOST` | The ref would mean different things on different machines |
| `ticketing.github.host` in the harness config | The daemon never reads the harness config (decision-032), and the issue names the CLI config |
| `GH_HOST` in every spawned `gh`'s environment | Per process, not per call; two hosts would need two daemons |
