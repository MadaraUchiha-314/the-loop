# Decision 142: the daemon reaches Jira through the pycontribs `jira` SDK, one site per deployment

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-06
- **Work item:** [issue-475](https://github.com/MadaraUchiha-314/the-loop/issues/475)
- **Deciders:** MadaraUchiha-314 (the ask, `design-approval`), the-loop (design)
- **Supersedes:** [decision-042](decision-042.md) point 13 ("Jira default: thin REST
  with an API token; a `cli` transport is supported for parity")
- **Refines:** [decision-139](decision-139.md) (one client per tracker, credentials named
  by environment variable and read at call time)
- **Spec:** [`docs/specs/issue-475/design.md`](../specs/issue-475/design.md) §C3, §C4,
  §Trade-offs 1 and 3

## Context

Decision-042 point 13 chose thin REST for Jira, reasoning that Atlassian publishes no
official Python SDK, so the reasoning that then kept GitHub on hand-written REST applied
unchanged. That reasoning was reversed for GitHub by decision-139: a hand-written client
rebuilt pagination, retries and auth modes that a maintained library already had. Jira
needs more of that than GitHub did. It has three authentication modes (Basic with an
email and API token on Cloud, the scoped-token gateway at
`https://api.atlassian.com/ex/jira/<cloudId>`, and a Bearer personal access token on
Data Center). It has two search endpoints (`/rest/api/3/search/jql` on Cloud, `/search`
on Data Center), and two body formats (ADF on REST v3, wiki markup on REST v2).

Issue-442 also retired every `cli` transport, so the `transport` and `cli` keys of the
old `integrations.jira` stub promise something nothing runs.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The pycontribs `jira` SDK** (`jira>=3.10,<4`), wrapped by one `jiraapi.JiraClient`. No other module imports the SDK. | It already handles the three auth modes, pagination, both search endpoints, transitions and retries. It is pure Python; over the existing lock it adds `defusedxml`, `oauthlib`, `requests-oauthlib` and `requests-toolbelt` (`requests` already arrives through PyGithub). It is a plain `dependencies` entry: no extras. |
| D2 | **REST v3 with ADF on Cloud, REST v2 with wiki markup on Data Center.** `deployment: cloud \| cloud-scoped \| data-center` picks the server URL, the auth mode and the REST version. | Data Center has no v3. A comment is written in the format its server renders. |
| D3 | **One Jira site per deployment** (`integrations.jira.site`). A ref still names its site, and a ref on another site fails closed. | Multi-site would put a site into every allow-list entry, project map and spec id, and nothing requires it. Lifting this later breaks no ref. |
| D4 | **A project → repository map** (`integrations.jira.projects.<KEY>.repository`). A project with no repository is mirror-only: a room, never a work-item source. | A Jira ticket has no repository, but its spec chain, worktree and pull requests need one. A ticket field is writable by any Jira user, so the mapping lives in the operator's config. |
| D5 | **Credentials are named by environment variable only** (`api.emailEnv`, `api.tokenEnv`), read at call time, never logged. The schema rejects a value that looks like a literal token or email. | The same rule decision-139 set for GitHub; rotating a token needs no restart. |
| D6 | **`integrations.jira.transport` and `.cli` are retired** at config `0.12.0`; `the-loop migrate-config` removes them. | Issue-442 retired CLI transports; a key that quietly does nothing is worse than an error. |

## Consequences

**Good.** One client holds the Jira credential, mirroring `ghapi.GitHubClient`, and the
`JiraProvider` integration joins the shared provider contract suite (decision-042
point 14). A GitHub-only deployment loads nothing from the SDK: the import is lazy.

**Costs, accepted.** Four more transitive packages in the lock. The SDK logs request
details through its own logger, so `jiraapi` installs a redaction filter on it, and error
messages are scrubbed of the `Authorization` header and the account email before they
leave the client.
