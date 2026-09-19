"""Unit tests for issue-389: the mention is the address, and three acts each end in
the session. Spec: docs/specs/issue-389/{requirements,design,testing-plan}.md (T1, T6).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from the_loop.channels import slack as slack_mod
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    MENTION,
    MENTION_SHORTCUTS,
    mention_findings,
    probe_subscription,
    subscription_findings,
)

MANIFEST = Path(slack_mod.__file__).with_name("slack-app-manifest.yaml")


# -- task 2: the manifest and the probe (R1.8, R6.1, T6, T10) ----------------------


def test_the_manifest_carries_the_mention_scope_event_and_shortcuts():
    """R1.8, R6.1: the app the guide imports hears a mention and offers the two
    message shortcuts; nothing it carried before is dropped."""
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    scopes = set(manifest["oauth_config"]["scopes"]["bot"])
    events = set(manifest["settings"]["event_subscriptions"]["bot_events"])
    assert MENTION.scope == "app_mentions:read" and MENTION.scope in scopes
    assert MENTION.event == "app_mention" and MENTION.event in events
    assert {"channels:history", "message.channels"} <= scopes | events
    shortcuts = manifest["features"]["shortcuts"]
    declared = {s["callback_id"]: s for s in shortcuts}
    assert set(declared) == set(MENTION_SHORTCUTS)
    for callback_id, shortcut in declared.items():
        assert shortcut["type"] == "message", callback_id
        assert shortcut["name"] and shortcut["description"]


def test_a_missing_mention_scope_is_a_finding_that_names_the_consequence():
    """R1.8: measured, not guessed — and unreadable scopes yield no finding."""
    assert mention_findings(None) == ()
    assert mention_findings(("chat:write", "app_mentions:read")) == ()
    (finding,) = mention_findings(("chat:write", "channels:history"))
    assert "app_mentions:read" in finding and "app_mention" in finding
    assert "nothing typed" in finding


def test_the_probe_appends_the_mention_finding_to_the_kind_finding(
    tmp_path, monkeypatch
):
    """R1.8: the one sentence both `status --probe` and the listener log — the
    mention finding rides after the kind's, never in place of it, and the kind
    findings themselves are untouched (issue-362's tests still pin them)."""
    from test_channels_dm import FakeProbeClient, parsed

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient(
        info={"id": "C123", "is_channel": True}, scopes="chat:write"
    )
    result = probe_subscription(
        parsed(tmp_path, channel="C123"), client_factory=lambda token: client
    )
    assert len(result["findings"]) == 2
    assert "channels:history" in result["findings"][0]
    assert "app_mentions:read" in result["findings"][1]
    assert subscription_findings("C123", ("public",), ("channels:history",)) == ()
