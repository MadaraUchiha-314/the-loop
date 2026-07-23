# Report: how the-loop queries GitHub via `gh` for issues/PRs

> Requested in [issue #60](https://github.com/MadaraUchiha-314/the-loop/issues/60):
> *what filters are we using, and how are we making sure that queries are performant?*
> Audited at the current `main` (post-v0.11.0). This is a point-in-time report, not a
> living capability doc.

## Scope and method

Audit of every place the codebase itself issues a **read query** against GitHub to
discover issues/PRs and their activity. Method: repo-wide search for `gh` invocations
across `cli/`, `skills/`, `commands/`, `hooks/`, and `.github/`.

Findings on scope:

- **Exactly one module queries GitHub: the poller's GitHub provider**
  ([`cli/the_loop/poller/github.py`](../../cli/the_loop/poller/github.py)). It is the
  deliberate single choke point — the poller core, dispatcher, registry and CLI are
  provider-agnostic ([decision-022](../decisions/decision-022.md)).
- The **webhook receiver queries nothing**: it is push-based ingress, GitHub calls us
  ([webhook-triggers](../capabilities/webhook-triggers.md)). Zero API reads.
- The **release workflow** uses `gh release create` — a write, out of scope here.
- The **skill/agent layer** references "GitHub via `gh`" only as free-form tooling for
  the harness agent (creating tickets, PRs, comments during the workflow); it
  prescribes no fixed discovery queries. The programmatic query surface is the poller.

## The three queries

`GhClient` shells out to the user's own authenticated `gh` CLI (no token of its own,
inherits `gh`'s auth/enterprise config) and parses `--json` stdout. Per poll cycle it
runs, for each configured repo:

**1. Labelled open issues** — `GhClient.list_labeled_issues`

```text
gh issue list --repo OWNER/REPO --label <label> --state open --limit 200 \
  --json number,title,labels,updatedAt,url,author
```

**2. Labelled open PRs** — `GhClient.list_labeled_prs`

```text
gh pr list --repo OWNER/REPO --label <label> --state open --limit 200 \
  --json number,title,labels,updatedAt,url,headRefName,body,author
```

**3. Conversation comments, per discovered item** — `GhClient.list_comments`

```text
gh issue view <n> --repo OWNER/REPO --json comments   # or `gh pr view` for PRs
```

## Question 1: what filters are we using?

All filtering is **server-side** — `gh` translates the flags into API-level filters, so
only matching items ever cross the wire; nothing is fetched-then-filtered client-side.

| Filter | Value | Effect |
|---|---|---|
| `--label` | the source's `label`, defaulting to `routing.autoExecuteLabel` (`the-loop: auto-execute`) | Only items explicitly opted into orchestration are returned. This is the primary selectivity lever: on a typical repo it narrows thousands of items to a handful. |
| `--state open` | fixed | Closed/merged items never enter a cycle. |
| `--limit 200` | `_LIST_LIMIT` constant | Hard cap per repo per kind. A labelled backlog larger than this is treated as pathological; the newest items still get through on later polls. |
| `--json <fields>` | explicit field projection | `gh` shapes its underlying GraphQL query from the requested fields, so we pay only for the seven-to-eight fields we use. `body` is requested **only** on the PR listing (closing keywords live there, linking a PR to its issue); issue bodies are not fetched during discovery. |
| `--repo OWNER/REPO` | from `polling.sources[].repos`, falling back to `ticketing.github` | Scope is an explicit allowlist of repos — never org-wide or search-wide queries. |
| `monitor.issues` / `monitor.pullRequests` | config, both default `true` | Either listing can be switched off entirely, halving discovery queries for single-kind setups. |

Two filters are intentionally **absent**:

- **No author filter at query time.** Authorization
  ([decision-023](../decisions/decision-023.md)) is enforced in the poller after
  fetching — `author` is part of the listing projection precisely so unauthorized
  items/comments can be dropped (and baselined) locally without extra queries.
- **No `since`/date filter on comments.** Comment novelty is decided against the
  durable `PollState` (see below), not the API.

## Question 2: how are we making sure queries are performant?

### Query-volume model

Per cycle, with `R` repos and `I` currently labelled open items across them:

```text
queries per cycle = 2R + I      (issue list + pr list per repo, one view per item)
```

At the defaults (`intervalSeconds: 60`, one repo) with e.g. 5 labelled items, that is
7 queries/minute ≈ 420/hour — comfortably inside GitHub's authenticated rate limits
(5,000 REST requests/hour; GraphQL's point budget prices these simple queries at ~1
point each). The label gate is what keeps `I` small by construction: only opted-in
work is ever expanded into a per-item comment query.

### Mechanisms in the code

- **Server-side filtering + field projection** (table above): the narrowest possible
  question is asked of the API, and only the fields consumed are transferred.
- **Bounded result sets**: `--limit 200` caps listings; `_SEEN_COMMENTS_CAP = 500`
  caps per-item dedup state so the state file cannot grow unboundedly on a chatty
  thread (the seen-set is re-seeded from the live comment list every cycle, so the
  newest comments always stay in the window).
- **Bounded latency**: every `gh` invocation runs under a 60s subprocess timeout
  (`GhClient.timeout`); a hung network call cannot stall the loop indefinitely.
- **Fixed, configurable cadence**: one discovery pass per `intervalSeconds`
  (default 60, hot-reloadable per cycle without restart). There is no adaptive
  tightening that could accidentally hammer the API.
- **Fault isolation, no retry storms**: a provider or per-item failure is logged to
  the event log and the cycle continues (`poll.provider_error` / `poll.item_error`);
  retry is simply "next cycle", so errors never multiply query volume.
- **Work dedup ≠ query dedup**: the durable `PollState` (atomic-write JSON) plus the
  session registry guarantee a comment is dispatched once and a session never spawned
  twice — so re-fetching the same data across cycles is idempotent and cheap
  downstream, even though it is re-fetched (see gaps below).
- **Push where possible, pull only where necessary**: the webhook receiver is the
  zero-query ingress; polling exists specifically for hosts GitHub cannot reach
  ([decision-022](../decisions/decision-022.md)). Choosing webhooks where available is
  the biggest performance lever of all.
- **`gh` handles pagination and transport**: comment pagination, HTTP/2 reuse, auth
  and GitHub Enterprise routing are delegated to the maintained CLI rather than
  re-implemented.

## Gaps / future optimization opportunities

Honest accounting — none of these bite at current scale (single operator, single repo,
label-gated backlog), but they are the known costs:

1. **Comments are re-fetched for every labelled item every cycle.** The listings
   already project `updatedAt`, and `PollState` records `lastPolledAt`, but the poller
   never compares them — an unchanged item still costs a `gh ... view --json comments`
   call. Skipping the comment query when `updatedAt <= lastPolledAt` would drop the
   steady-state cost from `2R + I` to `2R` queries per cycle for a quiet backlog.
2. **One subprocess per query.** Each call pays `gh` process startup (~100–300ms).
   Irrelevant at 7 queries/minute; would matter before any large-`I` deployment.
3. **No conditional requests.** The `gh issue/pr list` porcelain doesn't expose
   ETags/`If-None-Match`, so unchanged listings are still full responses. Moving to
   `gh api` with conditional requests would make quiet polls free against the REST
   rate limit — at the cost of re-owning pagination and response shapes.
4. **Truncation over 200 items is silent** (by design, logged as a code comment, not
   at runtime). An event-log warning when a listing hits the cap would make the
   pathological case observable.

## Pointers

- Provider + `gh` wrapper: [`cli/the_loop/poller/github.py`](../../cli/the_loop/poller/github.py)
- Cycle logic, state, cadence: [`cli/the_loop/poller/poller.py`](../../cli/the_loop/poller/poller.py)
- Design: [`docs/specs/issue-34/design.md`](../specs/issue-34/design.md) ·
  [decision-022](../decisions/decision-022.md) · [decision-023](../decisions/decision-023.md)
- Config knobs: `polling.*` and `webhooks.ghWebhook.routing.autoExecuteLabel` in
  [`skills/the-loop/templates/config.yaml`](../../skills/the-loop/templates/config.yaml)
