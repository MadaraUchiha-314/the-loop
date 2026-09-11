# Decision 121: the repositories an instance works with are declared once, at the top level, and every ingress reads that list — the webhook receiver included; `polling.sources[].repos` is removed and migrated; an empty list bounds nothing and says so

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-348](https://github.com/MadaraUchiha-314/the-loop/issues/348)
- **Deciders:** MadaraUchiha-314 (the ask, and owner sign-off at the PR); the-loop (design)
- **Refines:** [decision-116](decision-116.md) D4 and [decision-120](decision-120.md) D1
  (a command, and a kickoff, may name only a repository this instance is configured for —
  generalized here from two inbound shapes to all four), [decision-023](decision-023.md)
  (the authorized-actor guard on both trigger paths, which this sits beside rather than
  replaces), [decision-111](decision-111.md) D1 (a refusal leaves no mark)

## Context

`polling.sources[].repos` is read by twenty modules. `the_loop/webhook/` is not one of
them: the webhook package's only mention of `polling` is a comment about `maxRetries`.

So the poller was bounded by an operator-declared repository list and the receiver was
bounded by nothing of the kind. What actually bounded the receiver was the
`X-Hub-Signature-256` HMAC — and only when a secret is configured, since
`verify_signature` returns `None`, not `False`, when there is none — the authorized-actor
guard on the event's actor, and `instance.scope`, which answers *which instance* takes a
work item rather than *which repositories may reach this machine*. None of the three is
"the operator declared this repository".

The owner's words on [PR #347](https://github.com/MadaraUchiha-314/the-loop/pull/347):
*"repos are listed in `polling.sources.repos` and that means that the same repo filter are
not applied to gh-webhook events. we should unify the place where gh repo filter is
specified."*

The name is the bug. A key under `polling` that ought to govern the receiver is the same
mistake issue-142 fixed for `webhooks.ghWebhook.routing`, in the other direction: a block
nested under one ingress that both of them read.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A top-level `repositories`, a sibling of `routing` / `polling` / `channels`, is the one declaration** — `[HOST/]OWNER/REPO` (issue-311), read by the `gh-webhook` receiver, the poller, `/the-loop`'s `may_target` and the Slack kickoff. One builder, moved from `channels/repos.py` to `the_loop/repos.py`. | Four readers of one list is the point; four readers of four lists is how they drift, which is the state this fixes. The move out of `channels/` is not cosmetic: the old module imported `channels.slack` to read `kickoff.repo`, so the webhook router — stdlib-only and I/O-free — could not have read it without dragging a channel's config parser into the ingress. |
| D2 | **`channels.slack.kickoff.repo` stops declaring a repository and starts pointing at one.** It remains that channel's default target; a fallback outside the declared list is refused as `unknown-repo`. The migration adds it to `repositories`, so no configured install loses a target. | Otherwise the kickoff is the one path that may still write into a repository nobody declared, and "one place" would be two places wearing one name. The refusal reuses an outcome that already exists rather than inventing a fifth. |
| D3 | **The receiver drops on two questions under one reason code** (`undeclared-repository`): the delivery's own repository, and any work item it names — the issue-183 cross-repository linkage — that is outside the list. The check runs **above** the actor guard and above the bus, and a dropped delivery is not marked processed. | Filtering only the delivery leaves a linked ref as a way to name a work item in an undeclared repository; filtering only the refs lets an undeclared payload reach `is_authorized`, the collaborator roster and a Slack channel first. Above the actor guard because an undeclared repository's payload should touch as little of the process as possible; unmarked because a redelivery after the operator declares the repository must get through. |
| D4 | **An empty or absent `repositories` bounds nothing**, and the receiver warns once at start naming the key. | The alternative — empty fails closed — stops every webhook-only instance on upgrade, this repository's own dogfooding config included (`polling.sources: []` today, receiver-driven). That is a second decision, with its own migration, not a side effect of this one. The permissive direction is stated in the requirements, warned about at runtime, documented in the schema and on the options page, and is exactly 13.12.0's behaviour rather than a new permission. |
| D5 | **`polling.sources[].repos` is removed outright, not accepted with a warning**, at config version `0.8.0`; `the-loop migrate-config` moves every `github` source's list up (plus `kickoff.repo`, deduplicated, top-level entries first) and an un-migrated config refuses to start with `ConfigTooOld`. | A shadow override is how two lists drift for a whole release cycle, and this one decides what a machine will act on. It is the standing rule in `migrations.py`: *"Let's make breaking changes. /upgrade should be able to handle it."* A source under another provider keeps its own `repos` untouched — that key is that provider's, and `jira` is reserved. |
| D6 | **A source keeps what is genuinely per-source** — `provider`, `label`, `monitor`, `ghBinary` — and the per-repository failure isolation of [decision-106](decision-106.md) is untouched. Every `github` source polls every declared repository. | A source describes *how* to poll; the list describes *what*. With one source (every shipped and documented configuration) nothing changes; with two, the second is a different label or monitor over the same repositories, and the per-work-item ledger makes a doubled listing a wasted API call rather than a doubled dispatch. |

## Consequences

**What improves.** The two doors into an operator's machine are locked with the same key,
and the key is named after what it is. An operator reading their config can answer "what
will this instance act on?" from one block instead of from knowledge of which ingress
reads which key. A repository moved between ingresses is a one-place edit.

**Costs, accepted.**

- A breaking config change behind the versioned migration — the fifth, and the mechanism
  is well worn.
- One behaviour change on upgrade: a receiver that was accepting deliveries from a
  repository the operator never listed stops. That is the fix, not a regression, but it is
  a behaviour change, so the migration report says it out loud.
- An empty list still bounds nothing (D4). The hole is narrowed from "always" to "until
  you declare", and it is now visible: warned at start, and stated in the schema.

**Residual risk, recorded.** A hot reload whose `repositories` section is broken narrows
the set to empty, which is the *unbounded* case rather than the closed one. The builder
fails in the shrinking direction everywhere else; here the shrink lands on the one value
that means "no bound". Flipping D4 would close it, at the cost D4 exists to avoid. The
reload path keeps the start-up warning honest by re-reading the whole document, so the
condition is at least visible in the log.

**What this does not do.** It is not authentication, and it does not touch the signature
or actor guards; it does not change `instance.scope`; and it does not decide the kickoff's
repository picker, which is [#349](https://github.com/MadaraUchiha-314/the-loop/issues/349).
