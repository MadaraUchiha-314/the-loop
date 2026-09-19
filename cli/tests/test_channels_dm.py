"""Unit tests for issue-362: a direct message is a channel like any other.

Three layers, in the order they fail (``docs/specs/issue-362/design.md``):

1. the app manifest subscribes the bot to every conversation kind;
2. the-loop *says* when the configured channel emits events the app cannot
   receive — from the id's prefix with no network call, and confirmed against
   the installed app by ``channels status --probe``;
3. socket mode reconciles periodically, so a missed event costs
   ``read.catchUpSeconds`` rather than the process's lifetime.

Spec: docs/specs/issue-362/{bugfix,design,testing-plan}.md. No network: every
Slack call is made through a substituted client, as the rest of
``test_channels*.py`` does.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml

from the_loop.channels import slack as slack_mod
from the_loop.channels.slack import (
    CONVERSATION_KINDS,
    DEFAULT_BOT_TOKEN_ENV,
    SlackChannelConfig,
    kind_from_info,
    kinds_from_id,
    probe_subscription,
    subscription_findings,
    unchecked_advice,
)

MANIFEST = Path(slack_mod.__file__).with_name("slack-app-manifest.yaml")


def cli_config(tmp_path, channel="D0AU0SGP30T", read=None, **slack):
    section = {
        "enabled": True,
        "channel": channel,
        "publish": ["gate.feedback", "control.command", "work-item.create"],
        **slack,
    }
    if read is not None:
        section["read"] = read
    return {
        "state": {"root": str(tmp_path / "state")},
        "repositories": ["octocat/hello-world"],
        "routing": {"authorizedUsers": [{"github": "gh-UHUMAN", "slack": "UHUMAN"}]},
        "channels": {"slack": section},
    }


def parsed(tmp_path, **kwargs):
    return SlackChannelConfig.from_mapping(cli_config(tmp_path, **kwargs))


# -- T1: the manifest subscribes every conversation kind (R1.1) ---------------------


def test_the_manifest_subscribes_every_conversation_kind():
    """R1.1: all four history scopes and all four message events.

    The manifest is the only place the subscription is declared, and an operator
    who follows the guide imports it verbatim — so this is the fix itself.
    """
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    scopes = set(manifest["oauth_config"]["scopes"]["bot"])
    events = set(manifest["settings"]["event_subscriptions"]["bot_events"])
    for kind in CONVERSATION_KINDS.values():
        assert kind.scope in scopes, f"{kind.label}: {kind.scope} is not a bot scope"
        assert kind.event in events, f"{kind.label}: {kind.event} is not a bot event"
    # The pre-issue-362 pair is still there — this widens, it does not swap.
    assert {"channels:history", "groups:history"} <= scopes
    assert {"message.channels", "message.groups"} <= events


def test_every_conversation_kind_is_declared_once_and_completely():
    """The table the findings are built from: four kinds, each with a scope, an
    event and a human label, and no two sharing a scope or an event."""
    assert set(CONVERSATION_KINDS) == {"public", "private", "im", "mpim"}
    scopes = [kind.scope for kind in CONVERSATION_KINDS.values()]
    events = [kind.event for kind in CONVERSATION_KINDS.values()]
    assert len(set(scopes)) == len(scopes) and len(set(events)) == len(events)
    assert all(kind.label for kind in CONVERSATION_KINDS.values())


# -- T2: the kind, from the id's prefix (R2.1, design D2) --------------------------


@pytest.mark.parametrize(
    "channel_id,expected",
    [
        ("D0AU0SGP30T", ("im",)),  # the reporter's channel — unambiguous
        ("C123", ("public", "private")),  # the conversations model: either
        ("G123", ("private", "mpim")),  # a legacy private channel, or a group DM
        ("", ()),  # unset
        ("X999", ()),  # not a conversation id at all
        ("#general", ()),  # a name, not an id
    ],
)
def test_channel_kind_reads_the_id_prefix(channel_id, expected):
    """R2.1: the kind, with no network call — `status` calls nothing by contract."""
    assert kinds_from_id(channel_id) == expected


@pytest.mark.parametrize(
    "info,expected",
    [
        ({"is_im": True}, "im"),
        ({"is_mpim": True, "is_group": True, "is_private": True}, "mpim"),
        ({"is_private": True, "is_channel": True}, "private"),
        ({"is_channel": True}, "public"),
        ({}, "public"),
    ],
)
def test_kind_from_info_is_authoritative(info, expected):
    """R2.2: what `conversations.info` says, which the prefix can only guess.

    An mpim is also flagged private and group, and a private channel is also
    flagged a channel — so the order of the checks is the whole content here.
    """
    assert kind_from_info(info) == expected


# -- T2: the findings (R2.5, design D3) --------------------------------------------


def test_a_dm_without_im_history_is_a_finding_that_names_all_four_facts():
    """R2.5: the channel, its kind, the missing scope, the missing event — and
    the consequence, which is the part an operator needs to recognise the
    symptom they already have."""
    (finding,) = subscription_findings(
        "D0AU0SGP30T", ("im",), scopes=("chat:write", "channels:history")
    )
    assert "D0AU0SGP30T" in finding
    assert "direct message" in finding
    assert "im:history" in finding
    assert "message.im" in finding
    assert "only read when the listener starts" in finding
    assert "the-loop channels manifest" in finding


def test_a_dm_with_im_history_is_no_finding():
    assert (
        subscription_findings(
            "D0AU0SGP30T", ("im",), scopes=("chat:write", "im:history")
        )
        == ()
    )


def test_a_public_prefix_is_never_a_finding_when_either_candidate_is_granted():
    """design D2: `C…` is the ambiguous prefix and the one 95% of operators run.
    A false warning there would be worse than the silence this ticket is about,
    so a finding needs EVERY candidate kind's scope to be missing."""
    assert (
        subscription_findings(
            "C123", ("public", "private"), scopes=("chat:write", "channels:history")
        )
        == ()
    )
    (finding,) = subscription_findings(
        "C123", ("public", "private"), scopes=("chat:write",)
    )
    assert "public channel" in finding and "private channel" in finding
    assert "channels:history" in finding and "groups:history" in finding


def test_unreadable_scopes_are_never_a_finding():
    """design risk 4: `scopes=None` means "could not be read", and an unreadable
    header must produce NO finding — never a wrong one."""
    assert subscription_findings("D0AU0SGP30T", ("im",), scopes=None) == ()
    assert subscription_findings("C123", ("public", "private"), scopes=None) == ()


def test_only_a_dm_is_called_out_before_anything_is_probed():
    """R2.1 / design D2: with nothing probed there are no scopes to check. A `D…`
    is still called out — the shipped manifest could not serve one at all — and
    every ambiguous prefix stays quiet until `--probe` has facts."""
    (advice,) = unchecked_advice("D0AU0SGP30T")
    assert "--probe" in advice and "im:history" in advice and "message.im" in advice
    assert unchecked_advice("C123") == ()
    assert unchecked_advice("G123") == ()
    assert unchecked_advice("X999") == () and unchecked_advice("") == ()


def test_an_unrecognised_id_yields_no_findings():
    assert subscription_findings("X999", (), scopes=("chat:write",)) == ()
    assert subscription_findings("", (), scopes=None) == ()


# -- T3: the probe (R2.2, R2.3, bugfix §AC3, §AC4) ---------------------------------


class FakeProbeClient:
    """Records every call, so the probe's two-endpoint contract is assertable."""

    def __init__(self, info=None, scopes="chat:write,channels:history", raises=None):
        self.calls = []
        self._info = info if info is not None else {"id": "D0AU0SGP30T", "is_im": True}
        self._scopes = scopes
        self._raises = raises

    def conversations_info(self, *, channel):
        self.calls.append(("conversations_info", channel))
        if self._raises:
            raise self._raises
        return {"ok": True, "channel": self._info}

    def auth_test(self):
        self.calls.append(("auth_test", None))
        return FakeResponse({"ok": True, "user_id": "UBOT"}, self._scopes)


class FakeResponse(dict):
    """A ``SlackResponse``-shaped mapping: the payload, plus ``.headers``."""

    def __init__(self, payload, scopes):
        super().__init__(payload)
        self.headers = {"x-oauth-scopes": scopes}


def test_probe_reads_the_kind_from_conversations_info_and_the_scopes_from_auth_test(
    tmp_path, monkeypatch
):
    """R2.2: the authoritative answer — the kind from the API, the granted scopes
    from `auth.test`'s response header."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient()
    result = probe_subscription(parsed(tmp_path), client_factory=lambda token: client)
    assert result["kind"] == "im"
    assert result["scopes"] == ("chat:write", "channels:history")
    # Two absences, two findings (issue-389): the DM's history scope, then the
    # mention scope the address needs.
    assert len(result["findings"]) == 2
    assert "im:history" in result["findings"][0]
    assert "app_mentions:read" in result["findings"][1]


def test_probe_calls_only_conversations_info_and_auth_test(tmp_path, monkeypatch):
    """bugfix §AC4: two fixed calls on the operator's own configured id — no
    argument comes from a message, a button or a ticket."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient()
    probe_subscription(parsed(tmp_path), client_factory=lambda token: client)
    assert client.calls == [
        ("conversations_info", "D0AU0SGP30T"),
        ("auth_test", None),
    ]


def test_probe_reads_a_header_delivered_as_a_list(tmp_path, monkeypatch):
    """`slack_sdk` may hand back a header as a list; urllib does. Both shapes."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient()
    client.auth_test = lambda: FakeResponse(  # type: ignore[method-assign]
        {"ok": True}, ["chat:write, im:history, app_mentions:read"]
    )
    result = probe_subscription(parsed(tmp_path), client_factory=lambda token: client)
    assert result["scopes"] == ("chat:write", "im:history", "app_mentions:read")
    assert result["findings"] == ()


def test_probe_with_unreadable_scopes_reports_none_and_finds_nothing(
    tmp_path, monkeypatch
):
    """design risk 4: an SDK change that hides the header must produce NO finding,
    never a wrong one. The kind is still reported."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient()
    client.auth_test = lambda: {"ok": True}  # type: ignore[method-assign]
    result = probe_subscription(parsed(tmp_path), client_factory=lambda token: client)
    assert result["kind"] == "im" and result["scopes"] is None
    assert result["findings"] == ()


@pytest.mark.parametrize(
    "setup,expected",
    [
        ("no-token", "token"),
        ("no-channel", "channel"),
        ("api-error", "boom"),
    ],
)
def test_probe_skips_without_a_token_a_channel_or_on_an_api_error(
    tmp_path, monkeypatch, setup, expected
):
    """R2.3: a diagnostic that cannot run says why. It never raises."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    config = parsed(tmp_path)
    client = FakeProbeClient()
    if setup == "no-token":
        monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    elif setup == "no-channel":
        config = parsed(tmp_path, channel="")
    else:
        client = FakeProbeClient(raises=RuntimeError("boom"))
    result = probe_subscription(config, client_factory=lambda token: client)
    assert "findings" not in result
    assert expected in result["skipped"]


def test_probe_prints_no_token_value(tmp_path, monkeypatch):
    """bugfix §AC3: the probe's result carries the kind, the scope NAMES and the
    findings — never the token it authenticated with."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    client = FakeProbeClient()
    result = probe_subscription(parsed(tmp_path), client_factory=lambda token: client)
    assert "supersecret" not in json.dumps(result)


# -- T4 / T7: `read.catchUpSeconds` (R3.2, design D5, bugfix §AC6) -----------------


def test_catch_up_seconds_defaults_to_900(tmp_path):
    assert parsed(tmp_path, read={"mode": "socket"}).catch_up_seconds == 900


def test_a_config_without_catch_up_seconds_loads_and_gets_the_default(tmp_path):
    """T7 / design D6: additive and optional — a 0.10.0 config needs no migration."""
    config = parsed(tmp_path)
    assert config.enabled and config.catch_up_seconds == 900


def test_zero_means_connect_only(tmp_path):
    """R3.2: 16.0.1's behaviour stays reachable — and `or`-style parsing, which
    the neighbouring `intervalSeconds` uses, would silently turn it into 900."""
    config = parsed(tmp_path, read={"mode": "socket", "catchUpSeconds": 0})
    assert config.catch_up_seconds == 0


@pytest.mark.parametrize("value", [1, 30, 59])
def test_catch_up_seconds_below_the_floor_is_clamped_to_60(tmp_path, caplog, value):
    """bugfix §AC6: a reconcile is a safety net, not a second poll transport."""
    config = parsed(tmp_path, read={"mode": "socket", "catchUpSeconds": value})
    assert config.catch_up_seconds == 60
    assert "catchUpSeconds" in caplog.text


def test_a_junk_catch_up_seconds_falls_back_to_the_default(tmp_path):
    config = parsed(tmp_path, read={"mode": "socket", "catchUpSeconds": "often"})
    assert config.catch_up_seconds == 900


# -- T6: `channels status` (R2.1, R2.2, R2.3) --------------------------------------


def run_status(tmp_path, monkeypatch, capsys, config, *argv):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status", *argv])) == 0
    return capsys.readouterr().out


def test_status_names_the_conversation_kind_without_calling_slack(
    tmp_path, monkeypatch, capsys
):
    """R2.1: the reported configuration, diagnosed with no network call at all —
    `status` is the command an operator runs when things are already broken."""

    def explode(token):  # pragma: no cover — the point is that it is not called
        raise AssertionError("status must not call Slack without --probe")

    monkeypatch.setattr(slack_mod, "build_client", explode)
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    out = run_status(
        tmp_path, monkeypatch, capsys, cli_config(tmp_path, read={"mode": "socket"})
    )
    assert "channel kind: direct message" in out
    assert "im:history" in out and "message.im" in out
    assert "[!]" in out


def test_status_prints_the_reconcile_cadence(tmp_path, monkeypatch, capsys):
    """R3.1: socket mode now reconciles; `status` says how often, and says when
    an operator has turned it off."""
    out = run_status(
        tmp_path, monkeypatch, capsys, cli_config(tmp_path, read={"mode": "socket"})
    )
    assert "reconciling every 900s" in out
    off = run_status(
        tmp_path,
        monkeypatch,
        capsys,
        cli_config(tmp_path, read={"mode": "socket", "catchUpSeconds": 0}),
    )
    assert "reconciling only at connect" in off


def test_status_says_nothing_about_a_kind_it_cannot_derive(
    tmp_path, monkeypatch, capsys
):
    out = run_status(tmp_path, monkeypatch, capsys, cli_config(tmp_path, channel="X9"))
    assert "channel kind: unrecognised" in out
    assert "[!]" not in out


def test_status_probe_prints_the_confirmed_finding(tmp_path, monkeypatch, capsys):
    """R2.2: with `--probe` the answer is measured against the installed app."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-supersecret")
    client = FakeProbeClient()
    monkeypatch.setattr(slack_mod, "build_client", lambda token: client)
    out = run_status(
        tmp_path,
        monkeypatch,
        capsys,
        cli_config(tmp_path, read={"mode": "socket"}),
        "--probe",
    )
    assert "probe:" in out and "direct message" in out
    assert "chat:write" in out  # the granted scopes, by name
    assert "im:history" in out
    assert "supersecret" not in out  # bugfix §AC3


def test_status_probe_that_cannot_run_still_exits_zero(tmp_path, monkeypatch, capsys):
    """R2.3: a diagnostic never fails the command."""
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    out = run_status(tmp_path, monkeypatch, capsys, cli_config(tmp_path), "--probe")
    assert "probe:" in out and "not probed" in out
