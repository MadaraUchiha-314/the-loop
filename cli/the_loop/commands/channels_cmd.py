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
from typing import Mapping, Optional

from .base import Command, register
from .sessions_cmd import _cli_config
from .. import eventlog, strings
from ..channels import inbound
from ..channels.events import SUBSCRIBABLE_EVENTS
from ..channels.records import RECORD_TYPES, records_from_comments, render
from ..channels.slack import (
    EVENTS_UNVERIFIABLE_CAVEAT,
    MENTION,
    MENTION_SHORTCUTS,
    REACTION_STATES,
    SlackChannelConfig,
    expected_bot_events,
    kind_summary,
    probe_subscription,
    run_socket_listener,
    slack_state_path,
    unchecked_advice,
)
from ..cli_config import gateway_block
from ..repos import declared_repositories
from ..channels.state import ChannelState, ChannelStores, canonical


def _presence(env_name: str) -> str:
    return (
        strings.t("cli.channels.presence.set")
        if os.environ.get(env_name)
        else strings.t("cli.channels.presence.unset")
    )


def _transport(slack: SlackChannelConfig) -> str:
    """How an interactive payload reaches this instance (issue-503)."""
    return (
        strings.t("cli.channels.transport.gateway")
        if slack.read_mode == "gateway"
        else strings.t("cli.channels.transport.socket")
    )


def _read_mode_findings(config: dict) -> list:
    """The two issue-503 misconfigurations, read off the raw config: a ``gateway`` mode
    the parse switched off for want of a block (R3.2), and 20.3.0's ``socket`` beside a
    block (R4.2)."""
    from ..core.lifecycle import GATEWAY_MISSING, socket_beside_gateway

    raw = ((config.get("channels") or {}).get("slack") or {}).get("read") or {}
    mode = raw.get("mode") if isinstance(raw, dict) else None
    if mode == "gateway" and gateway_block(config) is None:
        return ["  [!] " + GATEWAY_MISSING.removeprefix("off · ")]
    if socket_beside_gateway(config):
        return [strings.t("cli.channels.status.socket-beside-gateway")]
    return []


def _posting_lines(slack: SlackChannelConfig, config: dict) -> list:
    """Where this instance's Slack posts go (issue-519, R1.2, R1.4): its own token,
    the gateway, or nowhere — the last a `[!]` finding naming the variable.

    The one line of `channels status` that asks something: with a gateway block it
    reads the gateway client's document from the local control-plane service (never
    Slack), because "no posting path" needs the gateway's own answer. With the service
    down it says the answer is not yet known rather than guessing (self-review 1)."""
    if not slack.enabled:
        return []
    from ..channels.slack import posting_path
    from ..core import lifecycle as core_lifecycle

    reported = None
    if gateway_block(config) is not None:
        doc = core_lifecycle.gateway_document(config)
        reported = doc.get("slackPosting") if isinstance(doc, dict) else None
    path = posting_path(
        slack, config, gateway_posting=str(reported) if reported else None
    )
    if path.kind == "local":
        return [strings.t("cli.channels.status.posting.local", detail=path.detail)]
    if path.kind == "gateway":
        how = (
            "" if reported == "on" else strings.t("cli.channels.status.posting.unknown")
        )
        return [
            strings.t(
                "cli.channels.status.posting.gateway", detail=path.detail, how=how
            )
        ]
    return [
        strings.t("cli.channels.status.posting.unavailable", detail=path.detail),
        strings.t(
            "cli.channels.status.posting.needs-token",
            env=slack.bot_token_env,
            detail=path.detail,
        ),
    ]


def _status(config: dict, probe: bool = False) -> int:
    from ..channels.base import ledger_name
    from ..channels.events import PUBLISHABLE_EVENTS

    slack = SlackChannelConfig.from_mapping(config)
    path = slack_state_path(config)
    stores = ChannelStores.beside(path)
    state = ChannelState.load(path, stores)
    print(strings.t("cli.channels.status.ledger", ledger=ledger_name(config)))
    print(strings.t("cli.channels.status.slack"))
    print(strings.t("cli.channels.status.enabled", enabled=str(slack.enabled).lower()))
    print(
        strings.t(
            "cli.channels.status.channel",
            channel=slack.channel or strings.t("cli.channels.status.unset"),
        )
    )
    print(strings.t("cli.channels.status.subscribe", events=", ".join(slack.subscribe)))
    # A list written before the stall notice existed hears questions and not
    # stalls, and nothing else would say so.
    if "session.awaiting_input" in slack.subscribe and (
        "session.stalled" not in slack.subscribe
    ):
        print(strings.t("cli.channels.status.subscribe.no-stall"))
    print(
        strings.t(
            "cli.channels.status.publish",
            grants=", ".join(slack.publish) or strings.t("cli.channels.status.nothing"),
        )
    )
    print(strings.t("cli.channels.status.verbosity", verbosity=slack.verbosity))
    # What the read mode costs an operator who is waiting (issue-362): poll says
    # its cadence, socket says how often it RECONCILES on top of its push reads —
    # which is the ceiling on how late a missed envelope can be.
    if slack.read_mode == "poll":
        cadence = strings.t(
            "cli.channels.status.cadence.poll", seconds=slack.read_interval_seconds
        )
    elif slack.read_mode == "socket":
        cadence = (
            strings.t(
                "cli.channels.status.cadence.reconciling",
                seconds=slack.catch_up_seconds,
            )
            if slack.catch_up_seconds
            else strings.t("cli.channels.status.cadence.connect-only")
        )
    elif slack.read_mode == "gateway":
        block = gateway_block(config)
        cadence = strings.t(
            "cli.channels.status.cadence.gateway", url=block.url if block else "?"
        )
    else:
        cadence = ""
    print(strings.t("cli.channels.status.read", mode=slack.read_mode, cadence=cadence))
    for line in _read_mode_findings(config):
        print(line)
    for line in _posting_lines(slack, config):
        print(line)
    for line in _split_check_lines(slack, config):
        print(line)
    for line in _subscription_lines(slack, probe, config):
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
        target = slack.kickoff_repo or strings.t(
            "cli.channels.status.kickoff.no-fallback"
        )
        if not declared:
            asks = strings.t("cli.channels.status.kickoff.nothing-declared")
        elif not slack.kickoff_picker:
            asks = strings.t(
                "cli.channels.status.kickoff.no-picker", mode=slack.read_mode
            )
        else:
            asks = strings.t("cli.channels.status.kickoff.asks")
        kickoff = strings.t(
            "cli.channels.status.kickoff.on",
            target=target,
            labels=", ".join(slack.kickoff_labels)
            or strings.t("cli.channels.status.kickoff.no-labels"),
            count=len(declared),
            asks=asks,
        )
    else:
        kickoff = strings.t("cli.channels.status.kickoff.off") + (
            strings.t("cli.channels.status.kickoff.no-grant")
            if slack.enabled and slack.channel
            else ""
        )
    print(strings.t("cli.channels.status.kickoff", kickoff=kickoff))
    # The slash command (issue-334): which verb families this channel may run,
    # or why none can arrive at all.
    from ..channels.commands import FAMILY_GRANTS

    if slack.push_reachable:
        granted = strings.t("cli.channels.status.granted")
        not_granted = strings.t("cli.channels.status.not-granted")
        families = " · ".join(
            f"{family}: {granted if grant in slack.publish else not_granted}"
            for family, grant in FAMILY_GRANTS.items()
        )
        print(
            strings.t(
                "cli.channels.status.commands",
                transport=_transport(slack),
                families=families,
            )
        )
    else:
        print(strings.t("cli.channels.status.commands-off", mode=slack.read_mode))
    # The address (issue-389): a mention is the one way a message in a room
    # reaches the-loop, and it arrives only over Socket Mode — so `status`
    # says what a mention needs, what the two shortcuts need, and how many
    # declared rooms hear every message instead.
    for line in _mention_lines(slack, stores):
        print(line)
    reactions = slack.reactions
    skipped = strings.t("cli.channels.status.reactions.skipped")
    print(
        strings.t("cli.channels.status.reactions")
        + (
            " / ".join(
                f"{state}={reactions.content_for(state) or skipped}"
                for state in REACTION_STATES
            )
            + strings.t("cli.channels.status.reactions.needs")
            if reactions.enabled
            else strings.t("cli.channels.status.off")
        )
    )
    # Identity is one list now (issue-309): say how many PEOPLE it names and how
    # many of them can speak here — never the ids themselves.
    print(
        strings.t(
            "cli.channels.status.authorized-one",
            members=len(slack.authorized_users),
            principals=len(slack.principals),
        )
        if len(slack.principals) == 1
        else strings.t(
            "cli.channels.status.authorized-many",
            members=len(slack.authorized_users),
            principals=len(slack.principals),
        )
    )
    # Presence only, by contract (R3.1): the value never reaches stdout.
    print(
        strings.t(
            "cli.channels.status.bot-token",
            presence=_presence(slack.bot_token_env),
            env=slack.bot_token_env,
        )
    )
    print(
        strings.t(
            "cli.channels.status.app-token",
            presence=_presence(slack.app_token_env),
            env=slack.app_token_env,
        )
    )
    print(
        strings.t(
            "cli.channels.status.conversations",
            items=len(state.conversations),
            threads=len(state.threads),
            cursors=len(state.cursors),
        )
    )
    for line in _jira_lines(config):
        print(line)
    # The common event definition (PR #267 review): what CAN be subscribed,
    # with what IS — so configuring `subscribe` never means guessing names.
    print(strings.t("cli.channels.status.subscribable"))
    for name, meaning in SUBSCRIBABLE_EVENTS.items():
        tick = "x" if name in slack.subscribe else " "
        print(f"  [{tick}] {name} — {meaning}")
    for name in slack.subscribe:
        if name not in SUBSCRIBABLE_EVENTS:
            print(strings.t("cli.channels.status.unknown-event", name=name))
    print(strings.t("cli.channels.status.publishable"))
    for name in PUBLISHABLE_EVENTS:
        tick = "x" if name in slack.publish else " "
        print(
            f"  [{tick}] {name} — {SUBSCRIBABLE_EVENTS.get(name) or _publish_meaning(name)}"
        )
    return 0


def _jira_lines(config: dict) -> list:
    """The Jira block (issue-475): the integration, its projects, the ledger and
    the mirror channel. Presence only for the credentials and the webhook
    secret — a variable's name, never its value — and no API call."""
    from ..channels.jira import JiraChannelConfig, origin_projects
    from ..jiraapi import JiraApiConfig
    from ..sessions.refs import jira_section

    api = JiraApiConfig.from_cli_config(config)
    lines = [strings.t("cli.channels.jira.head")]
    if not api.configured:
        lines.append(strings.t("cli.channels.jira.not-configured"))
        return lines
    lines.append(
        strings.t(
            "cli.channels.jira.integration", site=api.site, deployment=api.deployment
        )
    )
    origins = origin_projects(config)
    projects = [
        f"{key} → {origins[key]}"
        if key in origins
        else strings.t("cli.channels.jira.mirror-only", key=key)
        for key in api.projects
    ]
    lines.append(
        strings.t(
            "cli.channels.jira.projects",
            projects=", ".join(projects) or strings.t("cli.channels.jira.none"),
        )
    )
    names = [name for _, group in api._required() for name in group]  # noqa: SLF001
    missing = api.missing_credentials()
    lines.append(
        strings.t("cli.channels.jira.credentials")
        + (
            strings.t("cli.channels.jira.credentials.set")
            if not missing
            else strings.t(
                "cli.channels.jira.credentials.unset",
                missing=strings.t("cli.channels.jira.credentials.and").join(missing),
            )
        )
        + (f" ({', '.join(names)})" if names else "")
    )
    webhook = jira_section(config).get("webhook")
    secret_env = (
        str(webhook.get("secretEnv") or "") if isinstance(webhook, Mapping) else ""
    )
    lines.append(
        strings.t("cli.channels.jira.webhook")
        + (
            strings.t(
                "cli.channels.jira.webhook.on",
                presence=_presence(secret_env),
                env=secret_env,
            )
            if secret_env
            else strings.t("cli.channels.jira.webhook.off")
        )
    )
    lines.append(strings.t("cli.channels.jira.ledger"))
    channel = JiraChannelConfig.from_mapping(config)
    lines.append(
        strings.t("cli.channels.jira.channel")
        + (
            strings.t(
                "cli.channels.jira.channel.on",
                events=", ".join(channel.subscribe),
                verbosity=channel.verbosity,
            )
            if channel.enabled
            else strings.t("cli.channels.jira.channel.off")
        )
    )
    return lines


def _split_check_lines(slack: SlackChannelConfig, config: dict) -> list:
    """What the listener's own split check has measured (issue-413).

    Reads the state file and calls nothing, so `channels status` keeps its
    contract that the un-probed form makes no API call. Only socket mode has a
    listener to run the check, so poll mode says so once and stops.
    """
    from ..channels import splitwatch

    if slack.read_mode != "socket":
        return []
    state = splitwatch.read_state(splitwatch.split_state_path(config))
    lines = [
        strings.t(
            "cli.channels.status.split-check",
            line=splitwatch.cadence_line(state, slack),
        )
    ]
    lines += [f"  [!] {line}" for line in splitwatch.split_lines(state)]
    return lines


def _subscription_lines(
    slack: SlackChannelConfig, probe: bool, cli_config: Optional[dict] = None
) -> list:
    """What kind of conversation the channel is, and whether the app can hear it
    (issue-362 R2). Slack emits a different message event per conversation kind
    and delivers only what the app subscribed to, so a channel configured with a
    kind the app is not subscribed to reads as healthy while nothing typed in it
    arrives — the defect issue-362 reported.

    The first line costs **nothing**: the id's own prefix says the kind, which
    keeps `status`'s contract that it reads the state file and calls nothing.
    `--probe` adds the measured answer from `conversations.info` + `auth.test`
    — and, beside it, the events the manifest is expected to carry with the
    fixed caveat that no API call can confirm them (issue-393 R2.1).
    """
    if not slack.channel:
        return []
    lines = [
        strings.t("cli.channels.status.channel-kind", kind=kind_summary(slack.channel))
    ]
    if not probe:
        lines += [f"  [!] {advice}" for advice in unchecked_advice(slack.channel)]
        return lines
    result = probe_subscription(slack, cli_config=cli_config)
    if result.get("skipped"):
        # The manifest is local, so the expected events are printable even when
        # Slack could not be asked — labelled unverifiable either way.
        return lines + [
            strings.t("cli.channels.status.not-probed", reason=result["skipped"]),
            events_line(expected_bot_events()),
        ]
    kind = result["kind"]
    scopes = result["scopes"]
    lines.append(
        strings.t("cli.channels.status.probe", kind=kind)
        + (
            ", ".join(scopes)
            if scopes
            else strings.t("cli.channels.status.probe.no-scopes")
        )
    )
    lines.append(events_line(result.get("events") or ()))
    # The probe's own findings: the kind's absence first, then the mention's
    # (issue-389 R1.8) — composed in `probe_subscription`, printed here verbatim.
    lines += [f"  [!] {finding}" for finding in result.get("findings") or ()]
    return lines


def events_line(events) -> str:
    """The `events:` line (issue-393 R2.1): what the manifest subscribes the bot
    to, and the one caveat — the same sentence in `channels status --probe` and
    `doctor slack`, so an operator reads it once and recognises it."""
    named = (
        ", ".join(events)
        if events
        else strings.t("cli.channels.status.events.unreadable")
    )
    return strings.t(
        "cli.channels.status.events", named=named, caveat=EVENTS_UNVERIFIABLE_CAVEAT
    )


def _mention_lines(slack: SlackChannelConfig, stores: ChannelStores) -> list:
    """The three issue-389 lines: `mentions:`, `shortcuts:` and `rooms:`.

    Read from the config and the portable declarations only — no Slack call;
    `--probe` is what measures the scope (`mention_findings`).
    """
    if slack.push_reachable:
        mentions = strings.t(
            "cli.channels.status.mentions.on",
            event=MENTION.event,
            transport=_transport(slack),
            scope=MENTION.scope,
        )
        shortcuts = strings.t(
            "cli.channels.status.shortcuts.on",
            shortcuts=", ".join(MENTION_SHORTCUTS),
            transport=_transport(slack),
        )
    else:
        mentions = strings.t(
            "cli.channels.status.mentions.off",
            mode=slack.read_mode,
            event=MENTION.event,
        )
        shortcuts = strings.t("cli.channels.status.shortcuts.off", mode=slack.read_mode)
    targets = stores.declared_targets()
    hearing_all = sum(1 for target in targets if stores.listen_mode(target) == "all")
    rooms = strings.t(
        "cli.channels.status.rooms.value", rooms=len(targets), hearing=hearing_all
    )
    return [
        strings.t("cli.channels.status.mentions", mentions=mentions),
        strings.t("cli.channels.status.shortcuts", shortcuts=shortcuts),
        strings.t("cli.channels.status.rooms", rooms=rooms),
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
    on, off = (
        strings.t("cli.channels.buttons.on"),
        strings.t("cli.channels.buttons.off"),
    )
    head = strings.t(
        "cli.channels.buttons.head",
        approve=on if approve else off,
        commands=on if commands else off,
    )
    app_token = _presence(slack.app_token_env)
    steps: list = []
    # Behind a gateway the app-level token is the gateway's (issue-503): this
    # instance opens no connection, so it neither needs the token nor `socket`.
    if app_token != "set" and not slack.gateway:
        steps.append(
            strings.t(
                "cli.channels.buttons.mint-token",
                env=slack.app_token_env,
                presence=app_token,
            )
        )
    if not slack.push_reachable:
        wanted = "gateway" if slack.gateway else "socket"
        steps.append(
            strings.t(
                "cli.channels.buttons.set-read-mode",
                wanted=wanted,
                mode=slack.read_mode,
            )
        )
    missing = [
        f"{grant} ({label})"
        for grant, label in (
            ("gate.feedback", strings.t("cli.channels.buttons.label.approve")),
            ("control.command", strings.t("cli.channels.buttons.label.commands")),
        )
        if grant not in slack.publish
    ]
    if missing:
        steps.append(strings.t("cli.channels.buttons.add-grants") + ", ".join(missing))
    if not steps:
        return [head]
    steps.append(strings.t("cli.channels.buttons.restart"))
    lines = [
        head
        + (
            strings.t("cli.channels.buttons.via-gateway")
            if slack.gateway
            else strings.t("cli.channels.buttons.via-socket")
        )
        + strings.t("cli.channels.buttons.still-needed")
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
        print(strings.t("cli.channels.threads.none-for", work_item=work_item))
        return 1
    if as_json:
        print(json.dumps(records, indent=2))
        return 0
    if not records:
        print(strings.t("cli.channels.threads.none"))
        return 0
    title = {
        "workItem": strings.t("cli.channels.threads.column.work-item"),
        "channel": strings.t("cli.channels.threads.column.channel"),
        "thread": strings.t("cli.channels.threads.column.thread"),
        "opened": strings.t("cli.channels.threads.column.opened"),
        "origin": strings.t("cli.channels.threads.column.origin"),
        "listen": strings.t("cli.channels.threads.column.listen"),
    }
    room = strings.t("cli.channels.threads.room")
    widths = {
        "workItem": max(len(title["workItem"]), *(len(r["workItem"]) for r in records)),
        "channel": max(
            len(title["channel"]), *(len(r.get("channel", "")) for r in records)
        ),
        "thread": max(
            len(title["thread"]), *(len(r.get("thread", "")) for r in records)
        ),
        "opened": max(
            len(title["opened"]), *(len(r.get("opened", "")) for r in records)
        ),
        "origin": max(
            len(title["origin"]), *(len(r.get("origin", "")) for r in records)
        ),
    }
    # A room conversation (issue-378) has no thread: the column says so.
    widths["thread"] = max(widths["thread"], len(room))
    widths["listen"] = max(len(title["listen"]), *(len(r["listen"]) for r in records))
    header = "  ".join(
        [f"{title[column]:<{widths[column]}}" for column in title]
        + [strings.t("cli.channels.threads.column.link")]
    )
    print(header)
    for record in records:
        print(
            f"{record['workItem']:<{widths['workItem']}}  "
            f"{record.get('channel', ''):<{widths['channel']}}  "
            f"{record.get('thread') or room:<{widths['thread']}}  "
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
    conversation read through the daemon's GitHub client, which answers for an
    issue and a pull request alike (issue-442)."""
    from ..channels.github import github_api
    from ..ghapi import GitHubClient
    from ..sessions import WorkItemRef

    ref = WorkItemRef.parse(work_item)
    gh = GitHubClient.shared(github_api(config))
    login = gh.viewer_login(ref.host)
    comments = gh.list_issue_comments(ref.owner, ref.repo, ref.number, host=ref.host)
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
    from ..ghapi import GitHubApiError

    try:
        login, comments = _ledger_comments(config, work_item)
    except (ValueError, GitHubApiError) as exc:
        print(
            strings.t(
                "cli.channels.records.unreadable", work_item=work_item, error=exc
            ),
            file=sys.stderr,
        )
        return 1
    if not login:
        print(strings.t("cli.channels.records.no-login"), file=sys.stderr)
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


def _manifest(args: argparse.Namespace) -> int:
    """`channels manifest`: the packaged file, renamed, linked or kept (issue-464)."""
    from pathlib import Path

    from ..channels import app_manifest
    from ..channels.commands import manifest_text

    try:
        if args.write is not None:
            path = Path(args.write) if args.write else app_manifest.default_path()
            return _manifest_report(app_manifest.write(path, args.name))
        if args.name is None and not args.link and args.format == "yaml":
            print(manifest_text(), end="")
            return 0
        manifest = app_manifest.build(args.name)
    except ValueError as exc:
        print(strings.t("cli.channels.manifest.error", error=exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(strings.t("cli.channels.manifest.error", error=exc), file=sys.stderr)
        return 1
    if args.link:
        print(app_manifest.link(manifest))
    elif args.format == "json":
        print(app_manifest.render_json(manifest), end="")
    else:
        import yaml

        print(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), end="")
    return 0


def _manifest_report(result: dict) -> int:
    """What `--write` did, what Slack needs from the operator, and the link (R3.5)."""
    path, name, status = result["path"], result["name"], result["status"]
    if status == "unchanged":
        print(
            strings.t(
                "cli.channels.manifest.unchanged", path=path, name=json.dumps(name)
            )
        )
    else:
        print(
            strings.t("cli.channels.manifest.wrote", path=path, name=json.dumps(name))
        )
    if status == "updated":
        for label, key in (
            (strings.t("cli.channels.manifest.bot-scopes"), "scopes"),
            (strings.t("cli.channels.manifest.bot-events"), "events"),
        ):
            change = [f"+ {item}" for item in result[key]["added"]]
            change += [f"- {item}" for item in result[key]["removed"]]
            print(
                strings.t(
                    "cli.channels.manifest.change",
                    label=label,
                    change=", ".join(change)
                    if change
                    else strings.t("cli.channels.manifest.no-change"),
                )
            )
        scopes = result["scopes"]
        reinstall = (
            strings.t("cli.channels.manifest.reinstall")
            if scopes["added"] or scopes["removed"]
            else ""
        )
        print(strings.t("cli.channels.manifest.replace", reinstall=reinstall))
    print(strings.t("cli.channels.manifest.create-link", link=result["link"]))
    return 0


@register
class ChannelsCommand(Command):
    name = "channels"
    help = strings.t("cli.channels.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="channels_command", required=True)
        status = sub.add_parser(
            "status",
            help=strings.t("cli.channels.status.help"),
        )
        status.add_argument(
            "--probe",
            action="store_true",
            help=strings.t("cli.channels.status.probe.help"),
        )
        threads = sub.add_parser(
            "threads",
            help=strings.t("cli.channels.threads.help"),
        )
        threads.add_argument(
            "--work-item",
            default="",
            metavar="REF",
            help=strings.t("cli.channels.threads.work-item.help"),
        )
        threads.add_argument(
            "--json",
            action="store_true",
            help=strings.t("cli.channels.threads.json.help"),
        )
        records = sub.add_parser(
            "records",
            help=strings.t("cli.channels.records.help"),
        )
        records.add_argument(
            "work_item",
            metavar="REF",
            help=strings.t("cli.channels.records.work-item.help"),
        )
        records.add_argument(
            "--type",
            action="append",
            choices=list(RECORD_TYPES),
            default=[],
            help=strings.t("cli.channels.records.type.help"),
        )
        records.add_argument(
            "--format",
            choices=["json", "markdown"],
            default="markdown",
            help=strings.t("cli.channels.records.format.help"),
        )
        sub.add_parser(
            "poll",
            help=strings.t("cli.channels.poll.help"),
        )
        sub.add_parser(
            "listen",
            help=strings.t("cli.channels.listen.help"),
        )
        manifest = sub.add_parser(
            "manifest",
            help=strings.t("cli.channels.manifest.help"),
        )
        manifest.add_argument(
            "--name",
            help=strings.t("cli.channels.manifest.name.help"),
        )
        manifest.add_argument(
            "--format",
            choices=("yaml", "json"),
            default="yaml",
            help=strings.t("cli.channels.manifest.format.help"),
        )
        manifest.add_argument(
            "--link",
            action="store_true",
            help=strings.t("cli.channels.manifest.link.help"),
        )
        manifest.add_argument(
            "--write",
            nargs="?",
            const="",
            default=None,
            metavar="PATH",
            help=strings.t("cli.channels.manifest.write.help"),
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
            return _manifest(args)
        if args.channels_command == "poll":
            summary = inbound.poll_once(config)
            if summary.get("skipped"):
                print(strings.t("cli.channels.poll.skipped", reason=summary["skipped"]))
                return 1
            print(
                strings.t(
                    "cli.channels.poll.summary",
                    replies=summary["replies"],
                    processed=summary["processed"],
                    delivered=summary["delivered"],
                    created=summary.get("created", 0),
                    dropped=summary["dropped"],
                )
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
            holder = lock.holder() or strings.t("cli.channels.listen.unknown-holder")
            print(
                strings.t("cli.channels.listen.running", holder=holder), file=sys.stderr
            )
            return 1
    except OSError as exc:
        print(strings.t("cli.channels.listen.lockfile", error=exc), file=sys.stderr)
        return 1
    try:
        return run_socket_listener(config)
    finally:
        lock.release()
