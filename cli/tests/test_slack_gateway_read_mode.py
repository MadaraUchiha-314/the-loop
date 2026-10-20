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
