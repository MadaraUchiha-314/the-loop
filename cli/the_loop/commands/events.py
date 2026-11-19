"""``the-loop events`` — query the structured JSONL event log (issue-50).

The webhook receiver, the poller and the sessions CLI append every routing /
dispatch / session-lifecycle decision to ``.the-loop/logs/events.jsonl``
(see ``the_loop.eventlog``). This command is the query surface over that
file for humans and coding agents: filter by type/work-item/delivery/source/
level/time, tail it live, or dump the catalog of event types.

Examples::

    the-loop events                                   # last 50 events
    the-loop events --work-item github:octo/repo#15   # one item's full trail
    the-loop events --type 'dispatch.*' --level error # what failed
    the-loop events --delivery-id <uuid>              # one delivery, end to end
    the-loop events --since 2h --follow               # live tail
    the-loop events --types                           # documented event types
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .base import Command, register
from .. import eventlog, strings
from ..client.routing import via_service as _routing_via_service

# Envelope keys rendered as their own table columns; everything else lands in
# the free-form "detail" column.
_ENVELOPE_KEYS = ("ts", "source", "event", "level", "pid", "work_item")

_RELATIVE_SINCE_RE = re.compile(r"^(\d+)([smhd])$")
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_since(value: str) -> str:
    """``15m``/``2h``/``1d`` → an ISO-8601 UTC timestamp; ISO input passes through."""
    match = _RELATIVE_SINCE_RE.match(value.strip())
    if not match:
        return value  # assume ISO-8601 (compared lexicographically against ts)
    from datetime import datetime, timedelta, timezone

    delta = timedelta(seconds=int(match.group(1)) * _SECONDS[match.group(2)])
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _detail(record: dict) -> str:
    parts = []
    for key, value in record.items():
        if key in _ENVELOPE_KEYS:
            continue
        if isinstance(value, (list, dict)):
            value = json.dumps(value, default=str)
        parts.append(f"{key}={value}")
    return " ".join(parts)


def _print_table(records) -> int:
    rows = [
        (
            strings.t("cli.events.table.header.time"),
            strings.t("cli.events.table.header.source"),
            strings.t("cli.events.table.header.level"),
            strings.t("cli.events.table.header.event"),
            strings.t("cli.events.table.header.work-item"),
            strings.t("cli.events.table.header.detail"),
        )
    ]
    for r in records:
        rows.append(
            (
                str(r.get("ts", "-")),
                str(r.get("source", "-")),
                str(r.get("level", "-")),
                str(r.get("event", "-")),
                str(r.get("work_item") or ",".join(r.get("work_items") or []) or "-"),
                _detail(r),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    for row in rows:
        head = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:-1]))
        print(f"{head}  {row[-1]}".rstrip())
    if len(rows) == 1:
        print(strings.t("cli.events.print-table.no-matching-events"), file=sys.stderr)
    return 0


@register
class EventsCommand(Command):
    name = "events"
    help = strings.t("cli.events.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        default_file = str(eventlog.load_config().get("path", eventlog.DEFAULT_PATH))
        parser.add_argument(
            "--file",
            default=default_file,
            help=strings.t("cli.events.file.help"),
        )
        parser.add_argument(
            "--type",
            action="append",
            default=[],
            dest="types",
            metavar="PATTERN",
            help=strings.t("cli.events.type.help"),
        )
        parser.add_argument(
            "--work-item",
            help=strings.t("cli.events.work-item.help"),
        )
        parser.add_argument(
            "--delivery-id",
            help=strings.t("cli.events.delivery-id.help"),
        )
        parser.add_argument(
            "--source",
            choices=["gh-webhook", "poll", "sessions"],
            help=strings.t("cli.events.source.help"),
        )
        parser.add_argument(
            "--level",
            choices=list(eventlog.LEVELS),
            help=strings.t("cli.events.level.help"),
        )
        parser.add_argument(
            "--since",
            help=strings.t("cli.events.since.help"),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help=strings.t("cli.events.limit.help"),
        )
        parser.add_argument(
            "--format", choices=["table", "json", "jsonl"], default="table"
        )
        parser.add_argument(
            "--follow",
            action="store_true",
            help=strings.t("cli.events.follow.help"),
        )
        parser.add_argument(
            "--types",
            action="store_true",
            dest="list_types",
            help=strings.t("cli.events.types.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        if args.list_types:
            width = max(len(name) for name in eventlog.EVENT_TYPES)
            for name, description in eventlog.EVENT_TYPES.items():
                print(f"{name.ljust(width)}  {description}")
            return 0

        since = parse_since(args.since) if args.since else None
        filters = dict(
            types=args.types,
            work_item=args.work_item,
            delivery_id=args.delivery_id,
            source=args.source,
            min_level=args.level,
            since=since,
        )
        try:
            records = self._fetch(args, filters)
        except Exception as exc:
            from ..client import ServiceUnavailable

            if isinstance(exc, ServiceUnavailable):
                print(strings.t("cli.events.run.error", exc=exc), file=sys.stderr)
                return 2
            raise
        if args.limit and args.limit > 0:
            records = records[-args.limit :]

        if args.format == "json":
            print(json.dumps(records, default=str))
        elif args.format == "jsonl":
            for record in records:
                print(json.dumps(record, separators=(",", ":"), default=str))
        else:
            _print_table(records)

        if not args.follow:
            return 0
        return self._follow(args.file, filters, args.format)

    def _fetch(self, args: argparse.Namespace, filters: dict) -> list:
        """The matching records — via the service (issue-161, decision-058).

        Two deliberate local escapes: an **explicit** ``--file`` reads that file
        in-process (the service only ever serves its own configured log —
        arbitrary paths over HTTP would be a file-disclosure surface), and an
        invocation the service itself makes into this CLI stays local.
        """
        default_file = str(eventlog.load_config().get("path", eventlog.DEFAULT_PATH))
        explicit_file = args.file != default_file
        if _routing_via_service() and not explicit_file:
            from .. import client

            connection = client.connect()  # ServiceUnavailable handled in run()
            return list(
                connection.get(
                    "/events",
                    params={
                        "type": filters["types"],
                        "workItem": filters["work_item"],
                        "deliveryId": filters["delivery_id"],
                        "source": filters["source"],
                        "level": filters["min_level"],
                        "since": filters["since"],
                        "limit": 0,
                    },
                )
            )
        return list(eventlog.read_events(args.file, **filters))

    def _follow(self, path: str, filters: dict, fmt: str) -> int:
        """Poll the file for appended lines and print matches until Ctrl-C."""
        offset = Path(path).stat().st_size if Path(path).is_file() else 0
        try:
            while True:
                time.sleep(0.5)
                target = Path(path)
                if not target.is_file():
                    continue
                size = target.stat().st_size
                if size < offset:  # rotated/truncated — start over
                    offset = 0
                if size == offset:
                    continue
                with open(target, "r", encoding="utf-8") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                    offset = handle.tell()
                for record in eventlog.parse_lines(chunk.splitlines(), **filters):
                    if fmt == "table":
                        _print_line(record)
                    else:
                        print(json.dumps(record, separators=(",", ":"), default=str))
                sys.stdout.flush()
        except KeyboardInterrupt:
            return 0


def _print_line(record: dict) -> None:
    print(
        "  ".join(
            [
                str(record.get("ts", "-")),
                str(record.get("source", "-")),
                str(record.get("level", "-")),
                str(record.get("event", "-")),
                str(
                    record.get("work_item")
                    or ",".join(record.get("work_items") or [])
                    or "-"
                ),
                _detail(record),
            ]
        ).rstrip()
    )
