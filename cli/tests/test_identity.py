"""Identity in one place (issue-309, R5): `routing.authorizedUsers` entries are people."""

from __future__ import annotations

import logging

from the_loop.authz import resolve_authorized_users
from the_loop.identity import (
    Principal,
    github_logins,
    ids_for,
    parse_authorized_users,
    principal_for,
)


def test_a_bare_string_is_a_github_login():
    """R5.1 — the ledger's identity, exactly what the list has meant since issue-63."""
    principals = parse_authorized_users(["octocat", " hubot "])
    assert [p.ids for p in principals] == [{"github": "octocat"}, {"github": "hubot"}]
    assert github_logins(principals) == ["octocat", "hubot"]


def test_a_mapping_names_one_person_on_every_channel():
    """R5.1 — one entry, every id; `name` is a label and never an id."""
    principals = parse_authorized_users(
        [{"github": "jc1993", "slack": "U0456", "name": "John"}]
    )
    assert len(principals) == 1
    person = principals[0]
    assert person.ids == {"github": "jc1993", "slack": "U0456"}
    assert person.name == "John" and person.label == "John"
    assert person.id_on("slack") == "U0456" and person.id_on("jira") == ""
    assert person.to_dict() == {"github": "jc1993", "slack": "U0456"}


def test_every_login_consumer_reads_exactly_the_github_ids():
    """R5.2 — a person named only on Slack contributes nothing to the login list."""
    raw = ["octocat", {"slack": "U1"}, {"github": "dana", "slack": "U2"}]
    assert resolve_authorized_users(raw) == ["octocat", "dana"]
    assert ids_for(parse_authorized_users(raw), "slack") == ["U1", "U2"]


def test_a_malformed_entry_is_dropped_with_a_warning_never_coerced(caplog):
    """R5.5 — nothing authorizes anyone by accident, and nothing is silent."""
    with caplog.at_level(logging.WARNING, logger="the-loop.identity"):
        principals = parse_authorized_users(
            [42, {"name": "nobody"}, {"github": ["a", "b"]}, {"slack": None}, ""]
        )
    assert principals == []
    assert sum("dropped" in r.message for r in caplog.records) >= 3


def test_a_non_list_authorizes_nobody(caplog):
    with caplog.at_level(logging.WARNING, logger="the-loop.identity"):
        assert parse_authorized_users("octocat") == []
        assert parse_authorized_users({"github": "octocat"}) == []
        assert parse_authorized_users(None) == []
    assert any("not a list" in r.message for r in caplog.records)


def test_principal_for_resolves_from_config_never_from_the_message():
    """A8 — the ledger names the configured person; an unknown id is nobody."""
    principals = parse_authorized_users([{"github": "dana", "slack": "U2"}])
    assert principal_for(principals, "slack", "U2") == principals[0]
    assert principal_for(principals, "slack", "U9") is None
    assert principal_for(principals, "slack", "") is None
    assert principal_for(principals, "github", "dana") == principals[0]


def test_ids_are_exact_match_and_deduplicated():
    principals = parse_authorized_users(["Octocat", "Octocat", {"slack": "U1"}])
    assert github_logins(principals) == ["Octocat"]
    assert ids_for(principals, "slack") == ["U1"]
    assert principal_for(principals, "github", "octocat") is None  # exact, as before


def test_label_falls_back_to_the_login_then_to_any_id():
    assert Principal(ids={"github": "x"}).label == "x"
    assert Principal(ids={"slack": "U1"}).label == "slack:U1"
    assert Principal().label == "(nobody)"
