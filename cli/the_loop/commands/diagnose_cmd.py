"""``the-loop diagnose`` and ``the-loop doctor`` — the-loop looking at itself.

``diagnose`` (issue-242) is one self-diagnosis scan, on demand: the manual half
of the capability, so deployments running neither ingress daemon still get
self-diagnosis, and ``--dry-run`` is how an operator sees exactly what would
leave the machine **before** opting in (it works while the feature is disabled,
and posts nothing). Local-only, like ``critic run``: it spawns a local agent
process, so routing it through the control-plane service buys nothing yet.

``doctor slack`` (issue-393 F2) is the deployment-wide Slack diagnosis: the
app's scopes and expected events (the ``channels status --probe`` lines), every
declared channel resolved in the bot's own directory (R2.3), and a heartbeat
probe for a second Socket Mode consumer on the same app token (R2.2). It prints
ids and channel names only, never a token; where it cannot measure it says
*unverifiable*, and where it can it says *evidence, not proof* — Slack exposes
no API that lists an app's connections. Exit 1 when it found something
(``[!]``), 0 otherwise; the probes live in :mod:`the_loop.channels.doctor`.

``doctor jira`` (issue-475) checks a configured ``integrations.jira`` block the
daemon could not use: the site and deployment it would reach, each credential
variable set or not (by name, never a value), and the project map. Offline — it
sends nothing to Jira. ``resolve("jira")`` refuses on exactly these findings, so
the doctor is the same verdict, asked before a gate hook asks it.
"""

from __future__ import annotations

from typing import List, Optional

import argparse
import os
import sys

from .. import cli_config, eventlog, strings
from ..channels.doctor import (
    DEFAULT_BEATS,
    DEFAULT_WINDOW_SECONDS,
    check_declared_channels,
    consumer_verdict_text,
    probe_second_consumer,
)
from ..channels.slack import SlackChannelConfig
from ..core import selfdiagnosis
from ..jiraapi import JiraApiConfig, JiraApiError
from ..state import layout_from_config
from .base import Command, register
from .channels_cmd import _subscription_lines


@register
class DiagnoseCommand(Command):
    name = "diagnose"
    help = strings.t("cli.diagnose.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=strings.t("cli.diagnose.dry-run.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("diagnose")
        config_path = cli_config.default_cli_config_path()
        data = cli_config.load_cli_config(config_path)
        config = selfdiagnosis.SelfDiagnosisConfig.from_mapping(data)
        dry_run = bool(getattr(args, "dry_run", False))
        if not config.enabled and not dry_run:
            print(
                strings.t(
                    "cli.diagnose.run.self-diagnosis-is-off-set",
                    config_path=config_path,
                ),
                file=sys.stderr,
            )
            return 2

        layout = layout_from_config(data)
        log_path = (data.get("eventLog") or {}).get("path") or layout.event_log
        outcomes = selfdiagnosis.scan(
            config,
            log_path=log_path,
            state_path=layout.self_diagnosis,
            dry_run=dry_run,
        )
        if not outcomes:
            print(strings.t("cli.diagnose.run.nothing-to-diagnose-no-new"))
            return 0
        for outcome in outcomes:
            self._print(outcome, config)
        return 0

    @staticmethod
    def _print(outcome: dict, config: selfdiagnosis.SelfDiagnosisConfig) -> None:
        action = outcome.get("action")
        if action == "dry-run":
            if outcome.get("body"):
                print(strings.t("cli.diagnose.print.would-file-on", repo=config.repo))
                print(outcome.get("title", ""))
                print()
                print(outcome["body"])
            else:
                print(
                    strings.t(
                        "cli.diagnose.print.would-diagnose-agent-unavailable",
                        error=outcome.get("error", ""),
                    )
                )
                print(outcome.get("dossier", ""))
        elif action == "posted":
            print(
                strings.t(
                    "cli.diagnose.print.filed",
                    url=outcome.get("url"),
                    title=outcome.get("title"),
                )
            )
        elif action == "deferred":
            print(
                strings.t(
                    "cli.diagnose.print.deferred-daily-cap-maxissuesperday-reached",
                    fingerprint=outcome.get("fingerprint"),
                    max_issues_per_day=config.max_issues_per_day,
                )
            )
        else:
            print(
                strings.t(
                    "cli.diagnose.print.failed",
                    fingerprint=outcome.get("fingerprint"),
                    error=outcome.get("error"),
                ),
                file=sys.stderr,
            )


#: What each row of the doctor's report starts with: a fact, a finding that
#: costs the exit code, or something the doctor could not measure — which is
#: printed as loudly as a finding but never dressed up as one.
_OK, _FINDING, _UNKNOWN = "[ok]", "[!]", "[?]"


@register
class DoctorCommand(Command):
    name = "doctor"
    help = strings.t("cli.diagnose.doctor.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="doctor_command", required=True)
        slack = sub.add_parser(
            "slack",
            help=strings.t("cli.diagnose.doctor.slack.help"),
        )
        slack.add_argument(
            "--beats",
            type=int,
            default=DEFAULT_BEATS,
            metavar="N",
            help=strings.t(
                "cli.diagnose.doctor.slack.beats.help", default_beats=DEFAULT_BEATS
            ),
        )
        slack.add_argument(
            "--window",
            type=float,
            default=DEFAULT_WINDOW_SECONDS,
            metavar="SECONDS",
            help=strings.t(
                "cli.diagnose.doctor.slack.window.help",
                default_window_seconds=DEFAULT_WINDOW_SECONDS,
            ),
        )
        slack.add_argument(
            "--no-heartbeat",
            action="store_true",
            help=strings.t("cli.diagnose.doctor.slack.no-heartbeat.help"),
        )
        sub.add_parser(
            "jira",
            help=strings.t("cli.diagnose.doctor.jira.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("doctor")
        data = cli_config.load_cli_config(cli_config.default_cli_config_path())
        if getattr(args, "doctor_command", "slack") == "jira":
            return _doctor_jira(data)
        return _doctor_slack(
            data,
            beats=int(getattr(args, "beats", DEFAULT_BEATS) or DEFAULT_BEATS),
            window=float(
                getattr(args, "window", DEFAULT_WINDOW_SECONDS)
                or DEFAULT_WINDOW_SECONDS
            ),
            heartbeat=not bool(getattr(args, "no_heartbeat", False)),
        )


def _doctor_jira(config: dict) -> int:
    """Is the configured Jira block usable? Exit 1 when any ``[!]`` was printed.

    The same checks ``resolve("jira")`` fails closed on — the block, the server
    it would reach, every credential variable — so a finding here is a gate hook
    that would refuse. Variable names only; no value is read into the output.
    """
    api = JiraApiConfig.from_cli_config(config)
    print(strings.t("cli.diagnose.doctor-jira.jira-doctor-variable-names-only"))
    if not api.configured:
        print(
            strings.t(
                "cli.diagnose.doctor-jira.integrations-jira-is-not-configured",
                unknown=_UNKNOWN,
            )
        )
        return 0
    findings = 0
    try:
        server = api.server()
        print(
            strings.t(
                "cli.diagnose.doctor-jira.rest-v",
                ok=_OK,
                site=api.site,
                deployment=api.deployment,
                server=server,
                rest_version=api.rest_version,
            )
        )
    except JiraApiError as exc:
        findings += 1
        print(f"  {_FINDING} {exc}")
    print(strings.t("cli.diagnose.doctor-jira.credentials"))
    needed = [("email", api.email_env)] if api.cloud else []
    needed.append(("token", api.token_env))
    missing = set(api.missing_credentials())
    for what, names in needed:
        label = (
            " or ".join(names)
            if names
            else strings.t("cli.diagnose.doctor-jira.no-variable-named", what=what)
        )
        if label in missing or not names:
            findings += 1
            print(
                strings.t(
                    "cli.diagnose.doctor-jira.is-not-set-the-daemon",
                    finding=_FINDING,
                    label=label,
                    what=what,
                )
            )
        else:
            print(strings.t("cli.diagnose.doctor-jira.is-set", ok=_OK, label=label))
    print(strings.t("cli.diagnose.doctor-jira.projects"))
    section = ((config.get("integrations") or {}).get("jira")) or {}
    projects = section.get("projects") if isinstance(section, dict) else None
    if not isinstance(projects, dict) or not projects:
        findings += 1
        print(
            strings.t(
                "cli.diagnose.doctor-jira.integrations-jira-projects-lists-no",
                finding=_FINDING,
            )
        )
    else:
        for key in sorted(projects):
            entry = projects[key] if isinstance(projects[key], dict) else {}
            repository = str(entry.get("repository") or "").strip()
            if repository:
                print(f"  {_OK} {key} → {repository}")
            else:
                print(
                    strings.t(
                        "cli.diagnose.doctor-jira.mirror-only-a-room-never",
                        ok=_OK,
                        key=key,
                    )
                )
    return 1 if findings else 0


def _doctor_slack(config: dict, *, beats: int, window: float, heartbeat: bool) -> int:
    """The report, three sections, each best-effort: a section that cannot run
    prints why and the others still run. Exit 1 when any ``[!]`` was printed."""
    slack = SlackChannelConfig.from_mapping(config)
    findings = 0
    print(strings.t("cli.diagnose.doctor-slack.slack-doctor-ids-and-channel"))
    print(strings.t("cli.diagnose.doctor-slack.app"))
    if not slack.enabled:
        print(
            strings.t(
                "cli.diagnose.doctor-slack.channels-slack-is-not-enabled",
                unknown=_UNKNOWN,
            )
        )
    try:
        lines = _subscription_lines(slack, probe=True, cli_config=config)
    except Exception as exc:  # noqa: BLE001 — a diagnostic never crashes
        lines = [
            strings.t(
                "cli.diagnose.doctor-slack.scope-probe-raised",
                unknown=_UNKNOWN,
                exc_type=type(exc).__name__,
                exc=exc,
            )
        ]
    if not lines:
        lines = [
            strings.t(
                "cli.diagnose.doctor-slack.no-channel-for-probe", unknown=_UNKNOWN
            )
        ]
    for line in lines:
        print(line)
        findings += line.strip().startswith(_FINDING)
    print(strings.t("cli.diagnose.doctor-slack.channels"))
    findings += _print_channels(check_declared_channels(config))
    gateway = _gateway_lines(config)
    if gateway is not None:
        print(strings.t("cli.diagnose.doctor-slack.gateway"))
        for line in gateway:
            print(line)
            findings += line.strip().startswith(_FINDING)
    print(strings.t("cli.diagnose.doctor-slack.consumers"))
    if gateway is not None:
        print(
            strings.t(
                "cli.diagnose.doctor-slack.this-instance-reads-slack-through",
                unknown=_UNKNOWN,
            )
        )
        return 1 if findings else 0
    if not heartbeat:
        print(
            strings.t(
                "cli.diagnose.doctor-slack.skipped-no-heartbeat-whether-a",
                unknown=_UNKNOWN,
            )
        )
    else:
        result = probe_second_consumer(config, beats=beats, window_seconds=window)
        verdict = result.get("verdict")
        tag = {"ok": _OK, "split-suspected": _FINDING}.get(str(verdict), _UNKNOWN)
        print(f"  {tag} {consumer_verdict_text(result)}")
        findings += verdict == "split-suspected"
    return 1 if findings else 0


def _gateway_lines(config: dict) -> Optional[List[str]]:
    """The gateway section (issue-496, R9.3): ``None`` without a `gateway` block; else
    whether the gateway answers, its Socket Mode state, and this instance's client
    state. Ids and states only."""
    from ..core import lifecycle as core_lifecycle

    if not core_lifecycle.gateway_configured(config):
        return None
    doc = core_lifecycle.gateway_document(config)
    lines: List[str] = []
    state = str(doc.get("state") or "unknown")
    health = doc.get("health") or {}
    if state == "connected":
        lines.append(
            strings.t(
                "cli.diagnose.gateway-lines.reachable",
                ok=_OK,
                url=doc.get("url"),
                gateway_line=core_lifecycle.gateway_line(doc),
            )
        )
    elif state == "unknown":
        lines.append(
            strings.t(
                "cli.diagnose.gateway-lines.service-not-running", unknown=_UNKNOWN
            )
        )
    else:
        lines.append(
            strings.t(
                "cli.diagnose.gateway-lines.client",
                finding=_FINDING,
                gateway_line=core_lifecycle.gateway_line(doc),
            )
        )
    socket = (
        (health.get("slack") or {}).get("socket") if isinstance(health, dict) else None
    )
    if socket == "up":
        lines.append(strings.t("cli.diagnose.gateway-lines.socket-up", ok=_OK))
    elif socket in ("down", "off"):
        lines.append(
            strings.t(
                "cli.diagnose.gateway-lines.socket-down",
                finding=_FINDING,
                socket=socket,
            )
        )
    # outbound (issue-519, R1.3): who posts to Slack for this instance
    slack = SlackChannelConfig.from_mapping(config)
    if slack.enabled:
        posting = doc.get("slackPosting") or (
            (health.get("slack") or {}).get("posting")
            if isinstance(health, dict)
            else None
        )
        if os.environ.get(slack.bot_token_env):
            lines.append(
                strings.t(
                    "cli.diagnose.gateway-lines.own-token",
                    ok=_OK,
                    bot_token_env=slack.bot_token_env,
                )
            )
        elif posting == "on":
            lines.append(strings.t("cli.diagnose.gateway-lines.gateway-posts", ok=_OK))
        elif posting in ("disabled", "no-token", "socket-unconfigured"):
            lines.append(
                strings.t(
                    "cli.diagnose.gateway-lines.needs-token",
                    finding=_FINDING,
                    bot_token_env=slack.bot_token_env,
                    posting=posting,
                )
            )
        else:
            lines.append(
                strings.t(
                    "cli.diagnose.gateway-lines.posting-unknown",
                    unknown=_UNKNOWN,
                    bot_token_env=slack.bot_token_env,
                )
            )
    return lines


def _print_channels(report: dict) -> int:
    """One row per declared channel (R2.3); the number of findings printed."""
    findings = 0
    rows = report.get("channels") or []
    if report.get("reason") and not rows:
        print(f"  {_UNKNOWN} {report['reason']}")
        return 0
    if report.get("reason"):
        print(f"  {_UNKNOWN} {report['reason']}")
    for row in rows:
        declared, owner, ident = row.get("declared"), row.get("owner"), row.get("id")
        status = row.get("status")
        if status == "ok":
            what = (
                f"{declared} → {ident}"
                if ident and ident != declared
                else strings.t(
                    "cli.diagnose.print-channels.listed-in-directory", declared=declared
                )
            )
            print(f"  {_OK} {what} ({owner})")
        elif status == "miss":
            findings += 1
            print(
                strings.t(
                    "cli.diagnose.print-channels.resolves-to-no-channel-this",
                    finding=_FINDING,
                    declared=declared,
                    owner=owner,
                )
            )
        elif status == "absent":
            findings += 1
            print(
                strings.t(
                    "cli.diagnose.print-channels.declared-by-id-but-absent",
                    finding=_FINDING,
                    declared=declared,
                    owner=owner,
                )
            )
        elif status == "invalid":
            findings += 1
            print(
                strings.t(
                    "cli.diagnose.print-channels.is-neither-a-conversation-id",
                    finding=_FINDING,
                    declared=declared,
                    owner=owner,
                )
            )
        else:
            print(
                strings.t(
                    "cli.diagnose.print-channels.unverifiable-the-directory-could-not",
                    unknown=_UNKNOWN,
                    declared=declared,
                    owner=owner,
                )
            )
    if report.get("truncated"):
        print(
            strings.t(
                "cli.diagnose.print-channels.the-workspace-listing-was-cut",
                finding=_FINDING,
            )
        )
    return findings
