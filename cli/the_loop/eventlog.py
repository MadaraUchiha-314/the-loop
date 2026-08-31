"""Structured JSONL event log — end-to-end o11y of the-loop's CLI processes.

Every accept/reject/dispatch/spawn/retry/close decision the webhook receiver,
the poller and the session registry make is appended as one JSON object per
line to a single machine-queryable file (default
``.the-loop/logs/events.jsonl``, git-ignored). The file is the system's audit
trail: it answers "which events triggered this session?", "what was rejected,
and why?", and "what failed, and was it retried?" — for humans (``the-loop
events``, grep/jq) and for coding agents alike. JSONL over SQLite is
decision-025: append-only writes are atomic and multi-process-safe, the file
is directly greppable, and any dashboard/DB can be layered on top.

Every record shares one envelope::

    {"ts": "2026-07-22T06:31:20.123Z",  # UTC, ISO-8601, millisecond precision
     "source": "gh-webhook",            # emitting process: gh-webhook|poll|sessions
     "event": "dispatch.succeeded",     # dot-namespaced type (see EVENT_TYPES)
     "level": "info",                   # debug|info|warning|error
     "pid": 4242,                       # emitting process id
     ...}                               # event-specific fields, all optional

Common event-specific fields: ``work_item`` (``github:owner/repo#15``) /
``work_items``, ``delivery_id`` (GitHub ``X-GitHub-Delivery``), ``gh_event``
(+ ``action``), ``actor``, ``harness``, ``harness_session_id``, ``reason``
(why something was rejected/dropped), ``error`` and ``will_retry`` (failure
paths). The full catalog lives in :data:`EVENT_TYPES` (also ``the-loop events
--types``) and ``skills/the-loop/reference/observability.md``.

Emission is fire-and-forget: a broken log file must never break ingress, so
write failures are warned about once and swallowed. Library code calls the
module-level :func:`emit`, which is a no-op until a CLI entry point calls
:func:`configure` — pure unit tests and embedders pay zero I/O.

Spec: docs/specs/issue-50/design.md; decision-025.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence, Union

import yaml

from . import cli_config

logger = logging.getLogger("the-loop.eventlog")

DEFAULT_PATH = ".the-loop/logs/events.jsonl"

LEVELS = ("debug", "info", "warning", "error")

# The catalog of event types the-loop emits — the single source of truth used
# by `the-loop events --types` and mirrored in the observability reference.
# Adding an instrumentation point means adding its type (and description) here.
EVENT_TYPES: Dict[str, str] = {
    # -- webhook receiver (source: gh-webhook) --------------------------------
    "webhook.received": (
        "An inbound webhook POST was accepted for routing "
        "(gh_event, delivery_id, verified: HMAC signature checked)."
    ),
    "webhook.rejected": (
        "An inbound webhook POST was refused before routing "
        "(reason: invalid-signature | invalid-payload)."
    ),
    # -- routing (source: gh-webhook or poll) ---------------------------------
    "routing.routed": (
        "A verified event mapped to work item(s) and passed all guards "
        "(gh_event, work_items, labeled)."
    ),
    "routing.dropped": (
        "A verified event was not routed (reason: disabled-event | "
        "duplicate-delivery | no-work-item | unauthorized-actor; actor)."
    ),
    "routing.collaborator": (
        "A verified event was routed on a WORK-ITEM COLLABORATOR grant rather than "
        "`routing.authorizedUsers` (gh_event, actor, work_items) — issue-307. An "
        "authorized user granted this login the right to be *input* on these work "
        "items: the comment reaches the session, and the control and spawn seams "
        "still refuse it everything else."
    ),
    "routing.linkage_dropped": (
        "A work-item ref an event named ONLY through the issue-<n> branch "
        "convention does not exist, so it was removed from that event's work "
        "items before anything acted on it (work_item, source: branch, reason: "
        "not-found, gh_event, delivery_id) — issue-269. The branch convention is "
        "the one linkage source that supplies a repository the event never "
        "stated; every other source is routed unchecked."
    ),
    # -- dispatch (source: gh-webhook or poll) --------------------------------
    "dispatch.queued": (
        "A routed event was enqueued on a session's FIFO queue "
        "(work_item, spawn: whether it will spawn a new session)."
    ),
    "dispatch.dropped": (
        "A routed event was discarded at dispatch (reason: duplicate-delivery "
        "| already-processed | spawn-policy | awaiting-start | session-paused "
        "| collaborator-no-spawn | session-vanished | no-adapter | "
        "session-occupied | work-item-not-found | no-work-item). "
        "`collaborator-no-spawn` (issue-307) means the event reached dispatch on a "
        "work-item collaborator grant, which admits input and never a new session. "
        "`work-item-not-found` (issue-269) means every work item the event named "
        "was a branch-invented ref the provider says does not exist, and "
        "`no-work-item` that it named none to begin with; in both cases the "
        "delivery id is deliberately NOT released, because that is a permanent "
        "condition and a redelivery could only reach the same answer. "
        "`session-occupied` (issue-146) means a dead tmux session held the work "
        "item's `loop-<slug>` name and could not be cleared, so nothing was "
        "spawned and the delivery id was deliberately NOT released — retrying "
        "could only hit the same collision. "
        "`awaiting-start` and `session-paused` are *suppressions*: the delivery "
        "id is kept AND recorded as settled (issue-270), so the poll path "
        "resolves the comment instead of counting a retry against it — nothing "
        "is replayed when the item is started or the session resumed, and the "
        "session reads the thread itself instead (`poll.comment_settled`)."
    ),
    "dispatch.succeeded": (
        "An event was delivered to its harness session (work_item, harness, "
        "via: resume | tmux)."
    ),
    "dispatch.failed": (
        "Delivering an event to its session failed (work_item, harness, "
        "error; will_retry: the delivery id was released so a redelivery / "
        "next poll cycle can retry)."
    ),
    "dispatch.error": (
        "A dispatch worker crashed on an event (work_item, error; will_retry)."
    ),
    "dispatch.abandoned": (
        "The dispatcher shut down with events still queued; they were never "
        "delivered and are left for the next start to retry (count, "
        "delivery_ids) — issue-159. On the poll path the attempts they spent "
        "are handed back (`poll.attempts_released`)."
    ),
    "reaction.added": (
        "A dispatch-lifecycle emoji reaction was added to the triggering "
        "comment/issue/PR (work_item, state: started | completed | error, "
        "content, target) — issue-84, routing.reactions."
    ),
    "reaction.failed": (
        "Adding a dispatch-lifecycle reaction failed; the dispatch itself is "
        "unaffected (work_item, state, content, error)."
    ),
    # -- execution control (source: any; issue-106) ---------------------------
    "control.command": (
        "A control command was recognised and applied (work_item, command: "
        "start | stop | pause | resume | add-collaborator | remove-collaborator, "
        "source: comment | cli, actor, effect: spawned | resumed | paused | "
        "stopped | noop | granted | revoked | already-granted | "
        "not-a-collaborator) — the record of who asked for a run to start or "
        "stop, and (issue-307, with `collaborator`: the login) of who was "
        "invited onto a work item or removed from it."
    ),
    "control.rejected": (
        "A control command was recognised but refused (work_items, command, "
        "source, actor, reason: spawn-policy | awaiting-start | "
        "nothing-to-resume | unauthorized-actor | missing-collaborator) — e.g. a "
        "start for a work item that is not armed for autonomous execution (which "
        "is refused without being remembered), a command with no named authorized "
        "actor, or an `add-collaborator` naming no valid `@login`."
    ),
    "control.ambiguous": (
        "A comment carried two or more different control keywords, so nothing "
        "was executed and nothing was forwarded (work_items, actor, commands)."
    ),
    # A control comment is CONSUMED, never delivered — so on the poll path its
    # delivery is settled rather than counted as an attempt (issue-270). That
    # applies to all three outcomes above: applied (`control.command`), refused
    # (`control.rejected`) and ambiguous (`control.ambiguous`).
    "control.announced": (
        "A CLI control action was mirrored to the work item as a comment "
        "carrying the same keyword (work_item, command)."
    ),
    "control.announce_failed": (
        "Mirroring a CLI control action to the work item failed (work_item, "
        "command, error) — best-effort; the command was still applied locally."
    ),
    # -- session lifecycle (source: any) --------------------------------------
    "session.registered": (
        "A work item ↔ harness session link was recorded in the registry "
        "(work_item, harness, harness_session_id, cwd)."
    ),
    "session.pr_linked": (
        "A pull request was durably recorded as delivering a work item "
        "(work_item, pull_request) — issue-172. Written when the routing "
        "decision is made, so which session owns the PR's events stops being "
        "recomputed from `gh` — and, since issue-274, by the session that "
        "OPENED the pull request (`sessions link-pr`), which is the only "
        "writer a the-loop-authored PR has: it carries no closing reference, "
        "no `issue-<n>` branch and no closing keyword to infer from. Emitted "
        "only when the PR is newly listed."
    ),
    "session.pr_spawned": (
        "A recorded pull request got its own tmux session and harness "
        "conversation (work_item, pull_request, harness, harness_session_id, "
        "tmux_target) — `routing.tmux.sessionPerPr`. The work item's own "
        "session is untouched; this is an additional endpoint. Which pull "
        "requests reach this is the operator's choice (issue-258): under the "
        "default `cross-repository` only one in ANOTHER repository does, "
        "because the work item's own repository is its own session's; "
        "`always` adds same-repository pull requests that can be given a "
        "checkout of their own; `never` reaches this for none of them."
    ),
    "session.pr_session_declined": (
        "A pull request was NOT given a session of its own, and its event went "
        "into the work item's session instead (work_item, pull_request, "
        "reason: no-separate-checkout | workspace-failed | shared-worktree) — "
        "issue-253. An endpoint gets a conversation only when it has a working "
        "tree of its own; without `routing.workspace.root` there is none to "
        "give, and two harness sessions never share a tree. Under "
        "`sessionPerPr: always` a same-repository endpoint is also declined "
        "(reason workspace-failed) when its checkout cannot hold the pull "
        "request's head branch — which is every time the work item's own "
        "session already holds it under `workspace.strategy: worktree`."
    ),
    "session.pr_closed": (
        "A pull request's endpoint was closed while its work item's session "
        "kept running (work_item, pull_request) — a work item may be delivered "
        "by several PRs, so one merging ends only that conversation "
        "(issue-101, issue-172)."
    ),
    "session.link_failed": (
        "Recording a pull request against its work item failed (work_item, "
        "linked_ref, error). Best-effort: the event was still dispatched, and "
        "routing falls back to deriving the linkage as it did before issue-172."
    ),
    "graph.assignment_delivered": (
        "The graph entered an agent node and pushed that node's assignment "
        "into the loop's bound session (work_item; endpoint: the PR's ref when "
        "an inner loop was assigned) — issue-172, the deliver-assignment entry "
        "hook. The graph assigns; the session works; the claim reports back."
    ),
    "graph.assignment_failed": (
        "Pushing an entered node's assignment into its session failed "
        "(work_item, endpoint, error). Best-effort: the node is entered "
        "regardless, and the same state is re-rendered into every event prompt."
    ),
    "session.spawned": (
        "A new harness session was spawned for a work item — this is the "
        "'what triggered this session' record (work_item, harness, "
        "harness_session_id, runner, gh_event, delivery_id)."
    ),
    "session.spawn_failed": (
        "Spawning a session failed (work_item, harness, error; will_retry)."
    ),
    "session.respawned": (
        "A tmux-mode session found dead on delivery was respawned on a fresh "
        "tmux session, and the pending event delivered as its boot prompt "
        "(work_item, harness, harness_session_id, runner, tmux_target, "
        "resumed: whether the previous conversation was resumed or a fresh one "
        "started, gh_event, delivery_id)."
    ),
    "session.respawn_averted": (
        "A delivery reported its tmux session missing, but the session turned "
        "out to be alive when the respawn re-checked — so the pending event was "
        "delivered into the existing session and nothing was respawned "
        "(work_item, harness, tmux_target, gh_event, delivery_id). issue-146: "
        "the-loop never spawns over a live `loop-<slug>`; it routes into it."
    ),
    "session.resume_failed": (
        "A respawn could not resume the dead session's conversation and fell "
        "back to a fresh one (work_item, harness, harness_session_id, error) — "
        "e.g. an unresumable id or a harness without interactive resume. Not "
        "emitted when resuming is simply off (routing.tmux.resumeOnRespawn)."
    ),
    "session.announced": (
        "A comment announcing a newly spawned tmux session (and how to attach "
        "to it) was posted on the work item (work_item, tmux_target); a respawn "
        "reuses the name and posts nothing further."
    ),
    "session.work_item_missing": (
        "The session announcement came back 404: the work item the-loop just "
        "spawned a session for does not exist (work_item, tmux_target, error) — "
        "issue-269. Recorded, not acted on: a repository the credential cannot "
        "see answers 404 for items that do exist, so killing a live session on "
        "this evidence would destroy work. The ref is remembered as missing, so "
        "the next event naming it through a branch convention is dropped."
    ),
    "session.announce_failed": (
        "Posting the tmux-session announcement comment failed (work_item, "
        "tmux_target, error) — best-effort, the dispatch is unaffected."
    ),
    "session.awaiting_input": (
        "A session asked a human a question through `the-loop ask` and is now "
        "waiting for the answer (work_item, question, actor, comment_url, "
        "comment_posted: whether the question reached the ticket) — issue-208. "
        "The verb stamps the loop-prevention marker centrally, so the wait is "
        "recorded even when the agent forgot nothing. Closed by the next "
        "session.reply_sent; an answer given on the ticket instead is forwarded "
        "as usual but emits nothing, so the wait stays reported."
    ),
    "session.reply_sent": (
        "An operator's answer was delivered straight into the waiting session's "
        "tmux pane via POST /api/v1/sessions/reply (work_item, actor) — "
        "issue-208. Closes the work item's session.awaiting_input on the "
        "attention surface and the dashboard alike."
    ),
    # -- channels (source: ask | channels | poll | gh-webhook) ----------------
    "channel.posted": (
        "An outbound event was posted to a communication channel (channel, "
        "work_item, event_type, thread: the provider's conversation handle) — "
        "issue-245. The work item already carries the text; this is the "
        "fan-out."
    ),
    "channel.post_failed": (
        "A channel post failed (channel, work_item, event_type, error) — "
        "best-effort by contract: the ask's outcome is unaffected and the "
        "work item remains the record."
    ),
    "channel.reply_received": (
        "An authorized reply arrived through a channel and entered the "
        "pipeline (channel, work_item, actor: the channel-native member id). "
        "Payloads carry ids, never message text."
    ),
    "channel.dropped": (
        "An inbound channel message was not processed (reason: unmapped | "
        "self-authored | unauthorized-actor | undeliverable; channel, "
        "work_item, actor, error). undeliverable means the mirror stood but "
        "no session could take the reply."
    ),
    "channel.mirrored": (
        "A channel reply was posted onto its work item as the-loop's own "
        "marker-stamped comment — the single-source-of-truth rule (channel, "
        "work_item, actor)."
    ),
    "channel.mirror_skipped": (
        "A channel reply had no work item to mirror onto and was delivered "
        "anyway (channel, work_item, reason: standing-session) — a standing "
        "session owns no ticket, so this event IS its paper trail (issue-277)."
    ),
    "channel.mirror_failed": (
        "The work-item mirror of a channel reply could not be posted "
        "(channel, work_item, error); the delivery attempt still proceeds."
    ),
    "standing.started": (
        "A standing session — one that belongs to no work item — was spawned on "
        "a fresh conversation (standing, harness, harness_session_id, "
        "tmux_target, cwd). issue-277."
    ),
    "standing.resumed": (
        "A standing session was spawned continuing its RECORDED conversation "
        "rather than a fresh one (same payload as standing.started), which is "
        "what makes `the-loop restart` not amnesia for a supervisor session."
    ),
    "standing.resume_failed": (
        "A standing session's resume did not survive its liveness probe "
        "(standing, harness_session_id, error); a fresh conversation is started "
        "instead, so a standing.started follows."
    ),
    "standing.spawn_failed": (
        "A standing session could not be started (standing, harness, "
        "tmux_target, error): a missing harness binary, a cwd that is not "
        "there, an unreadable promptFile, or a live tmux session the-loop has "
        "no record of and will not spawn over."
    ),
    "standing.created": (
        "A standing session was brought into existence through the API rather "
        "than declared in the config (standing, harness, cwd, auto_start) — "
        "issue-277 R6. The definition now lives in its registry record."
    ),
    "standing.create_failed": (
        "A create wrote its record but the session would not start (standing, "
        "error); the record was removed again, so the name is free for a retry."
    ),
    "standing.deleted": (
        "A created standing session was stopped and its record removed "
        "(standing). Unlike standing.stopped, nothing comes back: the "
        "conversation id is gone with the record."
    ),
    "standing.stopped": (
        "A standing session's harness was terminated and its tmux session "
        "killed (standing, tmux_target). The record is KEPT, so the next start "
        "resumes the same conversation."
    ),
    "standing.stop_failed": (
        "A standing session's tmux session could not be killed (standing, "
        "tmux_target, error); the record is marked stopped regardless."
    ),
    "standing.said": (
        "A message was pasted into a running standing session and submitted "
        "(standing, tmux_target, actor). Nothing is posted to any ticket — "
        "there is none — so this event is the delivery's only record."
    ),
    "standing.announced": (
        "A standing session was announced in Slack and the resulting thread "
        "bound to it (standing, channel, thread), which is what makes replies "
        "in that thread reach its terminal."
    ),
    "standing.announce_failed": (
        "A standing session's Slack announcement did not land (standing, "
        "error). Best-effort by contract: the session is up regardless, it "
        "simply has no Slack thread."
    ),
    "session.closed": "A session was closed in the registry (work_item).",
    "session.paused": (
        "A session was paused, so events for its work item are held rather "
        "than delivered (work_item, harness, harness_session_id) — issue-106, "
        "the pause command."
    ),
    "session.resumed": (
        "A paused session returned to active and delivery resumed (work_item, "
        "harness, harness_session_id); events suppressed while paused are not "
        "replayed."
    ),
    "session.retained": (
        "A closed work item's tmux session was left running so its transcript "
        "stays readable (work_item, tmux_target); "
        "routing.tmux.keepSessionOnClose: false kills it instead."
    ),
    "session.autoclosed": (
        "A session was auto-closed because its work item ended (work_item, "
        "reason: issue-closed | pr-merged | pr-closed; merged)."
    ),
    "session.kept_open": (
        "A close event matched a session only through linkage — one of the "
        "work item's PRs closed, the work item itself did not — so the session "
        "was left active (work_item, reason, closed_ref, delivery_id); a work "
        "item may be delivered by several PRs (issue-101)."
    ),
    "session.reset": (
        "A work item's state on this machine was reset — `the-loop sessions "
        "reset` (work_item, actor, removed: which of workspace|session|control|"
        "poll went, found: false when there was nothing here, was_live, error). "
        "Appended like every other event: a reset can never erase its own trail."
    ),
    "session.cleaned": (
        "A work item's LOCAL resources were released — `the-loop cleanup`, the "
        "same verb from the CLI/API, or a closure by an authorized user "
        "(work_item, actor, source: comment | cli | close-event, removed: which "
        "of tmux|workspace|session went, endpoints: the conversations ended, "
        "found: false when there was nothing here, error). The PORTABLE record "
        "— control, poll, graph — is deliberately untouched, and nothing remote "
        "is changed (issue-186)."
    ),
    "cleanup.deferred": (
        "A work item closed but was NOT cleaned up, because the close event "
        "named no actor or an unauthorized one (work_item, reason: no-actor | "
        "unauthorized-actor, actor, closed_as, delivery_id). Fails closed on "
        "purpose: an authorized user's `the-loop cleanup` is the remedy "
        "(issue-186)."
    ),
    "session.harness_terminated": (
        "The harness process inside a retained tmux session was ended when the "
        "work item closed, so the pane stays readable but can no longer be "
        "typed into (work_item, harness, tmux_target, ok, error) — "
        "routing.tmux.killHarnessOnClose: false skips it."
    ),
    "workspace.prepared": (
        "A per-work-item checkout was made ready for a spawned session "
        "(work_item, strategy: worktree | clone, checkout, branch)."
    ),
    "workspace.cleaned": (
        "A work item's checkout was removed — when its session closed, or when "
        "its local resources were released by `the-loop cleanup` (work_item, "
        "strategy). Uncommitted work in that checkout went with it."
    ),
    "workspace.trusted": (
        "A spawned session's environment was pre-seeded in the harness's own "
        "config so it starts unattended and with the loop loaded — workspace "
        "trust, the bypass-permissions disclaimer when that mode is configured, "
        "and the-loop's own plugin (work_item, harness, cwd, applied) — "
        "issue-90 / routing.harnessTrust, issue-143 / routing.harnessPlugins."
    ),
    "workspace.trust_failed": (
        "Pre-seeding the harness's config failed (work_item, harness, cwd, "
        "error); the spawn still proceeds, but the session may stop on an "
        "interactive dialog or run without the-loop's plugin."
    ),
    # -- poller (source: poll) ------------------------------------------------
    "poll.cycle": (
        "One poll cycle finished (items_seen, spawns, comments_forwarded, "
        "closures, errors)."
    ),
    "poll.closure_detected": (
        "A poll cycle found that an active session's work item had ended "
        "upstream and closed it (work_item, state: closed | merged, kind); "
        "only ever after a successful listing, and never on an unanswerable "
        "state."
    ),
    "poll.provider_error": (
        "Asking a provider for its work items failed; retried next cycle "
        "(provider, error, will_retry)."
    ),
    "poll.item_error": (
        "Processing one polled work item failed; retried next cycle "
        "(work_item, error, will_retry)."
    ),
    "poll.unauthorized": (
        "A polled item was not started by the poller itself: its author is not "
        "an authorized user and nobody has armed it. Its comments are still "
        "acted on, judged by their own authors (work_item, actor)."
    ),
    "poll.comment_forwarded": (
        "A new authorized comment was forwarded to the item's session "
        "(work_item, comment_id, actor, attempt: which retry this was)."
    ),
    "poll.spawn_failed": (
        "The poller gave up spawning a session for an item after exhausting the "
        "retry budget (polling.maxRetries); later polls ignore it until new "
        "activity re-arms it (work_item, attempts, will_retry=False)."
    ),
    "poll.rearmed": (
        "Comments abandoned by a spent retry budget under a DIFFERENT the-loop "
        "version were un-resolved for one more full budget (work_item, comments, "
        "version) — issue-146, so a work item stranded by a bug an upgrade fixed "
        "is picked up instead of staying stuck. Never emitted for a give-up the "
        "running version recorded."
    ),
    "poll.attempts_released": (
        "A shutdown returned the retry budget of dispatches that were still "
        "queued and never delivered (released) — issue-159, so restarting the "
        "poller does not accumulate toward `polling.maxRetries`."
    ),
    "poll.comment_settled": (
        "A forwarded comment was resolved because the dispatcher is FINISHED "
        "with its delivery, not because it was delivered (work_item, "
        "comment_id, actor, outcome: awaiting-start | session-paused | "
        "collaborator-no-spawn | control-executed | control-rejected | "
        "control-ambiguous, "
        "will_retry=False) — issue-270. Either the event was suppressed on "
        "purpose (the work item is not started, or its session is paused) or it "
        "WAS a control command, executed here and never forwarded. The comment "
        "is baselined rather than retried or abandoned: it is not written to "
        "`gaveUp`, so no later version re-arms it, and nothing is replayed when "
        "the item is started or resumed — a spawned session reads the thread "
        "itself, which the spawn prompt tells it to do."
    ),
    "poll.comment_failed": (
        "The poller gave up forwarding a comment after exhausting the retry "
        "budget (polling.maxRetries); later polls ignore it (work_item, "
        "comment_id, actor, attempts, will_retry=False)."
    ),
    "poll.giveup_reported": (
        "A give-up (`poll.comment_failed`) was reported on the work item, so "
        "the human who wrote the comment learns it never reached the session "
        "(work_item, comment_id, attempts) — issue-240."
    ),
    "poll.giveup_report_failed": (
        "The give-up notice could not be posted — no `gh` on PATH, a "
        "non-GitHub work item, or an API error (work_item, comment_id, error). "
        "Best-effort: the give-up itself is recorded regardless."
    ),
    # -- process lifecycle (source: gh-webhook or poll) -----------------------
    "server.started": "The webhook receiver started (host, port, path, routing).",
    "server.stopped": "The webhook receiver shut down.",
    "poller.started": "The poller started (interval_seconds, sources).",
    "poller.stopped": "The poller shut down.",
    "poller.blocked": (
        "A poller refused to start because another one already holds the "
        "single-instance lock on the state root (pidfile, holder) — issue-159. "
        "Two pollers on one ledger interleave read-modify-write and "
        "re-forward each other's comments, so the second one does not run."
    ),
    "config.reloaded": (
        "A config edit was hot-reloaded into a running process (detail)."
    ),
    # -- process graph (source: any; issue-109) -------------------------------
    "graph.started": (
        "A work item entered the graph's start node, running its entry chain "
        "(work_item, node). Emitted by the ingress coupling on spawn "
        "(issue-113) and by anything else calling `Runtime.start`."
    ),
    "graph.advanced": (
        "A work item's exit chain passed and the matching edge was taken "
        "(work_item, node, to, outcome)."
    ),
    "graph.blocked": (
        "A node's exit chain was blocked by a hook; the node did not advance "
        "and the finding went back to the harness (work_item, node, hook)."
    ),
    "graph.parked": (
        "A node is waiting on a human; its exit chain re-runs on the next "
        "inbound event (work_item, node)."
    ),
    "graph.escalated": (
        "A node exhausted its attempts, or repeated the same finding, and "
        "stopped advancing (work_item, node, attempts, repeated)."
    ),
    "graph.no_edge": (
        "No declared edge matched a node's outcome, so the work item was "
        "parked rather than guessed at (work_item, node, outcome)."
    ),
    "graph.hook_degraded": (
        "A best-effort hook passed the node while recording that its outbound "
        "call did not happen — a checklist not posted, a phase label not "
        "synced (work_item, node, hook, error). issue-194: the node's verdict "
        "and the edge taken are unaffected, which is the whole point of "
        "best-effort; what is NOT acceptable is a work item parked on a "
        "question the ticket never received. The CLI prints the same fact as "
        "a warning line; this is where the daemon's operator finds it."
    ),
    "graph.completed": ("A work item reached a terminal node (work_item, node)."),
    "graph.cleaned": (
        "A work item entered the terminal `cleanup` node because the-loop was "
        "about to release its local resources (work_item, from: the node it "
        "stood on, reason) — issue-186. Not a force: no gate is bypassed and no "
        "verdict is claimed, so `check --recompute` still reports whatever never "
        "ran."
    ),
    "graph.spec_tree_excluded": (
        "A contribution started in a repository that never adopted the-loop "
        "(no harness config), so its spec tree was written into the "
        "checkout's git exclude file — working state the contribution PR can "
        "never carry (work_item, path). issue-185, PR #187 review."
    ),
    "harness.config_scaffolded": (
        "the-loop adopted a repository that carried no harness config, by writing "
        "its built-in defaults to `.the-loop/harness-config.yaml` (work_item, path, "
        "repo: the owner/repo named in it, or empty). The answer to 'who put this "
        "file in my repository?' — nothing else the-loop does creates configuration "
        "in a checkout, and an existing config is never overwritten. issue-193."
    ),
    "graph.skipped": (
        "The ingress→graph coupling declined to touch a work item's graph, so a "
        "successful delivery moved nothing (work_item, action: start | advance, "
        "reason: no-spec-dir | spec-dir-outside-checkout, spec_dir: the directory "
        "resolved from the repository's `workflow.specDir`, or the "
        "`routing.graph.specDir` override). The answer to 'it is labelled, armed "
        "and spawned — why is its graph still at node one?'. issue-123."
    ),
    "graph.link_failed": (
        "The ingress→graph coupling raised and was swallowed so the event was "
        "still delivered; the graph did not move (work_item, action, error). "
        "issue-113."
    ),
    "graph.forced": (
        "An operator forced a transition regardless of gates — the escape "
        "hatch. The pointer moved; the bypassed gate keeps its real verdict, "
        "so `check --recompute` still reports it (work_item, from, to, actor, "
        "reason)."
    ),
    # -- declared skips (issue-177) --------------------------------------------
    "graph.skips_declared": (
        "A human declared phases skipped for a work item — the `phase-selection` "
        "gate's authorized reply, or the `graph skip` verb (work_item, "
        "via: selection | cli, nodes; cli adds actor and reason). A declaration, "
        "never a verdict: `check` reports the nodes as skipped-by-declaration."
    ),
    "graph.opt_ins_selected": (
        "A human selected one or more OPT-IN phases for a work item at the "
        "`phase-selection` gate (work_item, via: selection, nodes). The mirror "
        "of graph.skips_declared: those phases are off by default, so this is "
        "the record of somebody asking for them. issue-188."
    ),
    "graph.skips_rejected": (
        "A skip token was refused — unknown, outside the skip vocabulary, or "
        "(cli) naming a node the pointer already reached (work_item, token, "
        "via, why). The declaration never takes effect; the full process runs."
    ),
    "graph.frozen": (
        "A work item's phase selection was frozen: the resolved graph — every "
        "node with whether it is walked or skipped — was recorded and pushed to "
        "the portable session record (work_item). issue-177."
    ),
    "graph.frozen_publish_failed": (
        "The frozen graph could not be written to the portable session record "
        "(work_item, error). Best-effort: the selection itself still stands, "
        "and graph-state.json keeps the authoritative copy. issue-177."
    ),
    "graph.node_skipped": (
        "The pointer routed around a declared-skipped node along its "
        "`on: skipped` edge — none of the node's hooks ran (work_item, node, "
        "plus the declaration's via/token/by/reason). issue-177. Distinct from "
        "graph.skipped, which is the ingress coupling declining to touch a "
        "graph at all."
    ),
    "graph.gate_session": (
        "A human gate was entered and its session resolved per `session: "
        "inherit` — inherited, or fresh-with-artifacts when the producing "
        "session is gone (work_item, node, resolution, session). issue-148."
    ),
    # -- control-plane API service (source: service) — issue-161 --------------
    "api.request": (
        "One control-plane API operation completed (method, path, status). "
        "Every mutating and reading route lands here; /health is exempt. "
        "Debug level (issue-283): a polling dashboard's own reads must not "
        "drown the events an operator reads the log for."
    ),
    "mcp.call": (
        "An MCP tool call was served over the control-plane's HTTP endpoint "
        "(tool, ok). Same authorization and audit trail as the REST surface."
    ),
    "config.updated": (
        "The CLI config was changed through the control plane (path, keys). "
        "The **key paths** are recorded and the values are not: a value names "
        "people, hosts and binaries, and this trail is as readable as the event "
        "log is. issue-222."
    ),
    # -- the server-push stream (source: service) — issue-239 ------------------
    "stream.subscribed": (
        "A client opened GET /api/v1/stream (subscribers: how many are now open, "
        "work_items / transcripts: the filters it asked for, cursor: where it "
        "resumed from, or absent for a fresh connection). The answer to 'who is "
        "watching this workstation?'."
    ),
    "stream.refused": (
        "A stream connection was refused and never accepted (reason: disabled | "
        "at-capacity | bad-cursor | bad-filter, subscribers). `at-capacity` means "
        "`service.stream.maxSubscribers` is reached — the bound that keeps an open "
        "dashboard from starving the REST surface; the others are caller errors, "
        "refused rather than widened to an unfiltered stream."
    ),
    "stream.desync": (
        "A subscriber was told to refetch everything rather than served a partial "
        "history (reason: truncated | rotated | replay-window | queue-overflow). "
        "Not an error — the self-healing path — but the signal that the log was "
        "rotated under the service, or that a client is reading slower than the "
        "workstation emits."
    ),
    "stream.disconnected": (
        "A subscriber's connection ended (frames: how many were delivered, "
        "reason: client | shutdown). The slot is released, and the tailer stops "
        "when the last subscriber leaves."
    ),
    "service.started": "The control-plane API service came up (host, port).",
    "service.stopped": "The control-plane API service shut down.",
    "restart.scheduled": (
        "A whole-system restart was scheduled (issue-228): a detached "
        "`the-loop restart` was spawned (pid, logfile, withUpgrade). Emitted by "
        "POST /api/v1/restart — the service cannot stop itself synchronously "
        "and still answer, so the API's contract is scheduling."
    ),
    "restart.completed": (
        "A `the-loop restart` finished (ok, withUpgrade): every running service "
        "stopped, the optional CLI upgrade ran, every enabled service started. "
        "Per-service outcomes are in the command's output/logfile. issue-228."
    ),
    "ingress.hosted": (
        "The control-plane service is hosting this ingress (poller | "
        "gh-webhook) as an in-process task (`service.hostIngresses`, "
        "issue-231). Its pidfile lock is held by the service's pid."
    ),
    "ingress.hosted_stopped": (
        "A hosted ingress finished during the service's shutdown; its lock is "
        "released. issue-231."
    ),
    "diagnosis.detected": (
        "Self-diagnosis (issue-242, opt-in) accepted a NEW failure fingerprint "
        "for diagnosis (fingerprint, trigger: the event type that raised it). "
        "Emitted once per fingerprint, on its first attempt."
    ),
    "diagnosis.posted": (
        "Self-diagnosis filed the issue (fingerprint, trigger, url) on the "
        "configured repository, labeled and self-authored — never armed."
    ),
    "diagnosis.deferred": (
        "Self-diagnosis hit the rolling daily cap (selfDiagnosis.maxIssuesPerDay) "
        "and left this candidate for a later scan (fingerprint, trigger). "
        "Deferred, not dropped."
    ),
    "diagnosis.failed": (
        "A diagnosis attempt failed (fingerprint, trigger, stage: agent | post, "
        "attempt, error — scrubbed). Warning-level on purpose: diagnosis.* is "
        "excluded from candidacy, and the level makes that belt-and-braces. "
        "After selfDiagnosis.maxRetries failures the fingerprint is abandoned."
    ),
}


def _utcnow() -> str:
    return (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ]  # microseconds -> milliseconds
        + "Z"
    )


class EventLog:
    """Append-only JSONL writer. Thread-safe; write failures never propagate.

    Each :meth:`emit` appends one ``\\n``-terminated JSON line via an
    ``O_APPEND`` write, so concurrently running processes (receiver + poller +
    sessions CLI) interleave whole lines, never corrupt each other.
    """

    def __init__(
        self, path: Union[str, Path] = DEFAULT_PATH, source: str = "", enabled=True
    ):
        self.path = Path(path)
        self.source = source
        self.enabled = enabled
        self._lock = threading.Lock()
        self._warned = False

    def emit(self, event: str, level: str = "info", **fields) -> None:
        """Append one event record. Unknown ``event`` types are still logged
        (forward compatibility), but instrumentation should register them in
        :data:`EVENT_TYPES`."""
        if not self.enabled:
            return
        record = {
            "ts": _utcnow(),
            "source": self.source,
            "event": event,
            "level": level if level in LEVELS else "info",
            "pid": os.getpid(),
        }
        record.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError as exc:
            if not self._warned:  # warn once — never break ingress over o11y
                self._warned = True
                logger.warning("cannot write event log %s: %s", self.path, exc)


# -- module-level emitter (a no-op until a CLI entry point configures it) -------

_log: Optional[EventLog] = None


def configure(
    source: str, path: Union[str, Path] = DEFAULT_PATH, enabled: bool = True
) -> EventLog:
    """Install the process-wide event log. Called once per CLI entry point."""
    global _log
    _log = EventLog(path=path, source=source, enabled=enabled)
    return _log


def configure_from_file(source: str) -> EventLog:
    """:func:`configure` from ``eventLog`` in the CLI config.

    An unset ``path`` resolves under ``state.root`` (issue-106) — the same
    ``<root>/logs/events.jsonl`` :data:`DEFAULT_PATH` names for the default root.
    """
    from .state import layout_from_config

    data = cli_config.load_cli_config(cli_config.default_cli_config_path())
    cfg = data.get("eventLog") or {}
    return configure(
        source,
        path=str(cfg.get("path") or layout_from_config(data).event_log),
        enabled=bool(cfg.get("enabled", True)),
    )


def load_config(config_path: Optional[Union[str, Path]] = None) -> dict:
    """Best-effort read of ``eventLog`` from the CLI config (``{}`` if unreadable).

    Defaults to the CLI config's resolved path (``cli_config.default_cli_config_path()``
    — ``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/cli-config.yaml``,
    then ``~/.the-loop/cli-config.yaml``, decision-032). ``eventLog`` is top-level in the
    CLI config, unlike the PLUGIN config's
    ``observability.devLevel``/``runtimeLevel``/``browserLogging``.
    """
    path = (
        Path(config_path)
        if config_path is not None
        else cli_config.default_cli_config_path()
    )
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001 - a broken config must not break ingress
        return {}
    return data.get("eventLog") or {}


def emit(event: str, level: str = "info", **fields) -> None:
    """Emit through the configured log; silently a no-op when unconfigured."""
    if _log is not None:
        _log.emit(event, level=level, **fields)


def reset() -> None:
    """Deconfigure the module-level log (tests)."""
    global _log
    _log = None


# -- reader ---------------------------------------------------------------------


def _matches_work_item(record: dict, ref: str) -> bool:
    if record.get("work_item") == ref:
        return True
    return ref in (record.get("work_items") or [])


def record_matches(
    record: dict,
    types: Sequence[str] = (),
    work_item: Optional[str] = None,
    delivery_id: Optional[str] = None,
    source: Optional[str] = None,
    min_level: Optional[str] = None,
    since: Optional[str] = None,
) -> bool:
    """Whether one parsed record passes the given filters.

    ``types`` are fnmatch patterns (``dispatch.*``); ``min_level`` is
    inclusive (``warning`` ⇒ warning + error); ``since`` is an ISO-8601 UTC
    timestamp compared lexicographically against ``ts``.
    """
    if types and not any(
        fnmatch.fnmatch(str(record.get("event", "")), t) for t in types
    ):
        return False
    if work_item and not _matches_work_item(record, work_item):
        return False
    if delivery_id and record.get("delivery_id") != delivery_id:
        return False
    if source and record.get("source") != source:
        return False
    if min_level in LEVELS:
        min_rank = LEVELS.index(str(min_level))
        level = record.get("level")
        if level not in LEVELS or LEVELS.index(str(level)) < min_rank:
            return False
    if since and str(record.get("ts", "")) < since:
        return False
    return True


def parse_lines(lines: Sequence[str], **filters) -> Iterator[dict]:
    """Parse JSONL lines into matching records, skipping corrupt/partial ones."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record_matches(record, **filters):
            yield record


def read_events(path: Union[str, Path], **filters) -> Iterator[dict]:
    """Stream matching records from a JSONL event log, oldest first.

    Tolerates a missing file and corrupt/partial lines (skipped) so a log
    truncated mid-write or rotated externally still reads. Filters are those
    of :func:`record_matches`.
    """
    try:
        handle = open(path, "r", encoding="utf-8")
    except OSError:
        return
    with handle:
        yield from parse_lines(list(handle), **filters)
