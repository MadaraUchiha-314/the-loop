# Decision 023: authorized-actor guard on both trigger paths (prompt-injection remediation)

- **Status:** accepted
- **Date:** 2026-07-22
- **Deciders:** @MadaraUchiha-314 (PR #45 review)
- **Work item:** issue-34
- **Spec:** `docs/specs/issue-34/` (requirement R8)

## Context

Both trigger paths — the webhook receiver (issue-15) and the poller (issue-34) — react to
work items carrying the-loop's auto-execute label, then feed the item's content (body,
comments, reviews) to the harness. That content is authored by anyone who can interact
with the issue/PR, not just the operator. Feeding it to the agent as if it were the
operator's instructions is a **prompt-injection vulnerability**: a malicious comment on a
labelled issue could steer the agent (PR #45 review). Label presence gates *what* is
orchestrated, but not *whose input* drives it.

## Decision

Add an **authorized-actor allowlist** enforced at both trigger paths: only actions taken
by GitHub logins in `webhooks.ghWebhook.routing.authorizedUsers` are an input the-loop
acts on. A small shared helper (`the_loop/authz.py`) is the single policy.

- **`is_authorized(actor, allowlist)`** — an action with no identifiable human actor (CI
  `workflow_run`/`check_*` status; carries status, not free-form instructions) is allowed;
  a named actor is allowed only if listed; an **empty allowlist fails closed** for
  human-authored actions.
- **Webhook** (`Router`): `event_actor` resolves the responsible human (comment/review
  author, or the `sender` who labelled/opened). Unauthorized events are dropped before
  dispatch. `pull_request` `closed` bypasses the guard — it only auto-closes the-loop's
  own session and injects nothing.
- **Poller**: the item's author (added to the `gh` listing) gates spawning; the comment
  author gates comment forwarding; a dropped comment is baselined so it is never
  re-evaluated. The labeller isn't visible via `gh ... list`, so the item author is the
  poller's authorizing identity (aligned with "each operator works their own items").
- **Default**: `resolve_authorized_users` falls back to `ticketing.github.owner` when
  `authorizedUsers` is unset, so the common single-operator setup works without extra
  config while still blocking third parties; empty-and-no-owner warns loudly and fails
  closed. The receiver re-resolves on hot-reload.
- **Operating model** (owner ruling): each user runs their own the-loop instance in their
  own environment for their own login(s); cross-user orchestration is out of scope.

The existing "payload excerpt is UNTRUSTED data" framing in the prompt templates stays as
defence-in-depth; this guard is the primary control (don't ingest unauthorized input at
all).

## Consequences

- New `the_loop/authz.py`; `RoutingConfig.authorized_users` + config
  `routing.authorizedUsers`; `Router`/`Poller` gain the guard; `WorkItem`/`GhItem` gain
  `author` and the `gh` listing fetches it. Both commands resolve + warn.
- Behaviour change: an installation with neither `authorizedUsers` nor
  `ticketing.github.owner` now acts on **nothing** human-authored until configured (this
  is the intended fail-closed posture; the config template ships the key with guidance).
- **Re-evaluation triggers:** wanting team-wide orchestration (multiple operators on one
  instance) — revisit the "own items" model; needing the *labeller's* identity in polling
  (would require the timeline/events API per item); org/team-based allowlisting (expand
  beyond individual logins).

## Alternatives considered

- **Rely only on the "untrusted data" prompt wrapper** — rejected: mitigation, not
  prevention; the safe posture is to not ingest unauthorized input at all.
- **Gate on the label alone** — rejected: the label authorizes the *item*, not the
  *authors* of the comments/body that follow, which is exactly the injection surface.
- **Allow-all when `authorizedUsers` is empty (non-breaking)** — rejected: that is the
  vulnerable status quo; fail-closed with an owner fallback keeps the common case working
  while being secure by default.
- **A separate top-level `security` config block** — deferred: the guard governs the
  shared routing/dispatch both ingresses already read, so `routing.authorizedUsers` keeps
  it in one place; can be promoted later if more security knobs appear.
