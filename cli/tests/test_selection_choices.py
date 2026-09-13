"""The model and effort sections of the phase-selection gate (issue-358).

Two independent questions on the checklist the gate already posts, answered by the
same signed reply. What is tested here is the whole of the trust boundary: a reply
can only ever pick a **key into what the operator declared**, and an ambiguous answer
to one section must not damage the other.
"""

from __future__ import annotations

import pytest

from pathlib import Path

from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection


def _ctx(**config):
    config.setdefault("harness", "claude")
    return HookContext(
        work_item=WorkItem(
            ref="github:octo/repo#358", id="issue-358", spec_dir=Path(".")
        ),
        node={"id": "phase-selection"},
        boundary="entry",
        repo=Path("."),
        config=config,
    )


def _declared(**over):
    config = {
        "harnesses": [{"name": "claude", "default": True}, {"name": "cursor"}],
        "models": [
            "opus-5",
            "fable-5.1",
            {"name": "gpt-5.6-sol", "harnesses": ["cursor"]},
        ],
        "effort": ["low", "high"],
    }
    config.update(over)
    return config


# -- what is offered ------------------------------------------------------------


def test_a_models_own_narrowing_keeps_it_off_another_harness():
    ctx = _ctx(**_declared())
    assert selection._model_rows(ctx) == ["opus-5", "fable-5.1"]


def test_the_other_harness_is_offered_everything_not_narrowed_away():
    """A bare name is a candidate for EVERY declared harness — the probe, not the
    declaration, decides whether cursor can actually run `opus-5`."""
    config = _declared()
    config["harness"] = "cursor"
    assert selection._model_rows(_ctx(**config)) == [
        "opus-5",
        "fable-5.1",
        "gpt-5.6-sol",
    ]


def test_effort_is_offered_in_the_loops_enum_order():
    assert selection._effort_rows(_ctx(**_declared())) == ["low", "high"]


def test_nothing_declared_offers_nothing():
    ctx = _ctx()
    assert selection._model_rows(ctx) == []
    assert selection._effort_rows(ctx) == []


# -- what the checklist says ----------------------------------------------------


def test_each_section_is_rendered_only_when_it_has_something_to_offer():
    body = "\n".join(selection._choice_lines(_ctx(**_declared())))
    assert "`model-opus-5`" in body and "`effort-high`" in body
    assert "`model-gpt-5.6-sol`" not in body, "narrowed away for this harness"

    assert selection._choice_lines(_ctx()) == [], "declare nothing, ask nothing"


def test_a_long_list_is_capped_and_counted_rather_than_truncated():
    names = [f"model-{n}" for n in range(selection.CANDIDATE_LIMIT + 5)]
    ctx = _ctx(**_declared(models=names))
    body = "\n".join(selection._choice_lines(ctx))
    assert "…and 5 more not shown" in body


def test_a_models_about_line_is_rendered_beside_it():
    ctx = _ctx(**_declared(models=[{"name": "opus-5", "about": "for real design"}]))
    assert "for real design" in "\n".join(selection._choice_lines(ctx))


def test_an_unavailable_model_is_withheld_from_the_checklist(tmp_path):
    """R7.3 — a model the harness refuses is never offered, so nobody can pick it."""
    import time

    from the_loop.modelprobe import REFUSED, Verdict, VerdictCache

    path = tmp_path / "verdicts.json"
    cache = VerdictCache(str(path))
    cache.put(Verdict("claude", "model", "fable-5.1", "", REFUSED, time.time()))

    ctx = _ctx(**_declared(verdictCache=str(path)))
    assert selection._model_rows(ctx) == ["opus-5"]


# -- what a reply means ---------------------------------------------------------


def test_one_ticked_row_is_a_choice():
    body = "- [x] `model-fable-5.1`\n- [ ] `model-opus-5`"
    assert (
        selection._parse_choice(body, selection.MODEL_PREFIX, ["opus-5", "fable-5.1"])
        == "fable-5.1"
    )


@pytest.mark.parametrize(
    "body",
    [
        "- [ ] `model-opus-5`",  # none ticked
        "- [x] `model-opus-5`\n- [x] `model-fable-5.1`",  # two ticked
        "",  # unreadable / deleted comment
        "- [x] `model-smuggled-9`",  # not an offered choice
    ],
)
def test_anything_ambiguous_is_no_choice(body):
    """Fail-closed to the operator's own configuration, never to a guess."""
    assert (
        selection._parse_choice(body, selection.MODEL_PREFIX, ["opus-5", "fable-5.1"])
        == ""
    )


def test_an_ambiguous_model_does_not_discard_a_valid_effort():
    """R1.5 — the two sections are resolved independently."""
    body = "- [x] `model-opus-5`\n- [x] `model-fable-5.1`\n- [x] `effort-high`"
    assert (
        selection._parse_choice(body, selection.MODEL_PREFIX, ["opus-5", "fable-5.1"])
        == ""
    )
    assert (
        selection._parse_choice(body, selection.EFFORT_PREFIX, ["low", "high"])
        == "high"
    )


# -- abuse ----------------------------------------------------------------------


def test_abuse_a_reply_naming_a_flag_or_a_path_resolves_to_nothing():
    """A2 — no text from a comment may ever reach an argv."""
    for smuggled in (
        "model---dangerously-skip-permissions",
        "model-../../etc/passwd",
        "model-/etc/passwd",
    ):
        body = f"- [x] `{smuggled}`"
        assert selection._parse_choice(body, selection.MODEL_PREFIX, ["opus-5"]) == ""


def test_abuse_a_shell_fragment_after_a_real_name_is_not_smuggled_through():
    """A2, the interesting half. `model-opus-5;rm -rf /` DOES select a model —
    `opus-5`, because the checklist's token grammar admits no `;` and stops
    there. What matters is that the row can only ever yield a name the operator
    declared: the trailing text is not truncated *args*, it was never part of the
    token, and nothing of it exists downstream to reach a command line."""
    body = "- [x] `model-opus-5;rm -rf /`"
    chosen = selection._parse_choice(body, selection.MODEL_PREFIX, ["opus-5"])
    assert chosen == "opus-5"
    assert ";" not in chosen and "rm" not in chosen


def test_abuse_a_choice_row_is_never_read_as_a_phase():
    """A model row must not become a declared skip or a refusal, either way it is
    ticked — otherwise picking a model would silently drop a phase."""
    body = "- [ ] `model-opus-5`\n- [ ] `effort-high`\n- [ ] `design`"
    skips, opt_ins, refused = selection._parse_selection(
        body, ["design"], [], ["phase-selection"]
    )
    assert skips == ["design"]
    assert refused == [] and opt_ins == []


# -- the gate's own authorization (A1, A6) ---------------------------------------


def _gate_ctx(comments, **config):
    """A context the real `classify-phase-selection` hook will run against."""
    config.setdefault("harness", "claude")
    config.setdefault("authorizedUsers", ["owner"])
    return HookContext(
        work_item=WorkItem(
            ref="github:octo/repo#358", id="issue-358", spec_dir=Path(".")
        ),
        node={"id": "phase-selection"},
        boundary="exit",
        repo=Path("."),
        config=config,
        event={"comments": comments},
    )


def test_abuse_an_unauthorized_reply_freezes_nothing(monkeypatch):
    """A1. The model rows ride the same authorization as every other answer at this
    gate — and the filter runs upstream of any parsing, so an unauthorized reply is
    never even read for a choice."""
    monkeypatch.setattr(
        selection, "_resolve", lambda ctx: pytest.fail("must not reach GitHub")
    )
    ctx = _gate_ctx(
        [
            {
                "author": "a-stranger",
                "body": "- [x] `model-fable-5.1`\nthe-loop execute",
            }
        ],
        **_declared(),
    )
    result = selection.classify_phase_selection(ctx)
    assert result.status == "wait"
    assert "model" not in (result.data or {})


def test_abuse_an_unreadable_checklist_keeps_the_operators_arguments(monkeypatch):
    """A6. A deleted or unreachable comment resolves to no choice — never to a
    guess, and never to the last thing somebody happened to tick."""
    posted = []

    class _Integration:
        def call(self, verb, **kw):
            if verb == "list-comments":
                raise OSError("github is unreachable")
            posted.append(kw)
            return {}

    monkeypatch.setattr(selection, "_resolve", lambda ctx: _Integration())
    ctx = _gate_ctx(
        [{"author": "owner", "body": "the-loop execute"}],  # no checklist in the reply
        **_declared(),
    )
    result = selection.classify_phase_selection(ctx)
    assert result.status == "pass"
    assert result.data["model"] == ""
    assert result.data["effort"] == ""


def test_an_authorized_reply_freezes_both_choices(monkeypatch):
    posted = []

    class _Integration:
        def call(self, verb, **kw):
            posted.append((verb, kw))
            return {}

    monkeypatch.setattr(selection, "_resolve", lambda ctx: _Integration())
    ctx = _gate_ctx(
        [
            {
                "author": "owner",
                "body": "- [x] `model-fable-5.1`\n- [x] `effort-high`\nthe-loop execute",
            }
        ],
        **_declared(),
    )
    result = selection.classify_phase_selection(ctx)
    assert result.data["model"] == "fable-5.1"
    assert result.data["effort"] == "high"
    assert result.data["frozenGraph"]["model"] == "fable-5.1"
    # ...and the human is told, in both directions (R1.6).
    confirmation = next(kw["body"] for verb, kw in posted if verb == "add-comment")
    assert "fable-5.1" in confirmation and "high" in confirmation
