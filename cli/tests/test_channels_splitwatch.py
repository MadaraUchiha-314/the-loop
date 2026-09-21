"""Unit tests for the listener's own split check (issue-413).

The defect: a second Socket Mode consumer holding the app-level token makes
Slack split the app's envelopes between the connections, so roughly half of
everything inbound never reaches this process — and leaves no trace here, because
nothing was offered to it. The only thing this instance can measure is its own
share of what it posted, which is what :class:`SplitWatch` does.

Four questions, one per section
(``docs/specs/issue-413/testing-plan.md`` T1–T4):

1. does a cycle measure, tidy up and stop when asked?
2. does a run of short checks warn once and then only periodically, and does a
   clean check close the ladder?
3. does the state survive the process, keep a rolling window, and stay honest
   about a window that was not clean?
4. does every obstacle answer ``unverifiable`` rather than ``ok`` — and never
   raise?

No network, no sockets: the Slack client is a fake that echoes exactly the beats
a test tells it to.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from the_loop import eventlog
from the_loop.channels import splitwatch
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    HEARTBEAT_MARKER,
    SlackChannelConfig,
)
from the_loop.channels.splitwatch import (
    ESCALATE_EVERY,
    RETAINED,
    SPLIT_CAVEAT,
    SPLIT_REMEDY,
    SplitState,
    SplitWatch,
    read_state,
    split_lines,
    summary_line,
)


# -- fakes ---------------------------------------------------------------------------


class FakeClient:
    """``chat.postMessage`` / ``chat.delete``, recorded — and, standing in for
    Slack, the echo: a posted heartbeat is handed straight back to the watch
    when ``echo`` says this beat landed here rather than on the phantom."""

    def __init__(self, echo=lambda index: True, watch=None, raises=None):
        self.echo = echo
        self.watch = watch
        self.raises = raises
        self.posted = []
        self.deleted = []

    def chat_postMessage(self, *, channel, text):
        if self.raises is not None:
            raise self.raises
        index = len(self.posted)
        ts = f"1700000000.{index:06d}"
        self.posted.append({"channel": channel, "text": text, "ts": ts})
        if self.echo(index) and self.watch is not None:
            self.watch.observe(text.split()[-1])
        return {"ok": True, "ts": ts}

    def chat_delete(self, *, channel, ts):
        self.deleted.append({"channel": channel, "ts": ts})
        return {"ok": True}


def config(**read):
    return SlackChannelConfig.from_mapping(
        {
            "channels": {
                "slack": {
                    "enabled": True,
                    "channel": "C0CENTRAL",
                    "read": {"mode": "socket", **read},
                }
            }
        }
    )


def watch(tmp_path, *, echo=lambda index: True, beats=2, raises=None, **kwargs):
    """A watch wired to a fake client that echoes what ``echo`` allows."""
    client = FakeClient(echo=echo, raises=raises)
    made = SplitWatch(
        tmp_path / "slack-split.json",
        client=client,
        config=kwargs.pop("config", config()),
        beats=beats,
        window_seconds=kwargs.pop("window_seconds", 0.3),
        interval_seconds=kwargs.pop("interval_seconds", 900),
        nonce_factory=_nonces(),
        **kwargs,
    )
    made._channel = kwargs.get("channel", "C0CENTRAL")
    client.watch = made
    return made, client


def _nonces():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return f"{counter['n']:016x}"

    return factory


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")


@pytest.fixture
def events(tmp_path):
    """The event log, configured so `emit` is not a no-op, as a list reader."""
    path = tmp_path / "events.jsonl"
    eventlog.configure("channels", path=path, enabled=True)
    yield lambda: [
        json.loads(line)
        for line in (path.read_text().splitlines() if path.exists() else [])
        if line.strip()
    ]
    eventlog.reset()


# -- T1: one cycle measures, tidies up, and stops when asked -------------------------


def test_every_echo_back_is_ok(tmp_path):
    """Nothing is lost: the watch heard back every beat it posted."""
    made, client = watch(tmp_path)
    state = made.run_cycle()
    assert state.verdict == "ok"
    assert (state.beats, state.echoed) == (2, 2)
    assert [post["channel"] for post in client.posted] == ["C0CENTRAL"] * 2
    assert all(
        post["text"].startswith(HEARTBEAT_MARKER + " ") for post in client.posted
    )


def test_a_withheld_echo_is_split_suspected(tmp_path):
    """One beat landing on the phantom is exactly what a split does to us."""
    made, _ = watch(tmp_path, echo=lambda index: index == 0)
    state = made.run_cycle()
    assert state.verdict == "split-suspected"
    assert (state.beats, state.echoed) == (2, 1)


def test_the_room_keeps_no_litter(tmp_path):
    """Every heartbeat that got a ts is deleted again, echoed or not."""
    made, client = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    assert [d["ts"] for d in client.deleted] == [p["ts"] for p in client.posted]


def test_a_failed_delete_does_not_move_the_verdict(tmp_path):
    """The measurement already happened; litter is a debug line, not a finding."""
    made, client = watch(tmp_path)
    client.chat_delete = lambda **_: (_ for _ in ()).throw(RuntimeError("no perms"))
    assert made.run_cycle().verdict == "ok"


def test_a_stopping_listener_abandons_the_window(tmp_path):
    """A half-measured window is not evidence of anything, so nothing is written."""
    stop = threading.Event()
    stop.set()
    made, client = watch(tmp_path, echo=lambda index: False, window_seconds=30)
    state = made.run_cycle(stop_event=stop)
    assert state.verdict == ""
    assert not Path(made.path).exists()
    # It still tidied up what it posted.
    assert len(client.deleted) == len(client.posted) == 2


# -- T2: the escalation ladder -------------------------------------------------------


def test_the_first_short_check_warns(tmp_path, events):
    made, _ = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    warnings = [e for e in events() if e["event"] == "channel.split_suspected"]
    assert len(warnings) == 1
    record = warnings[0]
    assert record["level"] == "warning"
    assert (record["beats"], record["echoed"], record["consecutive"]) == (2, 0, 1)
    assert record["channel_id"] == "C0CENTRAL"
    assert record["remedy"] == SPLIT_REMEDY


def test_a_run_of_short_checks_is_not_a_storm(tmp_path, events):
    """One warning, then silence until the ESCALATE_EVERY-th — a split lasts
    hours, and an operator who is warned every 15 minutes stops reading."""
    made, _ = watch(tmp_path, echo=lambda index: False)
    for _ in range(ESCALATE_EVERY):
        made.run_cycle()
    warned = [e for e in events() if e["event"] == "channel.split_suspected"]
    assert [e["consecutive"] for e in warned] == [1, ESCALATE_EVERY]


def test_a_clean_check_closes_the_ladder(tmp_path, events):
    made, client = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    client.echo = lambda index: True
    state = made.run_cycle()
    assert state.consecutive_short == 0
    cleared = [e for e in events() if e["event"] == "channel.split_cleared"]
    assert len(cleared) == 1
    assert cleared[0]["after"] == 1
    assert cleared[0]["level"] == "info"


def test_a_clean_check_after_a_clean_check_says_nothing(tmp_path, events):
    made, _ = watch(tmp_path)
    made.run_cycle()
    made.run_cycle()
    assert not [e for e in events() if e["event"].startswith("channel.split")]


# -- T3: the state file and the rolling window ---------------------------------------


def test_the_state_outlives_the_process(tmp_path):
    """The whole point: a finding that dies with its process reaches nobody."""
    made, _ = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    state = read_state(made.path)
    assert state is not None
    assert (state.verdict, state.echoed, state.interval_seconds) == (
        "split-suspected",
        0,
        900,
    )
    # A second watch on the same path continues the counters rather than
    # restarting them, so a restart does not reset the ladder.
    again, _ = watch(tmp_path, echo=lambda index: False)
    assert again.run_cycle().consecutive_short == 2


def test_the_window_keeps_the_newest_verdicts(tmp_path):
    made, _ = watch(tmp_path)
    for _ in range(RETAINED + 3):
        made.run_cycle()
    state = read_state(made.path)
    assert state is not None
    assert len(state.recent) == RETAINED
    assert set(state.recent) == {"ok"}
    assert state.checks == RETAINED + 3


def test_one_clean_check_does_not_hide_a_flapping_split(tmp_path):
    """The reporter's own evidence was 2/3 → 1/3 → 3/3 → 1/3. A report that
    cleared on the first `ok` would have hidden the incident from an operator
    half the times they looked."""
    made, client = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    client.echo = lambda index: True
    state = made.run_cycle()
    assert state.verdict == "ok"
    assert state.suspected and state.flapping


def test_a_full_clean_window_goes_quiet(tmp_path):
    made, client = watch(tmp_path, echo=lambda index: False)
    state = made.run_cycle()
    client.echo = lambda index: True
    for _ in range(RETAINED):
        state = made.run_cycle()
    assert not state.suspected


def test_an_absent_or_corrupt_state_reads_as_nothing(tmp_path):
    assert read_state(tmp_path / "missing.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert read_state(broken) is None
    listy = tmp_path / "listy.json"
    listy.write_text("[]", encoding="utf-8")
    assert read_state(listy) is None
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert read_state(empty) is None


def test_an_unwritable_path_warns_once_and_keeps_measuring(tmp_path, caplog):
    made, _ = watch(tmp_path / "state")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "slack-split.json").mkdir()  # a directory, not a file
    with caplog.at_level("WARNING"):
        assert made.run_cycle().verdict == "ok"
        assert made.run_cycle().verdict == "ok"
    warnings = [r for r in caplog.records if "slack split state" in r.getMessage()]
    assert len(warnings) == 1


# -- T4: every obstacle is unverifiable, never ok ------------------------------------


def test_no_channel_is_unverifiable(tmp_path):
    made, client = watch(tmp_path)
    made._channel = ""
    made._config = SlackChannelConfig.from_mapping(
        {"channels": {"slack": {"enabled": True, "read": {"mode": "socket"}}}}
    )
    state = made.run_cycle()
    assert state.verdict == "unverifiable"
    assert "channels.slack.channel is unset" in state.reason
    assert client.posted == []


def test_a_channel_that_resolves_to_nothing_is_unverifiable(tmp_path):
    made, client = watch(tmp_path)
    made._channel = ""
    made._config = SlackChannelConfig.from_mapping(
        {
            "channels": {
                "slack": {
                    "enabled": True,
                    "channel": "#nowhere",
                    "read": {"mode": "socket"},
                }
            }
        }
    )
    state = made.run_cycle()
    assert state.verdict == "unverifiable"
    assert "resolves to no channel" in state.reason
    assert client.posted == []


def test_no_bot_token_is_unverifiable(tmp_path, monkeypatch):
    monkeypatch.delenv(DEFAULT_BOT_TOKEN_ENV, raising=False)
    made, client = watch(tmp_path)
    state = made.run_cycle()
    assert state.verdict == "unverifiable"
    assert DEFAULT_BOT_TOKEN_ENV in state.reason
    assert client.posted == []


def test_a_client_that_raises_is_unverifiable(tmp_path):
    made, _ = watch(tmp_path, raises=RuntimeError("ratelimited"))
    state = made.run_cycle()
    assert state.verdict == "unverifiable"
    assert "ratelimited" in state.reason


def test_an_unverifiable_check_does_not_clear_a_finding(tmp_path):
    """A check that could not run is not evidence either way; counting it as
    clean would retire a real finding on a rate limit."""
    made, client = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    client.raises = RuntimeError("ratelimited")
    state = made.run_cycle()
    assert state.verdict == "unverifiable"
    assert state.consecutive_short == 1 and state.suspected


def test_the_check_is_off_when_the_operator_says_so(tmp_path):
    assert (
        SplitWatch.for_config(
            {
                "state": {"root": str(tmp_path)},
                "channels": {
                    "slack": {
                        "enabled": True,
                        "channel": "C0CENTRAL",
                        "read": {"mode": "socket", "splitCheckBeats": 0},
                    }
                },
            },
            client=FakeClient(),
        )
        is None
    )


def test_a_disabled_channel_has_no_watch(tmp_path):
    assert (
        SplitWatch.for_config(
            {"state": {"root": str(tmp_path)}, "channels": {"slack": {}}},
            client=FakeClient(),
        )
        is None
    )


def test_for_config_takes_the_configured_beats_and_cadence(tmp_path):
    made = SplitWatch.for_config(
        {
            "state": {"root": str(tmp_path)},
            "channels": {
                "slack": {
                    "enabled": True,
                    "channel": "C0CENTRAL",
                    "read": {
                        "mode": "socket",
                        "splitCheckBeats": 4,
                        "catchUpSeconds": 120,
                    },
                }
            },
        },
        client=FakeClient(),
    )
    assert made is not None
    assert (made.beats, made.interval_seconds) == (4, 120)
    assert made.path.name == "slack-split.json"


# -- rendering -----------------------------------------------------------------------


def test_nothing_is_said_about_a_clean_deployment(tmp_path):
    made, _ = watch(tmp_path)
    made.run_cycle()
    assert split_lines(read_state(made.path)) == []
    assert summary_line(None) == ""


def test_the_report_names_the_measurement_the_caveat_and_the_remedy(tmp_path):
    made, _ = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    lines = split_lines(read_state(made.path))
    assert len(lines) == 3
    assert "0/2 heartbeats reached the listener" in lines[0]
    assert lines[1] == SPLIT_CAVEAT
    assert lines[2] == SPLIT_REMEDY
    assert "rotate the token" in lines[2]


def test_the_cadence_line_says_what_is_configured(tmp_path):
    made, _ = watch(tmp_path)
    assert "not run yet" in splitwatch.cadence_line(None, config())
    made.run_cycle()
    line = splitwatch.cadence_line(read_state(made.path), config())
    assert "2 heartbeat(s) every 900s" in line and "2/2" in line
    assert "1 retained, none short" in line
    assert "off (channels.slack.read.splitCheckBeats: 0)" == splitwatch.cadence_line(
        None, config(splitCheckBeats=0)
    )
    assert "at connect only" in splitwatch.cadence_line(None, config(catchUpSeconds=0))


def test_the_cadence_line_never_contradicts_the_finding(tmp_path):
    """It counts the window it is describing, not the lifetime total — a line
    reading "none short" above a `[!]` naming four is one an operator stops
    trusting."""
    made, client = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    client.echo = lambda index: True
    made.run_cycle()
    line = splitwatch.cadence_line(read_state(made.path), config())
    assert "2 retained, 1 short" in line


def test_an_unverifiable_last_check_says_why(tmp_path):
    made, _ = watch(tmp_path, raises=RuntimeError("ratelimited"))
    made.run_cycle()
    line = splitwatch.cadence_line(read_state(made.path), config())
    assert "unverifiable: could not post the heartbeat" in line


def test_the_state_carries_ids_counts_and_times_only(tmp_path, monkeypatch):
    """Pasted into a ticket, the file must reveal nothing the workspace does not
    already know — and never a token."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-SECRETVALUE")
    made, _ = watch(tmp_path, echo=lambda index: False)
    made.run_cycle()
    raw = Path(made.path).read_text(encoding="utf-8")
    assert "SECRETVALUE" not in raw and "xoxb-" not in raw
    assert HEARTBEAT_MARKER not in raw
    assert set(json.loads(raw)) == set(SplitState().to_mapping())
