"""``the-loop comment`` · ``ticket`` · ``pr`` — the harness's GitHub verbs (issue-447).

What the agent in its session used ``gh`` for, as ``the-loop`` verbs: post a
comment on its work item, read or open a ticket, open, inspect and merge a pull
request. The logic is :mod:`the_loop.core.github_ops`; these commands parse,
route and render.

**Routing** is :func:`~the_loop.client.routing.harness_routed`: through the
control-plane service when one is running — its process holds the token, so the
session needs none — and otherwise in-process on the session's own token, with a
note on stderr. Never an auto-started service (decision-140 D2).

What must be read from the **checkout** — the branch ``pr create`` opens from —
is read here, on the CLI side, before routing: the service does not run in the
session's working directory.

Spec: docs/specs/issue-447/design.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict

from .base import Command, register
from .sessions_cmd import _cli_config, _render
from .. import eventlog
from ..client.routing import harness_routed, service_error
from ..core import github_ops, tickets
from ..ghapi import CLOSE_REASONS, MERGE_METHODS
from ..ghhost import current_branch

#: Fields of a core result that are the envelope, not the data.
_ENVELOPE = ("exitCode", "messages")


def _read_body(args: argparse.Namespace, what: str = "body") -> str:
    """``--body`` or ``--body-file`` (``-`` = stdin): where multi-line markdown
    goes to survive shell quoting, as ``ask --question-file`` does."""
    path = getattr(args, "body_file", None)
    if not path:
        return str(getattr(args, "body", "") or "")
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text("utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read the {what}: {exc}") from None


def _add_body(parser: argparse.ArgumentParser, required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--body", help="The text (markdown).")
    group.add_argument(
        "--body-file",
        help="Read the text from this file ('-' = stdin) — for multi-line markdown.",
    )


def _run(call: Callable[[], Dict[str, Any]], as_json: bool = False) -> int:
    """Run one routed call and render it; a caller mistake is exit 2."""
    try:
        result = call()
    except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
        mapped = service_error(exc)
        if mapped is None:
            if not isinstance(exc, ValueError):
                raise
            mapped = (f"error: {exc}", 2)
        print(mapped[0], file=sys.stderr)
        return mapped[1]
    if as_json and int(result.get("exitCode") or 0) == 0:
        data = {k: v for k, v in result.items() if k not in _ENVELOPE}
        print(json.dumps(data, indent=2))
    return _render(result)


@register
class CommentCommand(Command):
    name = "comment"
    help = (
        "Post a comment on a work item as the agent — marked, enveloped and "
        "mirrored to subscribed channels (never needs gh)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--work-item",
            required=True,
            help="Work-item ref, e.g. github:OWNER/REPO#15 (a PR's conversation too) "
            "or jira:SITE/KEY-7.",
        )
        _add_body(parser)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("comment")

        def call() -> Dict[str, Any]:
            body = _read_body(args, "comment")
            return harness_routed(
                lambda c: c.post(
                    "/work-items/comments", {"ref": args.work_item, "body": body}
                ),
                lambda: tickets.comment(args.work_item, body, _cli_config()),
            )

        return _run(call)


@register
class TicketCommand(Command):
    name = "ticket"
    help = "Read a ticket (body, comments, attachment links) or open one"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="ticket_command", required=True)
        show = actions.add_parser(
            "show", help="The ticket's body, comments and attachment links, as JSON"
        )
        show.add_argument(
            "ref", help="Work-item ref, e.g. github:OWNER/REPO#15 or jira:SITE/KEY-7"
        )
        show.set_defaults(_action=self._show)

        create = actions.add_parser(
            "create", help="Open a ticket (a GitHub issue, or a Jira ticket)"
        )
        where = create.add_mutually_exclusive_group(required=True)
        where.add_argument(
            "--repository",
            metavar="[HOST/]OWNER/REPO",
            help="Open a GitHub issue in this repository.",
        )
        where.add_argument(
            "--project",
            metavar="KEY",
            help="Open a Jira ticket in this project (one under "
            "integrations.jira.projects).",
        )
        create.add_argument("--title", required=True)
        _add_body(create)
        create.add_argument(
            "--label",
            action="append",
            default=[],
            help="A label to apply (repeatable), e.g. loop:requirements-definition.",
        )
        create.set_defaults(_action=self._create)

        close = actions.add_parser(
            "close",
            help="Close a registered work item's ticket (finish-tasks' cleanup)",
        )
        close.add_argument(
            "ref",
            help="Work-item ref, e.g. github:OWNER/REPO#15, or jira:SITE/KEY-7 "
            "(transitioned into Done)",
        )
        close.add_argument("--reason", choices=CLOSE_REASONS, default="completed")
        close.add_argument(
            "--work-item",
            default="",
            help="An ad-hoc (`the-loop do`) work item closing a ticket it names.",
        )
        close.set_defaults(_action=self._close)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("ticket")
        return args._action(args)

    def _show(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.get("/work-items/ticket", params={"ref": args.ref}),
                lambda: tickets.show_ticket(args.ref, _cli_config()),
            ),
            as_json=True,
        )

    def _close(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.post(
                    "/work-items/tickets/close",
                    {
                        "ref": args.ref,
                        "reason": args.reason,
                        "workItem": args.work_item,
                    },
                ),
                lambda: tickets.close_ticket(
                    args.ref, args.reason, args.work_item, _cli_config()
                ),
            )
        )

    def _create(self, args: argparse.Namespace) -> int:
        def call() -> Dict[str, Any]:
            body = _read_body(args)
            return harness_routed(
                lambda c: c.post(
                    "/work-items/tickets",
                    {
                        "repository": args.repository or "",
                        "project": args.project or "",
                        "title": args.title,
                        "body": body,
                        "labels": list(args.label),
                    },
                ),
                lambda: tickets.create_ticket(
                    args.repository or "",
                    args.title,
                    body,
                    args.label,
                    _cli_config(),
                    project=args.project or "",
                ),
            )

        return _run(call)


def _add_pr(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "pull_request",
        metavar="PR",
        help="The pull request: a ref (github:OWNER/REPO#16), its URL, or a "
        "number with --work-item.",
    )
    parser.add_argument(
        "--work-item",
        default="",
        help="Work-item ref a bare PR number is resolved against.",
    )


@register
class PrCommand(Command):
    name = "pr"
    help = (
        "Open, inspect, ready or merge a pull request for a work item (never needs gh)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="pr_command", required=True)

        create = actions.add_parser(
            "create",
            help="Open the pull request and link it to the work item in one act",
        )
        create.add_argument(
            "--work-item",
            required=True,
            help="Work-item ref the PR delivers; a jira: ref opens it in its "
            "project's repository.",
        )
        create.add_argument("--title", required=True)
        _add_body(create)
        create.add_argument(
            "--head",
            default="",
            help="The branch to merge from (default: the checkout's current branch; "
            "OWNER:BRANCH for a fork).",
        )
        create.add_argument(
            "--base",
            default="",
            help="The branch to merge into (default: the repository's default branch).",
        )
        create.add_argument(
            "--repository",
            default="",
            metavar="[HOST/]OWNER/REPO",
            help="Where to open it (default: the work item's repository).",
        )
        create.add_argument("--draft", action="store_true", help="Open it as a draft.")
        create.set_defaults(_action=self._create)

        status = actions.add_parser(
            "status", help="State, mergeability and one checks verdict, as JSON"
        )
        _add_pr(status)
        status.set_defaults(_action=self._status)

        checks = actions.add_parser(
            "checks",
            help="Every check on the PR's head, with failed jobs' log tails, as JSON",
        )
        _add_pr(checks)
        checks.add_argument(
            "--failing", action="store_true", help="List only the failing checks."
        )
        checks.add_argument(
            "--log-lines",
            type=int,
            default=github_ops.DEFAULT_LOG_LINES,
            metavar="N",
            help="Lines of each failed GitHub Actions job's log to include "
            f"(default {github_ops.DEFAULT_LOG_LINES}; 0 fetches none).",
        )
        checks.set_defaults(_action=self._checks)

        threads = actions.add_parser(
            "threads", help="The PR's unresolved review threads, as JSON"
        )
        _add_pr(threads)
        threads.add_argument(
            "--all", action="store_true", help="Include resolved threads."
        )
        threads.set_defaults(_action=self._threads)

        resolve = actions.add_parser(
            "resolve-thread",
            help="Resolve one of the PR's review threads (an id from `pr threads`)",
        )
        _add_pr(resolve)
        resolve.add_argument(
            "--thread", required=True, help="The thread's id (PRRT_…)."
        )
        resolve.set_defaults(_action=self._resolve)

        ready = actions.add_parser(
            "ready",
            help="Take a draft PR out of draft, ready for review",
        )
        _add_pr(ready)
        ready.set_defaults(_action=self._ready)

        merge = actions.add_parser(
            "merge",
            help="Merge the PR — refused when routing.mergeOnApproval is false",
        )
        _add_pr(merge)
        merge.add_argument("--method", choices=MERGE_METHODS, default="merge")
        merge.add_argument(
            "--sha",
            default="",
            help="The head commit you reviewed; GitHub refuses the merge if the "
            "branch has moved since (recommended).",
        )
        merge.set_defaults(_action=self._merge)

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("pr")
        return args._action(args)

    def _create(self, args: argparse.Namespace) -> int:
        def call() -> Dict[str, Any]:
            body = _read_body(args)
            head = args.head or current_branch(Path.cwd())
            if not head:
                raise ValueError(
                    "no branch is checked out here (detached HEAD?); pass --head"
                )
            return harness_routed(
                lambda c: c.post(
                    "/work-items/pull-requests",
                    {
                        "ref": args.work_item,
                        "title": args.title,
                        "body": body,
                        "head": head,
                        "base": args.base,
                        "repository": args.repository,
                        "draft": bool(args.draft),
                    },
                ),
                lambda: tickets.create_pull_request(
                    args.work_item,
                    args.title,
                    body,
                    head,
                    base=args.base,
                    repository=args.repository,
                    draft=bool(args.draft),
                    config=_cli_config(),
                ),
            )

        return _run(call)

    def _status(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.get(
                    "/pull-requests/status",
                    params={"ref": args.pull_request, "workItem": args.work_item},
                ),
                lambda: github_ops.pull_request_status(
                    args.pull_request, args.work_item, _cli_config()
                ),
            ),
            as_json=True,
        )

    def _checks(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.get(
                    "/pull-requests/checks",
                    params={
                        "ref": args.pull_request,
                        "workItem": args.work_item,
                        "failing": "true" if args.failing else "",
                        "logLines": str(args.log_lines),
                    },
                ),
                lambda: github_ops.pull_request_checks(
                    args.pull_request,
                    args.work_item,
                    failing_only=bool(args.failing),
                    log_lines=args.log_lines,
                    config=_cli_config(),
                ),
            ),
            as_json=True,
        )

    def _threads(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.get(
                    "/pull-requests/threads",
                    params={
                        "ref": args.pull_request,
                        "workItem": args.work_item,
                        "all": "true" if args.all else "",
                    },
                ),
                lambda: github_ops.pull_request_threads(
                    args.pull_request,
                    args.work_item,
                    include_resolved=bool(args.all),
                    config=_cli_config(),
                ),
            ),
            as_json=True,
        )

    def _resolve(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.post(
                    "/pull-requests/threads/resolve",
                    {
                        "ref": args.pull_request,
                        "workItem": args.work_item,
                        "thread": args.thread,
                    },
                ),
                lambda: github_ops.resolve_thread(
                    args.pull_request, args.thread, args.work_item, _cli_config()
                ),
            )
        )

    def _ready(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.post(
                    "/pull-requests/ready",
                    {"ref": args.pull_request, "workItem": args.work_item},
                ),
                lambda: github_ops.mark_ready(
                    args.pull_request, args.work_item, _cli_config()
                ),
            )
        )

    def _merge(self, args: argparse.Namespace) -> int:
        return _run(
            lambda: harness_routed(
                lambda c: c.post(
                    "/pull-requests/merge",
                    {
                        "ref": args.pull_request,
                        "workItem": args.work_item,
                        "method": args.method,
                        "sha": args.sha,
                    },
                ),
                lambda: github_ops.merge_pull_request(
                    args.pull_request,
                    args.work_item,
                    args.method,
                    _cli_config(),
                    sha=args.sha,
                ),
            )
        )
