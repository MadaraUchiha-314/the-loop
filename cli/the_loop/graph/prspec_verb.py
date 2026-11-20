"""``the-loop graph pr-spec``: verify one delivery PR's PR spec, then record it
(issue-543, design § Interfaces).

The online half of PR-scoped specs. It runs once per derivation, from the
origin checkout, with the PR's working tree at ``checkout``:

1. the checkout is the PR's (its ``origin`` remote and its branch);
2. is a PR spec required at all (``single-pr``, ``spec-only``, ``multi-pr``);
3. the chain may be derived from (approved, or its gate declared skipped);
4. the PR-spec path is safe (AC4);
5. the four files are complete;
6. every citation resolves and every item that must cite does;
7. no secret shapes (AC5);
8. the disclosure is allowed (AC1, AC2).

Every finding is reported at once. On success it writes exactly one file —
``pr-spec.json`` in the PR's inner-loop directory — and nothing else (AC3).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .frontmatter import read_front_matter, sections, split_front_matter
from .prspec import (
    PR_SPEC_FILES,
    PR_SPEC_RECORD,
    ChainIndex,
    Finding,
    PrSpecRecord,
    applicability,
    chain_digest,
    chain_parts,
    citation_tokens,
    missing_citations,
    pr_spec_dir,
    pr_spec_key,
    scan_secrets,
    unresolved_citations,
)
from .prspec_github import authorize_comment, check_disclosure

__all__ = [
    "REQUIRED_SECTIONS",
    "STILL_VALID_PHRASE",
    "PrSpecRequest",
    "PrSpecResult",
    "record_pr_spec",
]

#: The sections each PR-spec file must have, non-empty (R2.2–R2.6, R4.2). The
#: templates under ``skills/the-loop/templates/pr-spec/`` carry exactly these
#: headings; ``tests/test_pr_spec.py`` keeps the two in step.
REQUIRED_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "requirements.md": ("Context", "Requirements"),
    "design.md": ("Context", "Design"),
    "testing-plan.md": ("Context", "Test matrix"),
    "tasks.md": ("Context", "Tasks"),
}

#: Which gate locks each chain file: an approved file, or a declared skip of
#: its gate, may be derived from (R3.3).
_CHAIN_GATES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("requirements.md", "bugfix.md"), "requirements-approval"),
    (("design.md",), "design-approval"),
    (("testing-plan.md",), "design-approval"),
)

#: The line an authorized person writes on the PR to say a chain change does
#: not affect it (R5.2).
STILL_VALID_PHRASE = "pr-spec still-valid"

_CHAIN_FILES = (
    "requirements.md",
    "bugfix.md",
    "design.md",
    "testing-plan.md",
    "tasks.md",
)

_REV_RE = re.compile(r"[0-9a-fA-F]{7,64}")

_REMOTE_RE = re.compile(
    r"(?:https?://[^/]+/|ssh://git@[^/]+/|git@[^:]+:)(?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$"
)


@dataclass
class PrSpecRequest:
    """Everything the verb needs, resolved by the caller (``core.graphs``)."""

    work_item_id: str
    work_item_ref: str  # the outer work item, e.g. github:octo/origin#15
    pr_ref: str  # github:octo/api#12
    pr_repo: str  # octo/api
    pr_number: int
    origin: str  # octo/origin
    spec_dir: Path  # the origin checkout's docs/specs/<id>
    record_dir: Path  # the PR's inner-loop directory in the origin checkout
    checkout: Path
    pull_requests: Sequence[Any] = ()
    declared_repos: Sequence[str] = ()
    skips: Mapping[str, Any] = field(default_factory=dict)
    authorized: Sequence[str] = ()
    disclosure_approval: str = ""
    still_valid: str = ""
    now: str = ""


@dataclass
class PrSpecResult:
    recorded: bool
    findings: List[Finding]
    record: Optional[PrSpecRecord] = None
    record_path: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recorded": self.recorded,
            "record": self.record.as_dict() if self.record else None,
            "recordPath": self.record_path,
            "findings": [
                {"file": f.file, "line": f.line, "text": f.text} for f in self.findings
            ],
        }


def _git(checkout: Path, *args: str) -> Optional[str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(checkout), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _remote_repo(url: str) -> str:
    match = _REMOTE_RE.search(url.strip())
    return match["repo"] if match else ""


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def _check_checkout(req: PrSpecRequest, pull: Mapping[str, Any]) -> List[Finding]:
    """Check 1: the checkout's ``origin`` is the PR's repository and its branch
    is the PR's head branch."""
    where = str(req.checkout)
    if not req.checkout.is_dir():
        return [Finding(where, 0, "the PR checkout is not a directory")]
    remote = _git(req.checkout, "remote", "get-url", "origin")
    if not remote or not _same(_remote_repo(remote), req.pr_repo):
        return [
            Finding(where, 0, f"the checkout's `origin` remote is not {req.pr_repo}")
        ]
    branch = _git(req.checkout, "rev-parse", "--abbrev-ref", "HEAD")
    head = str(
        ((pull.get("head") or {}) if isinstance(pull, Mapping) else {}).get("ref") or ""
    )
    if not head:
        return [Finding(where, 0, f"could not read {req.pr_ref}'s head branch")]
    if branch != head:
        return [
            Finding(
                where,
                0,
                f"the checkout is on `{branch}`, not {req.pr_ref}'s branch `{head}`",
            )
        ]
    return []


def _spec_only(req: PrSpecRequest, pull: Mapping[str, Any]) -> bool:
    """Does the PR touch nothing outside ``docs/specs/<id>/``? Only an
    origin-repository PR can be the outer surface's spec PR. Any doubt is "no"."""
    if not _same(req.pr_repo, req.origin):
        return False
    base = str(
        ((pull.get("base") or {}) if isinstance(pull, Mapping) else {}).get("ref") or ""
    )
    if not base:
        return False
    merge_base = _git(req.checkout, "merge-base", f"origin/{base}", "HEAD")
    if not merge_base:
        return False
    changed = _git(req.checkout, "diff", "--name-only", f"{merge_base}..HEAD")
    if changed is None:
        return False
    names = [n for n in changed.splitlines() if n.strip()]
    prefix = f"docs/specs/{req.work_item_id}/"
    return bool(names) and all(n.startswith(prefix) for n in names)


def _check_chain(req: PrSpecRequest) -> List[Finding]:
    """Check 3: each chain file is approved, or its gate was declared skipped."""
    found: List[Finding] = []
    for names, gate in _CHAIN_GATES:
        path = next(
            (req.spec_dir / n for n in names if (req.spec_dir / n).is_file()), None
        )
        if isinstance(req.skips.get(gate), Mapping):
            continue
        if path is None:
            found.append(Finding(names[0], 0, "the work-item chain has no such file"))
        elif str(read_front_matter(path).get("status") or "") != "approved":
            found.append(
                Finding(
                    path.name,
                    0,
                    "the work-item file is not approved; derive from an approved chain",
                )
            )
    return found


def _resolve_dir(req: PrSpecRequest) -> Tuple[Optional[Path], str, List[Finding]]:
    """Check 4: the PR-spec directory, resolved inside the checkout (AC4)."""
    try:
        rel = pr_spec_dir(
            pr_spec_key(req.origin, req.pr_repo, req.work_item_id), req.pr_number
        )
    except ValueError as exc:
        return None, "", [Finding("", 0, f"no safe PR-spec path: {exc}")]
    root = req.checkout.resolve()
    target = (req.checkout / rel).resolve()
    if not target.is_relative_to(root):
        return (
            None,
            rel,
            [Finding(rel, 0, "the PR-spec path resolves outside the checkout")],
        )
    return target, rel, []


def _check_files(
    req: PrSpecRequest, target: Path, digest: str
) -> Tuple[Dict[str, str], Dict[str, Any], List[Finding]]:
    """Check 5: four files, each with the right front matter and sections."""
    texts: Dict[str, str] = {}
    front_of_first: Dict[str, Any] = {}
    found: List[Finding] = []
    for name, kind in PR_SPEC_FILES:
        path = target / name
        if not path.is_file() or path.is_symlink():
            found.append(Finding(name, 0, "missing (write it from templates/pr-spec/)"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            found.append(Finding(name, 0, "unreadable"))
            continue
        front, body = split_front_matter(text)
        texts[name] = text
        if not front_of_first:
            front_of_first = front
        expected = {
            "type": kind,
            "workItem": req.work_item_ref,
            "pullRequest": req.pr_ref,
            "chainDigest": digest,
        }
        for key, want in expected.items():
            have_value = str(front.get(key) or "")
            # Refs name GitHub repositories, whose names are case-insensitive.
            same = (
                have_value.lower() == want.lower()
                if key in ("workItem", "pullRequest")
                else have_value == want
            )
            if not same:
                found.append(Finding(name, 1, f"front matter `{key}` must be {want!r}"))
        if "status" in front:
            found.append(
                Finding(
                    name,
                    1,
                    "a PR spec carries no `status` (it is never approved on its own)",
                )
            )
        if not str(front.get("sourceRevision") or ""):
            found.append(Finding(name, 1, "front matter `sourceRevision` is empty"))
        have = sections(body)
        for heading in REQUIRED_SECTIONS[name]:
            if not have.get(heading, "").strip():
                found.append(
                    Finding(name, 0, f"section `{heading}` is missing or empty")
                )
    return texts, front_of_first, found


def _authorized(
    req: PrSpecRequest, client: Any
) -> Tuple[Optional[Dict[str, Any]], List[Finding]]:
    grant, problem = authorize_comment(
        client,
        req.still_valid,
        expected=req.pr_ref,
        authorized=req.authorized,
        must_contain=STILL_VALID_PHRASE,
    )
    return grant, ([Finding("--still-valid", 0, problem)] if problem else [])


def _parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _chain_changed_at(spec_dir: Path) -> Tuple[Optional[datetime], str]:
    """When the chain last changed: its newest commit touching a chain file.

    ``(None, reason)`` when that cannot be told: an uncommitted change to the
    chain, or no git history to read.
    """
    names = [n for n in _CHAIN_FILES if (spec_dir / n).is_file()]
    if not names:
        return None, "the work-item chain has no files"
    dirty = _git(spec_dir, "status", "--porcelain", "--", *names)
    if dirty is None:
        return None, "the work-item chain's git history cannot be read"
    if dirty:
        return None, "commit the chain change first, so its time is known"
    stamp = _git(spec_dir, "log", "-1", "--format=%cI", "--", *names) or ""
    when = _parse_time(stamp)
    if when is None:
        return None, "the work-item chain's last change cannot be dated"
    return when, ""


def _check_declared_after(
    req: PrSpecRequest, grant: Mapping[str, Any], previous: PrSpecRecord
) -> List[Finding]:
    """A ``--still-valid`` comment must postdate both the record it moves
    forward and the chain change it speaks to: a comment written before the
    change cannot be about it."""
    said = _parse_time(str(grant.get("at") or ""))
    recorded = _parse_time(previous.recorded_at)
    changed, why = _chain_changed_at(req.spec_dir)
    if changed is None:
        return [Finding("--still-valid", 0, why)]
    if said is None or recorded is None or said <= max(recorded, changed):
        return [
            Finding(
                "--still-valid",
                0,
                f"{grant.get('comment')} was written before the PR spec was last "
                "recorded or before the chain last changed; the declaration must "
                "come after the change it speaks to",
            )
        ]
    return []


def _check_committed(req: PrSpecRequest, rel: str) -> List[Finding]:
    """The four files are committed on the checkout's branch, as they are:
    a reviewer sees the branch, never the working tree."""
    tracked = _git(req.checkout, "ls-files", "--", rel)
    dirty = _git(req.checkout, "status", "--porcelain", "--", rel)
    if tracked is None or dirty is None:
        return [Finding(rel, 0, "the PR checkout's git state cannot be read")]
    have = {Path(line).name for line in tracked.splitlines() if line.strip()}
    missing = [n for n, _ in PR_SPEC_FILES if n not in have]
    if missing or dirty:
        return [
            Finding(
                rel,
                0,
                "commit the PR spec in the PR's branch before recording it "
                "(uncommitted or untracked files)",
            )
        ]
    return []


def _check_source_revisions(
    req: PrSpecRequest, texts: Mapping[str, str]
) -> List[Finding]:
    """Each file's ``sourceRevision`` names a commit of the origin repository."""
    found: List[Finding] = []
    seen: Dict[str, bool] = {}
    for name, text in texts.items():
        rev = str(split_front_matter(text)[0].get("sourceRevision") or "").strip()
        if not rev:
            continue  # reported by the front-matter check
        if rev not in seen:
            seen[rev] = bool(_REV_RE.fullmatch(rev)) and (
                _git(req.spec_dir, "cat-file", "-e", f"{rev}^{{commit}}") is not None
            )
        if not seen[rev]:
            found.append(
                Finding(
                    name,
                    1,
                    f"`sourceRevision` {rev!r} is not a commit of the origin repository",
                )
            )
    return found


def _write(req: PrSpecRequest, record: PrSpecRecord) -> str:
    path = req.record_dir / PR_SPEC_RECORD
    record.save(path)
    return str(path)


def record_pr_spec(req: PrSpecRequest, client: Any) -> PrSpecResult:
    """Run the checks; write ``pr-spec.json`` only when there are no findings."""
    findings: List[Finding] = []
    try:
        owner, _, name = req.pr_repo.partition("/")
        pull = client.get_pull(owner, name, req.pr_number)
    except Exception as exc:  # noqa: BLE001 — an unread PR verifies nothing
        return PrSpecResult(
            False,
            [Finding("", 0, f"could not read {req.pr_ref} ({exc.__class__.__name__})")],
        )
    findings += _check_checkout(req, pull)
    if findings:
        return PrSpecResult(False, findings)
    head_sha = _git(req.checkout, "rev-parse", "HEAD") or ""
    digest = chain_digest(req.spec_dir)
    parts = chain_parts(req.spec_dir)

    def base_record(**kw: Any) -> PrSpecRecord:
        return PrSpecRecord(
            pull_request=req.pr_ref,
            head_sha=head_sha,
            chain_digest=digest,
            chain_parts=parts,
            recorded_at=req.now,
            **kw,
        )

    # Check 2: applicability.
    if applicability(req.pull_requests, req.declared_repos, req.origin) == "single-pr":
        record = base_record(required=False, reason="single-pr")
        return PrSpecResult(True, [], record, _write(req, record))
    if _spec_only(req, pull):
        record = base_record(required=False, reason="spec-only")
        return PrSpecResult(True, [], record, _write(req, record))

    findings += _check_chain(req)
    target, rel, problems = _resolve_dir(req)
    findings += problems
    if target is None:
        return PrSpecResult(False, findings)

    if req.still_valid:
        # R5.2: a human declared the changed chain does not affect this PR. The
        # files are not re-derived, so only the record moves to the new digest.
        try:
            previous = PrSpecRecord.load(
                req.record_dir / PR_SPEC_RECORD, expected_pr=req.pr_ref
            )
        except ValueError as exc:
            findings.append(
                Finding(
                    PR_SPEC_RECORD, 0, f"--still-valid needs an existing record ({exc})"
                )
            )
            previous = None
        grant, problems = _authorized(req, client)
        findings += problems
        if grant is not None and previous is not None:
            findings += _check_declared_after(req, grant, previous)
        if findings or previous is None or not previous.required:
            if previous is not None and not previous.required:
                findings.append(
                    Finding(
                        PR_SPEC_RECORD,
                        0,
                        "--still-valid applies to a required PR spec only",
                    )
                )
            return PrSpecResult(False, findings)
        previous.chain_digest, previous.chain_parts = digest, parts
        previous.head_sha, previous.recorded_at = head_sha, req.now
        previous.still_valid = grant
        return PrSpecResult(True, [], previous, _write(req, previous))

    texts, front, problems = _check_files(req, target, digest)
    findings += problems
    findings += _check_committed(req, rel)
    findings += _check_source_revisions(req, texts)
    index = ChainIndex.load(req.spec_dir)
    findings += unresolved_citations(texts, index)
    findings += missing_citations(texts)
    findings += scan_secrets(texts)
    disclosure: Optional[Dict[str, Any]] = None
    if not _same(req.pr_repo, req.origin):
        disclosure, problem = check_disclosure(
            client,
            origin=req.origin,
            target=req.pr_repo,
            work_item=req.work_item_ref,
            approval_url=req.disclosure_approval,
            authorized=req.authorized,
        )
        if problem:
            findings.append(Finding("", 0, problem))
    if findings:
        return PrSpecResult(False, findings)
    record = base_record(
        required=True,
        reason="multi-pr",
        path=rel,
        source_revision=str(front.get("sourceRevision") or ""),
        citations=sum(len(citation_tokens(t)) for t in texts.values()),
        disclosure=disclosure,
    )
    return PrSpecResult(True, [], record, _write(req, record))
