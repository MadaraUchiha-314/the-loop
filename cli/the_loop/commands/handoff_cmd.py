"""``the-loop handoff post|show|import|note`` — the conversation handoff verb (issue-517).

A developer who talked an idea through with Claude hands it to the-loop with a
**handoff record** (:mod:`the_loop.core.handoff`). This verb is the record's
whole lifecycle on the CLI side:

* ``post`` renders the record, and with ``carried-by: ticket`` its files and part
  comments, and posts each comment in order through the path ``the-loop comment``
  takes — so every one is self-marked and trusted as the-loop's own.
* ``show`` prints the record frozen in ``work-item-state.json`` (read-only).
* ``import`` materializes the carried files into ``docs/specs/<id>/``: from the
  checked-out spec branch, from the ticket's comments, or from ``--from-dir``
  where the session extracted the spec-chain artifact's embedded files. Every
  file is checked against the record's ``sha256``; only verified files are
  written, and a mismatched or missing one is *refused* — reported, never an
  error exit, so the graph hook can demote (design §C8, R7.5).
* ``note`` points the record at the committed files and the PR (R5.4): it edits
  the record when the-loop posted it, else posts one comment that supersedes it.

The record crosses a trust boundary, so the rules here fail closed: no path ever
comes from the record (names are :data:`~the_loop.core.handoff.CHAIN`), a
symlinked target is never written through, and a branch must pass
:func:`~the_loop.core.handoff.is_valid_branch`.

Spec: docs/specs/issue-517/design.md §C3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .base import Command, register
from .sessions_cmd import _cli_config
from .. import eventlog
from ..authz import is_self_authored, mark_self_authored
from ..client.routing import daemon_spawned, harness_routed, service_error
from ..core import github_ops, tickets
from ..core.graphs import work_item_id
from ..core.handoff import (
    CHAIN,
    HandoffRecord,
    collect_parts,
    extract_files,
    is_valid_branch,
    render,
    sha256_text,
)
from ..ghhost import current_branch
from ..workitem import WorkItemRef

_SHA_RE = re.compile(r"[0-9a-f]{64}")
_COMMENT_URL_RE = re.compile(
    r"https://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/"
    r"(?:issues|pull)/(?P<number>[1-9][0-9]*)#issuecomment-(?P<id>[1-9][0-9]*)"
)


class UsageError(ValueError):
    """A caller mistake: exit 2, nothing sent or written."""


@dataclass(frozen=True)
class _Comment:
    """A ticket comment as ``ticket show`` returns it — :class:`CommentLike`."""

    body: str
    author: str
    url: str
    created_at: str


# -- shared helpers ------------------------------------------------------------


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _spec_dir(args: argparse.Namespace) -> Path:
    from ..graph.bootstrap import resolve_spec_root

    root = Path(args.repo).resolve() if args.repo else Path(".").resolve()
    return root / resolve_spec_root(override=args.spec_dir) / work_item_id(args.item)


def _load_state(args: argparse.Namespace):
    from ..graph.state import WorkItemState

    spec_dir = _spec_dir(args)
    return spec_dir, WorkItemState.load(spec_dir, work_item_id(args.item))


def _ref_from_comment_url(url: str) -> str:
    match = _COMMENT_URL_RE.fullmatch(url or "")
    if not match:
        return ""
    host = match.group("host")
    where = "" if host == "github.com" else f"{host}/"
    return (
        f"github:{where}{match.group('owner')}/{match.group('repo')}"
        f"#{match.group('number')}"
    )


def _item_ref(args: argparse.Namespace, record: HandoffRecord) -> WorkItemRef:
    """The GitHub issue the record lives on: ``--work-item``, a ref given as the
    positional, else the issue the record's comment URL (API metadata) names."""
    text = getattr(args, "work_item", "") or ""
    if not text and ":" in args.item:
        text = args.item
    if not text:
        text = _ref_from_comment_url(record.comment_url)
    if not text:
        raise UsageError("cannot tell which issue the record is on; pass --work-item")
    try:
        item = WorkItemRef.parse(text)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    if item.provider != "github":
        raise UsageError(f"{item.ref}: a handoff record lives on a GitHub issue")
    return item


def _routed_comment(ref: str, body: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    """One comment through ``the-loop comment``'s path (self-marked, enveloped)."""
    return harness_routed(
        lambda c: c.post("/work-items/comments", {"ref": ref, "body": body}),
        lambda: tickets.comment(ref, body, config),
    )


def _ticket_comments(
    ref: str, config: Mapping[str, Any]
) -> Tuple[Optional[List[_Comment]], str]:
    """The issue's conversation comments, through ``ticket show``'s path; or
    ``(None, why)`` when they cannot be read."""
    try:
        result = harness_routed(
            lambda c: c.get("/work-items/ticket", params={"ref": ref}),
            lambda: tickets.show_ticket(ref, config),
        )
    except Exception as exc:  # noqa: BLE001 — reported as a refusal reason
        mapped = service_error(exc)
        return None, mapped[0] if mapped else str(exc)
    if int(result.get("exitCode") or 0) != 0:
        texts = [m.get("text", "") for m in result.get("messages") or []]
        return None, "; ".join(t for t in texts if t) or "could not read the ticket"
    comments = [
        _Comment(
            body=str(c.get("body") or ""),
            author=str(c.get("author") or ""),
            url=str(c.get("url") or ""),
            created_at=str(c.get("createdAt") or ""),
        )
        for c in result.get("comments") or []
        if isinstance(c, Mapping) and c.get("kind", "conversation") == "conversation"
    ]
    return comments, ""


def _print(data: Mapping[str, Any]) -> None:
    print(json.dumps(data, indent=2))


def _guarded(call: Callable[[], int]) -> int:
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
        mapped = service_error(exc)
        if mapped is None:
            if not isinstance(exc, ValueError):
                raise
            mapped = (f"error: {exc}", 2)
        print(mapped[0], file=sys.stderr)
        return mapped[1]


# -- post ----------------------------------------------------------------------


def _read_record(path: str) -> HandoffRecord:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read the record {path}: {exc}") from None
    if not isinstance(data, dict):
        raise UsageError(f"{path} is not a JSON object")
    try:
        return HandoffRecord.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise UsageError(f"{path} is not a handoff record: {exc}") from None


def _read_files(record: HandoffRecord, files_dir: str) -> Dict[str, str]:
    """The carried bodies for a ``carried-by: ticket`` record, by artifact name."""
    if record.carried_by != "ticket":
        if files_dir:
            raise UsageError("--files is only for a carried-by ticket record")
        return {}
    if not record.artifacts:
        return {}
    if not files_dir:
        raise UsageError("a carried-by ticket record needs --files <dir>")
    files: Dict[str, str] = {}
    for artifact in record.artifacts:
        if artifact.name not in CHAIN:
            raise UsageError(f"{artifact.name!r} is not a spec-chain artifact")
        path = Path(files_dir) / artifact.name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot read {path}: {exc}") from None
        if sha256_text(text) != artifact.sha256:
            raise UsageError(f"{path} does not match the record's sha256")
        files[artifact.name] = text
    return files


def post(args: argparse.Namespace) -> int:
    record = replace(_read_record(args.record), author="", comment_url="")
    try:
        item = WorkItemRef.parse(args.work_item)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    if item.provider != "github":
        raise UsageError(f"{item.ref}: a handoff record is posted on a GitHub issue")
    files = _read_files(record, args.files or "")
    try:
        comments = render(record, files)
    except ValueError as exc:
        raise UsageError(f"the record would be refused: {exc}") from None
    config = _cli_config()
    posted: List[str] = []
    for body in comments:
        result = _routed_comment(item.ref, body, config)
        if int(result.get("exitCode") or 0) != 0:
            for message in result.get("messages") or []:
                print(message.get("text", ""), file=sys.stderr)
            _print({"workItem": item.ref, "posted": posted, "complete": False})
            return 1
        posted.append(str(result.get("url") or ""))
    _print({"workItem": item.ref, "posted": posted, "complete": True})
    return 0


# -- show ----------------------------------------------------------------------


def show(args: argparse.Namespace) -> int:
    _, state = _load_state(args)
    _print(state.handoff)
    return 0


# -- import --------------------------------------------------------------------


def materialize(
    spec_dir: Path,
    handoff: Mapping[str, Any],
    carried: Optional[Mapping[str, str]],
    carrier_error: str = "",
) -> Dict[str, Any]:
    """Write the carried files that verify; report the rest.

    ``carried`` is what the carrier delivered by name (``None`` for a branch:
    the files are already in the checkout). A file the carrier did not deliver,
    or delivered with the wrong hash, still verifies when the checkout already
    holds a copy that matches (R7.5's fall back to the branch). Nothing outside
    :data:`CHAIN` is ever read or written.
    """
    from ..graph.hooks.handoff import locked_by_handoff, via_of

    written: List[str] = []
    verified: List[str] = []
    refused: List[Dict[str, str]] = []
    via = via_of(str(handoff.get("commentUrl") or ""))
    root = spec_dir.resolve() if spec_dir.exists() else None
    if root is not None and spec_dir.is_symlink():
        # A symlinked spec folder would let a write land outside the checkout.
        return {
            "written": [],
            "verified": [],
            "refused": [
                {
                    "name": str(e.get("name", "")),
                    "reason": "the spec folder is a symlink",
                }
                for e in handoff.get("artifacts") or ()
                if isinstance(e, Mapping)
            ],
        }
    for entry in handoff.get("artifacts") or ():
        name = str(entry.get("name", "")) if isinstance(entry, Mapping) else ""
        sha = str(entry.get("sha256", "")) if isinstance(entry, Mapping) else ""
        if name not in CHAIN:
            refused.append({"name": name, "reason": "not a spec-chain artifact"})
            continue
        if not _SHA_RE.fullmatch(sha):
            refused.append({"name": name, "reason": "malformed sha256"})
            continue
        target = spec_dir / name
        if target.is_symlink():
            refused.append({"name": name, "reason": "the target is a symlink"})
            continue
        existing: Optional[str] = None
        if target.is_file():
            try:
                existing = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                existing = None
        if existing is not None and locked_by_handoff(existing, via):
            # Already imported and locked by this handoff: re-importing would
            # write the unlocked bytes back over the lock (self-review round 1).
            verified.append(name)
            continue
        text = carried.get(name) if carried is not None else None
        if text is not None and sha256_text(text) == sha:
            data = _lf(text).encode("utf-8")
            if not (target.is_file() and target.read_bytes() == data):
                spec_dir.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                written.append(name)
            verified.append(name)
            continue
        local: Optional[str] = None
        if target.is_file():
            try:
                local = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                local = None
        if local is not None and sha256_text(local) == sha:
            verified.append(name)
            continue
        if text is not None or (carried is None and local is not None):
            reason = "sha256 mismatch"
        else:
            reason = carrier_error or "missing"
        refused.append({"name": name, "reason": reason})
    return {"written": written, "verified": verified, "refused": refused}


def _read_dir(from_dir: Path) -> Dict[str, str]:
    """The :data:`CHAIN` files present in ``from_dir`` — no other name is read."""
    found: Dict[str, str] = {}
    for name in CHAIN:
        path = from_dir / name
        if path.is_file():
            try:
                found[name] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    return found


def import_files(args: argparse.Namespace) -> int:
    spec_dir, state = _load_state(args)
    if not state.handoff:
        raise UsageError(f"{work_item_id(args.item)} has no handoff record in state")
    record = HandoffRecord.from_dict(state.handoff)
    carried: Optional[Dict[str, str]] = None
    error = ""
    if args.from_dir:
        from_dir = Path(args.from_dir)
        if not from_dir.is_dir():
            raise UsageError(f"--from-dir {from_dir} is not a directory")
        carried = _read_dir(from_dir)
    elif record.carried_by == "artifact":
        raise UsageError(
            "the record is carried by the spec-chain artifact: extract its "
            "embedded files and pass --from-dir <dir>"
        )
    elif record.carried_by == "ticket":
        item = _item_ref(args, record)
        comments, error = _ticket_comments(item.ref, _cli_config())
        carried = {}
        if comments is not None:
            bodies = collect_parts(comments, record)
            if bodies is None:
                error = "the record comment or one of its part comments is missing"
            else:
                carried = extract_files(bodies)
    result = materialize(spec_dir, state.handoff, carried, error)
    eventlog.emit(
        "handoff.imported",
        level="warning" if result["refused"] else "info",
        work_item=work_item_id(args.item),
        written=len(result["written"]),
        refused=len(result["refused"]),
    )
    _print(result)
    return 0


# -- note ----------------------------------------------------------------------


def _pull_request(args: argparse.Namespace, state: Any, item: WorkItemRef) -> int:
    if args.pull_request:
        return int(args.pull_request)
    rows = [p for p in state.pull_requests if not p.is_self and p.number > 0]
    rows.sort(
        key=lambda p: (
            p.repository.lower() != f"{item.owner}/{item.repo}".lower(),
            p.state == "closed",
        )
    )
    if not rows:
        raise UsageError(
            "no pull request is recorded for the item; pass --pull-request"
        )
    return rows[0].number


def _edit(
    item: WorkItemRef,
    comment: _Comment,
    head: str,
    config: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Edit the-loop's own record comment in place; ``(ok, why not)``.

    In-process on the session's token: the control plane has no edit route, and
    a daemon-spawned session holds no token, so there it is never tried.
    """
    if daemon_spawned():
        return False, "a daemon-spawned session cannot edit comments"
    match = _COMMENT_URL_RE.fullmatch(comment.url)
    if not match or _ref_from_comment_url(comment.url) != item.ref:
        return False, "the record comment is not on this issue"
    from .. import comments as gh_comments
    from ..channels.envelope import parse as parse_envelope, stamp
    from ..channels.github import github_api

    body = mark_self_authored(head)
    envelope = parse_envelope(comment.body)
    if envelope is not None:
        body = stamp(body, envelope)
    try:
        github_ops._trusted(item, config)
        client = gh_comments.resolve_client(github_api(config), None, 30.0)
        client.rest(
            "PATCH",
            f"/repos/{item.owner}/{item.repo}/issues/comments/{match.group('id')}",
            {"body": body},
            host="" if item.default_host else item.host,
        )
    except Exception as exc:  # noqa: BLE001 — the fallback is a superseding comment
        return False, str(exc)
    return True, ""


def note(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve() if args.repo else Path(".").resolve()
    _, state = _load_state(args)
    if not state.handoff:
        raise UsageError(f"{work_item_id(args.item)} has no handoff record in state")
    record = HandoffRecord.from_dict(state.handoff)
    branch = args.branch or current_branch(root)
    if not is_valid_branch(branch):
        raise UsageError(
            f"branch {branch!r} is not a the-loop/ branch; pass --branch"
            if branch
            else "no branch is checked out here; pass --branch"
        )
    item = _item_ref(args, record)
    number = _pull_request(args, state, item)
    pointed = replace(
        record,
        carried_by="branch",
        branch=branch,
        pull_request=number,
        parts=0,
        author="",
        comment_url="",
    )
    try:
        head = render(pointed)[0]
    except ValueError as exc:
        raise UsageError(f"the pointed record would be refused: {exc}") from None
    config = _cli_config()
    carried = f"branch {branch} · PR #{number}"

    comments, _ = _ticket_comments(item.ref, config)
    own = next(
        (
            c
            for c in comments or ()
            if record.comment_url and c.url == record.comment_url
        ),
        None,
    )
    reason = "the record is not the-loop's own comment"
    if own is not None and is_self_authored(own.body):
        edited, reason = _edit(item, own, head, config)
        if edited:
            _print({"edited": True, "url": own.url, "carriedBy": carried})
            return 0
    body = (
        f"Supersedes the handoff record {record.comment_url or '(unknown)'}: the "
        f"carried files are committed on `{branch}` in PR #{number}, and from now "
        "on they are the source of truth.\n\n" + head
    )
    result = _routed_comment(item.ref, body, config)
    if int(result.get("exitCode") or 0) != 0:
        for message in result.get("messages") or []:
            print(message.get("text", ""), file=sys.stderr)
        return 1
    _print(
        {
            "edited": False,
            "url": str(result.get("url") or ""),
            "carriedBy": carried,
            "reason": reason,
        }
    )
    return 0


# -- the command ---------------------------------------------------------------


def _add_location(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "item",
        help="The work item: its spec id (issue-42) or its ref (github:OWNER/REPO#42).",
    )
    parser.add_argument(
        "--repo", default="", help="Repository root (default: the current directory)."
    )
    parser.add_argument(
        "--spec-dir",
        default="",
        dest="spec_dir",
        help="Where the specs live, relative to the repository root "
        "(default: routing.graph.specDir from the CLI config, else docs/specs).",
    )


def _add_work_item(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--work-item",
        default="",
        help="The issue the record is on (default: the positional when it is a "
        "ref, else the issue the record's comment URL names).",
    )


@register
class HandoffCommand(Command):
    name = "handoff"
    help = (
        "Post, show, import or re-point a conversation handoff record "
        "(issue-517) — the record that starts an item past its first phases"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="handoff_command", required=True)

        p_post = actions.add_parser(
            "post", help="Render the record and its parts and post them in order"
        )
        p_post.add_argument(
            "--work-item", required=True, help="The GitHub issue, github:OWNER/REPO#N."
        )
        p_post.add_argument(
            "--record",
            required=True,
            help="The record as JSON (the shape `handoff show` prints).",
        )
        p_post.add_argument(
            "--files",
            default="",
            help="carried-by ticket: the directory holding the carried files.",
        )
        p_post.set_defaults(_action=post)

        p_show = actions.add_parser(
            "show", help="The record frozen in work-item-state.json, as JSON"
        )
        _add_location(p_show)
        p_show.set_defaults(_action=show)

        p_import = actions.add_parser(
            "import",
            help="Write the carried files that verify into docs/specs/<id>/",
        )
        _add_location(p_import)
        _add_work_item(p_import)
        p_import.add_argument(
            "--from-dir",
            default="",
            dest="from_dir",
            help="carried-by artifact: where the session extracted the artifact's "
            "embedded files.",
        )
        p_import.set_defaults(_action=import_files)

        p_note = actions.add_parser(
            "note",
            help="Point the record at the committed files and the PR (edit, or "
            "post a superseding comment)",
        )
        _add_location(p_note)
        _add_work_item(p_note)
        p_note.add_argument(
            "--branch",
            default="",
            help="The spec branch (default: the checkout's current branch).",
        )
        p_note.add_argument(
            "--pull-request",
            type=int,
            default=0,
            dest="pull_request",
            help="The PR number (default: the item's PR recorded in state).",
        )
        p_note.set_defaults(_action=note)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("handoff")
        return _guarded(lambda: args._action(args))
