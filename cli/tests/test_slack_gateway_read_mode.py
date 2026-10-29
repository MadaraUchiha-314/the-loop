"""Unit and abuse-case tests for issue-503: ``channels.slack.read.mode: gateway`` —
an instance that takes Slack from the gateway and never opens Socket Mode itself.
Spec: docs/specs/issue-503/{requirements,design,testing-plan}.md (T1, T8)."""

from __future__ import annotations

import logging
import threading

import pytest

from the_loop.channels import inbound, watcher
from the_loop.channels.slack import READ_MODES, SlackChannelConfig

GRANTS = ["work-item.reply", "gate.feedback", "control.command", "work-item.create"]
GATEWAY = {"url": "https://gateway.example"}


def config(tmp_path, mode, *, gateway=True, publish=GRANTS):
    data = {
        "state": {"root": str(tmp_path / "state")},
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "C123",
                "publish": list(publish),
                "read": {"mode": mode},
            }
        },
    }
    if gateway:
        data["gateway"] = dict(GATEWAY)
    return data


def parsed(tmp_path, mode, **kw):
    return SlackChannelConfig.from_mapping(config(tmp_path, mode, **kw))


# -- R1: a `gateway` read mode --------------------------------------------------


def test_gateway_is_a_read_mode_and_keeps_its_value_beside_a_block(tmp_path):
    """R1.1."""
    assert "gateway" in READ_MODES
    slack = parsed(tmp_path, "gateway")
    assert slack.read_mode == "gateway" and slack.gateway


def test_the_poll_reader_never_starts_in_gateway_mode(tmp_path):
    """R1.3."""
    stop = threading.Event()
    assert watcher.start_watcher(config(tmp_path, "gateway"), stop) is None


def test_the_reconciliation_read_is_allowed_in_gateway_mode(tmp_path, monkeypatch):
    """R1.5: `channels poll` refuses only `off`; `gateway` reads like `socket`."""
    seen = []

    def fetch(self):
        seen.append(self.config.read_mode)
        raise inbound.ChannelError("stop here")

    monkeypatch.setattr(inbound.SlackBotChannel, "fetch_replies", fetch)
    out = inbound.poll_once(config(tmp_path, "gateway"))
    assert seen == ["gateway"]
    assert "read.mode is 'off'" not in str(out.get("skipped"))


# -- R2: interactivity keys on reachability -------------------------------------


def test_gateway_mode_with_a_block_is_push_reachable_and_interactive(tmp_path):
    """R2.1, R2.2: the three gates open under their grants, as in `socket`."""
    slack = parsed(tmp_path, "gateway")
    assert slack.push_reachable
    assert slack.interactive and slack.command_buttons and slack.kickoff_picker


@pytest.mark.parametrize("mode", ["poll", "off"])
def test_poll_and_off_stay_unreachable_beside_a_block(tmp_path, mode):
    """R2.4."""
    slack = parsed(tmp_path, mode)
    assert not slack.push_reachable
    assert not (slack.interactive or slack.command_buttons or slack.kickoff_picker)


def test_socket_without_a_block_is_unchanged(tmp_path):
    """Behaviour preserved: 20.3.0's `socket` still opens the gates."""
    slack = parsed(tmp_path, "socket", gateway=False)
    assert slack.push_reachable and slack.interactive and not slack.gateway


def test_the_grants_still_decide_under_gateway(tmp_path):
    """R2.2: reachability is one half; the grant is still the other."""
    slack = parsed(tmp_path, "gateway", publish=["work-item.reply"])
    assert slack.push_reachable
    assert not (slack.interactive or slack.command_buttons or slack.kickoff_picker)


def test_the_picker_is_refused_at_press_time_once_the_block_is_gone(tmp_path):
    """R2.3: the press-time re-check reads the same rule — a gateway-mode config
    whose block was removed refuses the picker answer as `unpublishable-event`."""
    from the_loop.channels.base import InboundReply

    gone = config(tmp_path, "gateway", gateway=False)
    reply = InboundReply(
        channel="slack",
        work_item="",
        author="UHUMAN",
        text="o/r",
        thread="1700.1",
        ts="1800.1",
        channel_id="C123",
    )
    outcome = inbound.process_kickoff_answer(
        reply,
        SlackChannelConfig.from_mapping(gone),
        gone,
        bot=None,  # type: ignore[arg-type] — refused before the bot is read
    )
    assert outcome["outcome"] == "unpublishable-event"


# -- R3 / T8: fail closed without a gateway --------------------------------------


def test_abuse_gateway_without_a_block_reads_nothing_and_says_why(tmp_path, caplog):
    """R3.1, AC1: a deleted `gateway:` block resolves `gateway` to `off` — nothing
    read, nothing interactive — with an error that names both keys."""
    with caplog.at_level(logging.ERROR, logger="the_loop.channels.slack"):
        slack = parsed(tmp_path, "gateway", gateway=False)
    assert slack.read_mode == "off" and not slack.gateway
    assert not (slack.push_reachable or slack.interactive or slack.kickoff_picker)
    text = caplog.text
    assert "channels.slack.read.mode" in text and "gateway" in text
    assert "gateway.url" in text


def test_abuse_gateway_without_a_block_skips_the_reconciliation_read(tmp_path):
    """R3.1: `channels poll` reads nothing either."""
    out = inbound.poll_once(config(tmp_path, "gateway", gateway=False))
    assert "off" in out["skipped"] and out["replies"] == 0


def test_abuse_a_block_without_a_url_is_no_gateway(tmp_path):
    """R3.1: a block with no usable url is not a gateway — fail closed."""
    data = config(tmp_path, "gateway")
    data["gateway"] = {"url": ""}
    assert SlackChannelConfig.from_mapping(data).read_mode == "off"


def test_abuse_an_unknown_mode_still_resolves_to_off(tmp_path):
    """AC2: a typo never reaches a reading mode — with or without a block."""
    assert parsed(tmp_path, "gatewy").read_mode == "off"
    assert parsed(tmp_path, "gatewy", gateway=False).read_mode == "off"


def test_abuse_a_hand_built_gateway_config_without_the_flag_is_unreachable():
    """AC4: `push_reachable` keeps its own conjunct, so a config built in-process
    with `read_mode="gateway"` and no gateway renders no unreceivable button."""
    slack = SlackChannelConfig(
        enabled=True, channel="C1", read_mode="gateway", publish=tuple(GRANTS)
    )
    assert not (slack.push_reachable or slack.interactive or slack.command_buttons)


# -- R1.2 / R4: no socket beside a gateway ----------------------------------------


@pytest.mark.parametrize(
    "mode, block, listener",
    [
        ("gateway", True, False),
        ("gateway", False, False),
        ("socket", True, False),  # R4.1: suppressed, as in 20.3.0
        ("socket", False, True),  # R3.3: the one config that listens
        ("poll", False, False),
        ("off", False, False),
    ],
)
def test_abuse_only_an_explicit_socket_without_a_block_enables_the_listener(
    tmp_path, mode, block, listener
):
    """R1.2, R3.3, AC1."""
    from the_loop.core import lifecycle

    enabled = lifecycle.enabled_services(config(tmp_path, mode, gateway=block))
    assert enabled["slack-listener"] is listener


def test_socket_beside_a_block_keeps_interactivity(tmp_path):
    """R4.1: the 20.3.0 form keeps working — no listener, buttons still on."""
    slack = parsed(tmp_path, "socket")
    assert slack.gateway and slack.interactive and slack.kickoff_picker


@pytest.mark.parametrize("mode", ["gateway", "socket"])
def test_abuse_channels_listen_refuses_beside_a_block_before_any_token(
    tmp_path, monkeypatch, caplog, mode
):
    """R4.3, AC3: no socket is opened, and the token variables are never read —
    the refusal names the gateway, not a missing token."""
    from the_loop.channels import slack as slack_mod

    read = []
    real_get = slack_mod.os.environ.get

    def spy(key, default=None):
        if "SLACK" in str(key):
            read.append(key)
        return real_get(key, default)

    monkeypatch.setattr(slack_mod.os.environ, "get", spy)
    with caplog.at_level(logging.ERROR, logger="the_loop.channels.slack"):
        assert slack_mod.run_socket_listener(config(tmp_path, mode)) == 1
    assert read == []
    assert "gateway" in caplog.text and "Socket Mode" in caplog.text


def test_channels_listen_refuses_gateway_mode_without_a_block(tmp_path, caplog):
    """R1.2: resolved to `off`, so the existing refusal answers — still no socket."""
    from the_loop.channels import slack as slack_mod

    with caplog.at_level(logging.ERROR, logger="the_loop.channels.slack"):
        assert (
            slack_mod.run_socket_listener(config(tmp_path, "gateway", gateway=False))
            == 1
        )


# -- R6.2 / R6.3: `status` agrees ---------------------------------------------


def test_status_row_names_the_gateway_in_gateway_mode(tmp_path):
    """R6.2: off with the gateway named, never enabled-but-down."""
    from the_loop.core import lifecycle

    cfg = config(tmp_path, "gateway")
    rows = {row["name"]: row for row in lifecycle.ingress_health(cfg)}
    assert rows["slack-listener"]["enabled"] is False
    assert rows["slack-listener"]["detail"] == lifecycle.GATEWAY_OFF
    services = {r["service"]: r for r in lifecycle.status_all(cfg)["services"]}
    assert services["slack-listener"]["detail"] == lifecycle.GATEWAY_OFF


def test_status_row_names_the_missing_block(tmp_path):
    """R6.3: gateway mode with no block — disabled, and the detail says why."""
    from the_loop.core import lifecycle

    cfg = config(tmp_path, "gateway", gateway=False)
    assert lifecycle.listener_off_detail(cfg) == lifecycle.GATEWAY_MISSING
    assert "no gateway block" in lifecycle.GATEWAY_MISSING
    rows = {row["name"]: row for row in lifecycle.ingress_health(cfg)}
    assert rows["slack-listener"]["enabled"] is False
    assert rows["slack-listener"]["detail"] == lifecycle.GATEWAY_MISSING
    services = {r["service"]: r for r in lifecycle.status_all(cfg)["services"]}
    assert services["slack-listener"]["detail"] == lifecycle.GATEWAY_MISSING


def test_the_generic_detail_is_unchanged_for_poll(tmp_path):
    """Behaviour preserved: poll without a block keeps 20.3.0's wording."""
    from the_loop.core import lifecycle

    assert lifecycle.listener_off_detail(config(tmp_path, "poll", gateway=False)) == (
        "channels.slack.enabled is false or read.mode is not socket"
    )


@pytest.mark.parametrize(
    "mode, block, expected",
    [("socket", True, True), ("gateway", True, False), ("socket", False, False)],
)
def test_socket_beside_gateway(tmp_path, mode, block, expected):
    from the_loop.core import lifecycle

    assert (
        lifecycle.socket_beside_gateway(config(tmp_path, mode, gateway=block))
        is expected
    )


@pytest.mark.parametrize("mode, warned", [("socket", True), ("gateway", False)])
def test_the_gateway_client_warns_once_about_socket_beside_it(
    tmp_path, monkeypatch, caplog, mode, warned
):
    """R4.2: the starter logs the migrate warning; `gateway` is quiet."""
    from the_loop.api import ingress

    monkeypatch.setattr(ingress, "_acquire", lambda name, path: (None, "held"))
    with caplog.at_level(logging.WARNING, logger="the_loop.api.ingress"):
        assert ingress._start_gateway_client(config(tmp_path, mode)) == (None, "held")
    hit = "read.mode: gateway" in caplog.text and "migrate-config" in caplog.text
    assert hit is warned


# -- R6.1 / R3.2 / R4.2: `channels status` tells the truth -------------------------


def _channels_status(tmp_path, monkeypatch, capsys, cfg):
    import argparse
    import json

    from the_loop.commands.channels_cmd import ChannelsCommand

    path = tmp_path / "cli-config.yaml"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    return capsys.readouterr().out


def test_channels_status_in_gateway_mode(tmp_path, monkeypatch, capsys):
    """R6.1: `read: gateway`, everything interactive available through the gateway,
    and no app-level-token step — the gateway holds that token."""
    monkeypatch.delenv("THE_LOOP_SLACK_APP_TOKEN", raising=False)
    out = _channels_status(tmp_path, monkeypatch, capsys, config(tmp_path, "gateway"))
    assert "  read:         gateway — events arrive through the gateway client" in out
    assert "https://gateway.example" in out and "no Socket Mode connection" in out
    assert "Approve / Request changes: on · Execute / Do / Start: on" in out
    assert "mint an app-level token" not in out
    assert "  commands:     /the-loop through the gateway" in out
    assert "  mentions:     @the-loop is the address" in out
    assert "through the gateway" in out.split("  shortcuts:")[1].splitlines()[0]
    # The picker is not refused for the read mode (here only for want of a
    # declared repository, which is the kickoff's own rule).
    assert "cannot ask which repository — read.mode" not in out
    assert "[!]" not in out.split("subscribable events")[0]


def test_channels_status_flags_gateway_mode_without_a_block(
    tmp_path, monkeypatch, capsys
):
    """R3.2: nothing reads Slack, and the line says why."""
    out = _channels_status(
        tmp_path, monkeypatch, capsys, config(tmp_path, "gateway", gateway=False)
    )
    assert (
        "[!] read.mode is gateway but no gateway block is configured — nothing "
        "reads Slack"
    ) in out
    assert "  read:         off" in out
    assert "Approve / Request changes: off" in out


def test_channels_status_flags_socket_beside_a_block(tmp_path, monkeypatch, capsys):
    """R4.2: the 20.3.0 form is named and the fix given."""
    out = _channels_status(tmp_path, monkeypatch, capsys, config(tmp_path, "socket"))
    assert "[!] read.mode is socket beside a gateway block" in out
    assert "the-loop migrate-config" in out and "read.mode: gateway" in out


def test_channels_status_socket_without_a_block_is_unchanged(
    tmp_path, monkeypatch, capsys
):
    """Behaviour preserved."""
    out = _channels_status(
        tmp_path, monkeypatch, capsys, config(tmp_path, "socket", gateway=False)
    )
    assert "  commands:     /the-loop over Socket Mode" in out
    assert "beside a gateway block" not in out


def test_channels_status_poll_beside_a_block_names_gateway_as_the_step(
    tmp_path, monkeypatch, capsys
):
    """R6.1: with a block present, the step to turn buttons on is `gateway`."""
    out = _channels_status(tmp_path, monkeypatch, capsys, config(tmp_path, "poll"))
    assert "set channels.slack.read.mode: gateway (now: poll)" in out
    assert "mint an app-level token" not in out
