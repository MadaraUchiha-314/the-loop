"""PR-scoped specs for a multi-PR work item (issue-543, decision-153).

A work item delivered by several pull requests keeps **one** spec chain in its
origin repository. Each delivery PR also carries a small, derived **PR spec** —
four files under ``docs/specs/<key>/pr-<n>/`` in the PR's own branch — so a
maintainer can review that PR from its own diff.

This module holds the pure building blocks both halves of the feature share:

* the **chain digest** that tells a recorded PR spec it has fallen behind;
* the **key and path** a PR spec is written under, validated like
  ``pr-loops/`` (the filesystem trust boundary of issue-183);
* the **citation grammar** (``[wi:R2.3]`` …) and the check that every item
  which must cite does;
* **applicability**: whether a work item is multi-PR at all;
* the **record** (``pr-spec.json``) the online verb writes and the offline
  ``pr-spec-current`` hook re-reads;
* the **secret scan** the verb runs over the four files before recording.

Nothing here touches the network or writes a file. The verb
(``the-loop graph pr-spec``) adds the PR checkout and GitHub; the hook adds the
graph.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .frontmatter import split_front_matter

__all__ = [
    "CHAIN_PARTS",
    "PR_SPEC_FILES",
    "PR_SPEC_RECORD",
    "ChainIndex",
    "Finding",
    "PrSpecRecord",
    "applicability",
    "chain_digest",
    "chain_parts",
    "changed_files",
    "citation_tokens",
    "digest_of_parts",
    "missing_citations",
    "pr_spec_dir",
    "pr_spec_key",
    "scan_secrets",
    "unresolved_citations",
]

#: The work-item chain a PR spec derives from, in digest order. Each entry is
#: ``(part name, candidate file names)``: requirements has two accepted names.
CHAIN_PARTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("requirements", ("requirements.md", "bugfix.md")),
    ("design", ("design.md",)),
    ("testing-plan", ("testing-plan.md",)),
    ("tasks", ("tasks.md",)),
)

#: The four files of a PR spec, and the ``type`` each one's front matter names.
PR_SPEC_FILES: Tuple[Tuple[str, str], ...] = (
    ("requirements.md", "pr-requirements"),
    ("design.md", "pr-design"),
    ("testing-plan.md", "pr-testing-plan"),
    ("tasks.md", "pr-tasks"),
)

#: The record's file name, in the PR's inner-loop directory.
PR_SPEC_RECORD = "pr-spec.json"

_ABSENT = "absent"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


# -- the chain digest ---------------------------------------------------------


def _body_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    _, body = split_front_matter(text)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def chain_parts(spec_dir: Path) -> Dict[str, str]:
    """``{part: sha256 of its body}`` for each chain file, front matter stripped.

    Front matter is stripped because the approval gates rewrite it: a lock
    alone must not mark every PR spec stale. A missing file hashes as
    ``absent``, so a ``tasks.md`` that appears later changes the digest.
    """
    parts: Dict[str, str] = {}
    for part, names in CHAIN_PARTS:
        parts[part] = _ABSENT
        for name in names:
            path = spec_dir / name
            if path.is_file():
                parts[part] = _body_hash(path)
                break
    return parts


def digest_of_parts(parts: Mapping[str, str]) -> str:
    joined = "".join(f"{part}:{parts.get(part, _ABSENT)}\n" for part, _ in CHAIN_PARTS)
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def chain_digest(spec_dir: Path) -> str:
    """The work-item chain's digest — what the gate compares (R5.1)."""
    return digest_of_parts(chain_parts(spec_dir))


def changed_files(old: Mapping[str, str], new: Mapping[str, str]) -> List[str]:
    """Chain file names whose body differs between two :func:`chain_parts`."""
    return [f"{part}.md" for part, _ in CHAIN_PARTS if old.get(part) != new.get(part)]


# -- where a PR spec lives ----------------------------------------------------

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _same_repo(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def pr_spec_key(origin: str, pr_repo: str, item_id: str) -> str:
    """The ``<key>`` of ``docs/specs/<key>/pr-<n>/`` (design § Persisted formats).

    ``<id>`` for a PR in the origin repository, ``<owner>__<repo>__<id>`` of the
    **origin** for any other. Every part is validated, never sanitized (AC4):
    the value becomes a directory in someone else's repository.
    """
    from .hooks.loops import repo_state_key

    origin_key = repo_state_key(origin)
    if not _ID_RE.fullmatch(item_id or "") or ".." in item_id:
        raise ValueError(f"unusable work-item id {item_id!r}")
    if not pr_repo or _same_repo(pr_repo, origin):
        return item_id
    repo_state_key(pr_repo)
    return f"{origin_key}__{item_id}"


def pr_spec_dir(key: str, number: int) -> str:
    """``docs/specs/<key>/pr-<n>`` — relative to the PR checkout's root."""
    if int(number) <= 0:
        raise ValueError(f"unusable pull-request number {number!r}")
    if not _ID_RE.fullmatch(key or "") or ".." in key:
        raise ValueError(f"unusable PR-spec key {key!r}")
    return f"docs/specs/{key}/pr-{int(number)}"


# -- citations ---------------------------------------------------------------

_TOKEN_RE = re.compile(r"\[wi:([^\]\s]+)\]")
_REQ_HEAD_RE = re.compile(r"^###\s+Requirement\s+(\d+)\b")
_EARS_ITEM_RE = re.compile(r"^(\d+)\.\s")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MATRIX_ROW_RE = re.compile(r"^\|\s*(T\d+)\s*\|")
_TASK_RE = re.compile(r"^\s*- \[[ xX]\] (\d+)\.")


@dataclass(frozen=True)
class Finding:
    """One problem with a PR spec, addressed by file and line."""

    file: str
    line: int
    text: str

    def render(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{where}: {self.text}"


def _lines(text: str) -> Iterator[Tuple[int, str, bool]]:
    """``(1-based line number, line, inside a fence)`` for every line."""
    fenced = False
    for number, line in enumerate(text.split("\n"), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            yield number, line, True
            continue
        yield number, line, fenced


def _unfenced(text: str) -> Iterator[Tuple[int, str]]:
    for number, line, fenced in _lines(text):
        if not fenced:
            yield number, line


def citation_tokens(text: str) -> List[str]:
    """Every ``[wi:…]`` target outside fenced blocks, in order."""
    return [m.group(1) for _, line in _unfenced(text) for m in _TOKEN_RE.finditer(line)]


def _slug(title: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces → ``-``."""
    title = re.sub(r"`", "", title.strip().lower())
    title = re.sub(r"[^\w\- ]", "", title)
    return title.replace(" ", "-")


@dataclass
class ChainIndex:
    """What a citation may point at in the work-item chain."""

    requirements: Dict[int, int] = field(default_factory=dict)  # R<n> → EARS items
    design_slugs: frozenset = frozenset()
    matrix_rows: frozenset = frozenset()
    tasks: frozenset = frozenset()

    @classmethod
    def load(cls, spec_dir: Path) -> "ChainIndex":
        def read(*names: str) -> str:
            for name in names:
                path = spec_dir / name
                if path.is_file():
                    return split_front_matter(path.read_text(encoding="utf-8"))[1]
            return ""

        requirements: Dict[int, int] = {}
        current: Optional[int] = None
        for _, line in _unfenced(read("requirements.md", "bugfix.md")):
            head = _REQ_HEAD_RE.match(line)
            if head:
                current = int(head.group(1))
                requirements.setdefault(current, 0)
                continue
            if line.startswith("## ") or (line.startswith("### ") and not head):
                current = None
                continue
            item = _EARS_ITEM_RE.match(line)
            if current is not None and item:
                requirements[current] = max(requirements[current], int(item.group(1)))
        slugs = frozenset(
            _slug(m.group(2))
            for _, line in _unfenced(read("design.md"))
            for m in [_HEADING_RE.match(line)]
            if m
        )
        rows = frozenset(
            m.group(1)
            for _, line in _unfenced(read("testing-plan.md"))
            for m in [_MATRIX_ROW_RE.match(line)]
            if m
        )
        tasks = frozenset(
            int(m.group(1))
            for _, line in _unfenced(read("tasks.md"))
            for m in [_TASK_RE.match(line)]
            if m
        )
        return cls(requirements, slugs, rows, tasks)

    def resolves(self, token: str) -> bool:
        m = re.fullmatch(r"R(\d+)(?:\.(\d+))?", token)
        if m:
            req = int(m.group(1))
            if req not in self.requirements:
                return False
            return m.group(2) is None or 1 <= int(m.group(2)) <= self.requirements[req]
        if token.startswith("design#"):
            return token[len("design#") :] in self.design_slugs
        m = re.fullmatch(r"TP-(T\d+)", token)
        if m:
            return m.group(1) in self.matrix_rows
        m = re.fullmatch(r"task-(\d+)", token)
        if m:
            return int(m.group(1)) in self.tasks
        return False


def unresolved_citations(files: Mapping[str, str], index: ChainIndex) -> List[Finding]:
    """Every ``[wi:…]`` token that does not resolve against the chain (R3.2)."""
    found: List[Finding] = []
    for name, text in files.items():
        for number, line in _unfenced(text):
            for m in _TOKEN_RE.finditer(line):
                if not index.resolves(m.group(1)):
                    found.append(
                        Finding(
                            name,
                            number,
                            f"citation [wi:{m.group(1)}] does not "
                            "resolve against the work-item chain",
                        )
                    )
    return found


def _span_has_token(lines: Sequence[str]) -> bool:
    return any(_TOKEN_RE.search(line) for line in lines)


def _requirement_entries(text: str) -> List[Tuple[int, List[str]]]:
    """``###`` entries — under ``## Requirements`` when the file has one."""
    rows = list(_unfenced(text))
    scoped = any(line.strip() == "## Requirements" for _, line in rows)
    in_section = not scoped
    entries: List[Tuple[int, List[str]]] = []
    current: Optional[Tuple[int, List[str]]] = None
    for number, line in rows:
        head = _HEADING_RE.match(line)
        level = len(head.group(1)) if head else 0
        if head and level <= 2 and scoped:
            in_section = line.strip() == "## Requirements"
        if head and level <= 3:
            if current:
                entries.append(current)
            current = (number, [line]) if (level == 3 and in_section) else None
            continue
        if current:
            current[1].append(line)
    if current:
        entries.append(current)
    return entries


def _task_entries(text: str) -> List[Tuple[int, List[str]]]:
    entries: List[Tuple[int, List[str]]] = []
    current: Optional[Tuple[int, List[str]]] = None
    for number, line in _unfenced(text):
        if _TASK_RE.match(line) or _HEADING_RE.match(line):
            if current:
                entries.append(current)
            current = (number, [line]) if _TASK_RE.match(line) else None
            continue
        if current:
            current[1].append(line)
    if current:
        entries.append(current)
    return entries


def _in_scope_rows(text: str) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    for number, line in _unfenced(text):
        if not _MATRIX_ROW_RE.match(line):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if len(cells) > 2 and cells[2] not in ("n/a", "no", "na", ""):
            rows.append((number, line))
    return rows


def missing_citations(files: Mapping[str, str]) -> List[Finding]:
    """Items that must cite and do not (R3.1): every ``###`` requirement entry,
    every task line, every in-scope Test matrix row."""
    found: List[Finding] = []
    for number, lines in _requirement_entries(files.get("requirements.md", "")):
        if not _span_has_token(lines):
            found.append(
                Finding(
                    "requirements.md",
                    number,
                    "requirement entry cites no work-item item",
                )
            )
    for number, lines in _task_entries(files.get("tasks.md", "")):
        if not _span_has_token(lines):
            found.append(Finding("tasks.md", number, "task cites no work-item item"))
    for number, line in _in_scope_rows(files.get("testing-plan.md", "")):
        if not _TOKEN_RE.search(line):
            found.append(
                Finding(
                    "testing-plan.md",
                    number,
                    "in-scope test matrix row cites no work-item item",
                )
            )
    return found


# -- applicability -----------------------------------------------------------


def _get(row: Any, key: str, attr: str = "") -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, attr or key, None)


def applicability(
    pull_requests: Iterable[Any], declared_repos: Iterable[str], origin: str
) -> str:
    """``multi-pr`` or ``single-pr`` (design § Architecture, R1.1–R1.3).

    Multi-PR when two or more delivering, not-closed pull requests are recorded,
    or when any of them — or any declared repository — lies outside the origin.
    A row whose repository is unknown, or an origin that is unknown, counts as
    outside: an unknown never relaxes the requirement.
    """
    delivering = [
        row
        for row in pull_requests
        if not (_get(row, "self", "is_self"))
        and (_get(row, "state") or "open") != "closed"
    ]
    if len(delivering) >= 2:
        return "multi-pr"
    repos = [str(_get(row, "repository") or "") for row in delivering]
    repos += [str(r) for r in declared_repos]
    if any(not origin or not repo or not _same_repo(repo, origin) for repo in repos):
        return "multi-pr"
    return "single-pr"


# -- the record --------------------------------------------------------------

_NOT_REQUIRED_REASONS = frozenset({"single-pr", "spec-only"})


@dataclass
class PrSpecRecord:
    """``pr-spec.json``: what ``the-loop graph pr-spec`` verified, once."""

    pull_request: str
    required: bool
    reason: str
    chain_digest: str
    path: str = ""
    head_sha: str = ""
    source_revision: str = ""
    citations: int = 0
    disclosure: Optional[Dict[str, Any]] = None
    still_valid: Optional[Dict[str, Any]] = None
    recorded_at: str = ""
    chain_parts: Optional[Dict[str, str]] = None
    version: int = 1

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "version": self.version,
            "pullRequest": self.pull_request,
            "required": self.required,
            "reason": self.reason,
            "path": self.path,
            "headSha": self.head_sha,
            "sourceRevision": self.source_revision,
            "chainDigest": self.chain_digest,
            "citations": self.citations,
            "disclosure": self.disclosure,
            "stillValid": self.still_valid,
            "recordedAt": self.recorded_at,
        }
        if self.chain_parts is not None:
            data["chainParts"] = dict(self.chain_parts)
        return data

    @classmethod
    def from_dict(cls, data: Any, expected_pr: str = "") -> "PrSpecRecord":
        """Validate every field (the record is agent-writable); raise on any doubt."""
        if not isinstance(data, Mapping):
            raise ValueError("the record is not a JSON object")
        if data.get("version") != 1:
            raise ValueError(f"unknown record version {data.get('version')!r}")
        pull_request = str(data.get("pullRequest") or "")
        if expected_pr and pull_request != expected_pr:
            raise ValueError(
                f"the record names {pull_request!r}, not this pull request {expected_pr!r}"
            )
        required = data.get("required")
        if not isinstance(required, bool):
            raise ValueError("`required` is not a boolean")
        reason = str(data.get("reason") or "")
        if required and reason != "multi-pr":
            raise ValueError(f"a required record cannot have reason {reason!r}")
        if not required and reason not in _NOT_REQUIRED_REASONS:
            raise ValueError(f"a not-required record cannot have reason {reason!r}")
        digest = str(data.get("chainDigest") or "")
        if not _DIGEST_RE.fullmatch(digest):
            raise ValueError("`chainDigest` is not sha256:<64 hex>")
        citations = data.get("citations", 0)
        if (
            not isinstance(citations, int)
            or isinstance(citations, bool)
            or citations < 0
        ):
            raise ValueError("`citations` is not a count")
        parts = data.get("chainParts")
        if parts is not None and not (
            isinstance(parts, Mapping)
            and all(isinstance(v, str) for v in parts.values())
        ):
            raise ValueError("`chainParts` is not a mapping of hashes")
        for key in ("disclosure", "stillValid"):
            if data.get(key) is not None and not isinstance(data.get(key), Mapping):
                raise ValueError(f"`{key}` is not an object")
        return cls(
            pull_request=pull_request,
            required=required,
            reason=reason,
            chain_digest=digest,
            path=str(data.get("path") or ""),
            head_sha=str(data.get("headSha") or ""),
            source_revision=str(data.get("sourceRevision") or ""),
            citations=citations,
            disclosure=dict(data["disclosure"]) if data.get("disclosure") else None,
            still_valid=dict(data["stillValid"]) if data.get("stillValid") else None,
            recorded_at=str(data.get("recordedAt") or ""),
            chain_parts=dict(parts) if parts is not None else None,
        )

    @classmethod
    def load(cls, path: Path, expected_pr: str = "") -> "PrSpecRecord":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"the record is unreadable: {exc.__class__.__name__}"
            ) from exc
        return cls.from_dict(data, expected_pr=expected_pr)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")
        return path


# -- the secret scan ---------------------------------------------------------


def _secret_patterns() -> Tuple[Tuple[str, "re.Pattern[str]"], ...]:
    from ..redact import _EMAIL_RE

    return (
        ("GitHub token", re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}")),
        ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
        ("Slack token", re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}")),
        ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("Authorization header", re.compile(r"(?i)\bAuthorization\s*:\s*\S+")),
        ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")),
        ("cookie header", re.compile(r"(?i)\b(?:Set-)?Cookie\s*:\s*\S+")),
        ("email address", _EMAIL_RE),
    )


def scan_secrets(files: Mapping[str, str]) -> List[Finding]:
    """One finding per line that holds a secret shape (AC5). Never rewrites,
    and never repeats the matched text: the finding is rendered back to an
    agent and may be logged."""
    patterns = _secret_patterns()
    found: List[Finding] = []
    for name, text in files.items():
        for number, line, _ in _lines(text):
            for label, pattern in patterns:
                if pattern.search(line):
                    found.append(
                        Finding(name, number, f"looks like a {label}; remove it")
                    )
                    break
    return found
