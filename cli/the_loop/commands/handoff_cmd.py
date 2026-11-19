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
from .. import eventlog, strings
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
        raise UsageError(strings.t("cli.handoff.item-ref.cannot-tell-issue"))
    try:
        item = WorkItemRef.parse(text)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    if item.provider != "github":
        raise UsageError(strings.t("cli.handoff.item-ref.not-github", ref=item.ref))
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
        return None, "; ".join(t for t in texts if t) or strings.t(
            "cli.handoff.ticket-comments.could-not-read"
        )
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
            mapped = (strings.t("cli.handoff.guarded.error", exc=exc), 2)
        print(mapped[0], file=sys.stderr)
        return mapped[1]


# -- post ----------------------------------------------------------------------


def _read_record(path: str) -> HandoffRecord:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(
            strings.t("cli.handoff.read-record.cannot-read", path=path, exc=exc)
        ) from None
    if not isinstance(data, dict):
        raise UsageError(strings.t("cli.handoff.read-record.not-an-object", path=path))
    try:
        return HandoffRecord.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise UsageError(
            strings.t("cli.handoff.read-record.not-a-record", path=path, exc=exc)
        ) from None


def _read_files(record: HandoffRecord, files_dir: str) -> Dict[str, str]:
    """The carried bodies for a ``carried-by: ticket`` record, by artifact name."""
    if record.carried_by != "ticket":
        if files_dir:
            raise UsageError(
                strings.t("cli.handoff.read-files.files-not-for-this-record")
            )
        return {}
    if not record.artifacts:
        return {}
    if not files_dir:
        raise UsageError(strings.t("cli.handoff.read-files.needs-files"))
    files: Dict[str, str] = {}
    for artifact in record.artifacts:
        if artifact.name not in CHAIN:
            raise UsageError(
                strings.t("cli.handoff.read-files.not-in-chain", name=artifact.name)
            )
        path = Path(files_dir) / artifact.name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(
                strings.t("cli.handoff.read-files.cannot-read", path=path, exc=exc)
            ) from None
        if sha256_text(text) != artifact.sha256:
            raise UsageError(
                strings.t("cli.handoff.read-files.sha256-mismatch", path=path)
            )
        files[artifact.name] = text
    return files


def post(args: argparse.Namespace) -> int:
    record = replace(_read_record(args.record), author="", comment_url="")
    try:
        item = WorkItemRef.parse(args.work_item)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    if item.provider != "github":
        raise UsageError(strings.t("cli.handoff.post.not-github", ref=item.ref))
    files = _read_files(record, args.files or "")
    try:
        comments = render(record, files)
    except ValueError as exc:
        raise UsageError(
            strings.t("cli.handoff.post.would-be-refused", exc=exc)
        ) from None
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
    from ..core.handoff import contained
    from ..graph.hooks.handoff import locked_by_handoff

    written: List[str] = []
    verified: List[str] = []
    refused: List[Dict[str, str]] = []
    if not contained(spec_dir, spec_dir):
        # A symlinked spec folder, or a symlinked docs/ or docs/specs/ above
        # it, would let a write land outside the checkout (self-review round 2).
        return {
            "written": [],
            "verified": [],
            "refused": [
                {
                    "name": str(e.get("name", "")),
                    "reason": strings.t(
                        "cli.handoff.materialize.spec-folder-symlinked"
                    ),
                }
                for e in handoff.get("artifacts") or ()
                if isinstance(e, Mapping)
            ],
        }
    for entry in handoff.get("artifacts") or ():
        name = str(entry.get("name", "")) if isinstance(entry, Mapping) else ""
        sha = str(entry.get("sha256", "")) if isinstance(entry, Mapping) else ""
        if name not in CHAIN:
            refused.append(
                {
                    "name": name,
                    "reason": strings.t("cli.handoff.materialize.not-in-chain"),
                }
            )
            continue
        if not _SHA_RE.fullmatch(sha):
            refused.append(
                {
                    "name": name,
                    "reason": strings.t("cli.handoff.materialize.malformed-sha256"),
                }
            )
            continue
        target = spec_dir / name
        if target.is_symlink():
            refused.append(
                {
                    "name": name,
                    "reason": strings.t("cli.handoff.materialize.target-symlinked"),
                }
            )
            continue
        existing: Optional[str] = None
        if target.is_file():
            try:
                existing = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                existing = None
        if existing is not None and locked_by_handoff(existing, name, handoff):
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
            reason = strings.t("cli.handoff.materialize.sha256-mismatch")
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
        raise UsageError(
            strings.t(
                "cli.handoff.no-record-in-state", work_item_id=work_item_id(args.item)
            )
        )
    record = HandoffRecord.from_dict(state.handoff)
    carried: Optional[Dict[str, str]] = None
    error = ""
    if args.from_dir:
        from_dir = Path(args.from_dir)
        if not from_dir.is_dir():
            raise UsageError(
                strings.t(
                    "cli.handoff.import.from-dir-not-a-directory", from_dir=from_dir
                )
            )
        carried = _read_dir(from_dir)
    elif record.carried_by == "artifact":
        raise UsageError(strings.t("cli.handoff.import.carried-by-artifact"))
    elif record.carried_by == "ticket":
        item = _item_ref(args, record)
        comments, error = _ticket_comments(item.ref, _cli_config())
        carried = {}
        if comments is not None:
            bodies = collect_parts(comments, record)
            if bodies is None:
                error = strings.t("cli.handoff.import.parts-missing")
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
        raise UsageError(strings.t("cli.handoff.pull-request.none-recorded"))
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
        return False, strings.t("cli.handoff.edit.daemon-spawned")
    match = _COMMENT_URL_RE.fullmatch(comment.url)
    if not match or _ref_from_comment_url(comment.url) != item.ref:
        return False, strings.t("cli.handoff.edit.not-on-this-issue")
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
        raise UsageError(
            strings.t(
                "cli.handoff.no-record-in-state", work_item_id=work_item_id(args.item)
            )
        )
    record = HandoffRecord.from_dict(state.handoff)
    branch = args.branch or current_branch(root)
    if not is_valid_branch(branch):
        raise UsageError(
            strings.t("cli.handoff.note.not-a-loop-branch", branch=branch)
            if branch
            else strings.t("cli.handoff.note.no-branch")
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
        raise UsageError(
            strings.t("cli.handoff.note.pointed-would-be-refused", exc=exc)
        ) from None
    config = _cli_config()
    carried = strings.t("cli.handoff.note.carried-by", branch=branch, number=number)

    comments, _ = _ticket_comments(item.ref, config)
    own = next(
        (
            c
            for c in comments or ()
            if record.comment_url and c.url == record.comment_url
        ),
        None,
    )
    reason = strings.t("cli.handoff.note.not-own-comment")
    if own is not None and is_self_authored(own.body):
        edited, reason = _edit(item, own, head, config)
        if edited:
            _print({"edited": True, "url": own.url, "carriedBy": carried})
            return 0
    body = (
        strings.t(
            "cli.handoff.note.supersedes",
            comment_url=record.comment_url or strings.t("cli.handoff.note.unknown-url"),
            branch=branch,
            number=number,
        )
        + head
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
        help=strings.t("cli.handoff.add-location.item.help"),
    )
    parser.add_argument(
        "--repo", default="", help=strings.t("cli.handoff.add-location.repo.help")
    )
    parser.add_argument(
        "--spec-dir",
        default="",
        dest="spec_dir",
        help=strings.t("cli.handoff.add-location.spec-dir.help"),
    )


def _add_work_item(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--work-item",
        default="",
        help=strings.t("cli.handoff.add-work-item.work-item.help"),
    )


@register
class HandoffCommand(Command):
    name = "handoff"
    help = strings.t("cli.handoff.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="handoff_command", required=True)

        p_post = actions.add_parser("post", help=strings.t("cli.handoff.post.help"))
        p_post.add_argument(
            "--work-item",
            required=True,
            help=strings.t("cli.handoff.post.work-item.help"),
        )
        p_post.add_argument(
            "--record",
            required=True,
            help=strings.t("cli.handoff.post.record.help"),
        )
        p_post.add_argument(
            "--files",
            default="",
            help=strings.t("cli.handoff.post.files.help"),
        )
        p_post.set_defaults(_action=post)

        p_show = actions.add_parser("show", help=strings.t("cli.handoff.show.help"))
        _add_location(p_show)
        p_show.set_defaults(_action=show)

        p_import = actions.add_parser(
            "import",
            help=strings.t("cli.handoff.import.help"),
        )
        _add_location(p_import)
        _add_work_item(p_import)
        p_import.add_argument(
            "--from-dir",
            default="",
            dest="from_dir",
            help=strings.t("cli.handoff.import.from-dir.help"),
        )
        p_import.set_defaults(_action=import_files)

        p_note = actions.add_parser(
            "note",
            help=strings.t("cli.handoff.note.help"),
        )
        _add_location(p_note)
        _add_work_item(p_note)
        p_note.add_argument(
            "--branch",
            default="",
            help=strings.t("cli.handoff.note.branch.help"),
        )
        p_note.add_argument(
            "--pull-request",
            type=int,
            default=0,
            dest="pull_request",
            help=strings.t("cli.handoff.note.pull-request.help"),
        )
        p_note.set_defaults(_action=note)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("handoff")
        return _guarded(lambda: args._action(args))
