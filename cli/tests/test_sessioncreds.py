"""Unit tests for `sessioncreds` — masking session credential values (issue-533, R5).

Spec: docs/specs/issue-533/design.md § sessioncreds · testing plan row T1.
"""

from __future__ import annotations

import logging

import pytest

from the_loop import eventlog, sessioncreds

VALUE = "session-credential-value-533"
ROTATED = "session-credential-rotated-533"


@pytest.fixture(autouse=True)
def _clean():
    sessioncreds._forget_all()
    yield
    sessioncreds._forget_all()


def _config(tmp_path, text):
    (tmp_path / ".env").write_text(text)
    return (
        {
            "env": {
                "file": ".env",
                "sessionCredentials": [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}],
            }
        },
        tmp_path / "cli-config.yaml",
    )


def test_abuse_533_a4_a_pasted_value_is_masked(tmp_path):
    config, path = _config(tmp_path, f"SESSION_GH_TOKEN={VALUE}\n")
    text = f"here is my env: GH_TOKEN={VALUE} and again {VALUE}"
    out = sessioncreds.scrub(text, config, path)
    assert VALUE not in out
    assert out.count(sessioncreds.MASK) == 2


def test_a_rotated_value_is_masked_and_the_old_one_remembered(tmp_path):
    """R5.2: the new value from the moment it is configured; the old one stays."""
    config, path = _config(tmp_path, f"SESSION_GH_TOKEN={VALUE}\n")
    sessioncreds.scrub("warm", config, path)
    (tmp_path / ".env").write_text(f"SESSION_GH_TOKEN={ROTATED}\n# changed size\n")
    out = sessioncreds.scrub(f"{VALUE} {ROTATED}", config, path)
    assert VALUE not in out and ROTATED not in out


def test_the_source_may_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SESSION_GH_TOKEN", VALUE)
    config = {"env": {"sessionCredentials": [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}]}}
    assert VALUE not in sessioncreds.scrub(f"x {VALUE} y", config)


def test_nothing_configured_is_the_identity_without_disk(monkeypatch):
    """R5.3."""
    def boom(*_a, **_k):
        raise AssertionError("read the disk")

    monkeypatch.setattr(sessioncreds, "_file_values", boom)
    assert sessioncreds.scrub(f"x {VALUE}", {}) == f"x {VALUE}"
    assert sessioncreds.scrub(f"x {VALUE}") == f"x {VALUE}"
    assert sessioncreds.scrub_tree({"a": VALUE}) == {"a": VALUE}


def test_a_short_value_is_not_masked_and_is_warned_about_once(caplog):
    with caplog.at_level(logging.WARNING, logger="the-loop.sessioncreds"):
        sessioncreds.remember(["abc"])
        sessioncreds.remember(["abc"])
    assert sessioncreds.scrub("abc def") == "abc def"
    assert caplog.text.count("shorter than") == 1
    assert "abc" not in caplog.text


def test_longest_first_so_a_value_containing_another_is_masked_whole():
    sessioncreds.remember([VALUE, VALUE + "-suffix"])
    assert sessioncreds.scrub(VALUE + "-suffix") == sessioncreds.MASK


def test_scrub_tree_walks_nested_fields():
    sessioncreds.remember([VALUE])
    out = sessioncreds.scrub_tree({"a": [VALUE, {"b": f"x{VALUE}"}], "n": 3})
    assert out == {"a": [sessioncreds.MASK, {"b": f"x{sessioncreds.MASK}"}], "n": 3}


def test_the_event_log_writes_masked_strings(tmp_path):
    """R5.1: defence in depth for a value that reaches a log line by any path."""
    sessioncreds.remember([VALUE])
    log = eventlog.EventLog(tmp_path / "events.jsonl", source="test")
    log.emit("session.awaiting_input", question=f"is {VALUE} right?")
    written = (tmp_path / "events.jsonl").read_text()
    assert VALUE not in written and sessioncreds.MASK in written
