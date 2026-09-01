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
