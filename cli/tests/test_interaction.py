"""Unit tests for the interaction mode — where a session takes its answers from.

Spec: docs/specs/issue-134/ (requirements R1, R2).

Three things are pinned here, and each one is a failure the-loop has to be unable
to have:

1. **Resolution never yields an undeclared mode**, and never yields ``cli`` by
   accident — a wrong ``work-item`` leaves a visible comment, a wrong ``cli``
   leaves a question in a pipe nobody reads.
2. **The directive reaches the prompt even from a template that never asked for
   it** — ``safe_substitute``'s silence is exactly how the rule would be lost.
3. **The bundled templates and the dispatcher's built-in fallbacks agree**, so a
   project without the plugin files installed gets the same instruction. That
   claim has been a code comment since issue-36 with nothing enforcing it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from the_loop.interaction import (
    DEFAULT_MODE,
    MODES,
    PLACEHOLDER,
    InteractionConfig,
    apply_directive,
    directive_for,
)
from the_loop.webhook.dispatcher import (
    DEFAULT_PROMPT_TEMPLATE,
    DEFAULT_SPAWN_TEMPLATE,
    RoutingConfig,
)


def flat(text: str) -> str:
    """Prose is hard-wrapped; assertions are about words, not line breaks."""
    return " ".join(text.split())


REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_TEMPLATE = REPO_ROOT / "skills/the-loop/templates/webhook-event-prompt.md"
SPAWN_TEMPLATE = REPO_ROOT / "skills/the-loop/templates/webhook-autoexecute-prompt.md"
CLI_CONFIG_SCHEMA = REPO_ROOT / ".the-loop" / "cli-config.schema.json"


# -- resolution (R1.1-R1.3) ---------------------------------------------------


def test_the_declared_vocabulary_is_exactly_two_modes():
    assert MODES == ("work-item", "cli")
    assert DEFAULT_MODE == "work-item"


@pytest.mark.parametrize("mode", MODES)
def test_a_declared_mode_resolves_to_itself(mode):
    assert InteractionConfig.from_mapping({"mode": mode}).mode == mode


@pytest.mark.parametrize("data", [{}, None, [], "cli", {"other": "cli"}])
def test_nothing_declared_resolves_to_the_default_silently(data, caplog):
    """A config predating issue-134 is not a mistake — it must not warn."""
    with caplog.at_level(logging.WARNING, logger="the-loop.interaction"):
        assert InteractionConfig.from_mapping(data).mode == DEFAULT_MODE
    assert caplog.records == []


@pytest.mark.parametrize("raw", ["  CLI ", "Work-Item", "cli\n"])
def test_case_and_whitespace_are_normalised(raw):
    assert InteractionConfig.from_mapping({"mode": raw}).mode == raw.strip().lower()


@pytest.mark.parametrize("raw", ["terminal", "", 7, None, ["cli"]])
def test_an_undeclared_mode_falls_back_to_work_item_and_warns(raw, caplog):
    """Fail closed toward the channel that always reaches a human (R1.3)."""
    with caplog.at_level(logging.WARNING, logger="the-loop.interaction"):
        resolved = InteractionConfig.from_mapping({"mode": raw})
    assert resolved.mode == "work-item"
    assert any("interaction.mode" in record.message for record in caplog.records)


@pytest.mark.parametrize("mode", ["cli", "work-item"])
def test_the_declared_modes_are_quiet(mode, caplog):
    # Both modes are workable under the tmux runner — the only runner there is
    # (issue-156): `cli` means a human sits in the attached pane.
    with caplog.at_level(logging.WARNING, logger="the-loop.interaction"):
        InteractionConfig.from_mapping({"mode": mode})
    assert caplog.records == []


def test_the_routing_config_carries_the_resolved_mode():
    """Both ingresses build their RoutingConfig this way, so one wiring covers both."""
    assert RoutingConfig.from_mapping({}).interaction.mode == DEFAULT_MODE
    declared = RoutingConfig.from_mapping({"interaction": {"mode": "cli"}})
    assert declared.interaction.mode == "cli"
    assert declared.interaction.directive == directive_for("cli")


# -- the directive text (R2.2, R2.3, R3.4) ------------------------------------


def test_the_work_item_directive_sends_questions_to_the_ticket():
    text = flat(directive_for("work-item"))
    assert "work-item" in text
    assert "never as an interactive prompt here" in text
    assert "silence as consent" in text


def test_the_cli_directive_asks_interactively_but_keeps_the_paper_trail():
    text = flat(directive_for("cli"))
    assert "interactively" in text
    assert "paper trail" in text.lower()
    assert "comment on the work item" in text


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_carries_the_artifact_rule(mode):
    """The artifact rule is an invariant, not a per-mode behaviour (decision-051)."""
    text = flat(directive_for(mode))
    assert "pull-request review" in text
    for artifact in ("brainstorm.md", "requirements.md", "design.md", "tasks.md"):
        assert artifact in text


def test_an_unknown_mode_still_yields_the_default_directive():
    assert directive_for("nonsense") == directive_for(DEFAULT_MODE)


def test_the_directive_is_constant_and_interpolates_nothing():
    """No payload-derived value reaches it — the whole security argument (R2/S1)."""
    for mode in MODES:
        assert "$" not in directive_for(mode)


# -- apply_directive: a custom template cannot drop the rule (R2.4) -----------


def test_a_template_that_declares_the_placeholder_is_left_alone():
    rendered = "body with the directive already in it"
    assert apply_directive(rendered, f"x ${PLACEHOLDER} y", "D") == rendered
    assert apply_directive(rendered, f"x ${{{PLACEHOLDER}}} y", "D") == rendered


def test_a_template_without_the_placeholder_gets_the_directive_appended():
    out = apply_directive("body\n", "no placeholder here", "THE DIRECTIVE")
    assert out.startswith("body")
    assert out.endswith("THE DIRECTIVE\n")


# -- parity: bundled templates ≡ built-in fallbacks (R2.5) --------------------


@pytest.mark.skipif(
    not EVENT_TEMPLATE.is_file(), reason="plugin templates absent (source distribution)"
)
def test_the_bundled_templates_match_the_built_in_fallbacks():
    """ "Kept in sync with skills/…" has been a comment since issue-36. Now it is a test."""
    assert EVENT_TEMPLATE.read_text(encoding="utf-8") == DEFAULT_PROMPT_TEMPLATE
    assert SPAWN_TEMPLATE.read_text(encoding="utf-8") == DEFAULT_SPAWN_TEMPLATE


def test_both_built_in_templates_declare_the_placeholder():
    for template in (DEFAULT_PROMPT_TEMPLATE, DEFAULT_SPAWN_TEMPLATE):
        assert f"${PLACEHOLDER}" in template


def test_the_directive_precedes_the_untrusted_payload_block():
    """Every the-loop instruction stays on the trusted side of the boundary."""
    for template in (DEFAULT_PROMPT_TEMPLATE, DEFAULT_SPAWN_TEMPLATE):
        assert template.index(f"${PLACEHOLDER}") < template.index("$payload_excerpt")


# -- schema (R1.4) ------------------------------------------------------------


def test_the_schema_declares_the_mode_enum():
    schema = json.loads(CLI_CONFIG_SCHEMA.read_text(encoding="utf-8"))
    routing = schema["properties"]["routing"]
    mode = routing["properties"]["interaction"]["properties"]["mode"]
    assert mode["enum"] == list(MODES)
    assert mode["default"] == DEFAULT_MODE
