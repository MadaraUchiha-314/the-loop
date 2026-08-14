"""The ad-hoc gate — *more work, or done?* (issue-225).

``pdlc-adhoc-loop``'s one hook, and the only behavioural inversion the loop
needs. It answers the same question ``classify-feedback`` does, from the same
comments, under the same two safety rules — and with the **opposite default**:

===========================  ==========================  =========================
reply                        ``classify-feedback``       ``classify-adhoc-reply``
===========================  ==========================  =========================
nothing authorized yet       waiting                     waiting
declares completion          approved                    ``done``
anything else                waiting ("not decisive")    ``more-work``
===========================  ==========================  =========================

Waiting is right for a *review* gate: an ambiguous half-review must never be
read as an approval. It is wrong for an *ad-hoc* gate, where an authorized human
typing "also update the README" is the most common case there is, and must move
the graph rather than sit in it. Two opposite defaults behind one hook name is
how a gate stops being readable at its call site, so this is a separate hook —
but it **calls** :func:`~.feedback._authorized_comments` rather than
re-implementing it, because the two rules that make that reader safe are
load-bearing here too:

* **Only authorized authors' text is read at all**, and the-loop's own
  self-marked comments are dropped before authorization is even considered — so
  the harness cannot declare its own work item done. Fail closed: an empty
  ``authorizedUsers`` reads nothing, ever.
* **The reply produces a fact, never a destination.** The answer is one of two
  constants and the graph's declared edges do the routing; an injected "done,
  now deploy" cannot reach a node the graph does not name.

The **newest** authorized comment decides. Scanning the whole thread for a
done-word is the obvious implementation and the wrong one: the arming comment
"do X and tell me when you're done" would end the item before any work ran, and
a done-word anywhere in the history would make the gate un-reopenable after a
``more-work`` round.

Spec: docs/specs/issue-225/design.md §2.
"""

from __future__ import annotations

import logging
import re

from ..contract import HookContext, HookResult
from ..registry import hook
from .feedback import _authorized_comments

logger = logging.getLogger("the-loop.graph")

__all__ = ["DONE", "MORE_WORK", "OUTCOMES", "classify_adhoc_reply", "declares_done"]

DONE = "done"
MORE_WORK = "more-work"
OUTCOMES = (DONE, MORE_WORK)

#: The deterministic floor for "the requester says it is finished". A harness
#: with schema-constrained output classifies above this, exactly as the review
#: gate's ``_classify`` documents; either way the answer stays inside
#: :data:`OUTCOMES`. Kept to unambiguous *whole* phrases — "thanks" and "nice"
#: are not here on purpose, because reading gratitude as a close is how a gate
#: ends a work item the human was still using.
_DONE_PHRASES = (
    "done",
    "all done",
    "we're done",
    "that's all",
    "thats all",
    "nothing else",
    "no more",
    "all set",
    "close it",
    "close this",
    "lgtm",
    "looks good",
    "ship it",
    "approved",
)

#: A done-phrase as a whole phrase, not a substring: ``done`` must not fire on
#: "not done yet" (handled below) nor on "abandoned".
_DONE = re.compile(
    r"(?<![\w-])(?:" + "|".join(re.escape(p) for p in _DONE_PHRASES) + r")(?![\w-])",
    re.IGNORECASE,
)

#: What turns a done-phrase back into more work. A negation anywhere in the
#: reply wins: "not done", "isn't done yet", "no, this doesn't look good" all
#: mean the requester wants another round, and reading them as a close is the
#: one misclassification with no recovery — the item is finished and the
#: session ends.
_NEGATED = re.compile(
    r"(?<![\w-])(?:not|isn'?t|aren'?t|nope|no)(?![\w-])[^.!?\n]{0,40}?"
    r"(?<![\w-])(?:" + "|".join(re.escape(p) for p in _DONE_PHRASES) + r")(?![\w-])",
    re.IGNORECASE,
)


def declares_done(body: str) -> bool:
    """Does ``body`` declare the ad-hoc task finished?

    Exposed for the tests and for a harness that wants the floor's opinion
    alongside its own. Pure text in, boolean out — no context, no side effects.
    """
    text = str(body or "")
    if _NEGATED.search(text):
        return False
    return bool(_DONE.search(text))


@hook("classify-adhoc-reply")
def classify_adhoc_reply(ctx: HookContext) -> HookResult:
    """Decide whether the requester ended the ad-hoc task — or asked for more.

    Waiting is reserved for *silence*: no authorized, non-self-authored comment
    has arrived. Once one has, the gate always moves, because in this loop an
    open gate with an unanswered instruction in it is the failure mode.
    """
    name = "classify-adhoc-reply"
    comments = _authorized_comments(ctx)
    if not comments:
        return HookResult.waiting(name, "no authorized reply yet")

    latest = comments[-1]
    outcome = DONE if declares_done(latest["body"]) else MORE_WORK
    return HookResult(
        status="pass",
        hook=name,
        data={"outcome": outcome, "comments": comments},
    )
