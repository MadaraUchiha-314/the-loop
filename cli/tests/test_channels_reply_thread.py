"""The reply thread's place in the room-delivery memory (issue-507).

Spec: docs/specs/issue-507/testing-plan.md T1.
"""

from __future__ import annotations

import pytest

from the_loop.channels import room_policy
from the_loop.channels.state import _delivery_record


def test_the_delivery_record_keeps_the_reply_thread():
    record = _delivery_record({"replyChannel": "C0ROOM", "replyThread": "1700.000100"})

    assert (record["replyChannel"], record["replyThread"]) == ("C0ROOM", "1700.000100")


def test_a_malformed_reply_thread_coerces_to_empty():
    record = _delivery_record({"replyChannel": None, "replyThread": 0})

    assert (record["replyChannel"], record["replyThread"]) == ("", "")


def test_migration_a_record_written_before_issue_507_has_no_reply_thread():
    record = _delivery_record({"lastEvent": "phase.started", "gateTs": {"a": "1.2"}})

    assert (record["replyChannel"], record["replyThread"]) == ("", "")
    assert record["gateTs"] == {"a": "1.2"}


@pytest.mark.parametrize(
    "event_type, expected",
    [
        ("phase.progress", True),
        ("session.progress", True),
        ("review.progress", True),
        ("comment.agent", False),
        ("phase.started", False),
        ("phase-approval-pending", False),
    ],
)
def test_is_progress(event_type, expected):
    assert room_policy.is_progress(event_type) is expected


@pytest.mark.parametrize(
    "thread, channel",
    [({"bad": "value"}, "C0ROOM"), ("not-a-ts", "C0ROOM"), ("1700.000100", ["C0"])],
)
def test_a_truthy_malformed_reply_thread_coerces_to_empty(thread, channel):
    """Critic C3: a malformed value never reaches Slack as a thread_ts."""
    record = _delivery_record({"replyChannel": channel, "replyThread": thread})

    assert record["replyThread"] == "" or record["replyChannel"] == ""
