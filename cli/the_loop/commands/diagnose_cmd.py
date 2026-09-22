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
"""

from __future__ import annotations

import argparse
import sys

from .. import cli_config, eventlog
from ..channels.doctor import (
    DEFAULT_BEATS,
    DEFAULT_WINDOW_SECONDS,
    check_declared_channels,
    consumer_verdict_text,
    probe_second_consumer,
)
from ..channels.slack import SlackChannelConfig
from ..core import selfdiagnosis
from ..state import layout_from_config
from .base import Command, register
from .channels_cmd import _subscription_lines


@register
class DiagnoseCommand(Command):
    name = "diagnose"
    help = (
        "scan the-loop's own event log for harness failures and file "
        "self-diagnosed issues (opt-in; --dry-run to preview)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "build and print the redacted report(s) without posting; works "
                "while selfDiagnosis is disabled, so you can preview before "
                "opting in"
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("diagnose")
        config_path = cli_config.default_cli_config_path()
        data = cli_config.load_cli_config(config_path)
        config = selfdiagnosis.SelfDiagnosisConfig.from_mapping(data)
        dry_run = bool(getattr(args, "dry_run", False))
        if not config.enabled and not dry_run:
            print(
                "self-diagnosis is off — set selfDiagnosis.enabled: true in "
                f"{config_path} to let the-loop file issues for its own "
                "failures, or preview with --dry-run",
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
            print("nothing to diagnose — no new failure fingerprints in the log")
            return 0
        for outcome in outcomes:
            self._print(outcome, config)
        return 0

    @staticmethod
    def _print(outcome: dict, config: selfdiagnosis.SelfDiagnosisConfig) -> None:
        action = outcome.get("action")
        if action == "dry-run":
            if outcome.get("body"):
                print(f"--- would file on {config.repo} ---")
                print(outcome.get("title", ""))
                print()
                print(outcome["body"])
            else:
                print(
                    "--- would diagnose (agent unavailable: "
                    f"{outcome.get('error', '')}) ---"
                )
                print(outcome.get("dossier", ""))
        elif action == "posted":
            print(f"filed {outcome.get('url')} — {outcome.get('title')}")
        elif action == "deferred":
            print(
                f"deferred {outcome.get('fingerprint')} — daily cap "
                f"(maxIssuesPerDay: {config.max_issues_per_day}) reached"
            )
        else:
            print(
                f"failed {outcome.get('fingerprint')} — {outcome.get('error')}",
                file=sys.stderr,
            )


#: What each row of the doctor's report starts with: a fact, a finding that
#: costs the exit code, or something the doctor could not measure — which is
#: printed as loudly as a finding but never dressed up as one.
_OK, _FINDING, _UNKNOWN = "[ok]", "[!]", "[?]"


@register
class DoctorCommand(Command):
    name = "doctor"
    help = (
        "Deployment-wide diagnosis of one integration — `doctor slack`: the "
        "app's scopes and expected events, every declared channel against the "
        "bot's directory, and a heartbeat probe for a second Socket Mode "
        "consumer (evidence, not proof; ids only, never tokens)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="doctor_command", required=True)
        slack = sub.add_parser(
            "slack",
            help=(
                "Diagnose the Slack deployment: scopes + expected events, "
                "declared channels resolved in the bot's directory, and whether a "
                "second Socket Mode consumer may be splitting inbound events"
            ),
        )
        slack.add_argument(
            "--beats",
            type=int,
            default=DEFAULT_BEATS,
            metavar="N",
            help=(
                f"Heartbeat messages to post (default {DEFAULT_BEATS}); with two "
                "consumers sharing the token a split hides one time in 2^N"
            ),
        )
        slack.add_argument(
            "--window",
            type=float,
            default=DEFAULT_WINDOW_SECONDS,
            metavar="SECONDS",
            help=(
                f"How long to wait for the heartbeats to come back (default "
                f"{DEFAULT_WINDOW_SECONDS:g})"
            ),
        )
        slack.add_argument(
            "--no-heartbeat",
            action="store_true",
            help="Skip the second-consumer probe — the doctor then posts nothing to Slack",
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("doctor")
        data = cli_config.load_cli_config(cli_config.default_cli_config_path())
        return _doctor_slack(
            data,
            beats=int(getattr(args, "beats", DEFAULT_BEATS) or DEFAULT_BEATS),
            window=float(
                getattr(args, "window", DEFAULT_WINDOW_SECONDS)
                or DEFAULT_WINDOW_SECONDS
            ),
            heartbeat=not bool(getattr(args, "no_heartbeat", False)),
        )


def _doctor_slack(config: dict, *, beats: int, window: float, heartbeat: bool) -> int:
    """The report, three sections, each best-effort: a section that cannot run
    prints why and the others still run. Exit 1 when any ``[!]`` was printed."""
    slack = SlackChannelConfig.from_mapping(config)
    findings = 0
    print(
        "slack doctor — ids and channel names only, never tokens; where a line "
        "says evidence it is not proof"
    )
    print("app:")
    if not slack.enabled:
        print(f"  {_UNKNOWN} channels.slack is not enabled — nothing here is in use")
    try:
        lines = _subscription_lines(slack, probe=True, cli_config=config)
    except Exception as exc:  # noqa: BLE001 — a diagnostic never crashes
        lines = [f"  {_UNKNOWN} the scope probe raised {type(exc).__name__}: {exc}"]
    if not lines:
        lines = [f"  {_UNKNOWN} no channels.slack.channel — the scope probe needs one"]
    for line in lines:
        print(line)
        findings += line.strip().startswith(_FINDING)
    print("channels:")
    findings += _print_channels(check_declared_channels(config))
    print("consumers:")
    if not heartbeat:
        print(
            f"  {_UNKNOWN} skipped (--no-heartbeat) — whether a second Socket Mode "
            "consumer shares this app token was not probed"
        )
    else:
        result = probe_second_consumer(config, beats=beats, window_seconds=window)
        verdict = result.get("verdict")
        tag = {"ok": _OK, "split-suspected": _FINDING}.get(str(verdict), _UNKNOWN)
        print(f"  {tag} {consumer_verdict_text(result)}")
        findings += verdict == "split-suspected"
    return 1 if findings else 0


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
                else f"{declared} — listed in the bot's directory"
            )
            print(f"  {_OK} {what} ({owner})")
        elif status == "miss":
            findings += 1
            print(
                f"  {_FINDING} {declared} → resolves to no channel this bot can see "
                f"({owner}) — check the spelling, invite the bot, or declare the "
                "conversation id"
            )
        elif status == "absent":
            findings += 1
            print(
                f"  {_FINDING} {declared} — declared by id but absent from the bot's "
                f"directory (its memberships and the workspace listing) ({owner}) — "
                "invite the bot, or every post there is refused"
            )
        elif status == "invalid":
            findings += 1
            print(
                f"  {_FINDING} {declared!r} is neither a conversation id nor a channel "
                f"name ({owner})"
            )
        else:
            print(
                f"  {_UNKNOWN} {declared} — unverifiable: the directory could not be "
                f"read ({owner}) — no token, a missing channels:read / groups:read "
                "scope, or a transport error"
            )
    if report.get("truncated"):
        print(
            f"  {_FINDING} the workspace listing was cut at the page cap — a miss "
            "above may exist beyond it; declare the conversation id instead of "
            "the name"
        )
    return findings
