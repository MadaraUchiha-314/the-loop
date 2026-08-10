"""The webhook URL an operator configures is the URL a notification reaches.

Feature: Slack notifications are configurable inside the-loop's own config

The unit tests in ``test_graph_integrations.py`` pin ``_url()``'s precedence.
What they cannot show is the whole path issue-203 was actually about: a value
written in ``.the-loop/cli-config.yaml`` travelling through ``resolve()`` and the
``notify`` hook to the HTTP request that carries it. That path is what env-only
configuration broke — never the resolver, always the wiring — so it gets a test
of its own.

The Slack HTTP boundary is faked in-process (``urllib.request.urlopen`` is
patched): the-loop does not test Slack, it tests where it points.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.sideeffects import notify

INLINE = "https://hooks.slack.example/inline"
FROM_ENV = "https://hooks.slack.example/from-env"


@pytest.fixture
def posted(monkeypatch) -> List[Dict[str, Any]]:
    """Every request the webhook transport would have sent."""
    sent: List[Dict[str, Any]] = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def _urlopen(request, timeout=None):
        sent.append(
            {"url": request.full_url, "body": json.loads(request.data.decode())}
        )
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    return sent


def _ctx(tmp_path: Path, slack: Dict[str, Any]) -> HookContext:
    spec = tmp_path / "docs" / "specs" / "issue-203"
    spec.mkdir(parents=True, exist_ok=True)
    return HookContext(
        work_item=WorkItem(ref="github:o/r#203", id="issue-203", spec_dir=spec),
        node={"id": "needs-review"},
        boundary="entry",
        repo=tmp_path,
        config={
            "integrations": {"slack": dict(slack, transport="webhook")},
            "notifications": {"events": {"phase-approval-pending": ["approver"]}},
        },
    )


def test_a_notification_is_delivered_to_the_url_configured_inline(
    tmp_path, monkeypatch, posted
):
    """
    Feature: Slack notifications are configurable inside the-loop's own config
    Scenario: a notification is delivered to the URL configured inline
      Given a CLI config whose integrations.slack.url holds a webhook URL
      And an environment that also exports THE_LOOP_SLACK_WEBHOOK_URL
      When a node's notify hook runs for a configured event
      Then the request goes to the configured URL, not the exported one
      And the hook reports the notification as delivered
    Requirement: docs/specs/issue-203/requirements.md#R1
    """
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    result = notify(_ctx(tmp_path, {"url": INLINE}))
    assert result.data["delivered"] is True, result.data.get("error")
    assert [request["url"] for request in posted] == [INLINE]
    assert "issue-203" in posted[0]["body"]["text"]


def test_a_configuration_with_no_inline_url_still_reads_the_environment(
    tmp_path, monkeypatch, posted
):
    """
    Feature: Slack notifications are configurable inside the-loop's own config
    Scenario: a configuration with no inline url still reads the environment
      Given a CLI config that names an env var and sets no inline URL
      And that variable is exported
      When a node's notify hook runs for a configured event
      Then the request goes to the exported URL, exactly as before issue-203
    Requirement: docs/specs/issue-203/requirements.md#R3
    """
    monkeypatch.setenv("THE_LOOP_SLACK_WEBHOOK_URL", FROM_ENV)
    result = notify(_ctx(tmp_path, {}))
    assert result.data["delivered"] is True, result.data.get("error")
    assert [request["url"] for request in posted] == [FROM_ENV]


def test_with_neither_source_nothing_is_posted_and_the_graph_continues(
    tmp_path, monkeypatch, posted
):
    """
    Feature: Slack notifications are configurable inside the-loop's own config
    Scenario: an unresolvable webhook url fails closed without wedging the graph
      Given a CLI config with no inline URL and no exported variable
      When a node's notify hook runs for a configured event
      Then no request is made
      And the hook passes, recording the failure and naming both remedies
    Requirement: docs/specs/issue-203/requirements.md#R2
    """
    monkeypatch.delenv("THE_LOOP_SLACK_WEBHOOK_URL", raising=False)
    result = notify(_ctx(tmp_path, {}))
    assert result.status == "pass", "a channel outage never wedges the graph"
    assert result.data["delivered"] is False
    assert "integrations.slack.url" in result.data["error"]
    assert "THE_LOOP_SLACK_WEBHOOK_URL" in result.data["error"]
    assert posted == []
