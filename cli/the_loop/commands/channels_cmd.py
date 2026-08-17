"""``the-loop channels`` — operate the communication channels (issue-245).

Three actions, one per read posture: ``status`` (what is configured, with
token *presence* only — never values), ``poll`` (one synchronous read cycle,
for cron and daemon-less deployments, R4.1), and ``listen`` (Socket Mode in
the foreground — push, no polling, no exposed endpoint, R4.2).

Spec: docs/specs/issue-245/design.md §D9.
"""

from __future__ import annotations

import argparse
import os

from .base import Command, register
from .sessions_cmd import _cli_config
from .. import eventlog
from ..channels import inbound
from ..channels.slack import SlackChannelConfig, run_socket_listener, slack_state_path
from ..channels.state import ChannelState


def _presence(env_name: str) -> str:
    return "set" if os.environ.get(env_name) else "unset"


def _status(config: dict) -> int:
    slack = SlackChannelConfig.from_mapping(config)
    state = ChannelState.load(slack_state_path(config))
    print("slack:")
    print(f"  enabled:      {str(slack.enabled).lower()}")
    print(f"  channel:      {slack.channel or '(unset)'}")
    print(f"  events:       {', '.join(slack.events)}")
    print(f"  verbosity:    {slack.verbosity}")
    print(
        f"  read:         {slack.read_mode}"
        + (
            f" every {slack.read_interval_seconds:g}s"
            if slack.read_mode == "poll"
            else ""
        )
    )
    print(f"  authorized:   {len(slack.authorized_users)} member id(s)")
    # Presence only, by contract (R3.1): the value never reaches stdout.
    print(f"  bot token:    {_presence(slack.bot_token_env)} ({slack.bot_token_env})")
    print(f"  app token:    {_presence(slack.app_token_env)} ({slack.app_token_env})")
    print(
        f"  conversations: {len(state.threads)} bound thread(s), "
        f"{len(state.cursors)} cursor(s)"
    )
    return 0


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
        sub.add_parser(
            "poll",
            help="Run one read cycle over the bound threads (cron-friendly)",
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
        if args.channels_command == "poll":
            summary = inbound.poll_once(config)
            if summary.get("skipped"):
                print(f"skipped: {summary['skipped']}")
                return 1
            print(
                f"{summary['replies']} repl(ies): {summary['processed']} "
                f"processed ({summary['delivered']} delivered), "
                f"{summary['dropped']} dropped"
            )
            return 0
        return run_socket_listener(config)
