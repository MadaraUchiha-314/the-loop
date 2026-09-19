"""Tests for the CLI half of work-item collaborators (issue-307).

``the-loop add-collaborator @login --work-item <ref>`` applies the same grant an
authorized user makes by keyword, and mirrors it back to the work item as a comment
carrying that keyword and that login — marked as the-loop's own, so the daemon never
reads it back and applies it twice.

Driven through :func:`the_loop.cli.main` with the ``gh``-shelling comment poster
stubbed; the roster is real, on a tmp path. The command runs in-process by design
(the `ask`/`reset` exception class), so no service is stood up here.
"""

import pytest

from the_loop.authz import is_self_authored
from the_loop.cli import main
from the_loop.collaborators import CollaboratorStore
from the_loop.control import ADD_COLLABORATOR, ControlConfig, parse_command
from the_loop.core import collaborators as core_collaborators

REF = "github:octo/repo#15"
DANA = "U0456GHIJ"


class FakeDirectory:
    """A workspace with two members, standing in for ``SlackDirectory``.

    Only ``user_id`` is consulted: an id is itself, a known handle is its id, and
    everything else is ``""`` — exactly the real directory's contract, so what
    the tests exercise is the command's handling of that answer.
    """

    members = {"dana": DANA, "ann": "W0789KLMN"}
    built = []

    def __init__(self, cli_config=None, *args, **kwargs):
        type(self).built.append(cli_config)

    def user_id(self, value):
        from the_loop.channels.directory import is_member_id, normalize_name

        text = str(value or "").strip()
        if is_member_id(text):
            return text
        return self.members.get(normalize_name(text), "")


@pytest.fixture
def directory(monkeypatch):
    FakeDirectory.built = []
    monkeypatch.setattr(core_collaborators, "SlackDirectory", FakeDirectory)
    return FakeDirectory


@pytest.fixture
def posted(monkeypatch):
    """Capture the paper-trail comment instead of shelling out to ``gh``."""
    calls = []

    def fake_post(item, body, gh_binary="gh", **kwargs):
        calls.append((item.ref, body, gh_binary))
        return True, ""

    monkeypatch.setattr(core_collaborators, "post_issue_comment", fake_post)
    return calls


def run(command, tmp_path, *logins, ref=REF, extra=()):
    return main(
        [
            command,
            *logins,
            "--work-item",
            ref,
            "--portable-dir",
            str(tmp_path / "portable"),
            *extra,
        ]
    )


def rosters(tmp_path):
    return CollaboratorStore(tmp_path / "portable")


def test_add_grants_and_records_the_grant_on_the_ticket(tmp_path, posted, capsys):
    assert run("add-collaborator", tmp_path, "@Dana") == 0
    assert rosters(tmp_path).logins(REF) == ["dana"]

    ((ref, body, _),) = posted
    assert ref == REF
    assert body.startswith("the-loop add-collaborator @dana")
    # the keyword is real — the thread reads the same whichever way it was issued
    assert parse_command(body, ControlConfig()).command == ADD_COLLABORATOR
    assert parse_command(body, ControlConfig()).subjects == ["dana"]
    # ...and self-marked, so neither ingress applies it a second time
    assert is_self_authored(body)
    assert "is now a collaborator" in capsys.readouterr().out


def test_the_record_says_who_granted_it_and_how(tmp_path, posted):
    run("add-collaborator", tmp_path, "@dana")
    (record,) = rosters(tmp_path).list(REF)
    assert record.source == "cli" and record.added_at.endswith("Z")


def test_several_logins_are_granted_in_one_call(tmp_path, posted):
    assert run("add-collaborator", tmp_path, "@dana", "ann") == 0
    assert rosters(tmp_path).logins(REF) == ["dana", "ann"]
    assert len(posted) == 2  # one comment per person, naming them


def test_remove_revokes(tmp_path, posted):
    run("add-collaborator", tmp_path, "@dana")
    assert run("remove-collaborator", tmp_path, "@DANA") == 0
    assert rosters(tmp_path).logins(REF) == []


def test_an_unchanged_roster_is_reported_and_not_announced(tmp_path, posted, capsys):
    run("add-collaborator", tmp_path, "@dana")
    posted.clear()

    assert run("add-collaborator", tmp_path, "@dana") == 1
    assert "already a collaborator" in capsys.readouterr().err
    assert posted == []  # a grant that did not happen is not put in the thread

    assert run("remove-collaborator", tmp_path, "@ann") == 1
    assert posted == []


def test_a_malformed_login_changes_nothing(tmp_path, posted, capsys):
    assert run("add-collaborator", tmp_path, "dana bell") == 2
    assert "not a GitHub login" in capsys.readouterr().err
    assert rosters(tmp_path).logins(REF) == [] and posted == []


def test_one_bad_login_refuses_the_whole_call(tmp_path, posted):
    """All-or-nothing: a typo in the third name must not half-apply the first two."""
    assert run("add-collaborator", tmp_path, "@dana", "@ann", "@bad/login") == 2
    assert rosters(tmp_path).logins(REF) == [] and posted == []


def test_a_malformed_work_item_changes_nothing(tmp_path, posted, capsys):
    assert run("add-collaborator", tmp_path, "@dana", ref="not-a-ref") == 2
    assert capsys.readouterr().err.startswith("error:")
    assert posted == []


def test_a_failing_gh_does_not_fail_the_grant(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        core_collaborators,
        "post_issue_comment",
        lambda *a, **k: (False, "gh: not found"),
    )
    assert run("add-collaborator", tmp_path, "@dana") == 0
    assert rosters(tmp_path).logins(REF) == ["dana"]
    assert "could not comment" in capsys.readouterr().err


def test_no_comment_applies_the_grant_silently(tmp_path, posted):
    assert run("add-collaborator", tmp_path, "@dana", extra=("--no-comment",)) == 0
    assert rosters(tmp_path).logins(REF) == ["dana"] and posted == []


# -- a collaborator by Slack id (issue-389, R7.1) ---------------------------------


def test_slack_grants_by_member_id_and_records_it_on_the_ticket(
    tmp_path, posted, directory, capsys
):
    """
    Feature: a collaborator is known by a login, a Slack id, or both
      Scenario: the CLI grants by member id
        Given a work item with an empty roster
        When `the-loop add-collaborator --slack U0456GHIJ --work-item …` is run
        Then the roster carries that Slack id and no login
        And the SAME keyword is posted back naming `slack:U0456GHIJ`, marked as
             the-loop's own so the daemon never re-applies it
    Requirement: docs/specs/issue-389/requirements.md#R7
    """
    assert run("add-collaborator", tmp_path, extra=("--slack", DANA)) == 0
    assert rosters(tmp_path).slack_ids(REF) == [DANA]
    assert rosters(tmp_path).logins(REF) == []

    ((ref, body, _),) = posted
    assert ref == REF
    assert body.startswith(f"the-loop add-collaborator slack:{DANA}")
    result = parse_command(body, ControlConfig())
    assert result.command == ADD_COLLABORATOR
    assert result.subjects == [] and result.slack == [DANA]
    assert is_self_authored(body)
    assert f"slack:{DANA} is now a collaborator" in capsys.readouterr().out
    assert directory.built == []  # an id costs no lookup


def test_slack_resolves_a_handle_through_the_directory(tmp_path, posted, directory):
    """
    Feature: a collaborator is known by a login, a Slack id, or both
      Scenario: the CLI grants by handle
        Given a workspace where @dana is U0456GHIJ
        When `the-loop add-collaborator --slack @dana` is run
        Then the roster stores the member ID, never the handle
    Requirement: docs/specs/issue-389/requirements.md#R7
    """
    assert run("add-collaborator", tmp_path, extra=("--slack", "@dana")) == 0
    assert rosters(tmp_path).slack_ids(REF) == [DANA]
    assert posted[0][1].startswith(f"the-loop add-collaborator slack:{DANA}")
    assert len(directory.built) == 1


def test_an_unresolvable_handle_refuses_the_whole_call(
    tmp_path, posted, directory, capsys
):
    """
    Feature: a collaborator is known by a login, a Slack id, or both
      Scenario: a handle nobody in the workspace holds
        Given a workspace with no @ghost
        When `the-loop add-collaborator @ann --slack @ghost` is run
        Then the command exits 2, explains the refusal, and NOTHING is written
             or posted — not even @ann (validate all, then apply)
    Requirement: docs/specs/issue-389/requirements.md#R7 (abuse case A11)
    """
    assert run("add-collaborator", tmp_path, "@ann", extra=("--slack", "@ghost")) == 2
    assert "ghost" in capsys.readouterr().err
    assert rosters(tmp_path).list(REF) == [] and posted == []


def test_a_login_and_a_slack_id_are_two_grants_with_two_comments(
    tmp_path, posted, directory
):
    assert run("add-collaborator", tmp_path, "@dana", extra=("--slack", DANA)) == 0
    assert rosters(tmp_path).logins(REF) == ["dana"]
    assert rosters(tmp_path).slack_ids(REF) == [DANA]
    assert [body.split("\n", 1)[0] for _, body, _ in posted] == [
        "the-loop add-collaborator @dana",
        f"the-loop add-collaborator slack:{DANA}",
    ]


def test_slack_may_be_repeated_and_is_deduped(tmp_path, posted, directory):
    assert (
        run(
            "add-collaborator",
            tmp_path,
            extra=("--slack", "@dana", "--slack", DANA, "--slack", "ann"),
        )
        == 0
    )
    assert rosters(tmp_path).slack_ids(REF) == [DANA, "W0789KLMN"]
    assert len(posted) == 2


def test_remove_revokes_by_slack_id(tmp_path, posted, directory):
    run("add-collaborator", tmp_path, extra=("--slack", DANA))
    assert run("remove-collaborator", tmp_path, extra=("--slack", "@dana")) == 0
    assert rosters(tmp_path).list(REF) == []
    assert run("remove-collaborator", tmp_path, extra=("--slack", DANA)) == 1


def test_naming_nobody_at_all_is_exit_2(tmp_path, posted, directory, capsys):
    assert run("add-collaborator", tmp_path) == 2
    assert "name at least one collaborator" in capsys.readouterr().err
    assert posted == []


def test_list_shows_the_slack_id(tmp_path, posted, directory):
    run("add-collaborator", tmp_path, "@dana", extra=("--slack", DANA))
    listed = core_collaborators.list_collaborators(
        REF, portable_dir=str(tmp_path / "portable")
    )
    assert [(c["login"], c.get("slack", "")) for c in listed["collaborators"]] == [
        ("dana", ""),
        ("", DANA),
    ]
