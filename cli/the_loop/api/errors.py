"""The two error classes the manager adds to the plane's mapping (issue-374).

The route class maps ``ValueError`` → 400, ``LookupError`` → 404 and ``SpliceError``
→ 500 (issue-212). A fleet needs two answers those cannot give: a key that resolves to
**several** instances is neither the caller's mistake nor a missing resource, and a
member that does not answer is neither either. Both are plain exceptions on purpose —
not subclasses of the three above — so nothing that catches a ``ValueError`` today
swallows a conflict, and the mapping is one ``except`` per outcome.

Pure Python: importable by :mod:`the_loop.core` and :mod:`the_loop.manager` without
FastAPI, exactly as :mod:`the_loop.api.config` is.
"""

from __future__ import annotations

from typing import Sequence

__all__ = ["Conflict", "MemberUnavailable"]


class Conflict(Exception):
    """A key that two or more instances answer for — ``409`` (R2.4, decision-138 D6).

    Never resolved by picking one: a ``stop`` sent to the first, or to both, is the
    two-daemons-steering-one-item failure decision-110 D6 avoided. The caller names
    one with the ``instance`` parameter.
    """

    def __init__(self, message: str, candidates: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.candidates = tuple(candidates)


class MemberUnavailable(Exception):
    """A registered instance that did not answer a keyed operation — ``502`` (R2.9).

    Raised for a transport failure, a timeout, a body that is not what the contract
    promises, or a member whose probe is not ``live``. Never an empty ``200``: a keyed
    operation that silently answered nothing would read as "no such session".
    """

    def __init__(self, message: str, instance: str = "") -> None:
        super().__init__(message)
        self.instance = instance
