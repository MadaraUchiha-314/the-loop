# Decision 048: a work-item ref names its host when it is not the default one

- **Status:** proposed
- **Date:** 2026-07-31
- **Deciders:** @MadaraUchiha-314 (issue #130, [PR #131 review](https://github.com/MadaraUchiha-314/the-loop/pull/131))
- **Work item:** issue-130
- **Spec:** `docs/specs/issue-130/`
- **Builds on:** [decision-047](decision-047.md) — the record `url` this makes correct off
  github.com — and issue-15's `WorkItemRef`, the identity every store keys on.

## Context

Issue #130 asked for a record's `ref` to be navigable. The first implementation derived
`https://github.com/<owner>/<repo>/issues/<n>` and documented GitHub Enterprise as out of
scope, on the reasoning that *a ref carries no host*.

The owner rejected that on review:

> Why is this out of scope? This should be in scope. When the poller is polling or the
> webhook is receiving, we can identify the host as well.

Which is correct, and checkable: a webhook payload carries `repository.html_url`, and a
polled item carries its own `html_url` (the poller already stores it as `WorkItem.url`).
The host was never unavailable — it was being **discarded** at the ingress, one line
before the ref was built.

That makes the original framing wrong in a way worth stating plainly: "a ref carries no
host" was a description of the format, offered as if it were a constraint. The format is
ours.

Once the host is admitted to be knowable, the question is only *where it belongs*. A
work item on `ghe.corp.example` and one on `github.com` with the same owner, repo and
number are **different work items**. Anything that treats them as one — a shared registry
entry, a shared poll ledger, one file name — is a collision, not a simplification. That
makes the host part of the identity, and the identity is the ref.

## Decision

**A work-item ref is `<provider>:[<host>/]<owner>/<repo>#<number>`, and the host is
written only when it is not the provider's default.**

- `github:octo/repo#15` — github.com, exactly as before.
- `github:ghe.corp.example/octo/repo#15` — a work item on GitHub Enterprise.

Consequences of that one rule:

1. **Backwards compatible where it counts.** Every ref string already on disk parses to
   the same work item, and `slug` — the *file name* of every state record — is unchanged
   for github.com. No migration, no shim.
2. **The host is identified from the event, never configured.** The receiver reads
   `repository.html_url`, falling back to the issue/PR URL (which is what the poller's
   synthesised payloads carry); a polled item reads its own URL. Both fall back to
   github.com, which is what a hostless ref has always meant. Configuration would be the
   wrong mechanism anyway: one daemon may poll two hosts, and the event knows which.
3. **The two derivations must agree**, because the router's ref keys the routing and the
   poller's keys the poll ledger. They now go through one helper (`host_from_url`) and one
   `WorkItemRef`.
4. **The grammar is closed.** A path is two segments, or three with a *recognisable* host
   (a dotted name, or one with an explicit port). Anything else is a malformed ref and
   raises. Previously `parse` split at the first slash and let the rest be the "repo", so
   `github:octo/repo/../../evil#15` produced a work item whose identity was a path
   fragment — the input the URL derivation in decision-047 had to defend against. Now it
   never becomes a ref at all, which is the better place to stop it.

## Consequences

**Positive.**

- A GitHub Enterprise work item links to where it actually lives, and is a distinct
  identity from a same-numbered item on github.com.
- The fail-closed URL rule stays, but its job shrinks: the malformed inputs it guarded
  against are now rejected at parse.
- The ref grammar gained a documented extension point rather than a special case — the
  reserved `jira:` provider inherits the same `[<host>/]` slot.

**Negative / accepted costs.**

- **An existing GitHub Enterprise deployment is re-identified.** Its refs, and therefore
  its state file names, change: the poll ledger re-baselines that thread once, and a
  session for it should be re-registered. Accepted, with the alternative stated below,
  because GHE was documented as unsupported until now; the behaviour is documented in
  `docs/cli/state.md` rather than left to be discovered.
- **`gh` invocations are not yet host-aware.** `comments.py`, `reactions.py` and the poll
  provider call `gh api repos/<owner>/<repo>/…`, which resolves through the operator's own
  `gh` host configuration. A single-GHE-host setup already works that way; a daemon
  spanning **two** hosts needs those calls to pass the ref's host explicitly. That is a
  follow-up work item, not this one — it touches authentication, and this change is what
  makes the host available to it.
- **A three-segment path changes meaning.** It used to parse (owner + a slashed remainder)
  and now means host/owner/repo, or is rejected. Nothing in the-loop ever produced one.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the host out of the ref; thread it through the writers | The stores are reached from four call sites and from the CLI, where no payload exists (`the-loop sessions start <ref>`). The ref is the one thing that reaches all of them — and, since two hosts mean two work items, the host is identity, not decoration. |
| A configured host (`state.urlHost` or reusing `workspace.defaultHost`) | Wrong shape: one daemon can poll github.com and an enterprise host at once. The event already knows, and configuration that can disagree with the event is a bug waiting to be filed. |
| `github@ghe.corp.example:octo/repo#15` (scp-style) | Unambiguous, but a second delimiter to explain and to escape, for a case the path slot already expresses. |
| Any three-segment path is `host/owner/repo` | Reads `github:octo/repo/sub#15` — almost certainly a typo — as a work item on a host called "octo", silently creating a second identity. Requiring the host to look like one (a dot, or a port) makes the typo an error instead. |
| A read-fallback to the hostless slug, so existing GHE state is adopted | The shim shape this codebase already uses twice (issue-106, issue-128) — kept in reserve rather than built, because GHE was documented as out of scope, so the population it would serve is speculative. Cheap to add if a real deployment needs it. |
