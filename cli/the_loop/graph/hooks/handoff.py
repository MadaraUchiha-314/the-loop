"""``import-handoff`` — re-check a handoff's carried files, demote on a failure.

A developer who talked an idea through with Claude hands it to the-loop at the
stage they reached (issue-517). The session at the ``import-handoff`` node
writes the carried artifacts to ``docs/specs/<id>/`` and commits them; this hook
is the deterministic check that follows. For each artifact the record names, in
chain order (:data:`~the_loop.core.handoff.CHAIN`), it asks three things:

* the file exists in the spec directory;
* its bytes hash to the record's ``sha256`` (abuse case 4);
* it passes the ``validate-artifacts`` section check of the node that produces
  it — read from the compiled graph, so the two can never drift apart.

On the **first** failure it *demotes*: the result names that producing node and
every node after it, up to (not including) the record's ``enter``, for the
runtime to remove from ``state.skips``. The walk then routes into the producing
node — earlier, never later, than ``enter`` (R7.3). When no file verifies at
all, the item starts at the first node after this one, ``brainstorming``
(R7.5). Un-skipping only ever adds work, so the hook may be wrong in the safe
direction only: **it never adds a skip.**

Artifacts the developer approved in the chat (``approved-in-chat``) and that
verified are locked here — ``status: approved``, ``approvedBy: [<author>]`` and
``approvedVia: handoff <commentUrl>`` (R6.5). The furthest artifact is never
locked by the handoff; only its gate does that (R8.3). The record already
enforces this; the hook enforces it again because the state file is
agent-writable.

A carried body is data. Nothing here interprets, executes or templates it: it is
hashed, its headings are read, and its front matter gains three lines.

Spec: docs/specs/issue-517/design.md §C8, §Security design.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ...core.handoff import CHAIN, HandoffRecord, sha256_text
from ..contract import HookContext, HookResult, Message
from ..frontmatter import split_front_matter
from ..model import Graph, Node, artifact_names
from ..registry import hook
from .artifacts import NAME as VALIDATE_ARTIFACTS
from .artifacts import validate_artifacts
from .feedback import _locked_text

NAME = "import-handoff"

_VIA_LINE = re.compile(r"^(\s*approvedVia\s*:)([^#]*)(#.*)?$")


def via_of(comment_url: str) -> str:
    """The ``approvedVia`` value a handoff's lock writes."""
    return f"handoff {comment_url}".strip()


def locked_by_handoff(text: str, via: str) -> bool:
    """Whether ``text`` carries this handoff's own lock (``status: approved``
    and ``approvedVia: <via>``).

    The lock rewrites the front matter, so the file no longer hashes to the
    record's ``sha256``. A re-run of the hook, or of ``the-loop handoff
    import``, must recognise its own lock rather than read it as tampering
    (self-review round 1). The shape check still runs on such a file.
    """
    if not via or via == "handoff":
        return False
    try:
        front, _ = split_front_matter(text)
    except Exception:  # noqa: BLE001 — unreadable front matter is not a lock
        return False
    return (
        str(front.get("status", "")).strip() == "approved"
        and str(front.get("approvedVia", "")) == via
    )


@dataclass
class Demotion:
    """What the check found: the nodes to un-skip, the refusal (at most one —
    the first), and the artifacts that verified, in chain order."""

    unskip: List[str] = field(default_factory=list)
    demoted: List[Dict[str, str]] = field(default_factory=list)
    verified: List[str] = field(default_factory=list)


def _producer(graph: Graph, name: str) -> Optional[Node]:
    """The node whose ``produces`` accepts ``name`` (``bugfix.md`` resolves to
    the node producing ``requirements.md|bugfix.md``)."""
    for node in graph.ordered():
        if any(name in artifact_names(entry) for entry in node.produces):
            return node
    return None


def _shape_entry(node: Node) -> Optional[Mapping[str, Any]]:
    """The ``with:`` of the producing node's own ``validate-artifacts`` entry —
    the one gating what it authored, not a ``validates:`` or conditional one."""
    for entry in node.exit:
        if not isinstance(entry, Mapping) or entry.get("hook") != VALIDATE_ARTIFACTS:
            continue
        params = entry.get("with") or {}
        if params.get("validates") or params.get("onlyWhenSkipped"):
            continue
        return params
    return None


def _shape_findings(ctx: HookContext, node: Node) -> List[str]:
    """The producing node's ``validate-artifacts`` run on the file as carried —
    the same hook, with the same params, so the gate that would have produced
    the artifact is the one that judges it. ``[]`` when it holds up, or when the
    node declares no shape check."""
    params = _shape_entry(node)
    if params is None:
        return []
    probe = dataclasses.replace(
        ctx,
        node=node.as_mapping(),
        boundary="exit",
        params=dict(params),
        results=[],
        skipped_artifacts=frozenset(),
        visited=frozenset(),
    )
    result = validate_artifacts(probe)
    if result.status == "block":
        return [m.text for m in result.messages] or ["failed its shape check"]
    return []


def _path_to(graph: Graph, start: str, enter: str) -> List[str]:
    """Nodes from ``start`` up to and not including ``enter``, in declaration
    order — the order the walk takes them.

    Declaration order, not the ``on: skipped`` edges: a skipped producing node
    routes *around* its approval gate (``brainstorming`` → ``requirements-
    definition``), and un-skipping the producer alone would leave the gate
    skipped, so the artifact it re-authors would reach the next phase unapproved.
    ``[]`` when ``enter`` does not come after ``start`` — a handoff never
    un-skips a node past its own entry.
    """
    ids = [n.id for n in graph.ordered()]
    if start not in ids or enter not in ids:
        return []
    first, last = ids.index(start), ids.index(enter)
    return ids[first:last] if first < last else []


def _inside(path: Path, root: Path) -> bool:
    """Whether ``path`` resolves inside ``root`` (a symlinked folder would not)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _ordered(record: HandoffRecord) -> List[Tuple[str, str]]:
    rank = {name: i for i, name in enumerate(CHAIN)}
    named = [(a.name, a.sha256) for a in record.artifacts if a.name in rank]
    return sorted(named, key=lambda pair: rank[pair[0]])


def demotion(ctx: HookContext, graph: Graph, record: HandoffRecord) -> Demotion:
    """Check ``record``'s artifacts in chain order; demote on the first failure.

    Pure but for reading files under ``ctx.work_item.spec_dir``. The node after
    the one this runs at (``brainstorming``) is where an item with no verified
    file starts.
    """
    spec_dir = ctx.work_item.spec_dir
    origin = ctx.node_id or NAME
    via = via_of(record.comment_url)
    found = Demotion()
    failure: Optional[Tuple[Node, str, str]] = None
    for name, sha in _ordered(record):
        node = _producer(graph, name)
        path = spec_dir / name
        reason = ""
        if path.is_symlink() or not _inside(path, spec_dir):
            # Never follow a link out of the spec folder (self-review round 1).
            reason = f"{name} is a symlink or lies outside the spec directory"
        elif not path.is_file():
            reason = f"{name} is missing from the spec directory"
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                text, reason = "", f"{name} could not be read: {exc}"
            if (
                not reason
                and sha256_text(text) != sha
                and not locked_by_handoff(text, via)
            ):
                reason = f"{name} does not match the record's sha256"
            if not reason and node is not None:
                reason = "; ".join(_shape_findings(ctx, node))
        if reason:
            if node is not None:
                failure = (node, name, reason)
            break
        found.verified.append(name)

    if failure is None and len(found.verified) == len(record.artifacts):
        return found
    if failure is not None:
        node, name, reason = failure
        found.demoted.append({"node": node.id, "artifact": name, "reason": reason})
        start = node.id
    else:
        start = ""
    if not found.verified:
        # R7.5: nothing carried could be verified — start from the beginning.
        start = graph.next_node(origin, "pass") or start
    if start:
        found.unskip = _path_to(graph, start, record.enter)
    return found


def _furthest(record: HandoffRecord) -> str:
    named = _ordered(record)
    return named[-1][0] if named else ""


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "").replace('"', "") + '"'


def _with_via(text: str, via: str) -> Optional[str]:
    """``text`` (front matter already present) with ``approvedVia: <via>``."""
    lines = text.split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if not text.startswith("---") or end is None:
        return None
    value = f"approvedVia: {_quoted(via)}"
    for i in range(1, end):
        if _VIA_LINE.match(lines[i]):
            lines[i] = value
            break
    else:
        lines.insert(end, value)
    return "\n".join(lines)


def _lock(path: Path, author: str, via: str) -> str:
    """Lock one artifact as approved by the handoff; ``""`` or the failure."""
    try:
        text = path.read_text(encoding="utf-8")
        front, _ = split_front_matter(text)
        prior = front.get("approvedBy")
        if (
            str(front.get("status", "")).strip() == "approved"
            and isinstance(prior, list)
            and author in [str(v) for v in prior]
            and str(front.get("approvedVia", "")) == via
        ):
            return ""  # already locked by this handoff
        updated = _locked_text(text, [author])
        updated = _with_via(updated, via) if updated is not None else None
        if updated is None:
            return "its front matter cannot be edited"
        path.write_text(updated, encoding="utf-8")
        front, _ = split_front_matter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return f"could not lock: {exc}"
    recorded = front.get("approvedBy")
    if (
        str(front.get("status", "")).strip() != "approved"
        or not isinstance(recorded, list)
        or author not in [str(v) for v in recorded]
        or str(front.get("approvedVia", "")) != via
    ):
        return "the lock did not land"
    return ""


@hook(NAME)
def import_handoff(ctx: HookContext) -> HookResult:
    """Verify the carried files; demote and lock. Always ``pass`` — the routing
    change is the un-skip the runtime applies — unless a lock cannot land."""
    if not ctx.handoff:
        return HookResult.ok(NAME, handoff=False)
    if ctx.graph is None:
        # Nothing to resolve producing nodes against: claim nothing verified,
        # lock nothing, change nothing.
        return HookResult.ok(NAME, handoff=True, verified=[])
    record = HandoffRecord.from_dict(ctx.handoff)
    found = demotion(ctx, ctx.graph, record)

    findings: List[Message] = []
    locked: List[str] = []
    furthest = _furthest(record)
    via = via_of(record.comment_url)
    for name in record.approved_in_chat:
        if name not in found.verified or name == furthest or not record.author:
            continue
        path = ctx.work_item.spec_dir / name
        problem = _lock(path, record.author, via)
        if problem:
            findings.append(Message(text=problem, path=name))
        else:
            locked.append(name)

    data: Dict[str, Any] = {
        "handoff": True,
        "verified": list(found.verified),
        "handoffUnskip": list(found.unskip),
        "handoffDemoted": [dict(d) for d in found.demoted],
        "locked": locked,
    }
    if findings:
        # Fail closed, as `lock-artifacts` does: an approval this hook cannot
        # prove it recorded is not reported as recorded.
        return HookResult.blocked(NAME, findings, retriable=False, **data)
    result = HookResult.ok(NAME, **data)
    for entry in found.demoted:
        result.messages.append(
            Message(
                text=f"demoted to {entry['node']}: {entry['reason']}",
                path=entry["artifact"],
                severity="warning",
            )
        )
    return result
