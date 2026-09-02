"""``the-loop channels`` — operate the communication channels (issue-245).

Four actions: ``status`` (what is configured, with token *presence* only —
never values), ``threads`` (which Slack thread carries which work item's
conversation, issue-312 — reads the state file, calls nothing), ``poll`` (one
synchronous read cycle, for cron and daemon-less deployments, R4.1), and
``listen`` (Socket Mode in the foreground — push, no polling, no exposed
endpoint, R4.2).

Spec: docs/specs/issue-245/design.md §D9.
"""

from __future__ import annotations

import argparse
import json
import os

from .base import Command, register
from .sessions_cmd import _cli_config
from .. import eventlog
from ..channels import inbound
from ..channels.events import SUBSCRIBABLE_EVENTS
from ..channels.slack import SlackChannelConfig, run_socket_listener, slack_state_path
from ..channels.state import ChannelState, canonical


def _presence(env_name: str) -> str:
    return "set" if os.environ.get(env_name) else "unset"


def _status(config: dict) -> int:
    from ..channels.base import ledger_name
    from ..channels.events import PUBLISHABLE_EVENTS

    slack = SlackChannelConfig.from_mapping(config)
    state = ChannelState.load(slack_state_path(config))
    print(f"ledger:         {ledger_name(config)}")
    print("slack:")
    print(f"  enabled:      {str(slack.enabled).lower()}")
    print(f"  channel:      {slack.channel or '(unset)'}")
    print(f"  subscribe:    {', '.join(slack.subscribe)}")
    print(f"  publish:      {', '.join(slack.publish) or '(nothing)'}")
    print(f"  verbosity:    {slack.verbosity}")
    print(f"  maxChars:     {slack.max_chars}")
    print(
        f"  read:         {slack.read_mode}"
        + (
            f" every {slack.read_interval_seconds:g}s"
            if slack.read_mode == "poll"
            else ""
        )
    )
    print(
        f"  buttons:      {'approve / request changes' if slack.interactive else 'link only'}"
        + (
            ""
            if slack.interactive
            else " (Approve buttons need read.mode: socket and the gate.feedback grant)"
        )
    )
    kickoff = (
        f"{slack.kickoff_repo} (labels: {', '.join(slack.kickoff_labels) or 'none'})"
        if slack.kickoff_enabled
        else "off"
        + (
            " — grant present, kickoff.repo unset"
            if "work-item.create" in slack.publish and not slack.kickoff_repo
            else ""
        )
    )
    print(f"  kickoff:      {kickoff}")
    # Identity is one list now (issue-309): say how many PEOPLE it names and how
    # many of them can speak here — never the ids themselves.
    print(
        f"  authorized:   {len(slack.authorized_users)} member id(s) among "
        f"{len(slack.principals)} routing.authorizedUsers entr"
        f"{'y' if len(slack.principals) == 1 else 'ies'}"
    )
    # Presence only, by contract (R3.1): the value never reaches stdout.
    print(f"  bot token:    {_presence(slack.bot_token_env)} ({slack.bot_token_env})")
    print(f"  app token:    {_presence(slack.app_token_env)} ({slack.app_token_env})")
    print(
        f"  conversations: {len(state.conversations)} work item(s) in "
        f"{len(state.threads)} bound thread(s), {len(state.cursors)} cursor(s) "
        "— `the-loop channels threads` lists them"
    )
    # The common event definition (PR #267 review): what CAN be subscribed,
    # with what IS — so configuring `subscribe` never means guessing names.
    print("subscribable events ([x] = in channels.slack.subscribe):")
    for name, meaning in SUBSCRIBABLE_EVENTS.items():
        tick = "x" if name in slack.subscribe else " "
        print(f"  [{tick}] {name} — {meaning}")
    for name in slack.subscribe:
        if name not in SUBSCRIBABLE_EVENTS:
            print(
                f"  [!] {name} — not in the shipped catalog; nothing shipped "
                "broadcasts it (a custom graph notify event, or a typo)"
            )
    print("publishable events ([x] = granted in channels.slack.publish):")
    for name in PUBLISHABLE_EVENTS:
        tick = "x" if name in slack.publish else " "
        print(
            f"  [{tick}] {name} — {SUBSCRIBABLE_EVENTS.get(name) or _publish_meaning(name)}"
        )
    return 0


def _threads(config: dict, work_item: str, as_json: bool) -> int:
    """Which thread carries which work item's conversation (issue-312 R3.3).

    Reads the channel state only — no Slack call, no token needed — and prints
    ids, timestamps and the permalink Slack returned; never a message's text.
    """
    state = ChannelState.load(slack_state_path(config))
    wanted = canonical(work_item) if work_item else ""
    records = [
        {"workItem": item, **record}
        for item, record in state.conversations.items()
        if not wanted or item == wanted
    ]
    if work_item and not records:
        print(f"no conversation for {work_item}")
        return 1
    if as_json:
        print(json.dumps(records, indent=2))
        return 0
    if not records:
        print("no conversations — no work item has a bound thread yet")
        return 0
    widths = {
        "workItem": max(len("work item"), *(len(r["workItem"]) for r in records)),
        "channel": max(len("channel"), *(len(r.get("channel", "")) for r in records)),
        "thread": max(len("thread"), *(len(r.get("thread", "")) for r in records)),
        "opened": max(len("opened"), *(len(r.get("opened", "")) for r in records)),
        "origin": max(len("origin"), *(len(r.get("origin", "")) for r in records)),
    }
    header = (
        f"{'work item':<{widths['workItem']}}  {'channel':<{widths['channel']}}  "
        f"{'thread':<{widths['thread']}}  {'opened':<{widths['opened']}}  "
        f"{'origin':<{widths['origin']}}  link"
    )
    print(header)
    for record in records:
        print(
            f"{record['workItem']:<{widths['workItem']}}  "
            f"{record.get('channel', ''):<{widths['channel']}}  "
            f"{record.get('thread', ''):<{widths['thread']}}  "
            f"{record.get('opened', ''):<{widths['opened']}}  "
            f"{record.get('origin', ''):<{widths['origin']}}  "
            f"{record.get('permalink') or '—'}"
        )
    return 0


def _publish_meaning(name: str) -> str:
    from ..channels.events import EVENTS

    spec = EVENTS.get(name)
    return spec.description if spec else ""


@register
class ChannelsCommand(Command):
    name = "channels"
    help = (
        "Operate the communication channels: status, one poll cycle, or the "
        "Socket Mode listener"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="channels_command", required=True)
        sub.add_parser(
            "status",
            help="Resolved channel config and conversation counts (no secrets)",
        )
        threads = sub.add_parser(
            "threads",
            help=(
                "Which Slack thread carries which work item's conversation "
                "(reads the state file; no secrets)"
            ),
        )
        threads.add_argument(
            "--work-item",
            default="",
            metavar="REF",
            help="Show one work item's conversation (exit 1 when it has none)",
        )
        threads.add_argument(
            "--json", action="store_true", help="Print the records as JSON"
        )
        sub.add_parser(
            "poll",
            help=(
                "Run one read cycle over the bound threads — and, with the "
                "work-item.create grant, the channel's top-level messages "
                "(cron-friendly)"
            ),
        )
        sub.add_parser(
            "listen",
            help="Receive replies over Slack Socket Mode in the foreground",
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("channels")
        config = _cli_config()
        if args.channels_command == "status":
            return _status(config)
        if args.channels_command == "threads":
            return _threads(config, args.work_item, args.json)
        if args.channels_command == "poll":
            summary = inbound.poll_once(config)
            if summary.get("skipped"):
                print(f"skipped: {summary['skipped']}")
                return 1
            print(
                f"{summary['replies']} message(s): {summary['processed']} "
                f"processed ({summary['delivered']} delivered), "
                f"{summary.get('created', 0)} work item(s) created, "
                f"{summary['dropped']} dropped"
            )
            return 0
        return run_socket_listener(config)
