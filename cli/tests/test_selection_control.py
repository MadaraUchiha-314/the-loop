"""The phase-selection control (issue-393 R9, feature F1): the checklist drawn as
Slack checkboxes, Execute composing the signed execute the GitHub path produces,
the typed `execute without <n, …>` / `skip <phase>` grammar, the no-interactivity
fallback, and the copy. Spec: docs/specs/issue-393/{requirements,design,
testing-plan}.md (T1 grammar, T2 checkbox/fallback Scenarios, T8 abuse cases 2, 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.channels import inbound
from the_loop.channels.base import InboundReply
from the_loop.channels.slack import (
    ACTION_PREFIX,
    CHECKBOX_LIMIT,
    DEFAULT_BOT_TOKEN_ENV,
    EXECUTE_ACTION,
    PHASE_BOX_ACTION,
    PHASE_SELECTION_MARKER,
    SELECTION_BLOCK,
    SURFACE_BOX_ACTION,
    SURFACE_TOKEN,
    SelectionRow,
    SlackChannelConfig,
    _CHECKLIST_ROW,
    _NON_PHASE_PREFIXES,
    _press_blocks,
    apply_without,
    compose_selection_execute,
    render_blocks,
    selection_rows,
    without_clause,
)
from the_loop.channels.verbs import compose_keyword, help_text
from the_loop.control import ControlConfig, parse_command
from the_loop.graph.hooks import selection
from test_channels_buttons import (
    FakeSlackClient,
    _wire,
    a_press,
    buttons,
    checklist_event,
    interactive_config,
    make_channel,
)

#: Shaped like `graph/hooks/selection.py`'s checklist: default-on phases, one
#: opt-in phase, one protected phase, the outer-loop row, the sessions rows, a
#: model row, the marker last.
CHECKLIST = f"""🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs.

- [x] brainstorming
- [x] requirements-definition
- [x] design
- [x] implementation

**Optional phases — these do NOT run unless you tick them.**

- [ ] design-critic-review — a second, adversarial read of the design.

These phases always run and are not selectable:

- security-review

**Where should the outer loop happen?**

- [ ] `{SURFACE_TOKEN}` — on a pull request in this repository.

**How many sessions should this work item's pull requests get?**

- [ ] `pr-sessions-never` — every pull request's events land in this session.
- [x] `pr-sessions-cross-repository` — another repository's pull request gets its own.
- [ ] `pr-sessions-always` — every pull request gets its own.

**Which model should this work item run on?**

- [ ] `model-opus-5`

{PHASE_SELECTION_MARKER}
"""

DEFAULT_ON = ["brainstorming", "requirements-definition", "design", "implementation"]
OPT_IN = ["design-critic-review"]
PROTECTED = ["security-review"]
KEYWORD = "the-loop execute"
OPEN = (f"{ACTION_PREFIX}open", "https://github.com/o/r/issues/7#c1")


class EphemeralClient(FakeSlackClient):
    """The buttons' fake, plus the ephemeral a refusal is told through."""

    def __init__(self):
        super().__init__()
        self.ephemeral = []  # (channel, user, text)

    def chat_postEphemeral(self, *, channel, user, text, thread_ts=None):
        self.ephemeral.append((channel, user, text))
        return {"ok": True}


def _control(blocks):
    """The control's checkboxes, as ``(action_id, [(value, ticked)])``."""
    out = []
    for block in blocks:
        if block.get("type") != "actions" or not str(
            block.get("block_id") or ""
        ).startswith(SELECTION_BLOCK):
            continue
        for element in block["elements"]:
            initial = {o["value"] for o in element.get("initial_options", [])}
            out.append(
                (
                    element["action_id"],
                    [(o["value"], o["value"] in initial) for o in element["options"]],
                )
            )
    return out


def _sections(blocks):
    return "\n".join(
        str((b.get("text") or {}).get("text") or "")
        for b in blocks
        if b.get("type") == "section"
    )


def _post_control(tmp_path, monkeypatch, client, config, text=CHECKLIST):
    """The checklist posted through a channel that can carry the control; the
    bound thread and the message a member sees."""
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    channel = make_channel(tmp_path, client, config=config)
    channel.post(checklist_event(text))
    return channel, "1700.000001", client.posted[-1]


def _press_with_state(
    blocks, ticks, *, surface=False, author="UHUMAN", thread="1700.000001", state=True
):
    """A press of Execute on the control, the boxes as ``ticks`` names them — the
    payload Slack sends: every stateful element under ``state.values``."""
    press = a_press(author=author, thread=thread)
    press["message"] = {**press["message"], "blocks": blocks}
    values = {}
    for block in blocks:
        if block.get("type") != "actions" or not str(
            block.get("block_id") or ""
        ).startswith(SELECTION_BLOCK):
            continue
        element = block["elements"][0]
        if element["action_id"] == SURFACE_BOX_ACTION:
            selected = list(element["options"]) if surface else []
        else:
            selected = [o for o in element["options"] if o["value"] in ticks]
        values[block["block_id"]] = {
            element["action_id"]: {
                "type": "checkboxes",
                "selected_options": [
                    {"text": o["text"], "value": o["value"]} for o in selected
                ],
            }
        }
    if state:
        press["state"] = {"values": values}
    return press


def _typed(config, channel, text, *, thread, author="UHUMAN", addressed=False):
    return inbound.process_reply(
        InboundReply(
            channel="slack",
            work_item="github:o/r#7",
            author=author,
            text=text,
            thread=thread,
            ts="1800.1",
            channel_id="C123",
            addressed=addressed,
        ),
        SlackChannelConfig.from_mapping(config),
        config,
        channel=channel,
    )


# -- the rows, read off the checklist's own text ----------------------------------


def test_the_rows_are_read_off_the_checklists_own_text():
    rows = selection_rows(CHECKLIST)
    assert rows is not None
    assert [(r.token, r.ticked) for r in rows.phases] == [
        ("brainstorming", True),
        ("requirements-definition", True),
        ("design", True),
        ("implementation", True),
        ("design-critic-review", False),
    ]
    assert rows.phases[-1].about == "a second, adversarial read of the design."
    assert rows.surface == SelectionRow(
        SURFACE_TOKEN, False, "on a pull request in this repository."
    )
    assert [(r.token, r.ticked) for r in rows.others] == [
        ("pr-sessions-never", False),
        ("pr-sessions-cross-repository", True),
        ("pr-sessions-always", False),
        ("model-opus-5", False),
    ]
    assert rows.always == ("security-review",)
    assert rows.phase("Design") == rows.phases[2] and rows.phase("nonesuch") is None
    assert selection_rows("no marker here\n- [x] design") is None


def test_the_row_grammar_and_the_non_phase_tokens_are_the_hooks():
    """The channel transcribes the hook's checklist with the hook's grammar —
    pinned, like the marker, so a change in either place fails here."""
    body = (
        "> - [ ] design\n- [x] `outer-loop-on-pull-request` — x\n"
        "* [X] `model-a` y\n  - [ ] b.c-d\n- plain\n- [x]\n"
    )
    ours = [(m.group("mark"), m.group("token")) for m in _CHECKLIST_ROW.finditer(body)]
    theirs = [
        (m.group("mark"), m.group("token"))
        for m in selection._CHECK_LINE.finditer(body)
    ]
    assert ours == theirs and len(ours) == 4
    assert SURFACE_TOKEN == selection.SURFACE_TOKEN
    assert selection.MODEL_PREFIX in _NON_PHASE_PREFIXES
    assert selection.EFFORT_PREFIX in _NON_PHASE_PREFIXES
    for token in (SURFACE_TOKEN, *selection.PR_SESSIONS_TOKENS, "model-x", "effort-y"):
        assert selection._is_non_phase(token)
        assert token == SURFACE_TOKEN or token.startswith(_NON_PHASE_PREFIXES)


# -- R9.1, R9.2: the control ----------------------------------------------------------


def test_the_checklist_mirror_renders_checkboxes_for_the_phases_and_the_outer_loop():
    """
    Scenario: the phase-selection checklist is a control in an interactive room
      Given the checklist's mirror and a channel whose Execute can be pressed
      When the message renders
      Then the phases are checkboxes, ticked as the checklist ticks them
      And the outer-loop question is an element of its own in the same message
      And Execute closes the message, its value the configured keyword

    Requirement: docs/specs/issue-393/requirements.md R9.1, R9.2
    """
    blocks = render_blocks(
        checklist_event(CHECKLIST), "normal", commands={"execute": KEYWORD}
    )
    assert _control(blocks) == [
        (
            f"{PHASE_BOX_ACTION}:0",
            [
                ("brainstorming", True),
                ("requirements-definition", True),
                ("design", True),
                ("implementation", True),
                ("design-critic-review", False),
            ],
        ),
        (SURFACE_BOX_ACTION, [(SURFACE_TOKEN, False)]),
    ]
    assert buttons(blocks) == [OPEN, (EXECUTE_ACTION, KEYWORD)]
    assert blocks[0]["type"] == "header" and blocks[-1]["type"] == "actions"
    texts = _sections(blocks)
    assert "Which phases does this work item need?" in texts
    assert "press *Execute*" in texts and "tick anything optional" in texts
    assert "☑" not in texts and "right here" not in texts, "the rows are the boxes"
    context = [b for b in blocks if b["type"] == "context"][-1]["elements"][0]["text"]
    assert "`security-review`" in context and "tick them on GitHub" in context
    options = next(
        b for b in blocks if b.get("block_id") == f"{SELECTION_BLOCK}:phases:0"
    )["elements"][0]["options"]
    assert options[0]["text"]["text"] == "1. `brainstorming`"
    assert options[4]["text"]["text"] == "5. `design-critic-review`"
    assert "adversarial" in options[4]["description"]["text"]
    assert "description" not in options[0]


def test_a_long_phase_list_is_chunked_at_slacks_ceiling():
    rows = "\n".join(f"- [x] phase-{n}" for n in range(CHECKBOX_LIMIT + 5))
    blocks = render_blocks(
        checklist_event(f"q\n\n{rows}\n\n{PHASE_SELECTION_MARKER}"),
        "normal",
        commands={"execute": KEYWORD},
    )
    control = _control(blocks)
    assert [a for a, _ in control] == [f"{PHASE_BOX_ACTION}:0", f"{PHASE_BOX_ACTION}:1"]
    assert len(control[0][1]) == CHECKBOX_LIMIT and len(control[1][1]) == 5
    second = next(
        b for b in blocks if b.get("block_id") == f"{SELECTION_BLOCK}:phases:1"
    )
    assert (
        second["elements"][0]["options"][0]["text"]["text"]
        == f"{CHECKBOX_LIMIT + 1}. `phase-{CHECKBOX_LIMIT}`"
    ), "the numbering the reply grammar counts continues across the chunks"


def test_a_loop_without_an_outer_loop_row_gets_no_surface_box():
    """A contribution (issue-199) asks no surface question; nor does its control."""
    body = CHECKLIST.replace(
        f"- [ ] `{SURFACE_TOKEN}` — on a pull request in this repository.\n", ""
    )
    control = _control(
        render_blocks(checklist_event(body), "normal", commands={"execute": KEYWORD})
    )
    assert [a for a, _ in control] == [f"{PHASE_BOX_ACTION}:0"]


def test_in_a_room_the_control_leads_with_the_question_and_no_header():
    blocks = render_blocks(
        checklist_event(CHECKLIST),
        "normal",
        commands={"execute": KEYWORD},
        agentic=True,
    )
    assert blocks[0]["type"] == "section"
    assert blocks[0]["text"]["text"].startswith("🤔 *Which phases")
    assert not any(b["type"] == "header" for b in blocks)


def test_the_control_is_posted_through_the_channel(tmp_path, monkeypatch):
    """T2: the message a member sees in a Socket Mode room granted control.command."""
    client = FakeSlackClient()
    _, _, posted = _post_control(
        tmp_path, monkeypatch, client, interactive_config(tmp_path)
    )
    assert [a for a, _ in _control(posted["blocks"])] == [
        f"{PHASE_BOX_ACTION}:0",
        SURFACE_BOX_ACTION,
    ]
    assert buttons(posted["blocks"]) == [OPEN, (EXECUTE_ACTION, KEYWORD)]


# -- R9.4: no interactivity, no control ---------------------------------------------


@pytest.mark.parametrize(
    "slack",
    [
        {"read": {"mode": "poll"}},
        {"publish": ["work-item.reply", "gate.feedback"]},
        {"control": {"keywords": {"execute": ""}}},
    ],
)
def test_without_an_interactivity_grant_the_message_points_at_the_github_checklist(
    tmp_path, monkeypatch, slack
):
    """
    Scenario: without an interactivity grant the message points at the GitHub checklist
      Given a channel that cannot receive a press (poll mode, no control.command
            grant, or a disabled execute keyword)
      When the checklist's mirror renders
      Then no checkbox is drawn and the digest stands
      And a line says the checklist is edited on GitHub, linked, and where to reply
      And nothing instructs "untick right here"

    Requirement: docs/specs/issue-393/requirements.md R9.4
    """
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeSlackClient()
    make_channel(tmp_path, client, **slack).post(checklist_event(CHECKLIST))
    blocks = client.posted[-1]["blocks"]
    assert _control(blocks) == []
    assert buttons(blocks) == [OPEN]
    assert blocks[-1]["type"] == "actions", "the link button still closes the message"
    line = [b for b in blocks if b["type"] == "context"][-1]["elements"][0]["text"]
    assert "edited <https://github.com/o/r/issues/7#c1|on GitHub>" in line
    if "control" in slack:
        assert "execute keyword there" in line, "a disabled keyword has no name"
    else:
        assert f"reply `{KEYWORD}` there" in line
    assert "right here" not in "\n".join(str(b) for b in blocks)


# -- R9.1: Execute composes the signed execute -------------------------------------------


def test_an_execute_press_composes_the_signed_execute_from_the_boxes(
    tmp_path, monkeypatch
):
    """
    Scenario: checkbox submission composes the signed execute
      Given the control in a bound thread
      When an authorized member unticks two phases, ticks the optional one and the
           outer-loop box, then presses Execute
      Then the ledger holds the member's execute with the list in it — the reply a
           person types on GitHub — attributed to them by the envelope
      And the gate's own parser reads exactly those skips, that opt-in, that surface
      And the message is edited: the control and the button gone, the link kept

    Requirement: docs/specs/issue-393/requirements.md R9.1
    """
    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = FakeSlackClient()
    _, thread, posted = _post_control(tmp_path, monkeypatch, client, config)
    press = _press_with_state(
        posted["blocks"],
        {"brainstorming", "implementation", "design-critic-review"},
        surface=True,
        thread=thread,
    )
    outcome = inbound.handle_socket_action(
        press, config, client_factory=lambda t: client
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "control.command"
    assert outcome["mirrored"] is True
    ref, body = records[0]
    assert ref == "github:o/r#7"
    assert f"> {KEYWORD}" in body, "the keyword, quoted as the member's own words"
    for line in (
        "> - [x] brainstorming",
        "> - [ ] requirements-definition",
        "> - [ ] design",
        "> - [x] implementation",
        "> - [x] design-critic-review",
        f"> - [x] `{SURFACE_TOKEN}`",
    ):
        assert line in body
    assert parse_command(body, ControlConfig()).command == "execute"
    skips, opt_ins, refused = selection._parse_selection(
        body, DEFAULT_ON, OPT_IN, PROTECTED
    )
    assert skips == ["requirements-definition", "design"]
    assert opt_ins == ["design-critic-review"] and refused == []
    assert selection._parse_surface(body) == selection.SURFACE_PULL_REQUEST
    from the_loop.channels.envelope import parse as parse_envelope

    envelope = parse_envelope(body)
    assert envelope is not None
    assert envelope.actor == {"github": "gh-UHUMAN", "slack": "UHUMAN"}
    assert len(client.updates) == 1
    _, ts, _, blocks = client.updates[0]
    assert ts == press["message"]["ts"]
    assert _control(blocks) == [] and buttons(blocks) == [OPEN]
    assert not any(
        str(b.get("block_id") or "").startswith(SELECTION_BLOCK) for b in blocks
    )
    assert blocks[-1]["elements"][0]["text"].startswith("✅ *Execute*")


def test_boxes_left_alone_compose_the_full_process():
    blocks = render_blocks(
        checklist_event(CHECKLIST), "normal", commands={"execute": KEYWORD}
    )
    press = _press_with_state(blocks, set(DEFAULT_ON))
    composed = compose_selection_execute(KEYWORD, press["message"], press["state"])
    skips, opt_ins, _ = selection._parse_selection(
        composed, DEFAULT_ON, OPT_IN, PROTECTED
    )
    assert skips == [] and opt_ins == []
    assert selection._parse_surface(composed) == selection.DEFAULT_SURFACE


def test_a_partial_or_malformed_state_keeps_the_boxes_as_drawn():
    """Fail-closed, the gate's own way: an element the payload does not carry
    keeps its rendered ticks — every default-on phase runs, no opt-in does, the
    outer loop stays on the work item. A message without the control composes
    the bare keyword, as an Execute press always did."""
    blocks = render_blocks(
        checklist_event(CHECKLIST), "normal", commands={"execute": KEYWORD}
    )
    message = {"blocks": blocks}
    composed = compose_selection_execute(KEYWORD, message, {"values": {}})
    assert composed.splitlines()[0] == KEYWORD
    assert "- [x] design" in composed and "- [ ] design-critic-review" in composed
    assert f"- [ ] `{SURFACE_TOKEN}`" in composed
    for broken in (None, "state", {"values": "garbage"}, {"values": {"x": "y"}}):
        assert compose_selection_execute(KEYWORD, message, broken) == composed
    plain = render_blocks(checklist_event(CHECKLIST), "normal")
    assert (
        compose_selection_execute(KEYWORD, {"blocks": plain}, {"values": {}}) == KEYWORD
    )
    assert compose_selection_execute(KEYWORD, {}, None) == KEYWORD


def test_abuse_a_smuggled_value_cannot_tick_a_phase_that_was_not_offered():
    """A value the message never offered is not a box: it reaches no record, and
    the composed reply still carries exactly one command."""
    blocks = render_blocks(
        checklist_event(CHECKLIST), "normal", commands={"execute": KEYWORD}
    )
    state = {
        "values": {
            f"{SELECTION_BLOCK}:phases:0": {
                f"{PHASE_BOX_ACTION}:0": {
                    "type": "checkboxes",
                    "selected_options": [
                        {"value": "security-review"},
                        {"value": "the-loop start"},
                        {"value": "design"},
                        "not even a mapping",
                    ],
                }
            }
        }
    }
    composed = compose_selection_execute(KEYWORD, {"blocks": blocks}, state)
    assert "security-review" not in composed and "start" not in composed
    assert "- [x] design" in composed and "- [ ] brainstorming" in composed
    assert parse_command(composed, ControlConfig()).command == "execute"


def test_a_toggle_of_a_box_alone_does_nothing(tmp_path, monkeypatch):
    """Ticking a box sends a block_actions with no value: no reply, no record —
    only Execute acts."""
    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = FakeSlackClient()
    _, thread, posted = _post_control(tmp_path, monkeypatch, client, config)
    toggle = a_press(thread=thread)
    toggle["actions"] = [
        {
            "action_id": f"{PHASE_BOX_ACTION}:0",
            "type": "checkboxes",
            "selected_options": [{"value": "design"}],
        }
    ]
    assert inbound.handle_socket_action(
        toggle, config, client_factory=lambda t: client
    ) == {"outcome": "ignored"}
    assert records == [] and client.updates == []


def test_a_landed_press_takes_the_control_away_and_a_failed_one_keeps_it():
    blocks = render_blocks(
        checklist_event(CHECKLIST), "normal", commands={"execute": KEYWORD}
    )
    landed = _press_blocks({"blocks": blocks}, True, "✅ line")
    assert _control(landed) == []
    assert not any(
        str(b.get("block_id") or "").startswith(SELECTION_BLOCK) for b in landed
    )
    assert landed[0] == blocks[0] and landed[-1]["type"] == "context"
    kept = _press_blocks({"blocks": blocks}, False, "⚠️ line")
    assert _control(kept) == _control(blocks), "a failed press keeps the retry"


# -- abuse case 2: an unauthorized submission freezes nothing ---------------------------


def test_abuse_an_unauthorized_checkbox_submission_freezes_nothing(
    tmp_path, monkeypatch
):
    """
    Scenario: an unauthorized member submits the phase-selection control
      Given the control in a bound thread
      When a member on no list presses Execute with boxes unticked
      Then the press is dropped before the record — no comment, no edit, nothing
           frozen — and, as for every stranger, no mark is left (decision-111 D1)
      When a collaborator (on the roster, not the allow-list) presses it
      Then they are told a control needs an authorized user, and nothing is frozen

    Requirement: docs/specs/issue-393/requirements.md §Security abuse case 2
    """
    from the_loop.collaborators import CollaboratorStore

    records = []
    _wire(monkeypatch, records)
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    _, thread, posted = _post_control(tmp_path, monkeypatch, client, config)
    stranger = _press_with_state(posted["blocks"], set(), author="UEVIL", thread=thread)
    assert inbound.handle_socket_action(
        stranger, config, client_factory=lambda t: client
    ) == {"outcome": "unauthorized-actor"}
    assert records == [] and client.updates == [] and client.ephemeral == []

    CollaboratorStore(Path(config["state"]["root"]) / "portable").add(
        "github:o/r#7", slack="UCOLLAB", actor="octocat", source="cli"
    )
    collaborator = _press_with_state(
        posted["blocks"], set(), author="UCOLLAB", thread=thread
    )
    outcome = inbound.handle_socket_action(
        collaborator, config, client_factory=lambda t: client
    )
    assert outcome == {"outcome": "unauthorized-act"}
    assert records == [] and client.updates == []
    assert client.ephemeral[-1][1] == "UCOLLAB"
    assert "needs an authorized user" in client.ephemeral[-1][2]


# -- R9.3: the typed grammar ---------------------------------------------------------


def test_skip_composes_to_execute_without():
    control = ControlConfig()
    assert (
        compose_keyword("skip brainstorming", control)
        == f"{KEYWORD} without brainstorming"
    )
    assert compose_keyword("SKIP design, 3", control) == f"{KEYWORD} without design, 3"
    assert compose_keyword("execute without 1, 3", control) == f"{KEYWORD} without 1, 3"
    renamed = ControlConfig.from_mapping({"keywords": {"execute": "loop go"}})
    assert compose_keyword("skip design", renamed) == "loop go without design"
    disabled = ControlConfig.from_mapping({"keywords": {"execute": ""}})
    assert compose_keyword("skip design", disabled) == "skip design", "a reply, then"


def test_without_clause_reads_numbers_and_names_after_the_keyword():
    assert without_clause(f"{KEYWORD} without 1, 3", KEYWORD) == ["1", "3"]
    assert without_clause(
        "The-Loop Execute WITHOUT design and `brainstorming`.", KEYWORD
    ) == ["design", "brainstorming"]
    assert without_clause(f"{KEYWORD} without the phases 2; 4", KEYWORD) == ["2", "4"]
    assert without_clause(f"{KEYWORD} without", KEYWORD) == []
    assert without_clause(KEYWORD, KEYWORD) is None
    assert without_clause(f"{KEYWORD}\n\n- [ ] design", KEYWORD) is None
    assert without_clause(f"without design, {KEYWORD}", KEYWORD) is None
    assert without_clause(f"{KEYWORD} withoutdesign", KEYWORD) is None
    assert without_clause(f"{KEYWORD} without 1", "") is None


def test_apply_without_unticks_the_named_phases_and_keeps_every_other_row():
    """T1: `execute without 1, 3` — by number in checklist order, or by name."""
    rows = selection_rows(CHECKLIST)
    assert rows is not None
    composed, refusal = apply_without(rows, ["1", "design"], KEYWORD)
    assert refusal == ""
    lines = composed.splitlines()
    assert lines[0] == KEYWORD
    for line in (
        "- [ ] brainstorming",
        "- [x] requirements-definition",
        "- [ ] design",
        "- [x] implementation",
        "- [ ] design-critic-review",
        f"- [ ] `{SURFACE_TOKEN}`",
        "- [x] `pr-sessions-cross-repository`",
        "- [ ] `model-opus-5`",
    ):
        assert line in lines
    skips, opt_ins, refused = selection._parse_selection(
        composed, DEFAULT_ON, OPT_IN, PROTECTED
    )
    assert skips == ["brainstorming", "design"] and opt_ins == [] and refused == []
    assert selection._parse_pr_sessions(composed, "never") == "cross-repository"
    assert parse_command(composed, ControlConfig()).command == "execute"


@pytest.mark.parametrize(
    ("items", "reason"),
    [
        (["desgin"], "`desgin` is not a phase this checklist offers"),
        (["security-review"], "`security-review` always runs on this work item"),
        (["9"], "There is no phase 9"),
        (["0"], "There is no phase 0"),
        ([SURFACE_TOKEN], "is not a phase this checklist offers"),
        (["pr-sessions-never"], "is not a phase this checklist offers"),
        ([], "needs the phases to leave out"),
        (["design", "desgin"], "`desgin` is not a phase"),
    ],
)
def test_abuse_an_unknown_or_unskippable_phase_refuses_the_whole_reply(items, reason):
    """Abuse case 4: a name the checklist does not offer — a typo, a protected
    phase, a row that is not a phase — refuses the reply with the reason, and
    names what was offered; one bad name among good ones refuses all of them."""
    rows = selection_rows(CHECKLIST)
    assert rows is not None
    composed, refusal = apply_without(rows, items, KEYWORD)
    assert composed == "" and reason in refusal
    assert "nothing was recorded" in refusal or "needs the phases" in refusal
    assert "1. `brainstorming`" in refusal and "5. `design-critic-review`" in refusal


def test_abuse_a_hostile_name_is_named_never_echoed():
    rows = selection_rows(CHECKLIST)
    assert rows is not None
    for hostile in ("<!channel>", "x" * 60, "design;rm -rf /", "@here"):
        composed, refusal = apply_without(rows, [hostile], KEYWORD)
        assert composed == "" and hostile not in refusal and "that name" in refusal


def test_a_typed_execute_without_records_the_checklist_with_those_phases_unticked(
    tmp_path, monkeypatch
):
    """T1, R9.3: the rows a typed reply counts are the live checklist's on the
    ticket — the same comment the gate reads — and the record is the same signed
    execute the boxes compose."""
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(
        inbound, "_selection_checklist", lambda work_item, cfg: CHECKLIST
    )
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    outcome = _typed(config, channel, f"{KEYWORD} without 1, 3", thread=thread)
    assert outcome["outcome"] == "processed" and outcome["event"] == "control.command"
    body = records[0][1]
    assert "> - [ ] brainstorming" in body and "> - [ ] design" in body
    assert "> - [x] requirements-definition" in body
    skips, _, refused = selection._parse_selection(body, DEFAULT_ON, OPT_IN, PROTECTED)
    assert skips == ["brainstorming", "design"] and refused == []


def test_skip_by_mention_is_the_same_signed_execute(tmp_path, monkeypatch):
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(
        inbound, "_selection_checklist", lambda work_item, cfg: CHECKLIST
    )
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    outcome = _typed(
        config, channel, "<@UBOT> skip design", thread=thread, addressed=True
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "control.command"
    body = records[0][1]
    assert f"> {KEYWORD}" in body and "> - [ ] design" in body
    assert "> - [x] brainstorming" in body
    assert "skip" not in body.split(">", 1)[1].lower(), "the shorthand is composed away"


def test_abuse_an_unknown_phase_typed_is_refused_with_the_reason_and_records_nothing(
    tmp_path, monkeypatch
):
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(
        inbound, "_selection_checklist", lambda work_item, cfg: CHECKLIST
    )
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    outcome = _typed(config, channel, f"{KEYWORD} without desgin", thread=thread)
    assert outcome == {"outcome": "unskippable-phase"}
    assert records == []
    assert client.ephemeral[-1][1] == "UHUMAN"
    assert "`desgin` is not a phase" in client.ephemeral[-1][2]
    assert ("C123", "1800.1", "warning") in client.reactions, "the error reaction"


def test_an_unreadable_checklist_refuses_rather_than_guessing(tmp_path, monkeypatch):
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(inbound, "_selection_checklist", lambda work_item, cfg: "")
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    outcome = _typed(config, channel, f"{KEYWORD} without 2", thread=thread)
    assert outcome == {"outcome": "unskippable-phase"} and records == []
    assert "Could not read the phase checklist" in client.ephemeral[-1][2]


def test_a_bare_execute_reads_no_checklist_and_records_the_keyword_alone(
    tmp_path, monkeypatch
):
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(
        inbound,
        "_selection_checklist",
        lambda work_item, cfg: pytest.fail("a bare keyword needs no checklist"),
    )
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    outcome = _typed(config, channel, KEYWORD, thread=thread)
    assert outcome["outcome"] == "processed"
    assert "- [" not in records[0][1]


def test_a_stranger_typing_the_grammar_is_dropped_before_anything_is_read(
    tmp_path, monkeypatch
):
    records = []
    _wire(monkeypatch, records)
    monkeypatch.setattr(
        inbound,
        "_selection_checklist",
        lambda work_item, cfg: pytest.fail("a stranger reads nothing"),
    )
    config = interactive_config(tmp_path)
    client = EphemeralClient()
    channel, thread, _ = _post_control(tmp_path, monkeypatch, client, config)
    assert _typed(
        config, channel, f"{KEYWORD} without 1", thread=thread, author="UEVIL"
    ) == {"outcome": "unauthorized-actor"}
    assert records == [] and client.ephemeral == []


def test_help_teaches_the_skip_grammar(tmp_path):
    text = help_text(SlackChannelConfig.from_mapping(interactive_config(tmp_path)))
    assert "`execute without 1, 3`" in text and "`skip <phase>`" in text


# -- the gate reads what the channel writes -------------------------------------------


def test_the_gate_reads_a_quoted_checklist():
    """The ledger relays a member's words quoted; a `> - [ ] design` is that
    person's unticked box, and it makes the reply's list win over the checklist."""
    body = (
        "🗣️ **the-loop** — control command from `dana` on the **slack** channel:\n\n"
        f"> {KEYWORD}\n> \n> - [ ] design\n> - [x] brainstorming\n"
        f"> - [x] `{SURFACE_TOKEN}`\n> - [x] `pr-sessions-always`"
    )
    assert selection._CHECK_LINE.search(body)
    skips, opt_ins, refused = selection._parse_selection(
        body, ["design", "brainstorming"], [], PROTECTED
    )
    assert skips == ["design"] and opt_ins == [] and refused == []
    assert selection._parse_surface(body) == selection.SURFACE_PULL_REQUEST
    assert selection._parse_pr_sessions(body, "never") == "always"


# -- R9.4, R9.5: the checklist's own copy -----------------------------------------------


def _hook_ctx():
    from the_loop.graph.contract import HookContext, WorkItem
    from the_loop.graph.model import load_graph

    return HookContext(
        work_item=WorkItem(ref="github:o/r#7", id="issue-7", spec_dir=Path(".")),
        node={"id": "phase-selection"},
        boundary="entry",
        repo=Path("."),
        config={"authorizedUsers": ["owner"]},
        graph=load_graph(),
    )


def test_the_checklist_copy_neither_threatens_nor_promises_ticking_right_here():
    """R9.5: no "recorded against your name"; the record of who chose what stays
    in the ledger. R9.4: no "right here on this comment" — the sentence is true
    on GitHub and in a room alike."""
    from the_loop.graph.model import load_graph

    body = selection._checklist_body(_hook_ctx())
    assert "recorded against your name" not in body
    assert "right here" not in body
    assert "Every phase of this loop is selectable" in body
    assert "recorded as its own declared choice" in body
    # and what the hook posts is what the channel reads: its rows are the control's
    rows = selection_rows(body)
    assert rows is not None
    ordered = list(load_graph().ordered())
    assert [r.token for r in rows.phases if r.ticked] == [
        n.id for n in ordered if n.skippable and not n.opt_in
    ]
    assert [r.token for r in rows.phases if not r.ticked] == [
        n.id for n in ordered if n.opt_in
    ]
    assert rows.surface is not None and not rows.surface.ticked
    assert len(rows.phases) > CHECKBOX_LIMIT, "the shipped loop needs the chunking"
