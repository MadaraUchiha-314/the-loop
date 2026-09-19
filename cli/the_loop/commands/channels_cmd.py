"""``the-loop channels`` — operate the communication channels (issue-245).

Five actions: ``status`` (what is configured, with token *presence* only —
never values; ``--probe`` also asks Slack what the configured channel is and
which bot scopes the app holds, issue-362), ``threads`` (which Slack thread carries which work item's
conversation, issue-312 — reads the state file, calls nothing), ``poll`` (one
synchronous read cycle, for cron and daemon-less deployments, R4.1), ``listen``
(Socket Mode in the foreground — push, no polling, no exposed endpoint, R4.2;
since issue-334 also the ``/the-loop`` slash command), and ``manifest`` (the
packaged Slack app manifest an operator imports, issue-334).

Spec: docs/specs/issue-245/design.md §D9.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .base import Command, register
from .sessions_cmd import _cli_config
from .. import eventlog
from ..channels import inbound
from ..channels.events import SUBSCRIBABLE_EVENTS
from ..channels.records import RECORD_TYPES, records_from_comments, render
from ..channels.slack import (
    MENTION,
    MENTION_SHORTCUTS,
    REACTION_STATES,
    SlackChannelConfig,
    kind_summary,
    probe_subscription,
    run_socket_listener,
    slack_state_path,
    unchecked_advice,
)
from ..repos import declared_repositories
from ..channels.state import ChannelState, ChannelStores, canonical


def _presence(env_name: str) -> str:
    return "set" if os.environ.get(env_name) else "unset"


def _status(config: dict, probe: bool = False) -> int:
    from ..channels.base import ledger_name
    from ..channels.events import PUBLISHABLE_EVENTS

    slack = SlackChannelConfig.from_mapping(config)
    path = slack_state_path(config)
    stores = ChannelStores.beside(path)
    state = ChannelState.load(path, stores)
    print(f"ledger:         {ledger_name(config)}")
    print("slack:")
    print(f"  enabled:      {str(slack.enabled).lower()}")
    print(f"  channel:      {slack.channel or '(unset)'}")
    print(f"  subscribe:    {', '.join(slack.subscribe)}")
    print(f"  publish:      {', '.join(slack.publish) or '(nothing)'}")
    print(f"  verbosity:    {slack.verbosity}")
    print(f"  maxChars:     {slack.max_chars}")
    # Above the cap (issue-338): the digest, or 13.10.0's cut.
    print(
        "  longMessages: "
        + (
            "digest — above maxChars: the ask first, choices numbered, code and "
            "traces as pointers, cut at a sentence, the link for the rest"
            if slack.long_messages == "digest"
            else "truncate — above maxChars: the first maxChars characters and a "
            "note (13.10.0)"
        )
    )
    # What the read mode costs an operator who is waiting (issue-362): poll says
    # its cadence, socket says how often it RECONCILES on top of its push reads —
    # which is the ceiling on how late a missed envelope can be.
    if slack.read_mode == "poll":
        cadence = f" every {slack.read_interval_seconds:g}s"
    elif slack.read_mode == "socket":
        cadence = (
            f", reconciling every {slack.catch_up_seconds}s"
            if slack.catch_up_seconds
            else ", reconciling only at connect (read.catchUpSeconds: 0)"
        )
    else:
        cadence = ""
    print(f"  read:         {slack.read_mode}{cadence}")
    for line in _subscription_lines(slack, probe):
        print(line)
    for line in _button_lines(slack):
        print(line)
    # Where a top-level message becomes an issue (issue-341): the message's own
    # `<repo>:` prefix, resolved against the declared set, with kickoff.repo as
    # the fallback — so `status` names both, and how many a prefix may pick from.
    # And since issue-349, whether the-loop may ASK when a message names none
    # (R5.2): an operator finds that out here rather than from a member who did
    # not get a question.
    if slack.kickoff_enabled:
        declared = declared_repositories(config)
        target = slack.kickoff_repo or "(no fallback — every message must name one)"
        if not declared:
            asks = "cannot ask which repository — nothing is declared"
        elif not slack.kickoff_picker:
            asks = (
                f"cannot ask which repository — read.mode is {slack.read_mode}, so a "
                "press cannot be received; an unresolved message is refused"
            )
        else:
            asks = (
                "asks which repository when a message names none, and opens it "
                "where the member picks"
            )
        kickoff = (
            f"{target} (labels: {', '.join(slack.kickoff_labels) or 'none'}); "
            f"a `<repo>:` prefix may name any of {len(declared)} declared "
            f"repositories; {asks}"
        )
    else:
        kickoff = "off" + (
            " — channels.slack.publish does not grant work-item.create"
            if slack.enabled and slack.channel
            else ""
        )
    print(f"  kickoff:      {kickoff}")
    # The slash command (issue-334): which verb families this channel may run,
    # or why none can arrive at all.
    from ..channels.commands import FAMILY_GRANTS

    if slack.read_mode == "socket":
        families = " · ".join(
            f"{family}: {'granted' if grant in slack.publish else 'not granted'}"
            for family, grant in FAMILY_GRANTS.items()
        )
        print(f"  commands:     /the-loop over Socket Mode — {families}")
    else:
        print(
            f"  commands:     off (read.mode is {slack.read_mode} — slash commands "
            "need read.mode: socket)"
        )
    # The address (issue-389): a mention is the one way a message in a room
    # reaches the-loop, and it arrives only over Socket Mode — so `status`
    # says what a mention needs, what the two shortcuts need, and how many
    # declared rooms hear every message instead.
    for line in _mention_lines(slack, stores):
        print(line)
    reactions = slack.reactions
    print(
        "  reactions:    "
        + (
            " / ".join(
                f"{state}={reactions.content_for(state) or '(skipped)'}"
                for state in REACTION_STATES
            )
            + " (on the accepted message; needs reactions:write)"
            if reactions.enabled
            else "off"
        )
    )
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


def _subscription_lines(slack: SlackChannelConfig, probe: bool) -> list:
    """What kind of conversation the channel is, and whether the app can hear it
    (issue-362 R2). Slack emits a different message event per conversation kind
    and delivers only what the app subscribed to, so a channel configured with a
    kind the app is not subscribed to reads as healthy while nothing typed in it
    arrives — the defect issue-362 reported.

    The first line costs **nothing**: the id's own prefix says the kind, which
    keeps `status`'s contract that it reads the state file and calls nothing.
    `--probe` adds the measured answer from `conversations.info` + `auth.test`.
    """
    if not slack.channel:
        return []
    lines = [f"  channel kind: {kind_summary(slack.channel)}"]
    if not probe:
        lines += [f"  [!] {advice}" for advice in unchecked_advice(slack.channel)]
        return lines
    result = probe_subscription(slack)
    if result.get("skipped"):
        return lines + [f"  probe:        not probed — {result['skipped']}"]
    kind = result["kind"]
    scopes = result["scopes"]
    lines.append(
        f"  probe:        conversations.info says {kind}; granted bot scopes: "
        + (", ".join(scopes) if scopes else "(the response carried no x-oauth-scopes)")
    )
    # The probe's own findings: the kind's absence first, then the mention's
    # (issue-389 R1.8) — composed in `probe_subscription`, printed here verbatim.
    lines += [f"  [!] {finding}" for finding in result.get("findings") or ()]
    return lines


def _mention_lines(slack: SlackChannelConfig, stores: ChannelStores) -> list:
    """The three issue-389 lines: `mentions:`, `shortcuts:` and `rooms:`.

    Read from the config and the portable declarations only — no Slack call;
    `--probe` is what measures the scope (`mention_findings`).
    """
    if slack.read_mode == "socket":
        mentions = (
            f"@the-loop is the address in every channel — {MENTION.event} over "
            f"Socket Mode; needs the bot scope {MENTION.scope} (`--probe` "
            "measures it). A DM with the bot and a room declared --listen all "
            "also hear plain messages"
        )
        shortcuts = (
            "Add as the-loop context / Record the-loop decision "
            f"({', '.join(MENTION_SHORTCUTS)}) over Socket Mode — each exactly "
            "the typed mention"
        )
    else:
        mentions = (
            f"off (read.mode is {slack.read_mode} — nothing addressed can "
            f"arrive; {MENTION.event} needs read.mode: socket)"
        )
        shortcuts = (
            f"off (read.mode is {slack.read_mode} — a message shortcut needs "
            "read.mode: socket)"
        )
    targets = stores.declared_targets()
    hearing_all = sum(1 for target in targets if stores.listen_mode(target) == "all")
    rooms = (
        f"{len(targets)} declared room(s); {hearing_all} hear(s) every message "
        "(--listen all), the rest mentions only"
    )
    return [
        f"  mentions:     {mentions}",
        f"  shortcuts:    {shortcuts}",
        f"  rooms:        {rooms}",
    ]


def _button_lines(slack: SlackChannelConfig) -> list:
    """The ``buttons:`` block (issue-337 R3): both button sets with whether each
    can be received, and — while either cannot — only the numbered steps that
    still apply. The app-level token is genuinely required: Slack delivers a
    press to an acknowledging Socket Mode connection or a public Request URL,
    and the-loop exposes none (decision-116 D5, decision-117 D3). Token
    presence only, never a value."""
    approve = slack.interactive
    commands = slack.command_buttons
    head = (
        f"  buttons:      Approve / Request changes: {'on' if approve else 'off'}"
        f" · Execute / Start: {'on' if commands else 'off'}"
    )
    app_token = _presence(slack.app_token_env)
    steps: list = []
    if app_token != "set":
        steps.append(
            "mint an app-level token: api.slack.com/apps → your app → Basic "
            "Information → App-Level Tokens → Generate (scope connections:write), "
            f"and export it as {slack.app_token_env} (now: {app_token})"
        )
    if slack.read_mode != "socket":
        steps.append(f"set channels.slack.read.mode: socket (now: {slack.read_mode})")
    missing = [
        f"{grant} ({label})"
        for grant, label in (
            ("gate.feedback", "Approve / Request changes"),
            ("control.command", "Execute / Start"),
        )
        if grant not in slack.publish
    ]
    if missing:
        steps.append("add to channels.slack.publish: " + ", ".join(missing))
    if not steps:
        return [head]
    steps.append(
        "the-loop restart — the service hosts the listener; `the-loop status` "
        "shows the slack-listener row, and this line reads on"
    )
    lines = [
        head + " — a press reaches the-loop only over a Socket Mode listener connected "
        "with the app-level token. Still needed:"
    ]
    lines += [f"                  {n}. {step}" for n, step in enumerate(steps, 1)]
    return lines


def _threads(config: dict, work_item: str, as_json: bool) -> int:
    """Which thread carries which work item's conversation (issue-312 R3.3).

    Reads the channel state only — no Slack call, no token needed — and prints
    ids, timestamps and the permalink Slack returned; never a message's text.
    """
    path = slack_state_path(config)
    stores = ChannelStores.beside(path)
    state = ChannelState.load(path, stores)
    wanted = canonical(work_item) if work_item else ""
    records = [
        {"workItem": item, **record, "listen": _listen_of(record, stores)}
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
    # A room conversation (issue-378) has no thread: the column says so.
    widths["thread"] = max(widths["thread"], len("(channel)"))
    widths["listen"] = max(len("listen"), *(len(r["listen"]) for r in records))
    header = (
        f"{'work item':<{widths['workItem']}}  {'channel':<{widths['channel']}}  "
        f"{'thread':<{widths['thread']}}  {'opened':<{widths['opened']}}  "
        f"{'origin':<{widths['origin']}}  {'listen':<{widths['listen']}}  link"
    )
    print(header)
    for record in records:
        print(
            f"{record['workItem']:<{widths['workItem']}}  "
            f"{record.get('channel', ''):<{widths['channel']}}  "
            f"{record.get('thread') or '(channel)':<{widths['thread']}}  "
            f"{record.get('opened', ''):<{widths['opened']}}  "
            f"{record.get('origin', ''):<{widths['origin']}}  "
            f"{record['listen']:<{widths['listen']}}  "
            f"{record.get('permalink') or '—'}"
        )
    return 0


def _listen_of(record: dict, stores: ChannelStores) -> str:
    """What the conversation hears (issue-389 R2.4): every message in a DM
    with the bot or a room declared `--listen all`; otherwise mentions."""
    channel = str(record.get("channel") or "")
    if channel[:1].upper() == "D":
        return "all"
    return stores.listen_mode(channel) if channel else "mentions"


def _ledger_comments(config: dict, work_item: str) -> tuple:
    """The ticket's comments as ``records_from_comments`` reads them — one
    ``gh`` listing through the poller's read-only client, tried as an issue
    and, when the ledger says the number is a pull request, as one."""
    from ..channels.github import gh_binary
    from ..poller.github import GhClient, GhError
    from ..sessions import WorkItemRef

    ref = WorkItemRef.parse(work_item)
    gh = GhClient(binary=gh_binary(config))
    login = gh.viewer_login(ref.host)
    try:
        comments = gh.list_comments(
            ref.owner, ref.repo, ref.number, is_pr=False, host=ref.host
        )
    except GhError as first:
        # `gh issue view` rejects a pull request's number; the ref does not
        # say which it is, so the PR read is the second try, and the first
        # error is the one reported when both fail.
        try:
            comments = gh.list_comments(
                ref.owner, ref.repo, ref.number, is_pr=True, host=ref.host
            )
        except GhError:
            raise first from None
    return login, [
        {
            "id": c.id,
            "body": c.body,
            "author": c.author,
            "created_at": c.created_at,
            "url": c.url,
        }
        for c in comments
    ]


def _records(config: dict, work_item: str, types: list, fmt: str) -> int:
    """A work item's channel records (issue-389 R4.7, R5.6): every marked,
    enveloped ``context.added`` / ``decision.recorded`` comment the ledger
    credential itself posted on its ticket, as JSON rows or as markdown.
    Read-only; exit 1 when the ledger cannot be read or the ref is not one."""
    from ..poller.github import GhError

    try:
        login, comments = _ledger_comments(config, work_item)
    except (ValueError, GhError) as exc:
        print(f"could not read the records of {work_item}: {exc}", file=sys.stderr)
        return 1
    if not login:
        print(
            "warning: could not read the gh login, so the records are listed by "
            "their marker alone — check each row's author before trusting it",
            file=sys.stderr,
        )
    records = records_from_comments(comments, types or None, login or None)
    if fmt == "json":
        print(json.dumps([r.to_dict() for r in records], indent=2))
        return 0
    print(render(records, canonical(work_item)), end="")
    return 0


def _publish_meaning(name: str) -> str:
    from ..channels.events import EVENTS

    spec = EVENTS.get(name)
    return spec.description if spec else ""


@register
class ChannelsCommand(Command):
    name = "channels"
    help = (
        "Operate the communication channels: status, one poll cycle, the "
        "Socket Mode listener, or the Slack app manifest"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="channels_command", required=True)
        status = sub.add_parser(
            "status",
            help="Resolved channel config and conversation counts (no secrets)",
        )
        status.add_argument(
            "--probe",
            action="store_true",
            help=(
                "Ask Slack what the configured channel is and which bot scopes "
                "the app was granted, and report what it cannot receive "
                "(conversations.info + auth.test; never prints a token)"
            ),
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
        records = sub.add_parser(
            "records",
            help=(
                "The context and decision records a channel wrote on a work "
                "item's ticket (one gh read; no Slack call, no secrets)"
            ),
        )
        records.add_argument("work_item", metavar="REF", help="The work item ref")
        records.add_argument(
            "--type",
            action="append",
            choices=list(RECORD_TYPES),
            default=[],
            help="Only records of this type (repeatable; default: both)",
        )
        records.add_argument(
            "--format",
            choices=["json", "markdown"],
            default="markdown",
            help="JSON rows, or markdown with the text quoted back (default)",
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
            help=(
                "Receive replies, button presses and /the-loop commands over "
                "Slack Socket Mode in the foreground"
            ),
        )
        sub.add_parser(
            "manifest",
            help=(
                "Print the Slack app manifest to import (scopes, events, Socket "
                "Mode, the /the-loop command)"
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("channels")
        config = _cli_config()
        if args.channels_command == "status":
            return _status(config, probe=args.probe)
        if args.channels_command == "threads":
            return _threads(config, args.work_item, args.json)
        if args.channels_command == "records":
            return _records(config, args.work_item, args.type, args.format)
        if args.channels_command == "manifest":
            from ..channels.commands import manifest_text

            print(manifest_text(), end="")
            return 0
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
        return _listen(config)


def _listen(config: dict) -> int:
    """The foreground listener, under the same single-instance lock the service
    holds when it hosts one (issue-334): two listeners for one instance would
    each see half of Slack's envelopes."""
    from ..core import daemons as core_daemons
    from ..runlock import RunLock

    lock = RunLock(
        core_daemons._pidfile(core_daemons.SLACK_LISTENER, config),
        name=core_daemons.SLACK_LISTENER,
    )
    try:
        if not lock.acquire():
            holder = lock.holder() or "unknown"
            print(
                f"error: a slack listener is already running (pid {holder}) — "
                "the service hosts one when service.hostIngresses is on; stop it "
                "with `the-loop stop` to run the listener in the foreground",
                file=sys.stderr,
            )
            return 1
    except OSError as exc:
        print(f"error: cannot use the listener lockfile: {exc}", file=sys.stderr)
        return 1
    try:
        return run_socket_listener(config)
    finally:
        lock.release()
