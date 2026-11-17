"""End-to-end through the real graph ``notify`` hook on a gateway consumer (issue-532).

The hook publishes on the bus with the config ``build_runtime`` built; before the fix
that config had no ``gateway`` block, so the first post raised "slack: no bot token"
and only the outbox retry (which reloads the full CLI config) reached the gateway. Only
the gateway client's HTTP transport is replaced; the hook, the bus, the Slack channel,
``posting_path``/``outbound_client`` and ``GatewaySlackClient`` are the real ones.

Feature: Graph notifications on a gateway consumer
Requirement: docs/specs/issue-532/bugfix.md

Scenario: a graph notification on a gateway consumer posts through the gateway on the first attempt
  Given a CLI config with a gateway block, an instance name and Slack enabled
  And no Slack bot token in the environment
  When a graph runtime built from that config runs the notify hook
  Then the post is delivered through the gateway under the instance's name
  And nothing is queued in the outbox
"""

from __future__ import annotations

import pytest

from the_loop.channels import outbox
from the_loop.gateway import client as gateway_client
from the_loop.graph import bootstrap
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.sideeffects import notify

BOT_ENV = "THE_LOOP_TEST_532_BOT_TOKEN"
GATEWAY_URL = "http://127.0.0.1:8799"
EVENT = "phase-approval-pending"


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def transport_for(url):
        def transport(verb, path, body, timeout):
            seen.append({"url": url, "verb": verb, "path": path, **body})
            return 200, {"ok": True, "ts": "1700000000.000100", "channel": "C0CENTRAL"}

        return transport

    monkeypatch.setattr(gateway_client, "urllib_transport", transport_for)
    return seen


def test_a_graph_notification_posts_through_the_gateway_first_time(
    tmp_path, monkeypatch, calls
):
    monkeypatch.delenv(BOT_ENV, raising=False)
    cli = {
        "state": {"root": str(tmp_path / "state")},
        "instance": {"name": "laptop-a"},
        "gateway": {"url": GATEWAY_URL},
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "C0CENTRAL",
                "botTokenEnv": BOT_ENV,
                "read": {"mode": "gateway"},
                "subscribe": [EVENT],
            }
        },
    }
    monkeypatch.setattr(bootstrap, "load_cli_config_best_effort", lambda: cli)
    runtime = bootstrap.build_runtime(tmp_path)

    spec = tmp_path / "docs" / "specs" / "issue-532"
    spec.mkdir(parents=True)
    ctx = HookContext(
        work_item=WorkItem(ref="github:octo/repo#532", id="issue-532", spec_dir=spec),
        node={"id": "requirements-approval"},
        boundary="entry",
        repo=tmp_path,
        config=runtime.config,
    )
    ctx.params = {"event": EVENT}

    result = notify(ctx)

    assert result.status == "pass", result.render()
    assert result.data.get("delivered") is True, result.render()
    # The channel opens the work item's thread root, then posts the notification
    # into it — both through the gateway, under this instance's name, first time.
    posts = [c for c in calls if c["method"] == "chat.postMessage"]
    assert [p["params"].get("thread_ts") for p in posts] == [
        None,
        "1700000000.000100",
    ]
    assert EVENT in posts[1]["params"]["text"]
    assert {p["url"] for p in posts} == {GATEWAY_URL}
    assert {p["instance"] for p in posts} == {"laptop-a"}
    assert outbox.entries(runtime.config) == []
