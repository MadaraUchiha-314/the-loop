"""The grammar after the mention (issue-389, decision-133 D3).

A message meant for the-loop carries ``@the-loop`` and arrives as Slack's
``app_mention`` event. What follows the mention is read by **one rule and no
model**: the first token is a verb, a control keyword's last word, or nothing
in particular — and then the message is a reply, delivered to the session as
input exactly as a thread reply has always been.

Three verbs are the-loop's own: ``record-context`` (a thread becomes auditable
context), ``record-decision <text>`` (a decision becomes a decision record) and
``help`` (the grammar, answered ephemerally). A control keyword's last word —
``start``, ``execute``, ``add-collaborator`` — is composed into the **configured**
keyword exactly as the slash command composes it (issue-334), so one grammar
serves the thread, the command and the mention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from ..control import COLLABORATOR_COMMANDS, ControlConfig

__all__ = [
    "KINDS",
    "VERBS",
    "Verb",
    "addresses_a_verb",
    "compose_keyword",
    "help_text",
    "parse_verb",
    "strip_mention",
]

#: The-loop's own verbs, matched as the whole first token, case-insensitively.
VERBS: Tuple[str, ...] = ("record-context", "record-decision", "help")

#: What a decision may be about. Optional on the typed form (``record-decision
#: tech: keep poll mode``); the modal's select offers exactly these.
KINDS: Tuple[str, ...] = ("product", "design", "tech")

#: A Slack user mention as it appears in message text: ``<@U0123>`` or
#: ``<@U0123|handle>``. Only the token naming the bot's own id is removed.
_MENTION_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")

#: The modal's rationale separator (issue-389 R6.3): fixed words, so a typed
#: decision may carry one too and both parse alike.
_WHY = " — why: "


@dataclass(frozen=True)
class Verb:
    """One parsed verb: its name, the text after it, and — for a decision — the
    kind and the rationale when either was given."""

    name: str
    rest: str
    kind: str = ""
    rationale: str = ""


def strip_mention(text: str, bot_id: str) -> Tuple[str, bool]:
    """``text`` without the bot's own mention token(s), and whether one was there.

    Another member's mention stays: it is part of what the person said. Runs of
    whitespace left by the removal collapse to one space, so the first token of
    the result is the first word the person typed after the mention.
    """
    if not bot_id:
        return text, False
    found = False

    def drop(match: re.Match) -> str:
        nonlocal found
        if match.group(1) == bot_id:
            found = True
            return " "
        return match.group(0)

    stripped = _MENTION_RE.sub(drop, text or "")
    if not found:
        return text, False
    # Only horizontal whitespace collapses: the kickoff's title/body split and a
    # multi-line decision read the text by its lines (R1.5).
    lines = [" ".join(line.split()) for line in stripped.split("\n")]
    return "\n".join(lines).strip(), True


def addresses_a_verb(text: str) -> bool:
    """Whether ``text`` reads as a mention followed by one of the-loop's verbs
    once EVERY ``<@…>`` token is removed — the shape of an address when the
    bot's own id is unknown, as opposed to a colleague mentioned in prose."""
    if "<@" not in (text or ""):
        return False
    bare = " ".join(_MENTION_RE.sub(" ", text).split())
    return parse_verb(bare) is not None


def parse_verb(text: str) -> Optional[Verb]:
    """The verb ``text`` opens with, or ``None`` when it opens with none.

    Only the **first token** is read (R3.1): ``we should record-context this`` is
    prose, and so is a token that merely starts like a verb. ``record-decision``
    additionally reads an optional leading ``<kind>:`` and a trailing
    ``— why: <rationale>``, the shape the modal composes (R6.3).
    """
    parts = (text or "").strip().split(None, 1)
    if not parts:
        return None
    name = parts[0].lower()
    if name not in VERBS:
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    if name != "record-decision":
        return Verb(name, rest)
    kind = ""
    head = rest.split(":", 1)
    if len(head) == 2 and head[0].strip().lower() in KINDS:
        kind = head[0].strip().lower()
        rest = head[1].strip()
    rationale = ""
    if _WHY in rest:
        rest, rationale = rest.rsplit(_WHY, 1)
        rest, rationale = rest.strip(), rationale.strip()
    return Verb(name, rest, kind=kind, rationale=rationale)


def compose_keyword(text: str, control: ControlConfig) -> str:
    """``text`` with a leading control verb replaced by its configured keyword.

    ``start`` → ``the-loop start``; an operator's ``loop go`` makes ``go`` (and
    the command's own name, ``start``) compose to ``loop go`` — the slash
    command's rule (:func:`~.commands._command_for`), so the three surfaces
    agree. A first token that names no enabled command leaves the text as it is:
    it is a reply. Nothing from the text reaches the composed keyword except the
    remainder, which the control parser validates as it validates a typed line.
    """
    from .commands import _command_for

    parts = (text or "").strip().split(None, 1)
    if not parts:
        return text
    command = _command_for(parts[0].lower(), control)
    if command is None:
        return text
    keyword = control.keyword(command)
    if not keyword:
        return text
    rest = parts[1].strip() if len(parts) > 1 else ""
    if command in COLLABORATOR_COMMANDS:
        # A member typed as Slack types them (R3.5): `<@U0456>` or
        # `<@U0456|dana>` is the roster's `slack:U0456` token.
        rest = _MENTION_RE.sub(r"slack:\1", rest)
    return f"{keyword} {rest}".strip()


def help_text(config) -> str:
    """The grammar, taught (R3.2): every verb, the keyword rule, the fallthrough,
    and which of the two act grants this channel holds. ``config`` is the parsed
    ``channels.slack`` section (its ``publish`` list is read)."""
    grants = "\n".join(
        f"• {grant}: {'granted' if grant in config.publish else 'not granted'}"
        for grant in ("context.added", "decision.recorded", "control.command")
    )
    return (
        "*Addressing the-loop* — mention it, then one of:\n"
        "• `record-context` (in a thread) — snapshot this thread onto the work "
        "item as context\n"
        "• `record-decision [product|design|tech:] <text> [— why: <rationale>]` "
        "— record a decision (authorized users only)\n"
        "• `add-collaborator @login` or `slack:U…` — let that person feed this "
        "work item (authorized users only)\n"
        "• `start`, `execute`, … — any control keyword's last word "
        "(authorized users only)\n"
        "• `help` — this text\n"
        "• anything else — a reply, delivered to the session as input\n"
        f"What this channel may do here:\n{grants}"
    )
