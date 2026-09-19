"""Work-item collaborators: the login grammar, the roster, and its boundaries (issue-307).

Three things are asserted here, and the second and third are the security ones:

* ``normalize_login``/``parse_logins`` — the **entire** parser for the one argument a
  control command carries. Everything that is not GitHub's login shape is refused rather
  than sanitised (abuse case A3).
* :class:`CollaboratorStore` — a roster per work item, in that item's portable record,
  answering membership **only** about the refs it is handed (abuse case A4).
* the human gates — a collaborator's comment is ignored by them exactly as any other
  non-authorized author's is (abuse case A5). Asserted directly rather than inherited
  from "we didn't change that file".

Spec: docs/specs/issue-307/testing-plan.md T1, T2, T8, T9.
"""

import pytest

from the_loop.collaborators import (
    CollaboratorRecord,
    CollaboratorStore,
    Subjects,
    normalize_login,
    parse_logins,
    parse_subjects,
)
from the_loop.control import ControlStore
from the_loop.workitem import COLLABORATORS, CONTROL, WorkItemStore

REF = "github:octo/repo#15"
PR = "github:octo/repo#42"
OTHER = "github:octo/repo#16"
DANA = "U0456GHIJ"  # a Slack member id, as the roster stores one (issue-389)


@pytest.fixture
def store(tmp_path):
    return CollaboratorStore(tmp_path / "portable")


# -- the login grammar (T1) -----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@dana", "dana"),
        ("dana", "dana"),
        ("@Dana", "dana"),
        ("  @MadaraUchiha-314  ", "madarauchiha-314"),
        ("a", "a"),
        ("a" * 39, "a" * 39),
    ],
)
def test_a_github_login_is_canonicalised(raw, expected):
    assert normalize_login(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "@",
        "-dana",  # leading hyphen
        "dana-",  # trailing hyphen
        "da--na",  # double hyphen
        "a" * 40,  # too long
        "dana bell",  # a space
        "dana.example",  # a dot
        "dana/../etc/passwd",  # a path
        "--permission-mode",  # an argv fragment
        "dana@example.com",
        "org/team",
        "dana\nthe-loop start",  # a second instruction
        None,
    ],
)
def test_anything_that_is_not_a_login_is_refused_not_cleaned_up(raw):
    """A3: the mitigation is refusal, so nothing partial can ever be stored."""
    assert normalize_login(raw) == ""


def test_the_login_run_after_a_keyword_stops_at_the_first_word_that_is_not_one():
    assert parse_logins(" @a @b please help with this") == ["a", "b"]
    assert parse_logins(" @a, @b") == ["a", "b"]
    assert parse_logins(" @Dana @dana") == ["dana"]  # one person, once
    assert parse_logins(" @dana.") == ["dana"]  # end of a sentence
    assert parse_logins(" thanks @dana") == []  # the name must come first
    assert parse_logins(" @dana/../etc") == []  # not a whole login token
    assert parse_logins("") == []


# -- the subject grammar: a login or a Slack id (issue-389, R7.1) ----------------


def test_subjects_are_logins_and_slack_ids_in_any_order():
    assert parse_subjects(" @a slack:U0456GHIJ @b, slack:W0789KLMN then prose") == (
        Subjects(logins=["a", "b"], slack=["U0456GHIJ", "W0789KLMN"])
    )
    assert parse_subjects(" slack:U0456GHIJ.") == Subjects(slack=["U0456GHIJ"])
    assert parse_subjects(" SLACK:U0456GHIJ") == Subjects(slack=["U0456GHIJ"])
    assert parse_subjects(" slack:U0456GHIJ slack:U0456GHIJ") == Subjects(
        slack=["U0456GHIJ"]
    )
    assert parse_subjects("") == Subjects()
    assert not Subjects()
    assert Subjects(slack=["U0456GHIJ"])


@pytest.mark.parametrize(
    "text",
    [
        " slack:@dana @a",  # a handle is not an id: nothing resolves here
        " slack:dana @a",
        " slack:u0456ghij @a",  # ids are uppercase; a lowercase one is a name
        " slack: U0456GHIJ @a",
        " slack:C0123ABCD @a",  # a conversation, not a member
        " slack:U0456GHIJ/../x @a",
    ],
)
def test_a_slack_token_that_is_not_a_member_id_stops_the_scan(text):
    """A11: the parser never guesses; a token that is not `slack:<member id>` ends
    the run, so nothing after it is a subject either."""
    assert parse_subjects(text) == Subjects()


def test_parse_logins_reads_past_a_slack_token_and_reports_logins_only():
    """The wrapper callers that only want logins keep: same answer, minus the ids."""
    assert parse_logins(" @a slack:U0456GHIJ @b help") == ["a", "b"]
    assert parse_logins(" slack:U0456GHIJ") == []


# -- the roster (T2) ------------------------------------------------------------


def test_a_grant_round_trips_with_its_provenance(store, tmp_path):
    assert store.add(
        REF, "@Dana", actor="octocat", source="comment", note="https://c/1"
    )
    records = store.list(REF)
    assert [r.login for r in records] == ["dana"]
    assert records[0].added_by == "octocat"
    assert records[0].source == "comment"
    assert records[0].note == "https://c/1"
    assert records[0].added_at.endswith("Z")
    # ...in the work item's portable record, in a section of its own
    written = WorkItemStore(tmp_path / "portable").read(REF)
    assert list(written[COLLABORATORS]["users"][0]) == [
        "login",
        "addedBy",
        "addedAt",
        "source",
        "note",
    ]


def test_adding_twice_and_removing_an_absent_login_report_themselves(store):
    assert store.add(REF, "dana") is True
    assert store.add(REF, "@DANA") is False  # already there, same person
    assert store.list(REF) and len(store.list(REF)) == 1
    assert store.remove(REF, "ann") is False
    assert store.remove(REF, "@Dana") is True
    assert store.list(REF) == []


def test_a_login_the_store_would_not_accept_raises_rather_than_writing(store):
    with pytest.raises(ValueError):
        store.add(REF, "dana bell")
    with pytest.raises(ValueError):
        store.remove(REF, "../etc")
    assert store.list(REF) == []


def test_membership_is_asked_only_about_the_refs_it_is_given(store):
    """A4: a grant on one work item does not reach another."""
    store.add(REF, "dana")
    assert store.is_collaborator("dana", REF)
    assert store.is_collaborator("@Dana", REF)
    assert not store.is_collaborator("dana", OTHER)
    # an event naming the item and the pull request delivering it: permitted
    assert store.permits("dana", [REF, PR])
    # an event naming neither: not
    assert not store.permits("dana", [OTHER, PR])
    assert not store.permits("ann", [REF])


def test_a_nameless_actor_is_never_a_collaborator(store):
    """The deliberate asymmetry with ``is_authorized``, which allows one."""
    store.add(REF, "dana")
    assert not store.is_collaborator(None, REF)
    assert not store.is_collaborator("", REF)
    assert not store.permits(None, [REF])


def test_an_unparseable_ref_grants_nothing(store):
    store.add(REF, "dana")
    assert not store.permits("dana", ["not-a-ref"])


def test_a_hand_edited_entry_that_names_no_login_grants_nobody(store, tmp_path):
    WorkItemStore(tmp_path / "portable").write_section(
        REF, COLLABORATORS, {"users": [{"login": "dana bell"}, {"login": "@Ann"}]}
    )
    assert [r.login for r in store.list(REF)] == ["ann"]
    assert not store.permits("dana bell", [REF])


def test_the_roster_lives_beside_the_other_sections_and_survives_them(store, tmp_path):
    control = ControlStore(str(tmp_path / "portable"))
    control.record(REF, "start", actor="octocat")
    store.add(REF, "dana")
    assert control.get(REF) is not None and store.logins(REF) == ["dana"]
    # clearing one leaves the other exactly as it was
    control.clear(REF)
    assert store.logins(REF) == ["dana"]
    assert store.clear(REF) is True
    assert store.clear(REF) is False
    assert WorkItemStore(tmp_path / "portable").section(REF, CONTROL) is None


def test_a_record_holding_only_a_roster_is_a_record(store, tmp_path):
    """A grant on an item nothing else is known about must not vanish."""
    store.add(REF, "dana")
    assert (tmp_path / "portable").is_dir()
    assert CollaboratorStore(tmp_path / "portable").logins(REF) == ["dana"]


def test_a_record_from_dict_ignores_a_shape_it_cannot_read():
    assert CollaboratorRecord.from_dict("nope") is None
    assert CollaboratorRecord.from_dict({}) is None
    dana = CollaboratorRecord.from_dict({"login": "@Dana"})
    assert dana is not None and dana.login == "dana"


# -- the roster carries a Slack id (issue-389, R7.1 / T1 / T10) -----------------


def test_a_record_written_before_slack_existed_reads_unchanged():
    """T10: an entry without `slack` keeps working, and writes back without it."""
    record = CollaboratorRecord.from_dict(
        {"login": "dana", "addedBy": "octocat", "addedAt": "t", "source": "cli"}
    )
    assert record is not None
    assert record.login == "dana" and record.slack == ""
    assert list(record.to_dict()) == ["login", "addedBy", "addedAt", "source", "note"]


def test_a_record_may_name_a_slack_id_beside_or_instead_of_a_login():
    both = CollaboratorRecord.from_dict({"login": "@Dana", "slack": " U0456GHIJ "})
    assert both is not None
    assert (both.login, both.slack) == ("dana", "U0456GHIJ")
    assert both.to_dict()["slack"] == "U0456GHIJ"
    assert list(both.to_dict())[:2] == ["login", "slack"]

    slack_only = CollaboratorRecord.from_dict({"slack": "W0789KLMN"})
    assert slack_only is not None
    assert (slack_only.login, slack_only.slack) == ("", "W0789KLMN")
    assert slack_only.to_dict()["login"] == ""


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"login": "", "slack": ""},
        {"slack": "@dana"},  # a handle, never resolved into the roster
        {"slack": "dana"},
        {"slack": "u0456ghij"},
        {"slack": "C0123ABCD"},  # a conversation id is not a person
        {"login": "dana bell", "slack": "U0456GHIJ"},  # a bad login is not ignored
        {"login": "dana", "slack": "nope"},  # nor a bad id beside a good login
    ],
)
def test_an_unresolvable_collaborator_authorizes_nobody(data, store, tmp_path):
    """A11: an entry that names no valid id, or an id that is not a member id, is
    skipped whole — it grants nobody rather than whoever the file happened to name.

    Requirement: docs/specs/issue-389/requirements.md#R7 (abuse case A11)
    """
    assert CollaboratorRecord.from_dict(data) is None
    WorkItemStore(tmp_path / "portable").write_section(
        REF, COLLABORATORS, {"users": [data, {"login": "ann"}]}
    )
    assert [r.login for r in store.list(REF)] == ["ann"]
    assert store.slack_ids(REF) == []
    for candidate in ("U0456GHIJ", "dana", "@dana", ""):
        assert not store.is_collaborator_slack(candidate, REF)
    assert not store.is_collaborator("dana", REF)


def test_a_slack_grant_round_trips_with_its_provenance(store, tmp_path):
    assert store.add(REF, slack=DANA, actor="octocat", note="https://c/2")
    (record,) = store.list(REF)
    assert (record.login, record.slack) == ("", DANA)
    assert record.added_by == "octocat" and record.note == "https://c/2"
    written = WorkItemStore(tmp_path / "portable").read(REF)
    assert written[COLLABORATORS]["users"][0]["slack"] == DANA
    assert store.slack_ids(REF) == [DANA]
    assert store.is_collaborator_slack(DANA, REF)
    assert store.is_collaborator_slack(f" {DANA} ", REF)
    assert not store.is_collaborator_slack(DANA, OTHER)  # A4 holds for ids too


def test_a_slack_only_entry_is_invisible_to_the_login_predicates(store):
    """`logins`, `is_collaborator` and `permits` keep their meaning: they answer
    about GitHub logins, and an entry with none is not one of them."""
    store.add(REF, slack=DANA)
    assert store.logins(REF) == []
    assert not store.is_collaborator("", REF)
    assert not store.permits("", [REF])
    assert not store.permits(DANA, [REF])  # an id is not a login


def test_a_slack_id_is_not_a_login_and_a_handle_is_not_an_id(store):
    store.add(REF, login="dana", slack=DANA)
    assert not store.is_collaborator_slack("@dana", REF)
    assert not store.is_collaborator_slack("dana", REF)
    assert not store.is_collaborator_slack(None, REF)
    assert not store.is_collaborator(DANA, REF)


def test_a_grant_dedupes_on_either_id_and_merges_a_second_one(store):
    """
    Feature: a collaborator is known by a login, a Slack id, or both
      Scenario: the same person, granted twice by different ids
        Given dana is on the roster by login
        When dana is granted again by login together with her Slack id
        Then the roster still has ONE entry, now carrying both ids
        And granting either id again changes nothing

    Requirement: docs/specs/issue-389/requirements.md#R7
    """
    assert store.add(REF, login="dana", actor="octocat", note="https://c/1")
    assert store.add(REF, login="@Dana", slack=DANA) is True  # merged, a change
    (record,) = store.list(REF)
    assert (record.login, record.slack) == ("dana", DANA)
    assert record.added_by == "octocat" and record.note == "https://c/1"
    assert store.add(REF, login="dana") is False
    assert store.add(REF, slack=DANA) is False
    assert store.add(REF, login="dana", slack=DANA) is False
    assert len(store.list(REF)) == 1
    assert store.logins(REF) == ["dana"] and store.slack_ids(REF) == [DANA]


def test_two_entries_the_same_grant_names_collapse_into_one(store):
    store.add(REF, login="dana")
    store.add(REF, slack=DANA)
    assert len(store.list(REF)) == 2
    assert store.add(REF, login="dana", slack=DANA) is True
    (record,) = store.list(REF)
    assert (record.login, record.slack) == ("dana", DANA)


def test_a_revocation_by_either_id_removes_the_entry(store):
    store.add(REF, login="dana", slack=DANA)
    assert store.remove(REF, slack="W0000ZZZZ") is False
    assert store.remove(REF, slack=DANA) is True
    assert store.list(REF) == []
    store.add(REF, login="dana", slack=DANA)
    assert store.remove(REF, "@DANA") is True  # the positional login still works
    assert store.list(REF) == []


def test_a_grant_with_no_id_or_a_bad_one_raises_rather_than_writing(store):
    with pytest.raises(ValueError):
        store.add(REF)
    with pytest.raises(ValueError):
        store.add(REF, slack="@dana")
    with pytest.raises(ValueError):
        store.add(REF, login="dana", slack="nope")
    with pytest.raises(ValueError):
        store.remove(REF)
    with pytest.raises(ValueError):
        store.remove(REF, slack="dana")
    assert store.list(REF) == []


def test_a_hand_edited_roster_dedupes_on_the_slack_id_too(store, tmp_path):
    WorkItemStore(tmp_path / "portable").write_section(
        REF,
        COLLABORATORS,
        {"users": [{"slack": DANA}, {"login": "ann", "slack": DANA}]},
    )
    assert [(r.login, r.slack) for r in store.list(REF)] == [("", DANA)]


# -- the human gates are not delegated (T8 / A5) --------------------------------


def _feedback_ctx(tmp_path, comments, authorized):
    from the_loop.graph.contract import HookContext, WorkItem

    return HookContext(
        work_item=WorkItem(ref=REF, id="issue-15", spec_dir=tmp_path),
        node={"id": "requirements-approval"},
        boundary="entry",
        repo=tmp_path,
        config={"authorizedUsers": list(authorized)},
        event={"comments": comments},
    )


def test_a_collaborators_comment_does_not_reach_a_human_gate(tmp_path):
    """A5: gates read ``authorizedUsers``, and a grant is not on that list."""
    from the_loop.graph.hooks.feedback import _authorized_comments

    comments = [
        {"author": "dana", "body": "approved, ship it"},
        {"author": "octocat", "body": "still looking"},
    ]
    read = _authorized_comments(_feedback_ctx(tmp_path, comments, ["octocat"]))
    assert [c["author"] for c in read] == ["octocat"]
