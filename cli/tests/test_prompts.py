"""Unit tests for the prompt loader (issue-540, R1).

Every prompt or prompt fragment the CLI sends to an agent is a Markdown file under
``the_loop/prompts/``. These tests pin the loader's contract: names resolve under that
directory only, a missing file fails loudly, and the two webhook prompts published as
skill templates are byte-identical to the packaged ones.
"""

from pathlib import Path
from string import Template

import pytest

from the_loop import prompts

REPO = Path(__file__).resolve().parents[2]


def test_load_returns_the_file_verbatim():
    text = prompts.load("webhook/event")
    assert text.startswith("# $event_source event for $work_item\n")
    assert text.endswith("```\n")


def test_inline_drops_exactly_one_trailing_newline():
    full = prompts.load("sessions/restart-notice")
    assert full.endswith("\n")
    assert prompts.load("sessions/restart-notice", inline=True) == full[:-1]


def test_render_fills_named_slots():
    text = prompts.render("standing/directive", name="supervisor", surfaces="here")
    assert text.startswith("You are **supervisor**, a the-loop *standing session*.")
    assert "**Where your operator speaks to you:** here." in text


def test_missing_prompt_names_the_file():
    with pytest.raises(FileNotFoundError, match=r"prompts/nope/missing\.md"):
        prompts.load("nope/missing")


@pytest.mark.parametrize(
    "name", ["../cli_config", "webhook/../../x", "/etc/passwd", "Webhook/Event", "", "a//b"]
)
def test_names_outside_the_directory_are_refused(name):
    with pytest.raises(ValueError):
        prompts.load(name)


def test_names_lists_every_shipped_prompt_and_each_loads():
    names = prompts.names()
    assert "webhook/event" in names and "webhook/autoexecute" in names
    for name in names:
        assert prompts.load(name), name


@pytest.mark.parametrize(
    "packaged, published",
    [
        ("webhook/event", "webhook-event-prompt.md"),
        ("webhook/autoexecute", "webhook-autoexecute-prompt.md"),
    ],
)
def test_skill_templates_are_identical_to_the_packaged_prompts(packaged, published):
    """R1.6: one text, two places — the skill copy is what operators read and copy."""
    skill = (REPO / "skills/the-loop/templates" / published).read_text(encoding="utf-8")
    assert skill == prompts.load(packaged)


def test_untrusted_placeholders_in_a_payload_stay_literal():
    """Abuse case 1: substitution is single-pass, so a payload cannot expand slots."""
    hostile = "$work_item ${interaction_directive} {name} {0}"
    rendered = Template(prompts.load("webhook/autoexecute")).safe_substitute(
        work_item="github:o/r#1", payload_excerpt=hostile
    )
    assert hostile in rendered
    rendered = prompts.render(
        "standing/directive", name="{surfaces}", surfaces="$work_item"
    )
    assert "You are **{surfaces}**" in rendered
    assert "speaks to you:** $work_item." in rendered
