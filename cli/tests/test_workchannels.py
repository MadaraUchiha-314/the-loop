"""Collaboration channels: the grammar, the roster and its invariants (issue-375).

Three things are asserted here, and the second and third are the ones the feature
leans on:

* ``parse_channel_ref``/``parse_channel_refs`` — the **entire** parser for the
  argument the two control keywords carry. Everything that is not a known type with
  a valid target is refused rather than sanitised (abuse case A1).
* :class:`CollaborationChannelStore` — a declaration per work item, in that item's
  portable record, with one channel per type and one work item per channel.
* the reverse lookup — which work item a room belongs to, and the deliberate ``""``
  for a room two records claim (abuse case A2).

Spec: docs/specs/issue-375/testing-plan.md T1, T2, T3.
"""

import pytest

from the_loop.workchannels import (
    ChannelRef,
    ChannelTakenError,
    CollaborationChannel,
    CollaborationChannelStore,
    describe_refusal,
    parse_channel_ref,
    parse_channel_refs,
)
from the_loop.workitem import COLLABORATION_CHANNELS, WorkItemStore

REF = "github:octo/repo#375"
OTHER = "github:octo/repo#376"
ROOM = "slack@C0TMP375"


@pytest.fixture
def store(tmp_path):
    return CollaborationChannelStore(tmp_path / "portable")


# -- the grammar (T1) -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("slack@C0TMP375", "slack@C0TMP375"),
        ("slack://C0TMP375", "slack@C0TMP375"),
        ("  slack@C0TMP375  ", "slack@C0TMP375"),
        ("slack@C0TMP375.", "slack@C0TMP375"),
        ("slack@C0TMP375`", "slack@C0TMP375"),  # `…add-channel slack@C0TMP375`
        ("slack@GABC123", "slack@GABC123"),
        ("slack@D0A1B2C", "slack@D0A1B2C"),
    ],
)
def test_a_channel_ref_is_canonicalised(raw, expected):
    """
    Feature: a work item names the room it is worked in
      Scenario: the two spellings and the prose around them
        Given a channel written as <type>@<target> or <type>://<target>
        When it is parsed
        Then both yield the same canonical <type>@<target>

    Requirement: docs/specs/issue-375/requirements.md R1.3
    """
    channel = parse_channel_ref(raw)
    assert channel is not None and channel.ref == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "slack",
        "slack@",
        "@C0TMP375",
        "slack@#tmp-issue-375",  # a NAME, which nothing here can resolve
        "slack@c0tmp375",  # lower case is not a conversation id
        "slack@X0TMP375",  # not one of C/G/D
        "jira@PROJ-1",  # no adapter on this deployment
        "Slack@C0TMP375",  # the type is lower case
        "slack@C0TMP375/../etc",
        "slack@C0TMP375 --permission-mode bypass",
        "the-loop",
    ],
)
def test_anything_else_is_refused_not_repaired(raw):
    """
    Feature: a work item names the room it is worked in
      Scenario: a token that is not a channel
        Given a body carrying something that is not <type>@<target>
        When it is parsed
        Then nothing is returned, and the refusal says which of the three
             checks — shape, type, target — rejected it

    Requirement: docs/specs/issue-375/requirements.md R1.2, R1.4, R1.5
    """
    assert parse_channel_ref(raw) is None
    assert describe_refusal(raw)


def test_a_run_of_refs_stops_at_the_first_token_that_is_not_one():
    """
    Feature: a work item names the room it is worked in
      Scenario: prose after the channel
        Given `slack@C0TMP375 slack@GABC123 — the incident room`
        When the run is parsed
        Then both channels are returned and the prose reaches nothing

    Requirement: docs/specs/issue-375/requirements.md R1.2
    """
    assert [
        c.ref for c in parse_channel_refs("slack@C0TMP375 slack@GABC123 — room")
    ] == [
        "slack@C0TMP375",
        "slack@GABC123",
    ]
    assert parse_channel_refs("please slack@C0TMP375") == []
    assert [c.ref for c in parse_channel_refs("slack@C0TMP375, slack@C0TMP375")] == [
        "slack@C0TMP375"
    ]


def test_the_unknown_type_refusal_names_the_known_ones():
    assert "slack" in describe_refusal("whatsapp@+1555")


# -- the roster (T2) ------------------------------------------------------------


def test_a_declaration_is_recorded_with_its_provenance(store, tmp_path):
    """
    Feature: a work item names the room it is worked in
      Scenario: an authorized user declares one
        Given a work item with no declared channel
        When slack@C0TMP375 is declared by octocat from a comment
        Then the work item's portable record carries it with who, when and how

    Requirement: docs/specs/issue-375/requirements.md R1.1
    """
    changed, replaced = store.add(REF, ROOM, actor="octocat", note="https://x/1")
    assert changed and replaced is None

    section = WorkItemStore(tmp_path / "portable").section(REF, COLLABORATION_CHANNELS)
    assert section is not None
    (entry,) = section["channels"]
    assert entry["ref"] == ROOM
    assert entry["type"] == "slack"
    assert entry["target"] == "C0TMP375"
    assert entry["addedBy"] == "octocat"
    assert entry["source"] == "comment"
    assert entry["note"] == "https://x/1"
    assert entry["addedAt"].endswith("Z")


def test_declaring_the_same_channel_twice_changes_nothing(store):
    assert store.add(REF, ROOM)[0] is True
    assert store.add(REF, ROOM) == (False, None)
    assert [record.ref for record in store.list(REF)] == [ROOM]


def test_a_second_channel_of_one_type_moves_the_conversation(store):
    """
    Feature: a work item names the room it is worked in
      Scenario: a second Slack channel on the same work item
        Given slack@C0TMP375 is declared
        When slack@GABC123 is declared on the same work item
        Then the work item has ONE slack channel, the new one, and the call
             reports which declaration it displaced

    Requirement: docs/specs/issue-375/requirements.md R1.7
    """
    store.add(REF, ROOM)
    changed, replaced = store.add(REF, "slack@GABC123")
    assert changed and replaced is not None and replaced.ref == ROOM
    assert [record.ref for record in store.list(REF)] == ["slack@GABC123"]
    assert store.for_type(REF).target == "GABC123"


def test_a_channel_another_work_item_holds_is_refused(store):
    """
    Feature: a work item names the room it is worked in
      Scenario: two work items in one room
        Given slack@C0TMP375 is declared on #375
        When it is declared on #376
        Then the declaration is refused, naming who holds it, and #375 keeps it

    Requirement: docs/specs/issue-375/requirements.md R3.4
    """
    store.add(REF, ROOM)
    with pytest.raises(ChannelTakenError) as excinfo:
        store.add(OTHER, ROOM)
    assert REF in str(excinfo.value)
    assert store.list(OTHER) == []
    assert store.declared_by(ROOM) == REF


def test_removing_and_clearing(store):
    store.add(REF, ROOM)
    assert store.remove(REF, "slack@GABC123") is False
    assert store.remove(REF, ROOM) is True
    assert store.list(REF) == []
    assert store.clear(REF) is False  # `remove` emptied the section already
    store.add(REF, ROOM)
    assert store.clear(REF) is True
    assert store.declared_by(ROOM) == ""


def test_a_malformed_ref_is_a_valueerror_not_a_write(store):
    with pytest.raises(ValueError):
        store.add(REF, "slack@#tmp-issue-375")
    with pytest.raises(ValueError):
        store.remove(REF, "nonsense")
    assert store.list(REF) == []


# -- the reverse lookup (T3) ----------------------------------------------------


def test_the_room_names_its_work_item(store):
    store.add(REF, ROOM)
    assert store.declared_by(ROOM) == REF
    assert store.declared_by(ChannelRef("slack", "C0TMP375")) == REF
    assert store.declared_by("slack@GABC123") == ""
    assert store.targets() == {"C0TMP375": REF}


def test_a_contested_room_is_attributed_to_nobody(store, tmp_path):
    """
    Feature: a work item names the room it is worked in
      Scenario: two records name one channel (a hand-edited file)
        Given two portable records that both declare slack@C0TMP375
        When the room is looked up
        Then it resolves to no work item at all, rather than to whichever
             record sorted first

    Requirement: docs/specs/issue-375/requirements.md R3.4
    """
    raw = WorkItemStore(tmp_path / "portable")
    payload = {"channels": [CollaborationChannel("slack", "C0TMP375").to_dict()]}
    raw.write_section(REF, COLLABORATION_CHANNELS, payload)
    raw.write_section(OTHER, COLLABORATION_CHANNELS, payload)

    assert store.declared_by(ROOM) == ""
    assert store.targets() == {}


def test_an_unreadable_entry_declares_nothing(store, tmp_path):
    WorkItemStore(tmp_path / "portable").write_section(
        REF, COLLABORATION_CHANNELS, {"channels": [{"ref": "slack@#name"}, "junk"]}
    )
    assert store.list(REF) == []
    assert store.for_type(REF) is None


def test_an_absent_store_declares_nothing(tmp_path):
    empty = CollaborationChannelStore(tmp_path / "nowhere")
    assert empty.list(REF) == []
    assert empty.declared_by(ROOM) == ""
    assert empty.targets() == {}
