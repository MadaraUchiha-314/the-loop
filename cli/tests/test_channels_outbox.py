"""Unit tests for the undelivered-event outbox (issue-409).

The bus used to throw away a fan-out that reached nobody. These drive the file
that now remembers it: what is queued and what is not, the cap, the backoff, the
drain's claim-post-settle cycle, and the two rules the security design rests on —
the drain never records, and the event log never carries the message text.
No network: channels are fakes and the state root is a ``tmp_path``.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from the_loop import eventlog
from the_loop.channels import outbox
from the_loop.channels.base import ChannelError, Event, PostResult
from the_loop.identity import Principal

PERSON = Principal(ids={"github": "octocat", "slack": "U1"}, name="Octo")


def config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}, "channels": {"slack": {}}}


def an_event(event_type="session.awaiting_input", source="cli", **kw):
    return Event(
        event_type=event_type,
        work_item=kw.pop("work_item", "github:o/r#7"),
        text=kw.pop("text", "A or B?"),
        source=source,
        **kw,
    )


def refused(channel="slack", error="channel_not_found"):
    return [PostResult(channel=channel, ok=False, error=error)]


class FakeChannel:
    """A subscriber that records what it was handed, and may refuse."""

    def __init__(self, subscribe=("session.awaiting_input",), fail="", name="slack"):
        self.name = name
        self._subscribe = set(subscribe)
        self.fail = fail
        self.posted = []

    def subscribes(self, event_type):
        return event_type in self._subscribe

    def may_publish(self, event_type):
        return False

    def post(self, event):
        if self.fail == "raise":
            raise RuntimeError("down")
        if self.fail:
            return PostResult(channel=self.name, ok=False, error=self.fail)
        self.posted.append(event)
        return PostResult(channel=self.name, ok=True, thread="t1")


@pytest.fixture
def log(tmp_path):
    """Module-level emits, routed somewhere readable for the test's duration."""
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    return path


def events_in(path, name):
    return [row for row in eventlog.read_events(path) if row["event"] == name]


# -- what is queued, and what is not (R1) ---------------------------------------------


def test_an_event_no_channel_took_is_queued_with_everything_needed_to_repost(
    tmp_path, log
):
    """R1.1, R1.4 — the entry carries the event, the channels asked and the error."""
    assert outbox.remember(
        an_event(actor=PERSON, url="https://gh/c/1", detail={"actor": "octocat"}),
        refused(),
        config(tmp_path),
    )
    queued = outbox.entries(config(tmp_path))
    assert len(queued) == 1
    entry = queued[0]
    assert entry["channels"] == ["slack"]
    assert entry["lastError"] == "slack: channel_not_found"
    assert entry["attempts"] == 0 and entry["at"]
    assert entry["event"]["eventType"] == "session.awaiting_input"
    assert entry["event"]["text"] == "A or B?"
    assert entry["event"]["url"] == "https://gh/c/1"
    assert entry["event"]["actor"] == {
        "ids": {"github": "octocat", "slack": "U1"},
        "name": "Octo",
    }
    warned = events_in(log, "channel.undelivered")
    assert warned and warned[0]["level"] == "warning"
    assert warned[0]["pending"] == 1 and warned[0]["channels"] == ["slack"]
    assert "A or B" not in json.dumps(warned)  # R4.1: ids and counts, never the text


def test_an_event_round_trips_through_the_file(tmp_path):
    """R1.4 — what comes back out is what the channel would have been handed."""
    original = an_event(
        "work-item.reply", source="slack", text="ship it", actor=PERSON, summary="s"
    )
    outbox.remember(original, refused(), config(tmp_path))
    restored = outbox._event_from(outbox.entries(config(tmp_path))[0]["event"])
    assert restored == original


def test_a_file_from_another_version_loads_with_what_it_has(tmp_path):
    """R1.4, T9 — unknown keys ignored, missing keys defaulted, never a raise."""
    path = outbox.path_for(config(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 99,
                "pending": {
                    "a": {"event": {"eventType": "x"}, "tomorrow": True},
                    "b": "not an entry",
                },
            }
        )
    )
    queued = outbox.entries(config(tmp_path))
    assert [entry["id"] for entry in queued] == ["a"]
    assert queued[0]["attempts"] == 0 and queued[0]["channels"] == []


@pytest.mark.parametrize("junk", ["", "{", "[]", '{"pending": 3}'])
def test_an_unreadable_outbox_reads_as_an_empty_one(tmp_path, junk):
    """R3.4 — a backlog nobody can read is not one anybody can act on."""
    path = outbox.path_for(config(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(junk)
    assert outbox.entries(config(tmp_path)) == []
    assert outbox.summary(config(tmp_path))["pending"] == 0


def test_an_unwritable_outbox_is_false_never_an_exception(tmp_path, monkeypatch):
    """R1.6 — a failed queue never changes what publish returns."""
    monkeypatch.setattr(
        outbox, "_save", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only"))
    )
    assert outbox.remember(an_event(), refused(), config(tmp_path)) is False


def test_the_cap_drops_the_oldest_and_says_so(tmp_path, log):
    """R1.5 — bounded at rest; the alternative is a file that grows all outage."""
    cfg = config(tmp_path)
    for index in range(outbox.OUTBOX_CAP + 3):
        outbox.remember(an_event(text=f"q{index}"), refused(), cfg)
    queued = outbox.entries(cfg)
    assert len(queued) == outbox.OUTBOX_CAP
    assert queued[0]["event"]["text"] == "q3"  # the three oldest went
    dropped = events_in(log, "channel.undelivered_dropped")
    assert len(dropped) == 3 and dropped[0]["level"] == "warning"
    assert dropped[0]["cap"] == outbox.OUTBOX_CAP


def test_the_summary_is_what_status_prints(tmp_path):
    """R3.1 — the count, the age of the oldest, the newest error."""
    cfg = config(tmp_path)
    assert outbox.summary(cfg) == {
        "pending": 0,
        "oldest": "",
        "waitedSeconds": 0,
        "lastError": "",
    }
    outbox.remember(an_event(), refused(error="rate_limited"), cfg)
    outbox.remember(an_event(), refused(error="channel_not_found"), cfg)
    report = outbox.summary(cfg)
    assert report["pending"] == 2
    assert report["lastError"] == "slack: channel_not_found"
    assert report["channels"] == ["slack"] and report["oldest"]


# -- the drain (R2) -------------------------------------------------------------------


def test_a_drained_entry_a_channel_takes_is_removed_and_reported(tmp_path, log):
    """R2.2 — delivered late is delivered: the entry goes, with one line."""
    cfg = config(tmp_path)
    outbox.remember(an_event(actor=PERSON), refused(), cfg)
    channel = FakeChannel()
    assert outbox.drain(cfg, channels=[channel]) == {
        "attempted": 1,
        "delivered": 1,
        "pending": 0,
    }
    assert [event.text for event in channel.posted] == ["A or B?"]
    assert channel.posted[0].actor == PERSON  # rendered as the original would have been
    late = events_in(log, "channel.delivered_late")
    assert late and late[0]["attempts"] == 1
    assert outbox.entries(cfg) == []


def test_a_refused_entry_keeps_its_attempt_its_error_and_its_backoff(tmp_path):
    """R2.3 — and the second cycle inside the backoff attempts nothing."""
    cfg = config(tmp_path)
    outbox.remember(an_event(), refused(), cfg)
    assert outbox.drain(cfg, channels=[FakeChannel(fail="still down")]) == {
        "attempted": 1,
        "delivered": 0,
        "pending": 1,
    }
    entry = outbox.entries(cfg)[0]
    assert entry["attempts"] == 1 and entry["lastError"] == "still down"
    assert entry["lastAttemptAt"]
    assert outbox.drain(cfg, channels=[FakeChannel()])["attempted"] == 0
    later = outbox._utcnow() + timedelta(seconds=outbox.RETRY_BASE_SECONDS + 1)
    assert outbox.drain(cfg, channels=[FakeChannel()], now=later)["delivered"] == 1


def test_the_backoff_doubles_and_is_capped(tmp_path):
    """R2.3 — one attempt a minute at first, one an hour once it has given up."""
    now = outbox._utcnow()
    record = {"attempts": 1, "lastAttemptAt": outbox._stamp(now)}
    assert not outbox._due(record, now + timedelta(seconds=30))
    assert outbox._due(record, now + timedelta(seconds=61))
    record["attempts"] = 3
    assert not outbox._due(record, now + timedelta(seconds=200))
    assert outbox._due(record, now + timedelta(seconds=241))
    record["attempts"] = 40  # far past the cap, and still an hour, not a century
    assert outbox._due(record, now + timedelta(seconds=outbox.RETRY_MAX_SECONDS + 1))


def test_one_cycle_attempts_at_most_its_budget_and_one_bad_entry_stops_nothing(
    tmp_path,
):
    """R2.5 — the backlog is drained oldest first, in bounded bites."""
    cfg = config(tmp_path)
    for index in range(5):
        outbox.remember(an_event(text=f"q{index}"), refused(), cfg)
    assert outbox.drain(cfg, channels=[FakeChannel()], budget=2) == {
        "attempted": 2,
        "delivered": 2,
        "pending": 3,
    }
    assert [e["event"]["text"] for e in outbox.entries(cfg)] == ["q2", "q3", "q4"]
    # A provider that raises on one entry is that entry's failure, not the cycle's.
    raising = FakeChannel(fail="raise")
    assert outbox.drain(cfg, channels=[raising])["delivered"] == 0
    assert len(outbox.entries(cfg)) == 3


def test_the_drain_posts_where_publish_would_have_and_never_records(
    tmp_path, monkeypatch
):
    """R2.4 — a replayed entry can never write a comment or answer a gate."""
    monkeypatch.setattr(
        "the_loop.channels.bus.publish",
        lambda *a, **k: pytest.fail("the drain must never go through the bus"),
    )
    cfg = config(tmp_path)
    outbox.remember(an_event(source="slack"), refused(), cfg)
    source = FakeChannel(name="slack")
    elsewhere = FakeChannel(name="teams")
    unsubscribed = FakeChannel(name="email", subscribe=("comment.human",))
    outbox.drain(cfg, channels=[source, elsewhere, unsubscribed])
    assert source.posted == [] and unsubscribed.posted == []  # source, and unasked
    assert len(elsewhere.posted) == 1


def test_an_entry_naming_no_event_leaves_the_queue(tmp_path):
    """A record the CLI cannot read is dropped, never retried forever."""
    cfg = config(tmp_path)
    path = outbox.path_for(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "pending": {"a": {"event": {}}}}))
    assert outbox.drain(cfg, channels=[FakeChannel()])["delivered"] == 0
    assert outbox.entries(cfg) == []


def test_draining_an_empty_outbox_costs_nothing(tmp_path):
    assert outbox.drain(config(tmp_path), channels=[FakeChannel()]) == {
        "attempted": 0,
        "delivered": 0,
        "pending": 0,
    }


# -- the drainer thread (R2.1, R2.6) --------------------------------------------------


def test_the_drainer_needs_channels_and_survives_a_raising_cycle(tmp_path, monkeypatch):
    """R2.1, R2.6 — no channels, no thread; a bad cycle never ends the daemon's."""
    import threading

    assert outbox.start_drainer({"state": {}}, threading.Event()) is None

    cycles = []

    def boom(_config):
        cycles.append(1)
        if len(cycles) == 1:
            raise RuntimeError("provider on fire")

    monkeypatch.setattr(outbox, "drain", boom)
    stop = threading.Event()
    thread = outbox.start_drainer(config(tmp_path), stop, interval_override=0.01)
    assert thread is not None
    for _ in range(200):
        if len(cycles) >= 3:
            break
        threading.Event().wait(0.01)
    stop.set()
    thread.join(timeout=2)
    assert len(cycles) >= 3  # it kept going after the first cycle raised


def test_a_channel_error_is_the_entrys_failure(tmp_path):
    """The bus's own rule: a ChannelError is a result, never an exception."""
    cfg = config(tmp_path)
    outbox.remember(an_event(), refused(), cfg)

    class Angry(FakeChannel):
        def post(self, event):
            raise ChannelError("slack: boom")

    assert outbox.drain(cfg, channels=[Angry()])["delivered"] == 0
    assert outbox.entries(cfg)[0]["lastError"] == "slack: boom"
