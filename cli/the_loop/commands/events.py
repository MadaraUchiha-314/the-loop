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
from .. import eventlog

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
    rows = [("Time", "Source", "Level", "Event", "Work item", "Detail")]
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
        print("(no matching events)", file=sys.stderr)
    return 0


@register
class EventsCommand(Command):
    name = "events"
    help = "Query the-loop's structured event log (routing, dispatch, sessions)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        default_file = str(eventlog.load_config().get("path", eventlog.DEFAULT_PATH))
        parser.add_argument(
            "--file",
            default=default_file,
            help="Event log to read (default: observability.eventLog.path).",
        )
        parser.add_argument(
            "--type",
            action="append",
            default=[],
            dest="types",
            metavar="PATTERN",
            help="Filter by event type; fnmatch patterns, repeatable "
            "(e.g. --type 'dispatch.*' --type session.spawned).",
        )
        parser.add_argument(
            "--work-item",
            help="Filter to one work item, e.g. github:OWNER/REPO#15.",
        )
        parser.add_argument(
            "--delivery-id",
            help="Filter to one GitHub delivery id (X-GitHub-Delivery).",
        )
        parser.add_argument(
            "--source",
            choices=["gh-webhook", "poll", "sessions"],
            help="Filter by emitting process.",
        )
        parser.add_argument(
            "--level",
            choices=list(eventlog.LEVELS),
            help="Minimum level (e.g. warning shows warning + error).",
        )
        parser.add_argument(
            "--since",
            help="Only events at/after this time: ISO-8601 UTC, or relative "
            "like 30s / 15m / 2h / 1d.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Show only the last N matching events (0 = no limit; default 50).",
        )
        parser.add_argument(
            "--format", choices=["table", "json", "jsonl"], default="table"
        )
        parser.add_argument(
            "--follow",
            action="store_true",
            help="After printing, keep watching the log and print new matches.",
        )
        parser.add_argument(
            "--types",
            action="store_true",
            dest="list_types",
            help="List all documented event types and exit.",
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
        records = list(eventlog.read_events(args.file, **filters))
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
