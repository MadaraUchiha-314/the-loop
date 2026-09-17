"""Slack names resolved to ids — the directory (issue-375, PR #376 review).

What is asserted here is the contract every caller leans on: an **id costs no
call**, a name costs one and is then cached, every failure resolves to ``""``
rather than to a guess, and a handle that changes hands is noticed out loud
rather than silently inherited.

The Slack boundary is a fake client counting its calls, so the rate-limit
behaviour — one refresh per miss, none per hit — is asserted rather than assumed.

Spec: docs/specs/issue-375/testing-plan.md T21, T22.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from the_loop.channels.directory import (
    TTL_SECONDS,
    SlackDirectory,
    is_conversation_id,
    is_member_id,
    normalize_name,
)


class FakeDirectoryClient:
    """``conversations.list`` / ``users.list``, paginated, counted."""

    def __init__(self, channels=None, members=None, fail=False):
        self.channels = (
            channels
            if channels is not None
            else [
                {"id": "C0TMP375", "name": "tmp-issue-375"},
                {"id": "GPRIV1", "name": "private-room"},
            ]
        )
        self.members = (
            members
            if members is not None
            else [
                {"id": "U0DANA", "name": "dana", "profile": {"display_name": "dana.b"}},
                {"id": "U0ANN", "name": "ann", "profile": {"display_name": ""}},
            ]
        )
        self.fail = fail
        #: Refreshes, not pages: a refresh walks every page, and what the rate
        #: limits care about — and what these tests assert — is how many times
        #: the whole listing was read.
        self.calls = {"conversations": 0, "users": 0}

    def conversations_list(self, *, types, exclude_archived, limit, cursor=None):
        if cursor is None:
            self.calls["conversations"] += 1
        if self.fail:
            raise RuntimeError("missing_scope")
        # One page, then the cursor runs out — the pagination contract, exercised.
        if cursor:
            return {"channels": [], "response_metadata": {"next_cursor": ""}}
        return {
            "channels": list(self.channels),
            "response_metadata": {"next_cursor": "page2"},
        }

    def users_list(self, *, limit, cursor=None):
        if cursor is None:
            self.calls["users"] += 1
        if self.fail:
            raise RuntimeError("missing_scope")
        return {"members": list(self.members), "response_metadata": {}}


@pytest.fixture
def directory(tmp_path, monkeypatch):
    """A directory over a fake workspace, and the client it reads, as a pair."""
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    client = FakeDirectoryClient()
    index = SlackDirectory(
        path=tmp_path / "local" / "slack-directory.json",
        token_env="THE_LOOP_SLACK_BOT_TOKEN",
        client_factory=lambda token: client,
    )
    return SimpleNamespace(index=index, client=client)


# -- what is an id, and what is a name ------------------------------------------


@pytest.mark.parametrize("value", ["C0TMP375", "GPRIV1", "D0A1B2", "C9", "C-OPS"])
def test_a_conversation_id_is_recognised(value):
    """`C9` and `C-OPS` included: `kinds_from_id` has read a leading C as an id
    since issue-362, so anything it calls an id must stay one here — a real id
    is alphanumeric, but the rule that separates the two is CASE, not shape."""
    assert is_conversation_id(value)
    assert normalize_name(value) == ""


@pytest.mark.parametrize("value", ["U0DANA", "W7GG2KY31"])
def test_a_member_id_is_recognised(value):
    assert is_member_id(value)
    assert normalize_name(value) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("#tmp-issue-375", "tmp-issue-375"),
        ("tmp-issue-375", "tmp-issue-375"),
        ("@dana", "dana"),
        ("Dana", "dana"),
        ("  #Room  ", "room"),
    ],
)
def test_a_name_loses_its_sigil_and_its_case(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "#", "@", "a b", "a/b", "a@b", "x" * 81])
def test_anything_else_is_not_a_name(raw):
    assert normalize_name(raw) == ""


# -- an id costs nothing (T21) ---------------------------------------------------


def test_an_id_is_returned_without_a_lookup(directory):
    """
    Feature: a person types the name, the-loop routes on the id
      Scenario: the value is already an id
        Given `C0TMP375`, which is a conversation id
        When it is resolved
        Then it comes back unchanged and Slack is never called

    Requirement: docs/specs/issue-375/requirements.md R6.2
    """
    assert directory.index.conversation_id("C0TMP375") == "C0TMP375"
    assert directory.index.user_id("U0DANA") == "U0DANA"
    assert directory.client.calls == {"conversations": 0, "users": 0}


# -- a name costs one call, then none (T21) --------------------------------------


def test_a_name_is_resolved_once_and_then_cached(directory, tmp_path):
    """
    Feature: a person types the name, the-loop routes on the id
      Scenario: the same name twice
        Given a workspace with #tmp-issue-375
        When the name is resolved twice
        Then the id comes back both times and Slack was read once

    Requirement: docs/specs/issue-375/requirements.md R6.1, R6.4
    """
    assert directory.index.conversation_id("#tmp-issue-375") == "C0TMP375"
    assert directory.index.conversation_id("tmp-issue-375") == "C0TMP375"
    assert directory.client.calls["conversations"] == 1
    saved = json.loads((tmp_path / "local" / "slack-directory.json").read_text())
    assert saved["conversations"]["names"]["tmp-issue-375"] == "C0TMP375"


def test_a_private_channel_resolves_too(directory):
    assert directory.index.conversation_id("#private-room") == "GPRIV1"


def test_only_the_handle_resolves_never_the_display_name(directory):
    """
    Feature: an operator names the person, not their member id
      Scenario: a display name is offered instead of a handle
        Given a member whose handle is `dana` and display name is `dana.b`
        When each is resolved
        Then the handle answers their member id and the display name answers
             nothing — `routing.authorizedUsers` has warned against display
             names since issue-309, and accepting handles does not widen that

    Requirement: docs/specs/issue-375/requirements.md R5.5
    """
    assert directory.index.user_id("@dana") == "U0DANA"
    assert directory.index.user_id("dana.b") == ""
    assert directory.client.calls["users"] == 1


def test_a_miss_on_a_fresh_map_does_not_re_read(directory):
    """
    Feature: a person types the name, the-loop routes on the id
      Scenario: a typo in a config file
        Given a name no channel has
        When it is resolved twice
        Then it answers "" both times and Slack is read ONCE — a typo cannot
             turn every message into an API call

    Requirement: docs/specs/issue-375/requirements.md R6.4
    """
    assert directory.index.conversation_id("#nope") == ""
    assert directory.index.conversation_id("#nope") == ""
    assert directory.client.calls["conversations"] == 1


def test_a_stale_map_is_refreshed_on_a_miss(directory, tmp_path, monkeypatch):
    """A channel created after the last read is findable: past the TTL, a miss
    pays for one refresh."""
    directory.index.conversation_id("#tmp-issue-375")
    assert directory.client.calls["conversations"] == 1
    directory.client.channels.append({"id": "C0NEW", "name": "new-room"})

    path = tmp_path / "local" / "slack-directory.json"
    payload = json.loads(path.read_text())
    payload["conversations"]["fetchedAt"] -= TTL_SECONDS + 1
    path.write_text(json.dumps(payload))

    assert directory.index.conversation_id("#new-room") == "C0NEW"
    assert directory.client.calls["conversations"] == 2


# -- every failure is "" (T22) ---------------------------------------------------


def test_a_failing_read_resolves_to_nothing(tmp_path, monkeypatch):
    """
    Feature: a person types the name, the-loop routes on the id
      Scenario: the app is missing channels:read
        Given a workspace read that raises
        When a name is resolved
        Then it answers "" — the caller refuses rather than guessing, and
             nothing is cached

    Requirement: docs/specs/issue-375/requirements.md R6.3
    """
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    index = SlackDirectory(
        path=tmp_path / "local" / "d.json",
        token_env="THE_LOOP_SLACK_BOT_TOKEN",
        client_factory=lambda token: FakeDirectoryClient(fail=True),
    )
    assert index.conversation_id("#tmp-issue-375") == ""
    assert index.user_id("@dana") == ""
    assert not (tmp_path / "local" / "d.json").exists()


def test_no_token_resolves_to_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("THE_LOOP_SLACK_BOT_TOKEN", raising=False)
    index = SlackDirectory(
        path=tmp_path / "local" / "d.json", token_env="THE_LOOP_SLACK_BOT_TOKEN"
    )
    assert index.conversation_id("#anything") == ""


def test_an_unreadable_cache_is_simply_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    path = tmp_path / "local" / "d.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    index = SlackDirectory(
        path=path,
        token_env="THE_LOOP_SLACK_BOT_TOKEN",
        client_factory=lambda token: FakeDirectoryClient(),
    )
    assert index.conversation_id("#tmp-issue-375") == "C0TMP375"


def test_a_deleted_member_is_not_in_the_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    index = SlackDirectory(
        path=tmp_path / "local" / "d.json",
        token_env="THE_LOOP_SLACK_BOT_TOKEN",
        client_factory=lambda token: FakeDirectoryClient(
            members=[{"id": "U0GONE", "name": "gone", "deleted": True}]
        ),
    )
    assert index.user_id("@gone") == ""


def test_the_two_maps_do_not_clobber_each_other(directory, tmp_path):
    """They refresh independently, so a conversations read must keep the users
    map another process wrote a moment earlier."""
    directory.index.user_id("@dana")
    directory.index.conversation_id("#tmp-issue-375")
    saved = json.loads((tmp_path / "local" / "slack-directory.json").read_text())
    assert saved["users"]["names"]["dana"] == "U0DANA"
    assert saved["conversations"]["names"]["tmp-issue-375"] == "C0TMP375"


# -- a handle that changes hands is said out loud (T22) ---------------------------


def test_a_handle_that_moved_is_warned_about(directory, tmp_path, caplog):
    """
    Feature: a person types the name, the-loop routes on the id
      Scenario: @dana is now somebody else
        Given @dana resolved to U0DANA and was cached
        When the workspace says @dana is U0OTHER
        Then the new id is returned AND a warning names both, because an
             allow-list entry following a handle is the one hole ids do not have

    Requirement: docs/specs/issue-375/requirements.md R5.4
    """
    assert directory.index.user_id("@dana") == "U0DANA"
    directory.client.members[0]["id"] = "U0OTHER"
    path = tmp_path / "local" / "slack-directory.json"
    payload = json.loads(path.read_text())
    payload["users"]["fetchedAt"] -= TTL_SECONDS + 1
    path.write_text(json.dumps(payload))

    with caplog.at_level("WARNING"):
        assert directory.index.user_id("@dana") == "U0OTHER"
    assert "changed hands" in caplog.text or "now resolves to" in caplog.text
