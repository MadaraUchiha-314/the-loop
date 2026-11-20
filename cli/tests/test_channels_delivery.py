"""The message plan and the delivery step (issue-549, task 9).

Pure over a recording client: order, unfurl flags, the record-before-next-call
rule, resuming from what was already posted, and a 429 retried, never skipped.

Spec: docs/specs/issue-549/design.md § Architecture (stage 4).
"""

from __future__ import annotations

import pytest

from the_loop.channels.base import ChannelError
from the_loop.channels.delivery import (
    RATE_LIMIT_ATTEMPTS,
    THREAD_OF_TOP,
    deliver,
    plan_message,
    retry_after,
)


class _Resp:
    def __init__(self, status, data, headers=None):
        self.status_code, self.data, self.headers = status, data, headers or {}


class Client:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = list(fail or [])  # exceptions raised by the next posts, in order

    def chat_postMessage(self, **params):
        self.calls.append(("post", params))
        if self.fail:
            error = self.fail.pop(0)
            if error is not None:
                raise error
        return {"ok": True, "ts": f"1700.{len(self.calls):06d}"}

    def chat_update(self, **params):
        self.calls.append(("update", params))
        return {"ok": True, "ts": params["ts"]}


def _plan(parts=("one", "two")):
    return plan_message(
        event_id="ev-1",
        channel="C1",
        short_text="Short.",
        short_blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": "Short."}}
        ],
        parts=parts,
        parts_thread=THREAD_OF_TOP,
    )


def _ratelimited(retry="3"):
    from slack_sdk.errors import SlackApiError

    return SlackApiError(
        "ratelimited",
        _Resp(429, {"ok": False, "error": "ratelimited"}, {"Retry-After": retry}),
    )


def test_the_plan_is_the_short_message_then_one_markdown_block_per_part():
    plan = _plan()
    assert plan.top.text == "Short." and plan.top.thread_ts == ""
    assert [p.blocks for p in plan.parts] == [
        ({"type": "markdown", "text": "one"},),
        ({"type": "markdown", "text": "two"},),
    ]
    assert all(p.text == "Short." for p in plan.parts)  # R2.7


def test_no_parts_thread_means_no_long_form():
    plan = plan_message(
        event_id="e",
        channel="C1",
        short_text="s",
        short_blocks=[],
        parts=("a",),
        parts_thread="",
    )
    assert plan.parts == ()


def test_delivery_posts_in_order_with_unfurl_off_and_records_before_the_next_call():
    client = Client()
    seen = []

    def record(delivered):
        seen.append((len(client.calls), delivered.top, delivered.parts))

    delivered = deliver(client, _plan(), record=record)
    assert [params["thread_ts"] for _, params in client.calls] == [
        None,
        "1700.000001",
        "1700.000001",
    ]
    for _, params in client.calls:
        assert params["unfurl_links"] is False and params["unfurl_media"] is False
    # each record lands after its own call and before the next one
    assert seen == [
        (1, "1700.000001", ()),
        (2, "1700.000001", ("1700.000002",)),
        (3, "1700.000001", ("1700.000002", "1700.000003")),
    ]
    assert delivered.parts == ("1700.000002", "1700.000003")


def test_delivery_resumes_after_what_already_landed():
    client = Client()
    already = {"channel": "C1", "top": "1700.9", "parts": ["1700.10"]}
    delivered = deliver(client, _plan(), already=already)
    assert len(client.calls) == 1
    (_, params), *_ = client.calls
    assert params["blocks"] == [{"type": "markdown", "text": "two"}]
    assert params["thread_ts"] == "1700.9"
    assert delivered.parts == ("1700.10", "1700.000001")


def test_a_record_for_another_channel_is_not_honoured():
    client = Client()
    deliver(client, _plan(), already={"channel": "C2", "top": "1700.9", "parts": []})
    assert len(client.calls) == 3


def test_a_429_waits_retry_after_and_retries_the_same_part():
    client = Client(fail=[None, _ratelimited("3")])
    waits = []
    delivered = deliver(client, _plan(), sleep=waits.append)
    assert waits == [3.0]
    texts = [params["blocks"][0].get("text") for _, params in client.calls]
    assert texts[1:] == ["one", "one", "two"]  # part 1 again, never skipped
    assert len(delivered.parts) == 2


def test_a_part_still_rate_limited_fails_the_delivery_and_keeps_what_landed():
    client = Client(fail=[None] + [_ratelimited("0")] * RATE_LIMIT_ATTEMPTS)
    landed = []
    with pytest.raises(ChannelError):
        deliver(client, _plan(), record=landed.append, sleep=lambda s: None)
    assert landed[-1].top == "1700.000001" and landed[-1].parts == ()


def test_retry_after_reads_the_gateway_shape_too():
    from slack_sdk.errors import SlackApiError

    gateway = SlackApiError("x", {"ok": False, "error": "ratelimited"})
    assert retry_after(gateway) == 1.0
    assert retry_after(RuntimeError("boom")) is None


def test_an_edit_updates_the_one_message():
    client = Client()
    plan = plan_message(
        event_id="e", channel="C1", short_text="s", short_blocks=[], edit_ts="1700.5"
    )
    delivered = deliver(client, plan)
    assert client.calls == [
        ("update", {"channel": "C1", "ts": "1700.5", "text": "s", "blocks": []})
    ]
    assert delivered.top == "1700.5" and delivered.edited


# -- progress edits with a long form (issue-549 task 11, R6.2, R6.3) -------------


class EditClient(Client):
    """Records deletes too; ``gone`` names ts values chat.update refuses."""

    def __init__(self, gone=()):
        super().__init__()
        self.gone = set(gone)

    def chat_update(self, **params):
        self.calls.append(("update", params))
        if params["ts"] in self.gone:
            return {"ok": False, "error": "message_not_found"}
        return {"ok": True, "ts": params["ts"]}

    def chat_delete(self, **params):
        self.calls.append(("delete", params))
        return {"ok": True}


def _edit_plan(parts, edit_parts):
    return plan_message(
        event_id="ev-2",
        channel="C1",
        short_text="Short.",
        short_blocks=[],
        parts=parts,
        parts_thread=THREAD_OF_TOP,
        edit_ts="1700.1",
        edit_parts=edit_parts,
    )


def test_an_edit_with_fewer_parts_edits_in_place_and_deletes_the_surplus():
    client = EditClient()
    delivered = deliver(client, _edit_plan(["new one"], ["1700.2", "1700.3", "1700.4"]))
    kinds = [(kind, params.get("ts")) for kind, params in client.calls]
    assert kinds == [
        ("update", "1700.1"),
        ("update", "1700.2"),
        ("delete", "1700.3"),
        ("delete", "1700.4"),
    ]
    assert client.calls[1][1]["blocks"] == [{"type": "markdown", "text": "new one"}]
    assert "unfurl_links" not in client.calls[1][1]  # chat.update takes none
    assert delivered.top == "1700.1" and delivered.parts == ("1700.2",)


def test_an_edit_with_more_parts_posts_the_extra_in_the_thread():
    client = EditClient()
    delivered = deliver(client, _edit_plan(["a", "b", "c"], ["1700.2"]))
    kinds = [kind for kind, _ in client.calls]
    assert kinds == ["update", "update", "post", "post"]
    for _, params in client.calls[2:]:
        assert params["thread_ts"] == "1700.1"
        assert params["unfurl_links"] is False and params["unfurl_media"] is False
    assert delivered.parts[0] == "1700.2" and len(delivered.parts) == 3


def test_a_reply_that_cannot_be_edited_is_posted_fresh():
    client = EditClient(gone={"1700.2"})
    delivered = deliver(client, _edit_plan(["a"], ["1700.2"]))
    kinds = [kind for kind, _ in client.calls]
    assert kinds == ["update", "update", "post"]
    assert delivered.parts != ("1700.2",) and len(delivered.parts) == 1


def test_a_message_that_is_gone_gets_a_new_post_and_its_whole_long_form():
    """R6.3: the old replies belong to the lost message; the new one gets its
    long form posted whole, and nothing of the old one is touched."""
    client = EditClient(gone={"1700.1"})
    delivered = deliver(client, _edit_plan(["a", "b"], ["1700.2", "1700.3"]))
    kinds = [kind for kind, _ in client.calls]
    assert kinds == ["update", "post", "post", "post"]
    assert not delivered.edited
    new_top = delivered.top
    assert all(p["thread_ts"] == new_top for _, p in client.calls[2:])


# -- self-review round 1 (issue-549): an edit Slack rate-limits is retried ------------


class FlakyEditClient(EditClient):
    """``chat.update`` answers with the queued errors first, then succeeds."""

    def __init__(self, update_errors):
        super().__init__()
        self.update_errors = list(update_errors)

    def chat_update(self, **params):
        self.calls.append(("update", params))
        if self.update_errors:
            raise self.update_errors.pop(0)
        return {"ok": True, "ts": params["ts"]}


def test_a_rate_limited_edit_of_the_top_is_retried_never_posted_fresh():
    """A 429 on the progress edit waits and edits again: no second progress
    message (non-functional: idempotent retries)."""
    client = FlakyEditClient([_ratelimited("0")])
    delivered = deliver(client, _edit_plan(["a"], ["1700.2"]), sleep=lambda _s: None)
    kinds = [kind for kind, _ in client.calls]
    assert kinds == ["update", "update", "update"]
    assert delivered.top == "1700.1" and delivered.parts == ("1700.2",)


def test_a_rate_limited_edit_of_a_reply_is_retried_in_place():
    """A 429 on a reply's edit keeps the reply where it is: no copy at the end
    of the thread, no stale part left behind."""
    client = FlakyEditClient([])
    plan = _edit_plan(["a", "b"], ["1700.2", "1700.3"])
    real = client.chat_update
    seen = []

    def update(**params):
        if params["ts"] == "1700.2" and not seen:
            seen.append(1)
            client.calls.append(("update", params))
            raise _ratelimited("0")
        return real(**params)

    client.chat_update = update
    delivered = deliver(client, plan, sleep=lambda _s: None)
    assert "post" not in [kind for kind, _ in client.calls]
    assert delivered.parts == ("1700.2", "1700.3")


def test_an_edit_that_fails_for_another_reason_raises_and_posts_nothing():
    """Only Slack saying the message cannot be edited falls back to a fresh
    post; a timeout raises, so the outbox retries the edit."""
    client = FlakyEditClient([TimeoutError("read timed out")])
    with pytest.raises(ChannelError):
        deliver(client, _edit_plan(["a"], ["1700.2"]), sleep=lambda _s: None)
    assert [kind for kind, _ in client.calls] == ["update"]


def test_a_part_carries_the_short_form_without_the_mentions():
    """R7.4: the mentions open the top message only; a long-form part's text
    fallback is the short form without the preamble."""
    plan = plan_message(
        event_id="ev-3",
        channel="C1",
        short_text="<@U1> <@U2>\nShort.",
        short_blocks=[],
        parts=["one", "two"],
        parts_thread=THREAD_OF_TOP,
        parts_text="Short.",
    )
    assert plan.top.text.startswith("<@U1>")
    assert [part.text for part in plan.parts] == ["Short.", "Short."]


def test_the_posted_memory_keeps_a_live_progress_message_s_record():
    """R6.2 (self-review round 1): past the cap, the newest record of a progress
    message still edited in place is kept, so an edit after many other events
    still finds its replies and never re-posts its long form."""
    from the_loop.channels.state import POSTED_CAP, _posted_map

    records = {
        "progress-1": {"channel": "C1", "top": "1700.1", "parts": ["1700.2"]},
        "progress-2": {"channel": "C1", "top": "1700.1", "parts": ["1700.2"]},
    }
    for n in range(POSTED_CAP + 5):
        records[f"other-{n}"] = {"channel": "C1", "top": f"1800.{n + 1}", "parts": []}
    records["progress-3"] = {"channel": "C1", "top": "1700.1", "parts": ["1700.2"]}
    kept = _posted_map(records, live=["1700.1"])
    # the edit in flight (3) and the one before it (2), which it reads
    assert {"progress-2", "progress-3"} <= set(kept) and "progress-1" not in kept
    assert len(kept) == POSTED_CAP + 2
    assert len(_posted_map(records)) == POSTED_CAP
