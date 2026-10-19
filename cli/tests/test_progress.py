"""`the-loop progress` — a session's non-blocking status line (issue-340).

The core verb (label gate, rate limit, shortening, the event it emits), its HTTP
binding and the CLI's routing choice. The Slack side — the one live line a room keeps —
is pinned in test_room_policy.py and test_channels_declared_integration.py.

Spec: docs/specs/issue-340/testing-plan.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.api.app import create_app
from the_loop.channels import bus as channel_bus
from the_loop.channels.base import PostResult
from the_loop.cli import main
from the_loop.core import progress as core_progress

REF = "github:octo/repo#340"


def _config(tmp_path, **progress):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    if progress:
        config["progress"] = progress
    return config


@pytest.fixture
def labels(monkeypatch):
    """The work item's labels, as its tracker reports them."""
    carried = {"labels": ["the-loop: progress"], "reads": 0, "error": None}

    def fake(ref, config):
        carried["reads"] += 1
        if carried["error"]:
            raise carried["error"]
        return list(carried["labels"])

    monkeypatch.setattr(core_progress, "_labels_of", fake)
    return carried


@pytest.fixture
def published(monkeypatch):
    """Every event the verb hands the bus."""
    events = []

    def fake_publish(event, cli_config=None, **kwargs):
        events.append((event, kwargs))
        return channel_bus.PublishResult(
            record=None, posts=[PostResult(channel="slack", ok=True)]
        )

    monkeypatch.setattr(channel_bus, "publish", fake_publish)
    return events


@pytest.fixture
def log(tmp_path):
    """A real event log, so the rate limit reads what the verb wrote."""
    path = tmp_path / ".the-loop" / "logs" / "events.jsonl"
    eventlog.configure("progress", path=path)
    yield path
    eventlog.reset()


def _emitted(path):
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return [r for r in rows if r["event"] == "session.progress"]


# -- shortening ----------------------------------------------------------------


def test_a_report_is_cut_to_two_lines_and_collapsed():
    """
    Feature: progress reports are short by construction
      Scenario: an agent writes a paragraph
        Given a report of four lines with ragged whitespace and a blank line
        When it is shortened
        Then only the first two non-empty lines remain, each on one line
    """
    text = "  Wiring   the retry\n\n   into the poller \nthen tests\nthen docs"
    assert core_progress.shorten(text) == "Wiring the retry\ninto the poller"


def test_a_long_report_is_truncated_with_an_ellipsis():
    out = core_progress.shorten("x" * 500, max_chars=40)
    assert len(out) == 40 and out.endswith("…")


# -- config --------------------------------------------------------------------


def test_the_config_defaults_and_ignores_malformed_values():
    assert core_progress.ProgressConfig.from_config({}).label == "the-loop: progress"
    cfg = core_progress.ProgressConfig.from_config(
        {"progress": {"label": 7, "minIntervalSeconds": -1, "maxChars": "lots"}}
    )
    assert cfg.label == core_progress.DEFAULT_LABEL
    assert cfg.min_interval_seconds == core_progress.DEFAULT_MIN_INTERVAL_SECONDS
    assert cfg.max_chars == core_progress.DEFAULT_MAX_CHARS


# -- the verb ------------------------------------------------------------------


def test_a_labelled_work_item_emits_one_progress_event(
    tmp_path, labels, published, log
):
    """
    Feature: progress reports during long-running sessions
      Scenario: an opted-in work item reports
        Given the work item carries the progress label
        When the session runs `the-loop progress`
        Then a session.progress event reaches the bus, unrecorded, and is logged
    """
    result = core_progress.progress_session(
        REF, "Wiring the retry; tests next.", config=_config(tmp_path), actor="agent"
    )
    assert result["sent"] is True and result["status"] == "sent"
    assert result["exitCode"] == 0
    ((event, kwargs),) = published
    assert event.event_type == "session.progress" and event.work_item == REF
    assert event.text == "Wiring the retry; tests next."
    assert kwargs["record"] is False  # a signal, never written on the ticket
    (row,) = _emitted(log)
    assert row["work_item"] == REF and row["channels_posted"] == 1


def test_an_unlabelled_work_item_emits_nothing_and_still_succeeds(
    tmp_path, labels, published, log
):
    """The label is the opt-in: removing it stops the reports with no config edit."""
    labels["labels"] = ["bug"]
    result = core_progress.progress_session(REF, "working", config=_config(tmp_path))
    assert result["status"] == "not-opted-in" and result["sent"] is False
    assert result["exitCode"] == 0
    assert published == [] and _emitted(log) == []


def test_the_label_is_read_every_time_so_adding_it_takes_effect_at_once(
    tmp_path, labels, published, log
):
    labels["labels"] = []
    config = _config(tmp_path, minIntervalSeconds=0)
    assert core_progress.progress_session(REF, "a", config=config)["sent"] is False
    labels["labels"] = [
        "The-Loop: Progress"
    ]  # a tracker's casing is not ours to police
    assert core_progress.progress_session(REF, "b", config=config)["sent"] is True
    assert labels["reads"] == 2


def test_an_empty_label_config_turns_the_feature_off(tmp_path, labels, published):
    result = core_progress.progress_session(
        REF, "working", config=_config(tmp_path, label="")
    )
    assert result["status"] == "disabled" and published == []
    assert labels["reads"] == 0  # off means no tracker call either


def test_a_second_report_inside_the_interval_is_coalesced(
    tmp_path, labels, published, log
):
    """
    Scenario: a chatty agent
      Given a report was emitted a moment ago
      When the agent reports again inside minIntervalSeconds
      Then nothing is emitted and the verb says when the next one is welcome
    """
    config = _config(tmp_path, minIntervalSeconds=300)
    assert core_progress.progress_session(REF, "first", config=config)["sent"] is True
    second = core_progress.progress_session(REF, "second", config=config)
    assert second["status"] == "rate-limited" and second["sent"] is False
    assert 0 < second["retryAfterSeconds"] <= 300
    assert len(published) == 1 and len(_emitted(log)) == 1


def test_the_interval_is_per_work_item(tmp_path, labels, published, log):
    config = _config(tmp_path, minIntervalSeconds=300)
    assert core_progress.progress_session(REF, "a", config=config)["sent"] is True
    other = core_progress.progress_session("github:octo/repo#341", "b", config=config)
    assert other["sent"] is True


def test_a_report_after_the_interval_is_sent(tmp_path, labels, published, log):
    old = (datetime.now(timezone.utc) - timedelta(seconds=600)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps({"ts": old, "event": "session.progress", "work_item": REF}) + "\n"
    )
    config = _config(tmp_path, minIntervalSeconds=300)
    assert core_progress.progress_session(REF, "again", config=config)["sent"] is True


def test_a_zero_interval_disables_the_limit(tmp_path, labels, published, log):
    config = _config(tmp_path, minIntervalSeconds=0)
    for text in ("a", "b", "c"):
        assert core_progress.progress_session(REF, text, config=config)["sent"] is True


def test_an_unreadable_label_sends_nothing_and_exits_one(
    tmp_path, labels, published, log
):
    """A flaky tracker must never turn into a flood: fail closed, say so."""
    labels["error"] = RuntimeError("503 from the tracker")
    result = core_progress.progress_session(REF, "working", config=_config(tmp_path))
    assert result["status"] == "label-unreadable" and result["exitCode"] == 1
    assert published == [] and _emitted(log) == []


def test_an_empty_report_or_malformed_ref_is_a_caller_mistake(tmp_path, labels):
    with pytest.raises(ValueError):
        core_progress.progress_session(REF, "  \n ", config=_config(tmp_path))
    with pytest.raises(ValueError):
        core_progress.progress_session("not-a-ref", "x", config=_config(tmp_path))
    assert labels["reads"] == 0  # refused before anything was read


def test_the_report_is_shortened_before_it_is_sent(tmp_path, labels, published, log):
    config = _config(tmp_path, maxChars=20)
    core_progress.progress_session(REF, "y" * 100, config=config)
    ((event, _),) = published
    assert len(event.text) == 20


# -- the label read ------------------------------------------------------------


def test_a_github_label_is_read_from_the_issue(monkeypatch):
    from the_loop.core import github_ops
    from the_loop.workitem import WorkItemRef

    seen = {}

    class Client:
        def labels_of(self, owner, repo, number, host=""):
            seen.update(owner=owner, repo=repo, number=number)
            return ["the-loop: progress"]

    monkeypatch.setattr(github_ops, "_client", lambda config, client: Client())
    out = core_progress._labels_of(WorkItemRef.parse(REF), {})
    assert out == ["the-loop: progress"]
    assert seen == {"owner": "octo", "repo": "repo", "number": 340}


def test_jira_carries_the_label_in_its_jira_safe_form():
    """Jira cannot hold `: ` in a label, so the configured spelling is compared as
    Jira spells it."""
    assert core_progress._label_matches(
        "the-loop: progress", ["the-loop:progress"], "jira"
    )
    assert not core_progress._label_matches("the-loop: progress", ["other"], "jira")


# -- the HTTP binding and the CLI ------------------------------------------------


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake(ref, text, config=None, actor=""):
        if not text.strip():
            raise ValueError("the progress report is empty; nothing to say")
        calls.append({"ref": ref, "text": text, "actor": actor})
        return {"exitCode": 0, "messages": [{"stream": "out", "text": "reported"}]}

    monkeypatch.setattr(core_progress, "progress_session", fake)
    return calls


def test_the_route_reports_with_the_callers_actor(tmp_path, captured):
    client = TestClient(create_app({"state": {"root": str(tmp_path / ".the-loop")}}))
    response = client.post(
        "/api/v1/sessions/progress",
        json={"ref": REF, "text": "halfway", "actor": "agent-user"},
    )
    assert response.status_code == 200, response.text
    assert captured == [{"ref": REF, "text": "halfway", "actor": "agent-user"}]


def test_an_empty_report_is_a_400(tmp_path, captured):
    client = TestClient(create_app({"state": {"root": str(tmp_path / ".the-loop")}}))
    response = client.post("/api/v1/sessions/progress", json={"ref": REF, "text": " "})
    assert response.status_code == 400


@pytest.mark.routed
def test_the_cli_reports_through_a_running_service(monkeypatch, captured, capsys):
    from the_loop import client

    posted = []
    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)
    monkeypatch.setattr(
        client.Client,
        "post",
        lambda self, path, body=None, **_k: (
            posted.append((path, body))
            or {"exitCode": 0, "messages": [{"stream": "out", "text": "reported"}]}
        ),
    )
    code = main(["progress", "--work-item", REF, "--text", "halfway"])
    assert code == 0
    assert posted and posted[0][0] == "/sessions/progress"
    assert posted[0][1]["text"] == "halfway" and captured == []
    assert "reported" in capsys.readouterr().out
