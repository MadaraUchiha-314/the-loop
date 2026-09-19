"""The records a work item's ledger holds from a channel (issue-389 R4.7, R5.6).

A ``record-context`` or ``record-decision`` act writes a **marked** comment on
the ticket: the-loop's attribution, a visible line naming the act and the
person, the quoted text, and the envelope naming the event type, the source,
the actor and the time (``github.mirror_body``). A session spawned after the
record was made — or one whose delivery was refused — needs those records
without parsing HTML comments by hand: this module reads them back into
plain rows, and ``the-loop channels records`` prints them.

Read-only: one ``gh`` listing of the ticket's comments, no Slack call, no
write. Anything that is not a marked, enveloped record of a wanted type is
skipped — a human's comment, a relay, the-loop's own reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from ..authz import is_self_authored
from .envelope import parse as parse_envelope

__all__ = ["RECORD_TYPES", "Record", "records_from_comments", "render"]

#: The two event types a channel records with the acts (design §4); the verb's
#: ``--type`` choices.
RECORD_TYPES: Sequence[str] = ("context.added", "decision.recorded")

_WHY_PREFIX = "_why:_ "
_DISCUSSED_PREFIX = "_discussed at:_ "


@dataclass(frozen=True)
class Record:
    """One record as the verb prints it — the envelope's facts, the quoted
    text, and what the visible lines carried beside it."""

    type: str
    url: str
    actor: Mapping[str, str]
    ts: str
    text: str
    summary: str = ""
    why: str = ""
    discussed_at: str = ""
    author: str = ""
    created_at: str = ""
    id: str = ""
    detail: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        row = asdict(self)
        row["actor"] = dict(self.actor)
        row["detail"] = dict(self.detail)
        return row


def _record_from_body(body: str) -> Optional[Record]:
    """The record in ``body`` — ``None`` unless it is the-loop's own marked
    comment carrying an envelope of a record type."""
    if not is_self_authored(body):
        return None
    envelope = parse_envelope(body)
    if envelope is None or envelope.type not in RECORD_TYPES:
        return None
    summary = ""
    quoted: List[str] = []
    why = ""
    discussed_at = ""
    for line in body.splitlines():
        if line.startswith("> "):
            quoted.append(line[2:])
        elif line == ">":
            quoted.append("")
        elif not summary and line.startswith("🗣️ "):
            summary = line
        elif line.startswith(_WHY_PREFIX):
            why = line[len(_WHY_PREFIX) :].strip()
        elif line.startswith(_DISCUSSED_PREFIX):
            discussed_at = line[len(_DISCUSSED_PREFIX) :].strip().strip("<>")
    return Record(
        type=envelope.type,
        url="",
        actor=dict(envelope.actor),
        ts=envelope.ts,
        text="\n".join(quoted).strip(),
        summary=summary,
        why=why,
        discussed_at=discussed_at,
    )


def records_from_comments(
    comments: Iterable[Mapping[str, object]], types: Optional[Iterable[str]] = None
) -> List[Record]:
    """Every record among ``comments`` — each a mapping with ``body`` and, when
    the ledger gives them, ``url``, ``author``, ``created_at`` and ``id`` — of
    the wanted ``types`` (both when ``None``), in the order given."""
    wanted = set(types or RECORD_TYPES)
    out: List[Record] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        record = _record_from_body(body)
        if record is None or record.type not in wanted:
            continue
        out.append(
            Record(
                type=record.type,
                url=str(comment.get("url") or ""),
                actor=record.actor,
                ts=record.ts,
                text=record.text,
                summary=record.summary,
                why=record.why,
                discussed_at=record.discussed_at,
                author=str(comment.get("author") or ""),
                created_at=str(comment.get("created_at") or ""),
                id=str(comment.get("id") or ""),
            )
        )
    return out


def render(records: Sequence[Record], work_item: str) -> str:
    """The markdown form: one section per record, the facts as a list, the
    text quoted back — pasteable into ``context.md`` or a decision record."""
    if not records:
        return f"no records on {work_item}\n"
    parts = [f"# Records on {work_item}", ""]
    for n, record in enumerate(records, 1):
        who = ", ".join(f"{k}:{v}" for k, v in sorted(record.actor.items())) or "?"
        parts.append(f"## {n}. {record.type} — {who} — {record.ts or '?'}")
        parts.append("")
        if record.url:
            parts.append(f"- url: {record.url}")
        if record.author:
            parts.append(f"- posted by: {record.author}")
        if record.why:
            parts.append(f"- why: {record.why}")
        if record.discussed_at:
            parts.append(f"- discussed at: {record.discussed_at}")
        if record.summary:
            parts.append(f"- {record.summary}")
        parts.append("")
        parts.extend(f"> {line}" if line else ">" for line in record.text.splitlines())
        parts.append("")
    return "\n".join(parts)
