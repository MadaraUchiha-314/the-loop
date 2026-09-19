"""The GitHub ledger — the channel of record (issue-309, decision-103).

GitHub was always where the-loop's conversation *lived*; issue-309 makes that a role
with a name. The ledger does one thing no other channel does: it **records** every
event that originated elsewhere, before any other channel receives it, so the work
item stays the single source of truth whatever surface the human actually used.

Four record shapes, chosen by event type — and the choice is the security design:

======================  =======================================  ======  ========
event                   body                                     marker  envelope
======================  =======================================  ======  ========
session.awaiting_input  the question (the record IS the ask)     yes     yes
work-item.reply,        quoted, scrubbed, keywords defanged      yes     yes
context.added,          (issue-389: the act named on the line)
decision.recorded
gate.feedback,          quoted, scrubbed, keywords **kept**      **no**  yes
control.command
work-item.create        a new issue: title + body                no      yes
======================  =======================================  ======  ========

The unmarked rows are the point. the-loop writes with the operator's own credentials
(decision-023), so a comment it posts *without* the self-authored marker is, to both
ingresses, a comment by an authorized user — and every guard that exists for such a
comment runs on it unchanged: the marker check, ``authorizedUsers``, the control
seam's named-actor re-check, ``classify-feedback``'s authorized-author filter. That
is how a channel advances the loop: **through the ledger, never around it.**
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from ..authz import mark_self_authored
from ..redact import (
    defang_control_keywords,
    neutralise_broadcasts,
    scrub,
    strip_html_comments,
)
from ..sessions import WorkItemRef
from .base import Event, PostResult
from .envelope import Envelope, stamp

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "GitHubLedger",
    "TITLE_MAX_CHARS",
    "control_keywords",
    "gh_binary",
    "mirror_body",
    "relay_body",
]

#: GitHub allows longer titles; a DM's first line rarely deserves more.
TITLE_MAX_CHARS = 80

#: The events whose record must reach the ledger's ingress as a HUMAN comment —
#: unmarked, keywords intact — because ingress is what acts on them.
_RELAYED = ("gate.feedback", "control.command")

#: The events whose record is the-loop's OWN marked comment — quoted, scrubbed,
#: keywords defanged — because the channel already delivered them into the
#: session and no gate may ever read them as a person's words (issue-389,
#: decision-133 D4): a reply, a thread handed over as context, a decision.
_MIRRORED = ("work-item.reply", "context.added", "decision.recorded")

#: What the visible line of each mirrored record says it is.
_MIRROR_LINES = {
    "work-item.reply": "reply from {who} on the **{source}** channel, recorded "
    "here as the answer of record",
    "context.added": "📎 context from {who} on the **{source}** channel — "
    "{count} message(s) from {thread}, recorded here and appended to "
    "`context.md` by the session",
    "decision.recorded": "📌 decision from {who} on the **{source}** channel"
    "{kind} — recorded here and written up as a decision record by the session",
}


def control_keywords(cli_config: Optional[Mapping]) -> Tuple[str, ...]:
    """Every control keyword this deployment recognises — defaults + configured."""
    from ..control import DEFAULT_KEYWORDS

    configured = (
        (dict(cli_config or {}).get("routing") or {}).get("control") or {}
    ).get("keywords") or {}
    keywords = dict(DEFAULT_KEYWORDS)
    if isinstance(configured, Mapping):
        keywords.update({str(k): str(v) for k, v in configured.items()})
    return tuple(keywords.values())


def gh_binary(cli_config: Optional[Mapping]) -> str:
    section = (
        (dict(cli_config or {}).get("integrations") or {}).get("github") or {}
    ).get("cli") or {}
    return str(section.get("binary", "gh"))


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" for line in (text.splitlines() or [""]))


def _who(event: Event) -> str:
    """The visible attribution: the person's label, and the channel-native id."""
    native = event.actor.id_on(event.source) if event.actor else ""
    label = event.actor.label if event.actor else "(unknown)"
    if native and native != label:
        return f"`{label}` (`{event.source}:{native}`)"
    return (
        f"`{label}`" if label != "(unknown)" else f"an unknown `{event.source}` member"
    )


def _envelope(event: Event) -> Envelope:
    return Envelope(
        type=event.event_type,
        source=event.source,
        actor=event.actor.to_dict() if event.actor else {},
    )


def mirror_body(event: Event, cli_config: Optional[Mapping]) -> str:
    """The record of a mirrored event — quoted, scrubbed, defanged, marked.

    A ``work-item.reply``, and since issue-389 a ``context.added`` snapshot and
    a ``decision.recorded`` decision: the visible line names the act, the
    person and — from ``event.detail`` — the thread, the count, the kind and
    the rationale, all composed from fixed words and the event's own fields.

    The marker is licensed here because the-loop composed this comment (a report
    quoting the channel user, the ``_reply_report`` precedent) — and it is
    load-bearing: an unmarked copy of the answer would be forwarded by the poller
    into the very session the pipeline already delivered it to, and an unmarked
    decision would be read by a gate as an approval (decision-133 D4).
    """
    # The quote is another author's words (issue-389 A5): every `<!-- … -->`
    # inside it goes — a pasted marker would make `mark_self_authored` treat
    # the body as already stamped, a pasted envelope would be parsed as the
    # record's own — and a Slack broadcast is neutralised so a snapshot never
    # pages a room when it is read back.
    safe = defang_control_keywords(
        neutralise_broadcasts(strip_html_comments(scrub(event.text))),
        control_keywords(cli_config),
    )
    detail = event.detail or {}
    thread = str(detail.get("thread") or "")
    kind = str(detail.get("kind") or "")
    line = _MIRROR_LINES.get(event.event_type, _MIRROR_LINES["work-item.reply"])
    line = line.format(
        who=_who(event),
        source=event.source,
        count=str(detail.get("count") or "?"),
        thread=f"<{thread}>" if thread else "a thread",
        kind=f" (kind: {kind})" if kind else "",
    )
    body = f"🗣️ **the-loop** — {line}:\n\n" + _quoted(safe)
    rationale = str(detail.get("rationale") or "").strip()
    if rationale:
        body += "\n\n_why:_ " + scrub(rationale).replace("\n", " ")
    if event.event_type == "decision.recorded" and thread:
        body += f"\n\n_discussed at:_ <{thread}>"
    return stamp(mark_self_authored(body), _envelope(event))


def relay_body(event: Event) -> str:
    """The record of a ``gate.feedback`` / ``control.command`` — quoted, scrubbed,
    **unmarked**, keywords intact, so the ledger's ingress reads it as this
    person's own words. The attribution says which channel it was typed on."""
    if event.event_type != "gate.feedback":
        what = "control command"
    elif str(event.detail.get("gate") or "") == "unknown":
        # The pipeline could not read the gate (issue-321): the record is a reply
        # the ledger's ingress judges, and must not claim an answer it never saw.
        what = "reply"
    else:
        what = "answer to the open gate"
    body = (
        f"🗣️ **the-loop** — {what} from {_who(event)} on the **{event.source}** "
        "channel, recorded here so the loop reads it from the work item:\n\n"
        + _quoted(scrub(event.text))
    )
    return stamp(body, _envelope(event))


def ask_body(event: Event) -> str:
    """The ask's record is the question itself, marked (issue-208) and enveloped."""
    return stamp(mark_self_authored(event.text), _envelope(event))


def issue_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = first.lstrip("#").strip() or "Work item from a channel"
    if len(first) > TITLE_MAX_CHARS:
        first = first[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return first


def issue_body(event: Event) -> str:
    """A kickoff issue's body: the message, an attribution, the envelope — and NO
    self-authored marker, because the issue must be armable (a marked ``issues``
    event is dropped at ingress: the self-diagnosis rule, decision-103 D7)."""
    body = (
        scrub(event.text).rstrip()
        + f"\n\n---\n\n🗣️ _Opened from the **{event.source}** channel by "
        f"{_who(event)} through the-loop._"
    )
    return stamp(body, _envelope(event))


class GitHubLedger:
    """The ledger: comments through the operator's ``gh`` (best-effort), issues too."""

    name = "github"

    def __init__(
        self,
        cli_config: Optional[Mapping[str, Any]] = None,
        *,
        post_comment: Optional[Callable] = None,
        create_issue: Optional[Callable] = None,
    ):
        self.cli_config: Dict[str, Any] = dict(cli_config or {})
        self._post_comment = post_comment
        self._create_issue = create_issue

    def subscribes(self, event_type: str) -> bool:
        return False  # the ledger is written to, not subscribed

    def may_publish(self, event_type: str) -> bool:
        return False  # its ingress publishes comment.*; a grant is a channel's

    def post(self, event: Event) -> PostResult:
        return self.record(event)

    # -- recording -----------------------------------------------------------

    def record(self, event: Event) -> PostResult:
        if event.event_type == "work-item.create":
            return self._create(event)
        try:
            item = WorkItemRef.parse(event.work_item)
        except ValueError as exc:
            return PostResult(channel=self.name, ok=False, error=str(exc))
        if item.provider != "github":
            return PostResult(
                channel=self.name,
                ok=False,
                error=f"{item.ref} is not a GitHub work item",
            )
        if event.event_type == "session.awaiting_input":
            body = ask_body(event)
        elif event.event_type in _RELAYED:
            body = relay_body(event)
        elif event.event_type in _MIRRORED:
            body = mirror_body(event, self.cli_config)
        else:
            body = stamp(mark_self_authored(event.text), _envelope(event))
        post = self._post_comment
        if post is None:
            from .. import comments

            post = comments.post_issue_comment_with_url
        try:
            outcome = tuple(post(item, body, gh_binary=gh_binary(self.cli_config)))
        except Exception as exc:  # the writer is best-effort by contract
            outcome = (False, str(exc), "")
        # Both writer shapes are honoured: `(ok, error)` and `(ok, error, url)`.
        ok, error = bool(outcome[0]), str(outcome[1] or "") if len(outcome) > 1 else ""
        url = str(outcome[2] or "") if len(outcome) > 2 else ""
        return PostResult(
            channel=self.name, ok=bool(ok), error=error or "", url=url or ""
        )

    def _create(self, event: Event) -> PostResult:
        repo = str(event.detail.get("repo") or "")
        if not repo:
            return PostResult(
                channel=self.name, ok=False, error="kickoff-disabled: no repo"
            )
        labels = [
            lbl.strip()
            for lbl in str(event.detail.get("labels") or "").split(",")
            if lbl.strip()
        ]
        create = self._create_issue
        if create is None:
            from .. import comments

            create = comments.create_issue
        try:
            ok, error, ref, url = create(
                repo,
                issue_title(event.text),
                issue_body(event),
                labels,
                gh_binary=gh_binary(self.cli_config),
            )
        except Exception as exc:  # best-effort, like every ledger write
            ok, error, ref, url = False, str(exc), "", ""
        return PostResult(
            channel=self.name,
            ok=bool(ok),
            error=error or "",
            url=url or "",
            ref=ref or "",
        )
