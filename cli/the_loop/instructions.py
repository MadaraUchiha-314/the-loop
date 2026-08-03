"""Resolve the instruction docs a repository registers — the observable half of
``customInstructions`` (issue-132).

``config.customInstructions`` has let an operator point the-loop at their own convention
docs since issue-59 (decision-029), and the loop reads them at the start of every work
item. What it never had was a way to *check* that: ``onMissing`` was honoured by the
agent's good behaviour and by nothing else, so a mistyped path contributed no guidance
and produced no signal, and a run against a broken registration looked exactly like a
correct one. ``onMissing: error`` was a setting that never errored.

This module answers one question — **which registered docs actually resolve?** — and
:mod:`the_loop.commands.instructions_cmd` turns the answer into a report and an exit
code. It is the same move ``the-loop scenarios`` makes for the Gherkin obligation: an
obligation nothing can observe is an obligation that drifts.

Two properties are load-bearing:

* **It takes an already-loaded config mapping**, never a path. The harness config is
  opened in exactly one module (:mod:`the_loop.harness_config`, decision-044), and
  ``test_harness_config.py`` H2 pins that.
* **It reports facts *about* docs, never their contents.** Absolute and out-of-repo
  paths are supported on purpose — per-machine and company-wide docs are the feature —
  so path confinement is not the boundary. The boundary is output: a doc's body has no
  channel into the report, which is what keeps a hostile doc inert here. The reported
  size is why a preview was not worth adding.

Spec: docs/specs/issue-132/  ·  Decision: 049
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

logger = logging.getLogger("the-loop.instructions")

__all__ = [
    "DEFAULT_ON_MISSING",
    "ON_MISSING_POLICIES",
    "STATES",
    "InstructionDoc",
    "collect_docs",
    "on_missing",
    "unresolved",
]

#: What became of one registered entry.
#:
#: ``missing`` and ``unreadable`` are deliberately distinct. "Nothing is at your path"
#: and "something is at your path but it is not a readable instruction doc" send the
#: operator to different places, and collapsing them would send half of them to the
#: wrong one.
STATES: Tuple[str, ...] = ("present", "missing", "unreadable", "invalid")

ON_MISSING_POLICIES: Tuple[str, ...] = ("warn", "error", "ignore")
DEFAULT_ON_MISSING = "warn"


@dataclass(frozen=True)
class InstructionDoc:
    """One entry of ``customInstructions.docs``, and what became of it.

    This is the command's public contract: ``as_dict`` is what ``--format json`` emits,
    so a harness can shell out to ``the-loop instructions`` and act on the result.
    """

    path: str  #: exactly as configured; "" when the entry carried no usable path
    resolved: str  #: absolute path, or "" when there was nothing to resolve
    state: str  #: one of :data:`STATES`
    notes: str = ""  #: the operator's own note about when the doc matters
    detail: str = ""  #: why an invalid/unreadable entry is what it is
    size: int = -1  #: bytes, for present docs only; -1 otherwise

    @property
    def resolved_ok(self) -> bool:
        """Whether this entry's guidance actually reaches the agent."""
        return self.state == "present"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "resolved": self.resolved,
            "state": self.state,
            "notes": self.notes,
            "detail": self.detail,
            "size": self.size,
        }


def _section(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("customInstructions")
    return section if isinstance(section, Mapping) else {}


def on_missing(config: Mapping[str, Any]) -> str:
    """``customInstructions.onMissing``, defaulting to ``warn``.

    An unrecognised value falls back to ``warn`` rather than to ``ignore``: a typo in
    the policy must not quietly disable the very check that catches typos.
    """
    value = str(_section(config).get("onMissing") or DEFAULT_ON_MISSING).strip().lower()
    if value not in ON_MISSING_POLICIES:
        logger.warning(
            "unknown customInstructions.onMissing %r; treating it as %r",
            value,
            DEFAULT_ON_MISSING,
        )
        return DEFAULT_ON_MISSING
    return value


def _invalid(entry: Any) -> InstructionDoc:
    """An entry the-loop could not read as a registration.

    Reported rather than dropped, and counted as unresolved. Silently skipping a
    malformed entry is the same silence issue-132 exists to remove — the operator
    believes a doc is registered, and nothing says otherwise.
    """
    if not isinstance(entry, Mapping):
        detail = f"entry is a {type(entry).__name__}, expected a mapping with a 'path'"
    else:
        raw = entry.get("path")
        detail = (
            "entry has no 'path'"
            if raw is None
            else f"'path' is a {type(raw).__name__}, expected a non-empty string"
            if not isinstance(raw, str)
            else "'path' is blank"
        )
    return InstructionDoc(path="", resolved="", state="invalid", detail=detail)


def _resolve(root: Path, entry: Mapping[str, Any]) -> InstructionDoc:
    configured = str(entry["path"]).strip()
    notes = str(entry.get("notes") or "").strip()

    # An absolute path is used as given: decision-029 supports per-machine docs living
    # outside the repository, so this is the feature and not an escape to confine.
    candidate = Path(configured)
    target = candidate if candidate.is_absolute() else root / candidate

    def record(state: str, detail: str = "", size: int = -1) -> InstructionDoc:
        return InstructionDoc(
            path=configured,
            resolved=str(target),
            state=state,
            notes=notes,
            detail=detail,
            size=size,
        )

    try:
        # exists() follows symlinks, so a broken link reads as "nothing is there" —
        # which it is.
        if not target.exists():
            return record("missing")
        if not target.is_file():
            return record("unreadable", "not a regular file")
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return record("unreadable", f"{type(exc).__name__}: {exc}")

    # The byte count, never a preview: the whole reason a hostile doc is inert here is
    # that its body has no channel into the report.
    return record("present", size=len(text.encode("utf-8")))


def collect_docs(root: Path, config: Mapping[str, Any]) -> List[InstructionDoc]:
    """Every registered instruction doc, in configured order, with its state.

    ``config`` is an already-loaded harness config (see :mod:`the_loop.harness_config`).
    Order is preserved because it is load-bearing: ``reference/instructions.md`` says
    later docs win on conflict, so a reordered report would misdescribe precedence.

    A ``docs`` value that is not a list yields no docs and a warning — fail closed to
    "nothing registered" rather than raise, matching the best-effort contract every
    repo-scoped read honours.
    """
    entries = _section(config).get("docs") or []
    if not isinstance(entries, (list, tuple)):
        logger.warning(
            "customInstructions.docs is a %s, expected a list; reading it as empty",
            type(entries).__name__,
        )
        return []

    docs: List[InstructionDoc] = []
    for entry in entries:
        if (
            isinstance(entry, Mapping)
            and isinstance(entry.get("path"), str)
            and entry["path"].strip()
        ):
            docs.append(_resolve(Path(root), entry))
        else:
            docs.append(_invalid(entry))
    return docs


def unresolved(docs: Sequence[InstructionDoc]) -> List[InstructionDoc]:
    """The docs whose guidance is **not** reaching the agent.

    Everything the command could not positively confirm as ``present`` counts — including
    ``invalid``. This is what ``onMissing`` is evaluated against.
    """
    return [doc for doc in docs if not doc.resolved_ok]
