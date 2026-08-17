"""How many tmux+claude sessions a work item's pull requests get — the vocabulary.

Three names, one resolver, and nothing else. It lives in a module of its own
because it has **two** readers that cannot see each other (issue-260):

* :mod:`the_loop.webhook.dispatcher`, which routes a pull request's events to a
  conversation, and
* :mod:`the_loop.graph.hooks.selection`, the `phase-selection` gate, which offers
  the choice on the ticket and freezes the answer.

The hook cannot import the dispatcher — ``dispatcher → graphlink → graph`` makes
that a cycle — and a second copy of a three-name vocabulary is exactly how the
config file and the checklist come to disagree about what ``always`` means. So
the names sit below both.

**Who decides** moved in issue-260 and the vocabulary did not. ``routing.tmux.
sessionPerPr`` is now the operator's *default*: the mode the checklist renders
pre-ticked and the answer for every work item that never answered. A work item's
own frozen choice overrides it, for that work item alone. What the three modes
*mean* is unchanged from issue-258/decision-092.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("the-loop.sessions")

__all__ = [
    "SESSION_PER_PR_ALWAYS",
    "SESSION_PER_PR_CROSS_REPOSITORY",
    "SESSION_PER_PR_MODES",
    "SESSION_PER_PR_NEVER",
    "session_per_pr_mode",
]

#: The three answers to "how many tmux+claude sessions do a work item's pull
#: requests get?" (issue-258). ``sessionPerPr`` used to be a boolean; the two
#: booleans still parse, to the two modes they have always meant.
SESSION_PER_PR_NEVER = "never"
SESSION_PER_PR_CROSS_REPOSITORY = "cross-repository"
SESSION_PER_PR_ALWAYS = "always"
SESSION_PER_PR_MODES = (
    SESSION_PER_PR_NEVER,
    SESSION_PER_PR_CROSS_REPOSITORY,
    SESSION_PER_PR_ALWAYS,
)


def session_per_pr_mode(value: Any) -> str:
    """Resolve a configured ``sessionPerPr`` to one of :data:`SESSION_PER_PR_MODES`.

    Total: every input produces a mode. ``True``/``False`` are what every config
    file written before issue-258 says, and they keep meaning exactly what they
    mean today — ``True`` is ``cross-repository``, **not** ``always``, because
    that is what it has meant since issue-253 narrowed it.

    Anything else resolves to the shipped default with a warning, the way
    ``routing.interaction.mode`` does. Fail *closed*: a typo lands on the
    narrower of the two splitting choices, never on the widest one.
    """
    if value is None:
        return SESSION_PER_PR_CROSS_REPOSITORY
    if isinstance(value, bool):
        return SESSION_PER_PR_CROSS_REPOSITORY if value else SESSION_PER_PR_NEVER
    if value in SESSION_PER_PR_MODES:
        return str(value)
    logger.warning(
        "routing.tmux.sessionPerPr: %r is not one of %s; using %r",
        value,
        ", ".join(SESSION_PER_PR_MODES),
        SESSION_PER_PR_CROSS_REPOSITORY,
    )
    return SESSION_PER_PR_CROSS_REPOSITORY
