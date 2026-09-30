---
type: requirements
phase: requirements-definition
workItem: "issue-447"
status: draft
approvedBy: []
collaborators: [architect, engineer, approver]
riskTier: 3                  # new verbs and control-plane routes over the existing client; no new credential, no config key
overrides: {}
---

# Requirements: the coding harness reaches GitHub through the-loop's verbs

> Phase 1 of 3 (requirements → design → tasks). Tier 3 (`human-approves-pr`): new
> `the-loop` verbs, control-plane routes and MCP tools over the client issue-442 built. It
> adds no credential, no configuration key and no schema change.

## Introduction

[Issue #447](https://github.com/MadaraUchiha-314/the-loop/issues/447) follows
[#442](https://github.com/MadaraUchiha-314/the-loop/issues/442). After #442, no process of
the-loop's uses `gh`: the daemon, the service and every `the-loop` verb reach GitHub
through `ghapi.GitHubClient` on PyGithub, under the token
`integrations.github.api.tokenEnv` names. The **coding harness** still uses `gh`. That is
the agent in its Claude Code or Cursor session. The skill and the slash commands say
"GitHub via `gh`/MCP", and `hooks/the-loop-link-pr.py` watches the agent's shell for
`gh pr create`. So every session still needs a `gh` login or a GitHub token of its own.
That is the deployment problem #442 removed from the daemon, moved one hop.

This is what the harness still reaches GitHub for, and what exists for it today:

| The agent needs to… | Today | `the-loop` verb |
|---|---|---|
| read the ticket's body, comments and attachments at session start | `gh`/MCP | **missing** → `ticket show` |
| post a free-form comment (spec-gate replies, the completion summary, the reviewer briefing, a decision record) | `gh`/MCP, marked by hand | **missing** → `comment` |
| open the pull request | `gh pr create` | **missing** → `pr create` |
| create a ticket (`/the-loop:create-ticket`) | `gh`/MCP | **missing** → `ticket create` |
| read PR review threads and CI status during `needs-review` | `gh`/MCP | **missing** → `pr status`, `pr threads` |
| merge on approval (`routing.mergeOnApproval: true`) | `gh pr merge` | **missing** → `pr merge` |
| record the PR it opened | `sessions link-pr`, run by the hook after `gh pr create` | exists; detection is a `gh` heuristic → `link-pr --discover` |
| ask a human; tell the graph a node is done; grant a collaborator; read channel records | `ask`, `graph complete`, `add-collaborator`, `channels records` | exist, unchanged |

The owner added one item on the ticket
([comment](https://github.com/MadaraUchiha-314/the-loop/issues/447#issuecomment-5915766741)):
`sessions link-pr --discover` finds the open pull requests whose head is the checkout's
branch and links them, and the `PostToolUse` hook stops parsing `gh` output and runs that
instead.

## Requirements

### Requirement 1 — a verb for every GitHub act the harness performs on a work item

**User story:** As an operator running the-loop's sessions in a container or a cloud
checkout, I want the agent to do its GitHub work through `the-loop` verbs, so that no
session needs `gh` installed or logged in.

#### Acceptance criteria (EARS)

1.1 WHEN the agent runs `the-loop comment --work-item <ref> --body <text>` (or
`--body-file <path|->`) THEN the system SHALL post the text on the work item as a
**marked, enveloped** comment and publish it on the bus, so a channel subscribed to
`comment.agent` receives it. It SHALL print the comment's URL. An empty body SHALL be
refused with exit 2 before any request.

1.2 WHEN the agent runs `the-loop ticket show <ref>` THEN the system SHALL print, as JSON,
the item's number, title, body, state, labels, author, URL, whether it is a pull request,
its comments (conversation, and for a pull request also reviews and review comments, in
time order, each with author, body, time, URL and kind), and the attachment URLs found in
the body and comments.

1.3 WHEN the agent runs `the-loop ticket create --repository <[host/]owner/repo> --title
<t> --body <b>|--body-file <p> [--label <l>]…` THEN the system SHALL open the issue and
print its ref and URL.

1.4 WHEN the agent runs `the-loop pr create --work-item <ref> --title <t> --body
<b>|--body-file <p> [--head <branch>] [--base <branch>] [--repository <owner/repo>]
[--draft]` THEN the system SHALL open the pull request and link it to the work item in the
same act, exactly as `sessions link-pr` would. It SHALL print the PR's ref and URL.
`--head` SHALL default to the checkout's current branch. `--base` SHALL default to the
repository's default branch. `--repository` SHALL default to the work item's repository.

1.5 IF the pull request is opened but linking it fails (for example, no session is
recorded for the work item) THEN the verb SHALL still exit 0, print the PR's ref and URL,
and say on stderr that it was not linked and why. A PR that was opened is never reported
as a failure.

1.6 WHEN the agent runs `the-loop pr status <pr>` THEN the system SHALL print, as JSON,
the PR's state, whether it is merged and mergeable, its head SHA, draft flag, and one
roll-up of its checks (`success`, `failure`, `pending` or `none`) over both check runs and
commit statuses, with the failing and pending check names.

1.7 WHEN the agent runs `the-loop pr threads <pr>` THEN the system SHALL print, as JSON,
the PR's **unresolved** review threads: id, path, line, outdated flag, and each comment's
author, body, time and URL. `--all` SHALL include resolved threads.

1.8 WHEN the agent runs `the-loop pr merge <pr> [--method merge|squash|rebase] [--sha
<reviewed-head>]` THEN the
system SHALL merge the PR **only if** the governing CLI config's
`routing.mergeOnApproval` is `true` (the default). WHEN it is `false`, THEN the verb SHALL
refuse with exit 1, merge nothing, and name the key. WHEN `--sha` is given THEN it SHALL
be sent as the expected head, so GitHub refuses the merge if the branch moved after the
review. WHEN GitHub answers that it did not merge THEN the verb SHALL exit 1.

1.9 A `<pr>` argument SHALL accept a ref (`github:[host/]owner/repo#n`), a pull-request
URL, or a bare number together with `--work-item` (resolved against the work item's
repository, as `sessions link-pr` does). Anything else SHALL be refused with exit 2 before
any request.

### Requirement 2 — the credential stays where it already is

**User story:** As an operator, I want the agent's session never to need a GitHub token
when a daemon is running on the box, and to need only `GH_TOKEN` when none is.

#### Acceptance criteria (EARS)

2.1 WHEN a control-plane service is reachable THEN every verb of R1 SHALL execute in the
service, whose process holds the token. The CLI process SHALL send only the verb's
arguments.

2.2 WHEN no service is reachable THEN the verb SHALL execute in-process on the token
`integrations.github.api.tokenEnv` names (default `GH_TOKEN`, then `GITHUB_TOKEN`), as
`ask` does. It SHALL NOT auto-start a service to do so. It SHALL say on stderr that it ran
in-process, so the fallback is never silent.

2.3 WHEN it runs in-process and no token is set THEN the verb SHALL exit 1 with a message
naming the variables to set, and make no request.

2.4 The token SHALL never appear in a verb's output, an error string the-loop composes,
or the event log. This is issue-442's A1, unchanged.

2.5 A verb SHALL address only github.com and the operator's own GitHub host (the
configured `integrations.github.host`, an enterprise `baseUrl`'s host, `$GH_HOST`). IF a
ref, URL or repository names any other host THEN the verb SHALL refuse it with exit 2
(HTTP 400) before any request, because the token would otherwise be sent to that host.

2.6 WHEN a running service does not serve a verb's route (a service older than the CLI)
THEN the verb SHALL run in-process with a note naming the restart, rather than fail.

### Requirement 3 — the service and MCP expose the same operations

**User story:** As a harness that prefers MCP to a shell, I want the same operations as
tools on the service's `/mcp` endpoint.

#### Acceptance criteria (EARS)

3.1 The control-plane service SHALL expose each operation of R1 as a route under
`/api/v1`, declared in the authored OpenAPI contract
(`docs/api-specs/openapi/the-loop.v1.yaml`). The routes SHALL be **work-item and
pull-request scoped** (the ref is a parameter), not a generic GitHub proxy. Both instance
roles (worker and manager) SHALL serve them.

3.2 The service's MCP endpoint SHALL expose each operation as a tool with the same
arguments. `pr merge` is included, under the same `mergeOnApproval` gate as the verb.

3.3 A service error SHALL map onto the CLI's existing conventions: a caller mistake is
exit 2, a GitHub refusal or a missing token is exit 1.

### Requirement 4 — `sessions link-pr --discover`, and a hook that no longer reads `gh`

**User story:** As the plugin, I want to record a PR against its work item however it was
opened, without parsing any tool's output.

#### Acceptance criteria (EARS)

4.1 WHEN `the-loop sessions link-pr --work-item <ref> --discover` runs THEN the system
SHALL list the **open** pull requests whose head is the checkout's current branch in the
checkout's `origin` repository (the work item's repository when the origin is not a GitHub
remote), and link each one found. Finding none SHALL exit 0 and say so. `--discover` and
`--pull-request` SHALL be mutually exclusive, and exactly one SHALL be given.

4.2 `--discover` SHALL accept `--branch` and `--repository` overrides. A detached HEAD
with no `--branch` SHALL be refused with exit 2.

4.3 WHEN a `Bash` tool call runs `git push` or a command that creates a pull request, or
a tool whose name ends in `create_pull_request` completes, THEN
`hooks/the-loop-link-pr.py` SHALL run `the-loop sessions link-pr --work-item <ref>
--discover`. It SHALL no longer look for `gh pr create`, and SHALL no longer parse a URL
out of a tool's response. It SHALL stay stdlib-only, exit 0 on every path, and resolve
the work item exactly as today.

4.4 A `Bash` call that ran `the-loop pr create` SHALL NOT trigger the hook, because that
verb links its own PR.

### Requirement 5 — the harness's instructions name the verbs

5.1 The skill (`SKILL.md` and its `reference/` docs) and the slash commands
(`work-on`, `execute-tasks`, `finish-tasks`, `create-ticket`) SHALL name the verbs of R1
where they now say "GitHub via `gh`/MCP". `gh` SHALL remain only as the stated fallback
when the CLI is not installed.

5.2 Each new verb SHALL have its page under `docs/cli/commands/`. The capability docs it
changes SHALL be updated in the same PR.

## Non-functional requirements

- **No new dependency.** Everything is built on `ghapi.GitHubClient` and the existing
  stdlib service client.
- **Bounded requests.** `pr status` makes at most three GitHub requests
  (the PR, its check runs, its combined status). `pr threads` makes one GraphQL request
  per 100 threads.
- **Hermetic tests.** No test touches the network. The verbs are tested in-process over
  a fake client, and the client methods over the replaying connection.

## Security considerations

The verbs add **writes the agent can trigger** (a comment, an issue, a pull request, a
merge). The token that performs them is the one the daemon or `GH_TOKEN` already holds,
so no new credential or scope enters the system. The design's security section carries
the mechanisms, and the testing plan's T7 row carries the negative tests.

| # | Abuse case | Required outcome |
|---|------------|------------------|
| A1 | a token leaks through a verb's output, an error, or the event log | never: issue-442's translation boundary is reused, and every message is the status plus GitHub's text |
| A2 | a prompt-injected session merges a PR the operator wanted a human to merge | `pr merge` is refused when `routing.mergeOnApproval` is `false`, read from the **service's** config when routed. The agent cannot override it by flag or argument, and the MCP tool is gated identically |
| A3 | hostile coordinates (owner, repo, number, branch, host) reach a URL path or a GraphQL variable, or a caller-named host receives the token | every coordinate passes the client's shape checks before any request. A branch name is validated against git's ref grammar subset, and GraphQL values travel only as variables. A host must be github.com or the operator's own (R2.5), so neither a prompt-injected agent nor a cross-site request to a loopback route can point the daemon's token at another server |
| A4 | a comment the agent posts is read back as human input, and resumes its own session | every `comment` body is stamped with the self-authored marker **centrally** and carries an envelope, so the ingress never re-publishes it (issue-104, issue-309 A10) |
| A5 | an in-process fallback quietly runs where the operator expected the service | the fallback is printed on stderr each time, and happens only when no service answers `/health` |
| A6 | the hook turns every `git push` into a shell-injection surface | the hook passes only the resolved work-item ref in an argv list, with no shell. It reads nothing out of the tool's response any more |
| A7 | `ticket show` hands untrusted text to the agent as instructions | the output is data, labelled as such by the skill. The verb interprets nothing, and fetches no attachment content (links only, decision-135) |

## Out of scope

- Jira (the reserved integration block).
- What the daemon itself does with GitHub (#442 covers it).
- `git` itself (clone, push), which uses a git credential, not a GitHub API token.
- Removing the `PostToolUse` hook. It stays as the safety net for PRs opened by hand or
  by MCP (issue note).
- Resolving review threads from a verb. The reviewing procedure's "resolve the thread"
  stays the harness's act until a follow-up asks for it.
