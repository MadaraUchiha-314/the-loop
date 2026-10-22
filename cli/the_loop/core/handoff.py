"""Core capability: the handoff record (issue-517, design §C2, R5, R6).

A developer who talked an idea through with Claude hands it to the-loop with one
command. That command posts a **handoff record** on the GitHub issue: a
versioned, machine-read comment naming the stage the developer reached, the node
the walk enters, the artifacts carried (each pinned by its ``sha256``) and where
they travel (a spec branch, the ticket itself, or the spec-chain artifact). The
poller and the spawned session read it to start the graph at that stage.

The record crosses a trust boundary — a public comment into state-writing code —
so this module is deliberately strict and fails closed:

* the record is a strict ``key: value`` block after :data:`MARKER`; an unknown
  version or an unknown key rejects it (R5.5);
* ``enter`` must equal :func:`stage_entry` for the stage and artifacts, and lie in
  :data:`ALLOWED_ENTRY`, so no record reaches implementation (abuse case 2);
* artifact names are the closed set :data:`CHAIN` — no path ever comes from the
  record;
* a carried branch must start ``the-loop/`` and pass ``git check-ref-format``'s
  rules (:func:`is_valid_branch`);
* :func:`find_record` admits a record only from an authorized author or
  the-loop itself, and the author and URL come from the API's comment metadata,
  never from the text (abuse case 1). Part comments count only when the record's
  author wrote them (:func:`collect_parts`).

With ``carried-by: ticket`` each file follows in a ``<details>`` block holding a
fenced body (a fence longer than any backtick run in the file, so carried
Markdown survives). A body past GitHub's 65,536-character comment limit
continues in part comments opening with ``<!-- the-loop:handoff-part v1 n/N -->``
— never truncated; a single large file is split into consecutive chunks that
:func:`extract_files` rejoins byte-equal.

Spec: docs/specs/issue-517/design.md §C2, §Security design.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from dataclasses import dataclass, replace
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

__all__ = [
    "ALLOWED_ENTRY",
    "CHAIN",
    "COMMENT_LIMIT",
    "MARKER",
    "PART_MARKER",
    "STAGES",
    "HandoffArtifact",
    "HandoffRecord",
    "collect_parts",
    "extract_files",
    "find_record",
    "is_valid_branch",
    "parse",
    "parse_with_reason",
    "render",
    "sha256_text",
    "stage_entry",
]

MARKER = "<!-- the-loop:handoff v1 -->"
# Format with ``n`` (1-based) and ``N`` (the total number of parts).
PART_MARKER = "<!-- the-loop:handoff-part v1 {n}/{N} -->"
COMMENT_LIMIT = 65536
# Room left in every rendered comment for the self-authorship stamp
# (``authz.mark_self_authored``) a the-loop-posted record carries.
_STAMP_RESERVE = 256
# A chunk of a split file is at least this long unless the file ends sooner.
_MIN_CHUNK = 1024

# The closed set of artifact names, in chain order. requirements.md and
# bugfix.md are the same rung and mutually exclusive.
CHAIN: Tuple[str, ...] = (
    "brainstorm.md",
    "requirements.md",
    "bugfix.md",
    "design.md",
    "testing-plan.md",
)
_RANK: Dict[str, int] = {
    "brainstorm.md": 0,
    "requirements.md": 1,
    "bugfix.md": 1,
    "design.md": 2,
    "testing-plan.md": 3,
}

STAGES: Tuple[str, ...] = (
    "exploring",
    "brainstorm-settled",
    "requirements-settled",
    "design-settled",
)
ALLOWED_ENTRY = frozenset(
    {
        "brainstorming",
        "brainstorm-approval",
        "requirements-approval",
        "test-planning",
        "design-approval",
    }
)
CARRIERS: Tuple[str, ...] = ("branch", "ticket", "artifact")
BRANCH_PREFIX = "the-loop/"

# Wire keys, in render order.
_KEYS: Tuple[str, ...] = (
    "stage",
    "enter",
    "artifacts",
    "carried-by",
    "spec-artifact",
    "from",
    "approved-in-chat",
    "mirror",
    "confirmation",
    "parts",
)
_REQUIRED = ("stage", "enter", "artifacts", "carried-by")
_KEY_WIDTH = 18  # len("approved-in-chat: ")
_INDENT = " " * _KEY_WIDTH

_ANY_MARKER_RE = re.compile(r"<!-- the-loop:handoff v(\d+) -->")
_PART_RE = re.compile(r"<!-- the-loop:handoff-part v(\d+) (\d+)/(\d+) -->")
_KEY_RE = re.compile(r"([a-z][a-z-]*):(?:[ \t]+(.*))?")
_FENCE_RE = re.compile(r"(`{3,})[A-Za-z0-9_-]*")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_BRANCH_RE = re.compile(r"branch (\S+)(?: · PR #([1-9][0-9]*))?")
_SPEC_ARTIFACT_RE = re.compile(r"(https://\S+) sha256:(\S*)")
_MIRROR_RE = re.compile(r"jira:[A-Za-z0-9][A-Za-z0-9.-]*/[A-Z][A-Z0-9_]*-[0-9]+")
_BLOCK_RE = re.compile(
    r"<details><summary>(?P<name>[^<\n]*)</summary>\n\n"
    r"(?P<fence>`{4,})[^\n`]*\n(?P<body>.*?)\n(?P=fence)\n\n</details>",
    re.S,
)
_BACKTICKS_RE = re.compile(r"`+")


def _without_files(body: str) -> str:
    """``body`` with its carried-file blocks removed, so a marker line inside a
    carried file (a brainstorm about this very feature) is never mistaken for
    the record's own marker."""
    return _BLOCK_RE.sub("", _lf(body))


@dataclass(frozen=True)
class HandoffArtifact:
    """One carried file: a :data:`CHAIN` name and the sha256 of its LF bytes."""

    name: str
    sha256: str


@dataclass(frozen=True)
class HandoffRecord:
    """A parsed v1 handoff record. ``author`` and ``comment_url`` are filled by
    :func:`find_record` from the comment's API metadata, never from the text."""

    version: int
    stage: str
    enter: str
    artifacts: Tuple[HandoffArtifact, ...]
    carried_by: str
    branch: str = ""
    pull_request: int = 0
    spec_artifact: str = ""
    spec_artifact_sha256: str = ""
    source: str = ""
    approved_in_chat: Tuple[str, ...] = ()
    mirror: str = ""
    confirmation: str = ""
    parts: int = 0
    author: str = ""
    comment_url: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """The camelCase shape ``work-item-state.json`` stores under ``handoff``."""
        return {
            "version": self.version,
            "stage": self.stage,
            "enter": self.enter,
            "artifacts": [{"name": a.name, "sha256": a.sha256} for a in self.artifacts],
            "carriedBy": self.carried_by,
            "branch": self.branch,
            "pullRequest": self.pull_request,
            "specArtifact": self.spec_artifact,
            "specArtifactSha256": self.spec_artifact_sha256,
            "source": self.source,
            "approvedInChat": list(self.approved_in_chat),
            "mirror": self.mirror,
            "confirmation": self.confirmation,
            "parts": self.parts,
            "author": self.author,
            "commentUrl": self.comment_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HandoffRecord":
        """Inverse of :meth:`as_dict`. Keys the runtime adds beside the record
        (``recordedAt``) are ignored. The input is the-loop's own state, already
        validated when it was first read — this does not re-validate."""
        return cls(
            version=int(data.get("version", 1)),
            stage=str(data.get("stage", "")),
            enter=str(data.get("enter", "")),
            artifacts=tuple(
                HandoffArtifact(str(a["name"]), str(a["sha256"]))
                for a in data.get("artifacts") or ()
            ),
            carried_by=str(data.get("carriedBy", "")),
            branch=str(data.get("branch", "")),
            pull_request=int(data.get("pullRequest") or 0),
            spec_artifact=str(data.get("specArtifact", "")),
            spec_artifact_sha256=str(data.get("specArtifactSha256", "")),
            source=str(data.get("source", "")),
            approved_in_chat=tuple(str(n) for n in data.get("approvedInChat") or ()),
            mirror=str(data.get("mirror", "")),
            confirmation=str(data.get("confirmation", "")),
            parts=int(data.get("parts") or 0),
            author=str(data.get("author", "")),
            comment_url=str(data.get("commentUrl", "")),
        )


class CommentLike(Protocol):
    """What the reader needs of a comment — :class:`the_loop.poller.base.Comment`
    satisfies it."""

    @property
    def body(self) -> str: ...

    @property
    def author(self) -> str: ...

    @property
    def url(self) -> str: ...

    @property
    def created_at(self) -> str: ...


# -- helpers -----------------------------------------------------------------


def sha256_text(text: str) -> str:
    """Hex sha256 of ``text`` as UTF-8 bytes with LF line endings (CRLF and a
    lone CR count as LF)."""
    return hashlib.sha256(_lf(text).encode("utf-8")).hexdigest()


def _lf(text: str) -> str:
    """``text`` with CRLF and lone CR line endings made LF (a lone CR would
    otherwise fuse with the LF a rendered block adds after it)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def stage_entry(stage: str, artifact_names: Iterable[str]) -> str:
    """The node a ``stage`` enters, given the carried artifact names (R6 table).

    *design-settled* enters ``design-approval`` when ``testing-plan.md`` is
    carried, else ``test-planning``. Raises :class:`ValueError` on an unknown
    stage.
    """
    if stage == "exploring":
        return "brainstorming"
    if stage == "brainstorm-settled":
        return "brainstorm-approval"
    if stage == "requirements-settled":
        return "requirements-approval"
    if stage == "design-settled":
        if "testing-plan.md" in set(artifact_names):
            return "design-approval"
        return "test-planning"
    raise ValueError(f"unknown handoff stage {stage!r}")


def _check_ref_format(name: str) -> bool:
    """``git check-ref-format``'s rules for a full ref name, in pure Python."""
    if not name or name == "@":
        return False
    for ch in name:
        if ord(ch) < 0x20 or ord(ch) == 0x7F or ch in " ~^:?*[\\":
            return False
    if ".." in name or "@{" in name or "//" in name:
        return False
    if name.startswith("/") or name.endswith("/") or name.endswith("."):
        return False
    for component in name.split("/"):
        if not component or component.startswith(".") or component.endswith(".lock"):
            return False
    return True


def is_valid_branch(name: str) -> bool:
    """Whether ``name`` is a branch a handoff may name: under ``the-loop/`` and
    valid per ``git check-ref-format``."""
    return (
        name.startswith(BRANCH_PREFIX)
        and len(name) > len(BRANCH_PREFIX)
        and _check_ref_format(name)
    )


def _stage_fits(stage: str, names: Sequence[str]) -> bool:
    """Whether the carried artifacts are the ones ``stage`` carries (R6 table)."""
    have = set(names)
    spec = bool(have & {"requirements.md", "bugfix.md"})
    later = bool(have & {"design.md", "testing-plan.md"})
    if stage == "exploring":
        return have <= {"brainstorm.md"}
    if stage == "brainstorm-settled":
        return have == {"brainstorm.md"}
    if stage == "requirements-settled":
        return spec and not later
    if stage == "design-settled":
        return spec and "design.md" in have
    return False


def _furthest(names: Sequence[str]) -> str:
    return max(names, key=lambda n: _RANK[n]) if names else ""


# -- parse -------------------------------------------------------------------


def _marker_lines(lines: Sequence[str]) -> List[Tuple[int, int]]:
    """``(line index, version)`` of every record-marker line (at column 0)."""
    found: List[Tuple[int, int]] = []
    for i, line in enumerate(lines):
        match = _ANY_MARKER_RE.fullmatch(line.rstrip())
        if match:
            found.append((i, int(match.group(1))))
    return found


def _record_block(lines: Sequence[str], start: int) -> Tuple[Optional[List[str]], int]:
    """The key–value lines after the marker at ``start``, and the index of the
    first line after the block. ``None`` when a fenced block never closes."""
    i = start + 1
    fence_match = _FENCE_RE.fullmatch(lines[i].rstrip()) if i < len(lines) else None
    if fence_match:
        fence = fence_match.group(1)
        block: List[str] = []
        for j in range(i + 1, len(lines)):
            if lines[j].rstrip() == fence:
                return block, j + 1
            block.append(lines[j])
        return None, len(lines)
    block = []
    while i < len(lines) and lines[i].strip():
        block.append(lines[i])
        i += 1
    return block, i


def parse_with_reason(body: str) -> Tuple[Optional[HandoffRecord], str]:
    """Parse a v1 record out of a comment body, or say why it is not one.

    Returns ``(record, "")`` or ``(None, reason)``. ``author`` and
    ``comment_url`` are left empty: only :func:`find_record` fills them.
    """
    lines = _without_files(body or "").split("\n")
    markers = _marker_lines(lines)
    if not markers:
        return None, "no handoff marker"
    if len(markers) > 1:
        return None, "more than one handoff marker in one comment"
    start, version = markers[0]
    if version != 1:
        return None, f"unknown handoff record version v{version}"
    block, _ = _record_block(lines, start)
    if block is None:
        return None, "unterminated record block"

    values: Dict[str, str] = {}
    last_key = ""
    for line in block:
        if not line.strip() or line[:1] in (" ", "\t"):
            if last_key != "confirmation":
                return (
                    None,
                    f"unexpected continuation line under {last_key or 'marker'!r}",
                )
            text = line[len(_INDENT) :] if line.startswith(_INDENT) else line.lstrip()
            values["confirmation"] += "\n" + text.rstrip()
            continue
        match = _KEY_RE.fullmatch(line.rstrip())
        if not match:
            return None, f"malformed line {line[:60]!r}"
        key, value = match.group(1), (match.group(2) or "").strip()
        if key not in _KEYS:
            return None, f"unknown key {key!r}"
        if key in values:
            return None, f"duplicate key {key!r}"
        values[key] = value
        last_key = key
    for key in _REQUIRED:
        if key not in values:
            return None, f"missing required key {key!r}"

    stage = values["stage"]
    if stage not in STAGES:
        return None, f"unknown stage {stage!r}"

    artifacts: List[HandoffArtifact] = []
    if values["artifacts"]:
        for item in values["artifacts"].split(","):
            tokens = item.split()
            if not tokens:
                return None, "empty artifact entry"
            name = tokens[0]
            if name not in _RANK:
                return None, f"artifact name {name!r} is outside the closed set"
            if (
                len(tokens) != 2
                or not tokens[1].startswith("sha256:")
                or not _SHA_RE.fullmatch(tokens[1][len("sha256:") :])
            ):
                return None, f"artifact {name!r}: missing or malformed sha256"
            artifacts.append(HandoffArtifact(name, tokens[1][len("sha256:") :]))
    names = [a.name for a in artifacts]
    if len(set(names)) != len(names):
        return None, "an artifact is listed twice"
    if "requirements.md" in names and "bugfix.md" in names:
        return None, "requirements.md and bugfix.md are mutually exclusive"
    if not _stage_fits(stage, names):
        return None, f"stage {stage!r} does not fit the artifacts {names}"

    enter = values["enter"]
    if enter not in ALLOWED_ENTRY:
        return None, f"enter {enter!r} is not an allowed starting step"
    expected = stage_entry(stage, names)
    if enter != expected:
        return (
            None,
            f"enter {enter!r} does not match stage {stage!r} (expected {expected!r})",
        )

    carried = values["carried-by"]
    branch, pull_request = "", 0
    if carried in ("ticket", "artifact"):
        carried_by = carried
    else:
        match = _BRANCH_RE.fullmatch(carried)
        if not match:
            return None, f"malformed carried-by {carried[:60]!r}"
        carried_by, branch = "branch", match.group(1)
        pull_request = int(match.group(2) or 0)
        if not is_valid_branch(branch):
            return None, f"branch {branch!r} is not a valid the-loop/ branch"

    spec_artifact, spec_sha = "", ""
    if "spec-artifact" in values:
        match = _SPEC_ARTIFACT_RE.fullmatch(values["spec-artifact"])
        if not match or not _SHA_RE.fullmatch(match.group(2)):
            return None, "spec-artifact must be '<https URL> sha256:<hex>'"
        spec_artifact, spec_sha = match.group(1), match.group(2)
    if carried_by == "artifact" and not spec_artifact:
        return None, "carried-by artifact names no spec-artifact"

    approved: List[str] = []
    if values.get("approved-in-chat"):
        approved = [n.strip() for n in values["approved-in-chat"].split(",")]
        for name in approved:
            if name not in names:
                return None, f"approved-in-chat names {name!r}, which is not carried"
        if len(set(approved)) != len(approved):
            return None, "approved-in-chat lists an artifact twice"
        furthest = _furthest(names)
        if furthest in approved:
            return None, (
                f"approved-in-chat names the furthest artifact {furthest!r}; "
                "only its gate approves it"
            )

    mirror = values.get("mirror", "")
    if mirror and not _MIRROR_RE.fullmatch(mirror):
        return None, f"malformed mirror {mirror[:60]!r}"

    parts = 0
    if "parts" in values:
        if not re.fullmatch(r"[0-9]{1,4}", values["parts"]):
            return None, f"malformed parts {values['parts'][:20]!r}"
        parts = int(values["parts"])
        if parts and carried_by != "ticket":
            return None, "parts are only carried with carried-by ticket"

    record = HandoffRecord(
        version=1,
        stage=stage,
        enter=enter,
        artifacts=tuple(artifacts),
        carried_by=carried_by,
        branch=branch,
        pull_request=pull_request,
        spec_artifact=spec_artifact,
        spec_artifact_sha256=spec_sha,
        source=values.get("from", ""),
        approved_in_chat=tuple(approved),
        mirror=mirror,
        confirmation=values.get("confirmation", ""),
        parts=parts,
    )
    return record, ""


def parse(body: str) -> Optional[HandoffRecord]:
    """The v1 record in ``body``, or ``None`` (see :func:`parse_with_reason`)."""
    return parse_with_reason(body)[0]


# -- render ------------------------------------------------------------------


def _fence(text: str, minimum: int) -> str:
    longest = max((len(m) for m in _BACKTICKS_RE.findall(text)), default=0)
    return "`" * max(minimum, longest + 1)


def _line(key: str, value: str) -> str:
    return f"{key + ':':<{_KEY_WIDTH}}{value}".rstrip()


def _render_head(record: HandoffRecord) -> str:
    """The record comment's marker and key–value block (no files)."""
    lines: List[str] = [
        _line("stage", record.stage),
        _line("enter", record.enter),
        _line(
            "artifacts",
            ", ".join(f"{a.name} sha256:{a.sha256}" for a in record.artifacts),
        ),
    ]
    if record.carried_by == "branch":
        carried = f"branch {record.branch}"
        if record.pull_request:
            carried += f" · PR #{record.pull_request}"
    else:
        carried = record.carried_by
    lines.append(_line("carried-by", carried))
    if record.spec_artifact:
        lines.append(
            _line(
                "spec-artifact",
                f"{record.spec_artifact} sha256:{record.spec_artifact_sha256}",
            )
        )
    if record.source:
        lines.append(_line("from", record.source))
    if record.approved_in_chat:
        lines.append(_line("approved-in-chat", ", ".join(record.approved_in_chat)))
    if record.mirror:
        lines.append(_line("mirror", record.mirror))
    if record.confirmation:
        first, *rest = _lf(record.confirmation).split("\n")
        lines.append(_line("confirmation", first))
        lines.extend((_INDENT + r).rstrip() for r in rest)
    if record.parts:
        lines.append(_line("parts", str(record.parts)))
    block = "\n".join(lines)
    fence = _fence(block, 3)
    return f"{MARKER}\n{fence}text\n{block}\n{fence}"


def _block(name: str, fence: str, chunk: str) -> str:
    return f"<details><summary>{name}</summary>\n\n{fence}markdown\n{chunk}\n{fence}\n\n</details>"


def _pack(head: str, files: Sequence[Tuple[str, str]], total: int) -> List[str]:
    """Lay ``files`` out after ``head``, starting a part comment whenever the
    next block does not fit; ``total`` is the part count the markers state."""
    budget = COMMENT_LIMIT - _STAMP_RESERVE
    if len(head) > budget:
        raise ValueError("handoff record header alone exceeds the comment limit")
    comments: List[str] = []
    current = head
    for name, text in files:
        fence = _fence(text, 4)
        overhead = len(_block(name, fence, "")) + 2
        pos, first = 0, True
        while first or pos < len(text):
            first = False
            remaining = len(text) - pos
            avail = budget - len(current) - overhead
            if avail < min(remaining, _MIN_CHUNK):
                comments.append(current)
                current = PART_MARKER.format(n=len(comments), N=total)
                avail = budget - len(current) - overhead
                if avail < min(remaining, _MIN_CHUNK):
                    raise ValueError(f"cannot fit {name!r} in a part comment")
            chunk = text[pos : pos + avail]
            current += "\n\n" + _block(name, fence, chunk)
            pos += len(chunk)
    comments.append(current)
    return comments


def render(
    record: HandoffRecord, files: Optional[Mapping[str, str]] = None
) -> List[str]:
    """The record comment, then any part comments, each ≤ :data:`COMMENT_LIMIT`.

    ``files`` (``carried-by: ticket`` only) are the carried bodies by artifact
    name; they are laid out in the record's artifact order, line endings
    normalized to LF, and split across parts — never truncated. The rendered
    record's ``parts`` is the computed count, whatever ``record.parts`` said.
    Raises :class:`ValueError` on a record the parser would refuse, or files the
    record does not carry.
    """
    if record.version != 1:
        raise ValueError(f"cannot render handoff record version {record.version}")
    ordered: List[Tuple[str, str]] = []
    if files:
        if record.carried_by != "ticket":
            raise ValueError("only a carried-by ticket record carries files")
        names = [a.name for a in record.artifacts]
        unknown = sorted(set(files) - set(names))
        if unknown:
            raise ValueError(f"files not listed in the record: {unknown}")
        ordered = [(n, _lf(files[n])) for n in names if n in files]

    total = 0
    for _ in range(8):
        head = _render_head(replace(record, parts=total))
        comments = _pack(head, ordered, total)
        if len(comments) - 1 == total:
            break
        total = len(comments) - 1
    else:  # pragma: no cover - the part count settles in two or three passes
        raise RuntimeError("handoff part count did not settle")

    parsed, reason = parse_with_reason(comments[0])
    if parsed is None:
        raise ValueError(f"record would not parse back: {reason}")
    return comments


# -- files -------------------------------------------------------------------


def _payload(text: str) -> Optional[str]:
    """The part of a record or part comment that may hold file blocks: what
    follows the record block or the part marker. ``None`` for anything else."""
    lines = text.split("\n")
    markers = _marker_lines(lines)
    if len(_marker_lines(_without_files(text).split("\n"))) == 1 and markers:
        # The record block precedes every file block, so the first marker is
        # the record's own; any later one is quoted inside a carried file.
        block, after = _record_block(lines, markers[0][0])
        return None if block is None else "\n".join(lines[after:])
    for i, line in enumerate(lines):
        if _PART_RE.fullmatch(line.rstrip()):
            return "\n".join(lines[i + 1 :])
    return None


def extract_files(bodies: Iterable[str]) -> Dict[str, str]:
    """The carried files in ``bodies`` (the record, then its parts, in order).

    Consecutive chunks of one file are rejoined; names outside :data:`CHAIN` are
    ignored. The caller checks each result against the record's ``sha256``.
    """
    files: Dict[str, str] = {}
    for body in bodies:
        payload = _payload(_lf(body or ""))
        if payload is None:
            continue
        for match in _BLOCK_RE.finditer(payload):
            name = match.group("name")
            if name in _RANK:
                files[name] = files.get(name, "") + match.group("body")
    return files


# -- read --------------------------------------------------------------------


def _chronological(comments: Iterable[CommentLike]) -> List[CommentLike]:
    indexed = list(enumerate(comments))
    indexed.sort(key=lambda pair: (pair[1].created_at or "", pair[0]))
    return [c for _, c in indexed]


def _same_login(a: str, b: str) -> bool:
    return bool(a) and a.casefold() == b.casefold()


def contained(path: Path, start: Path) -> bool:
    """Whether ``path`` is reached from its repository root without passing
    through a symlink.

    The root is the nearest ancestor of ``start`` holding ``.git`` (``start``
    itself when there is none). A symlinked ``docs``, ``docs/specs``, spec
    folder or file makes the resolved path differ from the literal one below
    the root, which is how a write would leave the checkout (self-review
    round 2). Symlinks *above* the root, such as a linked home directory, are
    the operator's own and are allowed.
    """
    absolute = Path(os.path.abspath(path))
    root = Path(os.path.abspath(start))
    for candidate in (root, *root.parents):
        if (candidate / ".git").exists():
            root = candidate
            break
    try:
        literal = absolute.relative_to(root)
        resolved = absolute.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return literal == resolved


def find_record(
    comments: Iterable[CommentLike],
    is_authorized: Callable[[str], bool],
) -> Tuple[Optional[HandoffRecord], List[str]]:
    """The newest well-formed v1 record whose author is authorized.

    ``is_authorized`` takes a login (``routing.authorizedUsers``). It is the
    only admission rule: the-loop's own records count because on GitHub
    the-loop posts as the operator, an authorized login. The self-marker is
    never evidence on its own, since anyone can paste it, and a comment with
    no author (a deleted account comes back as ``""``) is refused before
    ``is_authorized`` sees it, because that check admits a missing actor.
    The returned record's ``author`` and ``comment_url`` come from the
    comment's metadata. The second value names each newer record that was
    rejected and why, for the ``handoff.ignored`` event.
    """
    reasons: List[str] = []
    for comment in reversed(_chronological(comments)):
        body = comment.body or ""
        if not _marker_lines(_without_files(body).split("\n")):
            continue
        where = comment.url or "comment"
        author = str(comment.author or "").strip()
        if not author:
            reasons.append(f"{where}: the comment has no author")
            continue
        if not is_authorized(author):
            reasons.append(f"{where}: author {author!r} is not authorized")
            continue
        record, reason = parse_with_reason(body)
        if record is None:
            reasons.append(f"{where}: {reason}")
            continue
        return replace(record, author=author, comment_url=comment.url), reasons
    return None, reasons


def collect_parts(
    comments: Iterable[CommentLike], record: HandoffRecord
) -> Optional[List[str]]:
    """The record's body followed by its part bodies 1..N, for
    :func:`extract_files`; ``None`` when the record comment or any part is
    missing.

    A part counts only when the record's author wrote it, after the record, and
    it states the record's part count; the first such part for each number wins.
    """
    ordered = _chronological(comments)
    index = next(
        (
            i
            for i, c in enumerate(ordered)
            if c.url == record.comment_url and _same_login(c.author, record.author)
        ),
        None,
    )
    if index is None:
        return None
    bodies = [ordered[index].body]
    if not record.parts:
        return bodies
    found: Dict[int, str] = {}
    for comment in ordered[index + 1 :]:
        if not _same_login(comment.author, record.author):
            continue
        for line in _lf(comment.body or "").split("\n"):
            match = _PART_RE.fullmatch(line.rstrip())
            if match:
                version, n, total = (int(g) for g in match.groups())
                if version == 1 and total == record.parts and 1 <= n <= total:
                    found.setdefault(n, comment.body)
                break
    if len(found) != record.parts:
        return None
    return bodies + [found[n] for n in range(1, record.parts + 1)]
