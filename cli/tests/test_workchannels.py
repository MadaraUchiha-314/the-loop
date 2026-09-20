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
    LISTEN_MODES,
    ChannelRef,
    ChannelTakenError,
    CollaborationChannel,
    CollaborationChannelStore,
    describe_refusal,
    listen_mode_for,
    parse_channel_ref,
    parse_channel_refs,
    resolve_channel_ref,
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
        # …and the spelling a person actually knows (PR #376 review): a channel
        # NAME, with or without its #, resolved to an id before it is stored.
        ("slack@#tmp-issue-375", "slack@#tmp-issue-375"),
        ("slack@tmp-issue-375", "slack@tmp-issue-375"),
        ("slack://#tmp-issue-375", "slack@#tmp-issue-375"),
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
        store.add(REF, "jira@PROJ-1")
    with pytest.raises(ValueError):
        store.remove(REF, "nonsense")
    assert store.list(REF) == []


def test_the_store_refuses_an_unresolved_name(store):
    """
    Feature: a work item names the room it is worked in
      Scenario: a name reaches the store without being resolved
        Given `slack@#tmp-issue-375`, which parses but is not an id
        When it is declared
        Then the store refuses it, so there is exactly ONE place a name becomes
             an id and exactly one place that failure is reported

    Requirement: docs/specs/issue-375/requirements.md R1.11
    """
    with pytest.raises(ValueError, match="resolve it"):
        store.add(REF, "slack@#tmp-issue-375")
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
    """A hand-edited record naming a channel by NAME is ignored too: the ingress
    routes on ids, and a stored name would mean a lookup per message."""
    WorkItemStore(tmp_path / "portable").write_section(
        REF,
        COLLABORATION_CHANNELS,
        {"channels": [{"ref": "slack@a/b"}, {"ref": "slack@#a-name"}, "junk"]},
    )
    assert store.list(REF) == []
    assert store.for_type(REF) is None


def test_an_absent_store_declares_nothing(tmp_path):
    empty = CollaborationChannelStore(tmp_path / "nowhere")
    assert empty.list(REF) == []
    assert empty.declared_by(ROOM) == ""
    assert empty.targets() == {}


# -- the listen mode (issue-389 §2, R2.1 / T1 / T10 / A12) -------------------------


def test_the_two_listen_modes_are_named_and_mentions_is_the_default():
    assert LISTEN_MODES == ("mentions", "all")
    record = CollaborationChannel("slack", "C0TMP375")
    assert record.listen == "mentions"
    assert record.to_dict()["listen"] == "mentions"


def test_a_listen_mode_round_trips():
    record = CollaborationChannel("slack", "C0TMP375", listen="all")
    assert record.to_dict()["listen"] == "all"
    read = CollaborationChannel.from_dict(record.to_dict())
    assert read is not None and read.listen == "all"


def test_a_declaration_without_listen_reads_as_mentions():
    """T10: a declaration written before the field existed is a `mentions` room —
    the quieter mode, which is also what every room was before issue-389."""
    read = CollaborationChannel.from_dict(
        {"ref": ROOM, "type": "slack", "target": "C0TMP375", "addedBy": "octocat"}
    )
    assert read is not None and read.listen == "mentions"


@pytest.mark.parametrize(
    "value", ["everything", "ALL", "All", "", None, 1, True, ["all"], {"all": 1}]
)
def test_a_bad_listen_value_reads_as_mentions(value):
    """A12: a forged or hand-edited `listen` is honoured only when it is one of the
    two modes, exactly spelled; anything else falls to `mentions`, never to `all`.

    Requirement: docs/specs/issue-389/requirements.md#R2 (abuse case A12)
    """
    read = CollaborationChannel.from_dict({"ref": ROOM, "listen": value})
    assert read is not None and read.listen == "mentions"


def test_a_listen_mode_on_an_invalid_declaration_buys_nothing():
    """A12: declaration validity comes first — `listen: all` on an entry that stores
    a name rather than an id, or no channel at all, is not a declaration at all."""
    assert (
        CollaborationChannel.from_dict({"ref": "slack@#room", "listen": "all"}) is None
    )
    assert CollaborationChannel.from_dict({"listen": "all"}) is None


def test_the_store_writes_the_listen_mode_and_a_redeclaration_replaces_it(
    store, tmp_path
):
    """
    Feature: a room can be switched to hear everything
      Scenario: the mode is declared, then re-declared
        Given slack@C0TMP375 declared with `--listen all`
        Then the record carries `listen: all` with the declaration's provenance
        When the same channel is declared again with `mentions`
        Then the call reports a change and the record now says `mentions`
        And declaring it again with `mentions` changes nothing

    Requirement: docs/specs/issue-389/requirements.md#R2
    """
    changed, replaced = store.add(REF, ROOM, actor="octocat", listen="all")
    assert changed and replaced is None
    section = WorkItemStore(tmp_path / "portable").section(REF, COLLABORATION_CHANNELS)
    assert section is not None
    (entry,) = section["channels"]
    assert entry["listen"] == "all" and entry["addedBy"] == "octocat"
    assert store.for_type(REF).listen == "all"

    changed, replaced = store.add(REF, ROOM, actor="ann", listen="mentions")
    assert changed and replaced is None
    (record,) = store.list(REF)
    assert record.listen == "mentions" and record.added_by == "ann"
    assert store.add(REF, ROOM, listen="mentions") == (False, None)
    assert store.add(REF, ROOM) == (False, None)  # the default IS mentions


def test_a_listen_mode_the_store_does_not_know_is_refused_not_written(store):
    with pytest.raises(ValueError, match="mentions"):
        store.add(REF, ROOM, listen="everything")
    with pytest.raises(ValueError):
        store.add(REF, ROOM, listen="ALL")
    assert store.list(REF) == []


def test_the_listen_mode_of_a_room_is_read_by_its_channel_id(store):
    """
    Feature: a room can be switched to hear everything
      Scenario: the ingress asks how a room listens
        Given no declaration
        Then the answer is `mentions` — the mode of every room that is not a room
        When slack@C0TMP375 is declared with `all`
        Then the answer for C0TMP375 is `all`, and for any other id `mentions`

    Requirement: docs/specs/issue-389/requirements.md#R2
    """
    assert listen_mode_for(store, "C0TMP375") == "mentions"
    store.add(REF, ROOM, listen="all")
    assert listen_mode_for(store, "C0TMP375") == "all"
    assert listen_mode_for(store, "GABC123") == "mentions"
    assert listen_mode_for(store, "") == "mentions"
    assert listen_mode_for(store, "not an id") == "mentions"


def test_a_contested_room_listens_to_mentions_only(store, tmp_path):
    """A room two records claim is attributed to nobody, and so hears nothing but
    the mention — the same fail-closed answer `declared_by` gives."""
    raw = WorkItemStore(tmp_path / "portable")
    payload = {
        "channels": [CollaborationChannel("slack", "C0TMP375", listen="all").to_dict()]
    }
    raw.write_section(REF, COLLABORATION_CHANNELS, payload)
    raw.write_section(OTHER, COLLABORATION_CHANNELS, payload)
    assert listen_mode_for(store, "C0TMP375") == "mentions"


def test_an_absent_store_listens_to_mentions_only(tmp_path):
    assert listen_mode_for(CollaborationChannelStore(tmp_path / "nowhere"), "C0A") == (
        "mentions"
    )


# -- resolve_channel_ref's refusal distinguishes truncated from exhausted (B1) --


class _FakeDirectory:
    """Minimal SlackDirectory stand-in: a name resolver plus the truncation
    flag resolve_channel_ref reads on a miss (issue-393 R1.4)."""

    def __init__(self, resolved="", truncated=False):
        self._resolved = resolved
        self._truncated = truncated

    def conversation_id(self, value):
        return self._resolved

    def listing_was_truncated(self):
        return self._truncated


def test_resolve_names_the_truncated_listing_on_a_miss():
    """
    Feature: a channel name resolves wherever the bot can already speak
      Scenario: a miss over a truncated listing is not "no such channel"
        Given a directory whose workspace listing was truncated at the page cap
        When a name it could not find is resolved
        Then the refusal says the listing was truncated and the name may exist
             beyond the cap — never a flat "no such channel"

    Requirement: docs/specs/issue-393/requirements.md R1.4 (B1)
    """
    ref = parse_channel_ref("slack@#test-room")
    assert ref is not None
    with pytest.raises(ValueError, match="truncated"):
        resolve_channel_ref(ref, directory=_FakeDirectory(truncated=True))


def test_resolve_says_no_such_channel_on_an_exhausted_miss():
    """The counter-case: a listing that ran to its end is a trustworthy miss,
    so the refusal is the definitive one (spelling / invite / scopes)."""
    ref = parse_channel_ref("slack@#test-room")
    assert ref is not None
    with pytest.raises(ValueError, match="no Slack channel named"):
        resolve_channel_ref(ref, directory=_FakeDirectory(truncated=False))
