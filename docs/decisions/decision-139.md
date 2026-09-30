# Decision 139: the daemon holds one GitHub token and speaks PyGithub — no `gh` in any process of the-loop's

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-09-30
- **Work item:** [issue-442](https://github.com/MadaraUchiha-314/the-loop/issues/442)
- **Deciders:** MadaraUchiha-314 (the ask), the-loop (design)
- **Supersedes in part:** [decision-023](decision-023.md) (the operator's own `gh`
  credentials — the *identity* half stands: the-loop still posts under a real account
  whose login it reads back; the *mechanism* half, `gh` as the credential holder, is
  replaced) · **Refines:** [decision-041](decision-041.md) (breaking config changes ride a
  versioned migration), [decision-104](decision-104.md) (the host is the ref's),
  [decision-106](decision-106.md) (issues-disabled is a permanent per-scope condition)

## Context

Every GitHub read and write the daemon makes spawns the operator's `gh` binary, which a
`pip install` cannot carry and a container cannot log in. The vendor-SDK report
(issue-212) named PyGithub the technically best swap and deferred it on one question:
where the token comes from. Issue-442 asks for the swap and for every operation to
survive it.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The credential is the token `integrations.github.api.tokenEnv` names**, read from the process environment at call time; no `gh auth token` bridge, no keychain, no file of the-loop's own. | It is the source the API transport, the attachment fetch and `env.file` (issue-318) already use; one credential, one place. A bridge through `gh` would hide a missing token until the one box without `gh`. |
| D2 | **One module, `ghapi.GitHubClient`, on PyGithub**, with the twelve operations the-loop performs as methods and one exception type; no caller imports PyGithub. | The seam every caller already had (`runner=`) becomes `client=`; the library is a detail behind it, which is what lets a GitHub App auth land later without touching callers. |
| D3 | **REST typed objects where they cost nothing extra, PyGithub's `graphql_query` for the two things REST lacks** — the PR listing with `closingIssuesReferences` and a reaction on a node id. | The PR listing *is* the query `gh pr list --json` ran, so issue-93's linkage and every shape survive; the reaction mutation is the one `gh api graphql` sent. |
| D4 | **Comment ids stay GraphQL node ids** on the poll path (`node_id` off the REST document). | Issue-246's constraint: a numeric id would re-forward every operator's baselined thread on upgrade. |
| D5 | **No rate-limit sleep**: `retry=2` at the connection level, the caller's timeout, never PyGithub's `GithubRetry`. | A poll cycle or a dispatch thread must fail loudly in seconds, as a failed `gh` did, not park until a window resets. |
| D6 | **`integrations.github.transport` and `.cli` are retired** behind config version `0.11.0` and a migration that removes them and notes the token. | There is one transport; a key that quietly does nothing is the failure decision-041 forbids. |
| D7 | **The agent's `gh` is untouched.** | `integrations` has always governed the control plane only; the harness's tooling is the harness's. |

## Consequences

**Good.** `pip install the-loopy-one` plus a token is a complete deployment; no
subprocess per call; one HTTP session per host; pagination, retries and error typing come
from a maintained library; the environment table loses a binary.

**Costs, accepted.** Six transitive packages join the wheel (`requests`, `urllib3`,
`pynacl`, `pyjwt`, `typing-extensions`, `Deprecated`); the daemon now holds a secret the
operator must scope and rotate (the docs name the minimum scopes); an upgrade across
`0.11.0` needs the migration and a token before the daemon posts anything again — which
is loud by design (A8).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Extend the stdlib `urllib` API transport to every call | Re-owns pagination, retries, GraphQL and error typing the ticket asked to take from PyGithub |
| Keep `gh auth token` as a fallback | Re-introduces the binary in the one place that hides its absence (D1) |
| Keep `transport: cli` accepted and ignored | Decision-041; `additionalProperties: false` refuses it anyway (D6) |
| REST `/pulls` plus a call per PR for linkage | N+1 requests per cycle; the GraphQL listing is one (D3) |
| PyGithub's default `GithubRetry` | Sleeps until the rate-limit reset — up to an hour inside a poll cycle (D5) |
| Per-host tokens now | Nothing asked; the config can grow a map without a caller changing |
