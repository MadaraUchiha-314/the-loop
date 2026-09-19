"""Tests for the CLI half of collaboration channels (issue-375).

``the-loop add-channel slack@C… --work-item <ref>`` applies the same declaration an
authorized user makes by keyword, and mirrors it back to the work item as a comment
carrying that keyword and that channel — marked as the-loop's own, so the daemon
never reads it back and applies it twice.

Driven through :func:`the_loop.cli.main` with the ``gh``-shelling comment poster
stubbed; the declarations are real, on a tmp path. The command runs in-process by
design (the `ask`/`add-collaborator` exception class), so no service is stood up.

Spec: docs/specs/issue-375/testing-plan.md T4.
"""

import pytest

from the_loop.authz import is_self_authored
from the_loop.cli import main
from the_loop.control import ADD_CHANNEL, ControlConfig, parse_command
from the_loop.core import workchannels as core_workchannels
from the_loop.workchannels import CollaborationChannelStore

REF = "github:octo/repo#375"
OTHER = "github:octo/repo#376"
ROOM = "slack@C0TMP375"


@pytest.fixture
def posted(monkeypatch):
    """Capture the paper-trail comment instead of shelling out to ``gh``."""
    calls = []

    def fake_post(item, body, gh_binary="gh", **kwargs):
        calls.append((item.ref, body, gh_binary))
        return True, ""

    monkeypatch.setattr(core_workchannels, "post_issue_comment", fake_post)
    return calls


def run(command, tmp_path, *channels, ref=REF, extra=()):
    return main(
        [
            command,
            *channels,
            "--work-item",
            ref,
            "--portable-dir",
            str(tmp_path / "portable"),
            *extra,
        ]
    )


def store(tmp_path):
    return CollaborationChannelStore(tmp_path / "portable")


def test_add_declares_and_records_it_on_the_ticket(tmp_path, posted):
    """
    Feature: an operator declares a work item's room from the terminal
      Scenario: the declaration and its paper trail
        Given a work item with no declared channel
        When `the-loop add-channel slack@C0TMP375 --work-item …` is run
        Then the declaration is recorded and the SAME keyword is posted back on
             the work item, marked as the-loop's own so the daemon never
             re-applies it

    Requirement: docs/specs/issue-375/requirements.md R1.9
    """
    assert run("add-channel", tmp_path, ROOM) == 0
    assert [record.ref for record in store(tmp_path).list(REF)] == [ROOM]

    ((ref, body, _),) = posted
    assert ref == REF
    assert body.startswith("the-loop add-channel slack@C0TMP375")
    assert is_self_authored(body)
    # The comment reads back as the very command an authorized user would type.
    result = parse_command(body, ControlConfig())
    assert result.command == ADD_CHANNEL
    assert result.subjects == [ROOM]


def test_the_uri_spelling_is_the_same_declaration(tmp_path, posted):
    assert run("add-channel", tmp_path, "slack://C0TMP375") == 0
    assert [record.ref for record in store(tmp_path).list(REF)] == [ROOM]
    assert posted[0][1].startswith("the-loop add-channel slack@C0TMP375")


def test_declaring_twice_is_exit_1_and_posts_nothing_new(tmp_path, posted):
    run("add-channel", tmp_path, ROOM)
    posted.clear()
    assert run("add-channel", tmp_path, ROOM) == 1
    assert posted == []


def test_remove_undeclares(tmp_path, posted):
    run("add-channel", tmp_path, ROOM)
    assert run("remove-channel", tmp_path, ROOM) == 0
    assert store(tmp_path).list(REF) == []
    assert run("remove-channel", tmp_path, ROOM) == 1


@pytest.mark.parametrize(
    "argument", ["slack@#tmp-issue-375", "jira@PROJ-1", "slack@c0tmp375", "nonsense"]
)
def test_a_refused_channel_writes_nothing_and_posts_nothing(
    tmp_path, posted, capsys, argument
):
    """
    Feature: an operator declares a work item's room from the terminal
      Scenario: a channel name, an unknown type, a bad id
        Given an argument that is not a valid <type>@<target>
        When the command is run
        Then it exits 2, explains which check refused it, and nothing is
             written or posted

    Requirement: docs/specs/issue-375/requirements.md R1.4, R1.5
    """
    assert run("add-channel", tmp_path, argument) == 2
    assert store(tmp_path).list(REF) == []
    assert posted == []
    assert "error:" in capsys.readouterr().err


def test_a_bad_work_item_ref_is_exit_2(tmp_path, posted):
    assert run("add-channel", tmp_path, ROOM, ref="not-a-ref") == 2
    assert posted == []


def test_a_channel_another_work_item_holds_is_exit_2(tmp_path, posted, capsys):
    """
    Feature: an operator declares a work item's room from the terminal
      Scenario: the room is already somebody's
        Given slack@C0TMP375 declared on #375
        When it is declared on #376 from the terminal
        Then the command exits 2 naming #375, and #376 declares nothing

    Requirement: docs/specs/issue-375/requirements.md R3.4
    """
    run("add-channel", tmp_path, ROOM)
    assert run("add-channel", tmp_path, ROOM, ref=OTHER) == 2
    assert store(tmp_path).list(OTHER) == []
    assert REF in capsys.readouterr().err


def test_all_or_nothing_across_several_channels(tmp_path, posted):
    assert run("add-channel", tmp_path, ROOM, "slack@#nope") == 2
    assert store(tmp_path).list(REF) == []
    assert posted == []


def test_no_comment_skips_the_paper_trail(tmp_path, posted):
    assert run("add-channel", tmp_path, ROOM, extra=("--no-comment",)) == 0
    assert [record.ref for record in store(tmp_path).list(REF)] == [ROOM]
    assert posted == []


def test_a_failed_comment_keeps_the_declaration(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        core_workchannels, "post_issue_comment", lambda *a, **k: (False, "gh exploded")
    )
    assert run("add-channel", tmp_path, ROOM) == 0
    assert [record.ref for record in store(tmp_path).list(REF)] == [ROOM]
    assert "could not comment" in capsys.readouterr().err


# -- the listen mode (issue-389 §2, R2.1) -----------------------------------------


def test_add_channel_listen_all_is_recorded_and_spelled_back(tmp_path, posted):
    """
    Feature: an operator switches a room to hear everything from the terminal
      Scenario: add-channel --listen all is recorded with provenance
        Given a work item with no declared channel
        When `the-loop add-channel slack@C0TMP375 --listen all --work-item …` is run
        Then the declaration carries `listen: all` from the CLI
        And the SAME keyword is posted back with `--listen all`, so the thread
             says how the room listens and the daemon can read it back

    Requirement: docs/specs/issue-389/requirements.md#R2
    """
    assert run("add-channel", tmp_path, ROOM, extra=("--listen", "all")) == 0
    (record,) = store(tmp_path).list(REF)
    assert record.listen == "all" and record.source == "cli"

    ((ref, body, _),) = posted
    assert ref == REF
    assert body.startswith("the-loop add-channel slack@C0TMP375 --listen all")
    result = parse_command(body, ControlConfig())
    assert result.subjects == [ROOM] and result.listen == "all"
    assert is_self_authored(body)


def test_the_default_listen_mode_is_mentions_and_is_not_spelled(tmp_path, posted):
    assert run("add-channel", tmp_path, ROOM) == 0
    (record,) = store(tmp_path).list(REF)
    assert record.listen == "mentions"
    assert "--listen" not in posted[0][1]


def test_redeclaring_with_another_mode_is_a_change(tmp_path, posted):
    run("add-channel", tmp_path, ROOM)
    posted.clear()
    assert run("add-channel", tmp_path, ROOM, extra=("--listen", "all")) == 0
    declared = store(tmp_path).for_type(REF)
    assert declared is not None and declared.listen == "all"
    assert len(posted) == 1 and "--listen all" in posted[0][1]
    assert run("add-channel", tmp_path, ROOM, extra=("--listen", "all")) == 1
    assert run("add-channel", tmp_path, ROOM, extra=("--listen", "mentions")) == 0
    declared = store(tmp_path).for_type(REF)
    assert declared is not None and declared.listen == "mentions"


def test_an_unknown_listen_mode_is_refused_by_the_parser(tmp_path, posted):
    """A12: the two modes are the flag's choices; a third never reaches core."""
    with pytest.raises(SystemExit) as excinfo:
        run("add-channel", tmp_path, ROOM, extra=("--listen", "everything"))
    assert excinfo.value.code == 2
    assert store(tmp_path).list(REF) == [] and posted == []
