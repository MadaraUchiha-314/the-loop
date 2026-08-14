"""Open a daemon's logfile before it detaches (what remains of issue-191).

This module once carried the full double-fork + ready-handshake detach for
``poll start --daemon``. issue-228 removed that command, and with it the only
caller: every remaining detached start is a ``Popen(start_new_session=True)``
with the logfile on fds 1/2 (:mod:`the_loop.core.daemons`,
:mod:`the_loop.core.lifecycle`), and ``the-loop start`` proves a daemon came up
by waiting for its pidfile lock instead of the pipe handshake (decision-084).
What survives is the one piece both idioms share: opening the logfile *first*,
in the process with a terminal, so "the output has nowhere to go" fails loudly
rather than producing a daemon that logs nowhere — the defect issue-191 existed
to prevent.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["open_logfile"]


def open_logfile(path: os.PathLike | str) -> int:
    """An append-mode fd on ``path``, creating its parent directory.

    Called **before** any spawn on purpose: a daemon whose output has nowhere to
    go is the defect this module exists to prevent, so the failure has to reach
    the operator's terminal rather than the logfile that could not be opened.
    Raises ``OSError``.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
