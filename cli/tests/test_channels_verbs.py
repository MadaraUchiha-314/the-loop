"""Unit tests for issue-389 task 3: the grammar after the mention (R3.1, R3.2,
R3.4; design §3). Spec: docs/specs/issue-389/testing-plan.md T1."""

from __future__ import annotations

from the_loop.channels.slack import SlackChannelConfig
from the_loop.channels.verbs import (
    KINDS,
    VERBS,
    Verb,
    compose_keyword,
    help_text,
    parse_verb,
    strip_mention,
)
from the_loop.control import ControlConfig
from test_channels import cli_config


def test_strip_mention_removes_the_bots_token_wherever_it_sits():
    """R1.1: the `<@bot>` token is removed anywhere; another member's stays."""
    assert strip_mention("<@UBOT> record-context", "UBOT") == ("record-context", True)
    assert strip_mention("please <@UBOT|the-loop> help", "UBOT") == (
        "please help",
        True,
    )
    assert strip_mention("ping <@UOTHER> about it", "UBOT") == (
        "ping <@UOTHER> about it",
        False,
    )
    assert strip_mention("no mention here", "UBOT") == ("no mention here", False)
    assert strip_mention("<@UBOT>", "") == ("<@UBOT>", False)


def test_parse_verb_reads_the_first_token_and_nothing_else():
    """R3.1: exactly one of the verbs, case-insensitively; anything else is None
    (a reply), including prose that merely mentions a verb later."""
    assert VERBS == ("record-context", "record-decision", "help")
    assert parse_verb("record-context") == Verb("record-context", "")
    assert parse_verb("  Record-Context please") == Verb("record-context", "please")
    assert parse_verb("help") == Verb("help", "")
    assert parse_verb("HELP me") == Verb("help", "me")
    assert parse_verb("we should record-context this") is None
    assert parse_verb("") is None
    assert parse_verb("record-contexts") is None


def test_parse_verb_reads_a_decisions_kind_and_rationale():
    """R5.1: `record-decision [<kind>:] <text> [— why: <rationale>]` — the shape
    the modal composes (R6.3), so typed and tapped decisions parse alike."""
    assert KINDS == ("product", "design", "tech")
    assert parse_verb("record-decision we ship on Friday") == Verb(
        "record-decision", "we ship on Friday"
    )
    assert parse_verb("record-decision tech: keep poll mode") == Verb(
        "record-decision", "keep poll mode", kind="tech"
    )
    assert parse_verb(
        "record-decision product: drop the modal — why: nobody asked"
    ) == Verb(
        "record-decision", "drop the modal", kind="product", rationale="nobody asked"
    )
    # An unknown kind is text, not a kind.
    assert parse_verb("record-decision legal: no") == Verb(
        "record-decision", "legal: no"
    )
    # Empty text is still a verb — the pipeline refuses it (R5.2).
    assert parse_verb("record-decision") == Verb("record-decision", "")
    assert parse_verb("record-decision tech:") == Verb(
        "record-decision", "", kind="tech"
    )


def test_compose_keyword_builds_the_configured_line_from_the_last_word():
    """R3.4: `start` becomes `the-loop start`, exactly as the slash command
    composes it; prose stays prose; a disabled keyword composes nothing."""
    control = ControlConfig.from_mapping({})
    assert compose_keyword("start", control) == "the-loop start"
    assert compose_keyword("execute now", control) == "the-loop execute now"
    assert compose_keyword("add-collaborator slack:U0123", control) == (
        "the-loop add-collaborator slack:U0123"
    )
    assert compose_keyword("what is blocking you?", control) == "what is blocking you?"
    assert compose_keyword("", control) == ""
    renamed = ControlConfig.from_mapping({"keywords": {"start": "loop go"}})
    assert compose_keyword("go", renamed) == "loop go"
    # The command's own name composes too — the slash command's rule, so the
    # three surfaces agree on what `start` means under a renamed keyword.
    assert compose_keyword("start", renamed) == "loop go"
    disabled = ControlConfig.from_mapping({"keywords": {"start": ""}})
    assert compose_keyword("start", disabled) == "start"


def test_help_text_teaches_the_grammar_and_names_this_channels_grants(tmp_path):
    """R3.2: the vocabulary, taught — every verb, the keyword rule, the
    fallthrough, and which of the two new grants this channel holds."""
    config = SlackChannelConfig.from_mapping(
        cli_config(tmp_path, publish=["work-item.reply", "context.added"])
    )
    text = help_text(config)
    for verb in VERBS:
        assert verb in text
    assert "add-collaborator" in text and "anything else" in text.lower()
    assert "context.added: granted" in text
    assert "decision.recorded: not granted" in text


# -- self-review round 1 (findings 2 and 3) ------------------------------------------


def test_strip_mention_keeps_the_lines():
    """A mentioned kickoff keeps its title/body split, a decision its lines."""
    assert strip_mention("<@UBOT> octo/repo: Fix teardown\n\nSteps: x  y", "UBOT") == (
        "octo/repo: Fix teardown\n\nSteps: x y",
        True,
    )
    assert strip_mention("  <@UBOT>  hi\n", "UBOT") == ("hi", True)


def test_compose_keyword_reads_a_member_mention_as_the_roster_token():
    """R3.5: `<@U…>` and `<@U…|handle>` after `add-collaborator` become
    `slack:U…`; another verb's mentions are left as typed."""
    control = ControlConfig.from_mapping({})
    assert (
        compose_keyword("add-collaborator <@U0456GHIJ|dana> @octocat", control)
        == "the-loop add-collaborator slack:U0456GHIJ @octocat"
    )
    assert (
        compose_keyword("remove-collaborator <@U0456GHIJ>", control)
        == "the-loop remove-collaborator slack:U0456GHIJ"
    )
    assert (
        compose_keyword("start <@U0456GHIJ>", control) == "the-loop start <@U0456GHIJ>"
    )


def test_help_public_is_read_from_the_first_line_only():
    """issue-397 O4/O5: `help public` asks for the answer as a visible reply;
    only the first token after `help` on its FIRST line is read, so a connector
    that signs every message on a second line ("*Sent using* @Claude", O5)
    neither turns `help` public nor breaks the verb."""
    from the_loop.channels.verbs import PUBLIC_HELP, wants_public_help

    assert PUBLIC_HELP == "public"
    assert wants_public_help(Verb("help", "")) is False
    assert wants_public_help(Verb("help", "public")) is True
    assert wants_public_help(Verb("help", "PUBLIC please")) is True
    assert wants_public_help(Verb("help", "me public")) is False
    assert wants_public_help(Verb("record-context", "public")) is False
    # O5: the connector's signature line is never the word that is read.
    signed = parse_verb("help\n*Sent using* @Claude")
    assert signed is not None and signed == Verb("help", "*Sent using* @Claude")
    assert wants_public_help(signed) is False
    signed_public = parse_verb("help public\n*Sent using* @Claude")
    assert signed_public is not None and wants_public_help(signed_public) is True
    assert wants_public_help(Verb("help", "\npublic")) is False
