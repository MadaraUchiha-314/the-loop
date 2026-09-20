"""Integration: a comment declares a work item's collaboration channel (issue-375).

The real :class:`Dispatcher` against a routed ``issue_comment`` event, with the
real declaration store on a tmp path and a real ``GitHubReactor`` whose ``gh``
invocation is captured — so what is asserted is what the daemon does with a
comment an authorized user typed, including the acknowledgment issue-371 wired to
every consumed event.

Spec: docs/specs/issue-375/testing-plan.md T12–T15.
"""

from conftest import FakeTmux
from test_reactions_integration import (
    REF,
    contents,
    make_control_dispatcher,
    routed_command,
    wait_until,
)

OTHER = "github:octo/repo#16"
ROOM = "slack@C0TMP375"


def declarations(dispatcher, ref=REF):
    return [record.ref for record in dispatcher.channel_store.list(ref)]


def _resolving(dispatcher, names):
    """Point the dispatcher's one resolution seam at a fixed workspace.

    The seam `_resolve_channel` exists so the whole command path can be driven
    with no workspace at all — the only thing stubbed is the call that would talk
    to Slack, and the grammar, the store and the refusals stay real.
    """
    from the_loop.workchannels import ChannelRef, parse_channel_ref

    def resolve(ref):
        channel = parse_channel_ref(ref)
        assert channel is not None
        if channel.is_id:
            return channel, ""
        found = names.get(channel.name, "")
        if not found:
            raise ValueError(f"no Slack channel named {channel.target!r}")
        return ChannelRef(type=channel.type, target=found), channel.name

    dispatcher._resolve_channel = resolve


def test_a_declaration_from_an_authorized_comment_is_recorded_and_acknowledged(
    tmp_path, monkeypatch
):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: an authorized user types the keyword
        Given control is enabled and octocat is an authorized user
        When octocat comments `the-loop add-channel slack@C0TMP375`
        Then the work item's record carries that channel with the comment's URL
        And the comment is acknowledged, and nothing is delivered to a session
             because the comment WAS the command

    Requirement: docs/specs/issue-375/requirements.md R1.1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    (record,) = dispatcher.channel_store.list(REF)
    assert record.ref == ROOM
    assert record.added_by == "octocat"
    assert record.source == "comment"
    assert record.note == "https://c/77"
    assert contents(runner) == ["content=hooray"]
    assert tmux.delivers == [] and tmux.spawns == []


def test_the_uri_spelling_declares_the_same_channel(tmp_path, monkeypatch):
    """R1.3: `slack://C…` and `slack@C…` are one declaration."""
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command("the-loop add-channel slack://C0TMP375"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert declarations(dispatcher) == [ROOM]


def test_a_channel_name_is_resolved_to_its_id(tmp_path, monkeypatch):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: the name a person actually knows
        Given control is enabled and octocat is an authorized user
        When octocat comments `the-loop add-channel slack@#tmp-issue-375`
        Then the record stores the conversation ID, keeps the NAME for display,
             and the comment is acknowledged

    Requirement: docs/specs/issue-375/requirements.md R1.5, R6.1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    _resolving(dispatcher, {"tmp-issue-375": "C0TMP375"})

    dispatcher.handle(routed_command("the-loop add-channel slack@#tmp-issue-375"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    (record,) = dispatcher.channel_store.list(REF)
    assert record.ref == ROOM  # the ID is what the ingress will route on
    assert record.name == "tmp-issue-375"  # …and the name is what a human reads
    assert record.label == "slack@#tmp-issue-375"
    assert contents(runner) == ["content=hooray"]


def test_a_name_that_resolves_to_nothing_is_refused(tmp_path, monkeypatch):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: a channel the bot cannot see
        Given a workspace where #ghost does not exist (or the bot is not in it)
        When octocat declares it
        Then nothing is declared and the comment is acknowledged as an error —
             a declaration that would fail at the first post never happens

    Requirement: docs/specs/issue-375/requirements.md R6.3
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    _resolving(dispatcher, {})

    dispatcher.handle(routed_command("the-loop add-channel slack@#ghost"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert contents(runner) == ["content=confused"]


def test_an_unknown_channel_type_is_refused(tmp_path, monkeypatch):
    """R1.4: a type with no adapter is refused, not stored and ignored."""
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command("the-loop add-channel jira@PROJ"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert contents(runner) == ["content=confused"]


def test_an_unauthorized_author_declares_nothing(tmp_path, monkeypatch):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: somebody who does not direct the loop types the keyword
        Given octocat is the only authorized user
        When mallory comments the add-channel keyword
        Then nothing is declared — declaring is an ACTION, and actions read
             routing.authorizedUsers alone

    Requirement: docs/specs/issue-375/requirements.md R1.1, abuse case A3
    """
    tmux = FakeTmux()
    dispatcher, _ = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}", author="mallory"))
    dispatcher.stop()

    assert declarations(dispatcher) == []


def test_remove_undeclares_from_a_comment(tmp_path, monkeypatch):
    """R1.6: the other half of the pair, same authorization."""
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}", delivery="c-1"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.handle(routed_command(f"the-loop remove-channel {ROOM}", delivery="c-2"))
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()

    assert declarations(dispatcher) == []


def test_a_comment_carrying_two_different_keywords_declares_nothing(
    tmp_path, monkeypatch
):
    """R1.1: the existing ambiguity rule covers the new pair — a body that also
    says `the-loop start` is refused outright rather than half-applied."""
    tmux = FakeTmux()
    dispatcher, _ = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM} and the-loop start"))
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert tmux.spawns == []


def test_a_channel_another_work_item_holds_is_refused(tmp_path, monkeypatch):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: the room already backs another work item
        Given #16 declared slack@C0TMP375
        When an authorized user declares it on #15
        Then #15 declares nothing and the comment is acknowledged as an error

    Requirement: docs/specs/issue-375/requirements.md R3.4
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.channel_store.add(OTHER, ROOM, actor="octocat")

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert declarations(dispatcher, OTHER) == [ROOM]
    assert contents(runner) == ["content=confused"]


def test_declaring_neither_arms_nor_spawns(tmp_path, monkeypatch):
    """
    Feature: a work item is declared into a channel from its ticket
      Scenario: naming a room is not starting the work
        Given a labelled work item with no session
        When an authorized user declares its collaboration channel
        Then no session is spawned and no control record is written — a
             declaration says where the work is discussed, not that it runs

    Requirement: docs/specs/issue-375/requirements.md R1.1
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert tmux.spawns == [] and tmux.delivers == []
    assert dispatcher.control_store.get(REF) is None


# -- the listen mode (issue-389 §2) -----------------------------------------------


def test_a_room_is_switched_to_hear_everything_by_an_authorized_comment(
    tmp_path, monkeypatch
):
    """
    Feature: a room can be switched to hear everything, by an authorized user only
      Scenario: add-channel --listen all is recorded with provenance
        Given control is enabled and octocat is an authorized user
        When octocat comments `the-loop add-channel slack@C0TMP375 --listen all`
        Then the declaration carries `listen: all` with who, when and the URL
        And the comment is acknowledged as executed
        When octocat re-declares the room with `--listen mentions`
        Then the mode is replaced and the comment is acknowledged again

    Requirement: docs/specs/issue-389/requirements.md#R2
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(
        routed_command(f"the-loop add-channel {ROOM} --listen all", delivery="l-1")
    )
    assert wait_until(lambda: len(runner.commands) == 1)
    (record,) = dispatcher.channel_store.list(REF)
    assert record.listen == "all"
    assert record.added_by == "octocat" and record.note == "https://c/77"
    assert dispatcher.delivery_outcome("l-1") == "control-executed"

    dispatcher.handle(
        routed_command(f"the-loop add-channel {ROOM} --listen mentions", delivery="l-2")
    )
    assert wait_until(lambda: len(runner.commands) == 2)
    dispatcher.stop()

    (record,) = dispatcher.channel_store.list(REF)
    assert record.listen == "mentions"
    assert contents(runner) == ["content=hooray", "content=hooray"]
    assert tmux.delivers == [] and tmux.spawns == []


def test_a_declaration_without_a_mode_listens_to_mentions(tmp_path, monkeypatch):
    """R2.1: the default is `mentions`."""
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    (record,) = dispatcher.channel_store.list(REF)
    assert record.listen == "mentions"


def test_an_unknown_listen_mode_declares_nothing(tmp_path, monkeypatch):
    """
    Feature: a room can be switched to hear everything, by an authorized user only
      Scenario: a mode the-loop does not know
        Given control is enabled and octocat is an authorized user
        When octocat comments `add-channel slack@C0TMP375 --listen everything`
        Then nothing is declared and the comment is acknowledged as an error —
             the command is refused whole rather than declared with a default

    Requirement: docs/specs/issue-389/requirements.md#R2 (abuse case A12)
    """
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)

    dispatcher.handle(
        routed_command(
            f"the-loop add-channel {ROOM} --listen everything", delivery="l-3"
        )
    )
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert contents(runner) == ["content=confused"]
    assert dispatcher.delivery_outcome("l-3") == "control-rejected"


def test_a_collaborator_cannot_switch_a_room(tmp_path, monkeypatch):
    """
    Feature: a room can be switched to hear everything, by an authorized user only
      Scenario: a collaborator cannot switch a room
        Given dana is a collaborator on the work item, and not an authorized user
        When dana comments `the-loop add-channel slack@C0TMP375 --listen all`
        Then nothing is declared and the attempt is recorded as a refusal —
             the switch is a binding act, and binding acts read
             routing.authorizedUsers alone

    Requirement: docs/specs/issue-389/requirements.md#R2 (abuse case A2)
    """
    tmux = FakeTmux()
    dispatcher, _ = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.collaborator_store.add(REF, login="dana", actor="octocat")

    dispatcher.handle(
        routed_command(
            f"the-loop add-channel {ROOM} --listen all", delivery="l-4", author="dana"
        )
    )
    assert wait_until(lambda: dispatcher.delivery_outcome("l-4") == "control-rejected")
    dispatcher.stop()

    assert declarations(dispatcher) == []
    assert tmux.delivers == []


def test_a_new_declaration_confirms_the_room_through_the_opener(tmp_path, monkeypatch):
    """
    Feature: the room hears about its declaration (issue-397 O1)
      Scenario: an authorized user declares a room from the ticket
        Given the dispatcher was handed a conversation opener
        When octocat comments `the-loop add-channel slack@C0TMP375`
        Then the opener is called once with the work item — the same idempotent
             open the spawn path makes — so the room gets its "every update …
             is posted here" message now, not at the item's first update
        And declaring the same room again opens nothing (already declared)
        And undeclaring it opens nothing

    Requirement: docs/specs/issue-397/requirements.md R1
    """
    tmux = FakeTmux()
    opened = []
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.opener = opened.append

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    assert opened == [REF]

    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}", delivery="k-2"))
    assert wait_until(lambda: len(runner.commands) == 2)
    assert opened == [REF]

    dispatcher.handle(routed_command(f"the-loop remove-channel {ROOM}", delivery="k-3"))
    assert wait_until(lambda: len(runner.commands) == 3)
    dispatcher.stop()
    assert opened == [REF]
    assert declarations(dispatcher) == []


def test_a_failing_confirmation_never_undoes_the_declaration(tmp_path, monkeypatch):
    """
    Scenario: the room cannot be confirmed
      Given the opener raises (a channel bug, a workspace that is down)
      When octocat declares a room
      Then the declaration is recorded and acknowledged exactly as before

    Requirement: docs/specs/issue-397/requirements.md R1.3
    """
    tmux = FakeTmux()

    def broken(_ref):
        raise RuntimeError("workspace down")

    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    dispatcher.opener = broken
    dispatcher.handle(routed_command(f"the-loop add-channel {ROOM}"))
    assert wait_until(lambda: len(runner.commands) == 1)
    dispatcher.stop()
    assert declarations(dispatcher) == [ROOM]
    assert contents(runner) == ["content=hooray"]
