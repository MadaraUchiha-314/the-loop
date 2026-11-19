"""Writing-contract parity (issue-165).

the-loop's artifacts are read by a human who has to approve them, and nothing in the
harness used to say how they should read. issue-165 added a writing contract: a bundled
``the-loop:writing`` skill (the policy it carried in the harness config left with
issue-352 — the contract is the skill itself) and a
pointer to that skill in every template producing a human-read artifact.

**There are no length budgets, deliberately.** The first draft of this work item shipped
per-artifact word budgets; the owner rejected them on PR #168 for the reason that settles
it — a work item's scope is not known in advance, so any number is wrong for half the work
items, and a cap only pushes prose into an appendix. The skill's test is *density* (can a
sentence come out without losing information?), which is a review judgement and is
deliberately NOT asserted here. See decision-061.

Prose describing a rule does not execute it — that is what issue-124 and issue-148 both
cost. So the mechanical parts of the contract are asserted here:

======  =========================================================  =========================
P1      the writing skill exists and its front-matter parses       the skill is renamed or dropped
P2      every human-read template points at the writing skill      a template ships with no contract
P3      every pointer names the one bundled skill                  the two drift apart
P4      no P0 writing tell appears in shipped prose                a chatbot tic reaches a user-facing doc
======  =========================================================  =========================

What is deliberately NOT asserted: whether a document is *well written*, or how long it
is. R5.3 of ``docs/specs/issue-165/requirements.md`` draws that line — presence is
mechanical, quality is a review item — and the surveyed prior art
(https://github.com/conorbronsdon/avoid-ai-writing) reports false-positive rates above
60% on non-native speakers for exactly this kind of pattern matching. P4 is therefore
limited to tells with no legitimate technical reading, and it scans **shipped prose only**
— never ``docs/specs/`` or the evidence under it, because a build that can go red over the
style of a committed record is the "a style pass rewrites a record" abuse case from
``design.md`` §Security design.

Pure filesystem reads: no network, no subprocess, no fixtures.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "skills"
WRITING_SKILL = SKILLS / "writing" / "SKILL.md"
WRITING_TELLS = SKILLS / "writing" / "reference" / "tells.md"
TEMPLATES = SKILLS / "the-loop" / "templates"
#: The one writing skill the-loop ships (issue-352: no longer a harness-config default).
WRITING_SKILL_NAME = "the-loop:writing"

pytestmark = pytest.mark.skipif(
    not SKILLS.is_dir(),
    reason="plugin skills not present (source distribution)",
)

#: The pointer each human-read template carries: an HTML comment naming the skill that
#: governs it. Invisible when the markdown renders, greppable, and it sits where the
#: author is already looking. A comment rather than visible prose because the template's
#: own text is a cost to every reader of every artifact made from it.
_POINTER = re.compile(r"<!--[^>]*?`(the-loop:[\w.-]+)`\s+skill", re.DOTALL)

#: Templates producing an artifact a human reads and approves. ``brainstorm.md`` and the
#: ``evidence/`` records are excluded on purpose: the brainstorm is a scratchpad and a gate
#: record states what happened, so neither is written *at* a reviewer. ``bugfix.md`` is
#: listed beside ``requirements.md`` because they are two accepted names for ONE artifact
#: (decision-045), and a rule that reached only one of them is the issue-124 shape.
HUMAN_READ_TEMPLATES = [
    "requirements.md",
    "bugfix.md",
    "design.md",
    "testing-plan.md",
    "tasks.md",
    "pr-briefing.md",
    "decision.md",
    "capability.md",
]

#: Files exempt from P4. The tells catalogue quotes the tells it bans — it is the one
#: place in the repository where they are the subject rather than the voice.
_TELL_EXEMPT = {WRITING_TELLS}

#: P0 tells: unambiguous machine-writing artifacts with no legitimate technical reading.
#: Word-tier lists ("leverage", "robust", "seamless") stay in ``tells.md`` as judgement.
#: They are common, correct English in a technical document, and banning them here would
#: be a gate people route around.
P0_TELLS: List[tuple[str, str]] = [
    (r"\bdelv(?:e|es|ed|ing) into\b", "throat-clearing filler"),
    (r"\bit'?s worth noting that\b", "hedged filler; state the thing"),
    (r"\b(?:it is|it's) important to note that\b", "hedged filler; state the thing"),
    (
        r"\bin today'?s (?:fast-paced|competitive|digital|ever-changing)\b",
        "slot-fill opener",
    ),
    (r"\blet'?s dive (?:in|into)\b", "chatbot tic"),
    (r"\bunleash(?:ing)? the (?:power|potential)\b", "marketing slot-fill"),
    (r"\bembark(?:ing)? on (?:a|this|the) journey\b", "marketing slot-fill"),
    (r"\bi hope this helps\b", "chatbot artifact"),
    (r"\bfeel free to reach out\b", "chatbot artifact"),
    (
        r"\blet me know if you(?:'d| would| ever)?\s+(?:have|need|want|like)\b",
        "chatbot artifact",
    ),
    (r"\bas an AI(?: language)? (?:model|assistant)\b", "chatbot artifact"),
    (r"\bas of my (?:last )?(?:knowledge )?(?:update|cutoff)\b", "cutoff disclaimer"),
    (r"\bgame[- ]?chang(?:er|ing)\b", "hollow intensifier"),
]

#: Emoji leading a heading. Structure carries the emphasis in this repository; an emoji in
#: a heading is the single most reliable formatting tell.
_EMOJI_HEADING = re.compile(
    r"^\s{0,3}#{1,6}\s*[\U0001F300-\U0001FAFF☀-➿⬀-⯿]", re.MULTILINE
)

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _schema_skill_name() -> str:
    """The skill the pointers must name — one constant, so a rename is one edit."""
    return WRITING_SKILL_NAME


#: Doc trees P4 does not scan.
#:
#: ``docs/specs`` is the historical record: a build that could go red over the style of a
#: committed spec is the "a style pass rewrites a record" abuse case, and the pressure it
#: creates is to edit the record. ``docs/operating-model/reference`` is a build-time copy
#: of ``skills/the-loop/reference`` (``docs/scripts/sync-content.mts``) — the source is
#: already scanned, and reporting a finding twice tells the reader to fix a generated file.
_DOCS_EXCLUDED = ("specs", "operating-model/reference", "node_modules", ".vitepress")


def _shipped_prose() -> List[Path]:
    """Prose the-loop ships to a reader — the plugin, the CLI docs and the site."""
    paths = [p for p in SKILLS.rglob("*.md") if p not in _TELL_EXEMPT]
    paths += sorted((REPO_ROOT / "commands").glob("*.md"))
    paths += sorted((REPO_ROOT / "rules").glob("*.mdc"))
    paths.append(REPO_ROOT / "README.md")

    docs = REPO_ROOT / "docs"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md")):
            rel = path.relative_to(docs).as_posix()
            if any(rel.startswith(skip) for skip in _DOCS_EXCLUDED):
                continue
            paths.append(path)
    return [p for p in paths if p.is_file()]


# ---------------------------------------------------------------------------- P1


def test_p1_writing_skill_exists_and_parses() -> None:
    """The bundled writing skill is present with Agent Skills front-matter (R1.1)."""
    assert WRITING_SKILL.is_file(), f"missing writing skill: {WRITING_SKILL}"
    assert WRITING_TELLS.is_file(), f"missing tells catalogue: {WRITING_TELLS}"

    head = _FRONT_MATTER.match(WRITING_SKILL.read_text(encoding="utf-8"))
    assert head, "SKILL.md must open with YAML front matter"
    block = head.group(0)
    assert re.search(r"^name:\s*writing\s*$", block, re.MULTILINE), (
        "the skill's `name` must be `writing` — it is namespaced by the plugin, so it "
        "resolves as `the-loop:writing`, which is what the template pointers name"
    )
    description = re.search(r"^description:\s*(\S.*)$", block, re.MULTILINE)
    assert description, (
        "SKILL.md needs a `description` — it decides whether the skill fires"
    )


# ---------------------------------------------------------------------------- P2


@pytest.mark.parametrize("filename", HUMAN_READ_TEMPLATES)
def test_p2_human_read_template_points_at_the_skill(filename: str) -> None:
    """Every artifact a human approves is authored under the contract (R2.1)."""
    template = TEMPLATES / filename
    assert template.is_file(), f"human-read template is missing: {template}"

    assert _POINTER.search(template.read_text(encoding="utf-8")), (
        f"{filename} does not name the writing skill. Add the pointer comment near the "
        "top — an author starting from this template should not have to know the skill "
        "exists to be governed by it."
    )


# ---------------------------------------------------------------------------- P3


def test_p3_pointers_name_the_configured_skill() -> None:
    """Every template names the one bundled skill (R5.1)."""
    expected = _schema_skill_name()
    for filename in HUMAN_READ_TEMPLATES:
        pointer = _POINTER.search((TEMPLATES / filename).read_text(encoding="utf-8"))
        assert pointer, f"{filename}: no pointer (P2 covers this)"
        assert pointer.group(1) == expected, (
            f"{filename} names skill={pointer.group(1)!r} but the bundled skill "
            f"is {expected!r}"
        )


# ---------------------------------------------------------------------------- P4


def test_p4_no_p0_tell_in_shipped_prose() -> None:
    """No unambiguous machine-writing artifact reaches a user-facing document (R5.2)."""
    findings: List[str] = []
    for path in _shipped_prose():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for pattern, why in P0_TELLS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line}: {match.group(0)!r} — {why}")
        for match in _EMOJI_HEADING.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                f"{rel}:{line}: emoji in a heading — structure carries emphasis"
            )

    assert not findings, "P0 writing tells in shipped prose:\n" + "\n".join(findings)


# ------------------------------------------------------------------ P5–P10 (issue-544)
#
# The layered, story-first contract. Presence is still the only thing asserted: the
# card has a fixed heading, the design template a fixed shape, the review reference
# its standing checks. The card's ~120 words is a guide the skill states, and
# nothing here measures it.

CARD_HEADING = "## The short version"

#: Templates that open with the card. The brainstorm is a scratchpad, but it is the
#: first thing a reviewer meets, so it carries the card too.
CARD_TEMPLATES = [
    "brainstorm.md",
    "requirements.md",
    "bugfix.md",
    "design.md",
    "testing-plan.md",
    "tasks.md",
    "pr-briefing.md",
]

DESIGN_SECTIONS = [
    "The short version",
    "Interfaces",
    "Architecture",
    "Technology choices",
    "UI/UX design",
    "Security design",
    "Testing strategy",
    "Open questions",
    "Review comments",
]

REVIEWING = SKILLS / "the-loop" / "reference" / "reviewing.md"
EXPLAINER_REFERENCE = SKILLS / "the-loop" / "reference" / "explainer.md"
WORKFLOW = SKILLS / "the-loop" / "reference" / "workflow.md"


def _body(path: Path) -> str:
    return _FRONT_MATTER.sub("", path.read_text(encoding="utf-8"), count=1)


def _h2(text: str) -> List[str]:
    return re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)


@pytest.mark.parametrize("filename", CARD_TEMPLATES)
def test_p5_template_opens_with_the_card(filename: str) -> None:
    """Requirement: docs/specs/issue-544/requirements.md R2 AC 1, AC 6."""
    sections = _h2(_body(TEMPLATES / filename))
    assert sections and sections[0] == CARD_HEADING[3:], (
        f"{filename}: the first section must be `{CARD_HEADING}`, found {sections[:1]}"
    )


def test_p6_the_skill_states_the_layers_and_a_soft_card_guide() -> None:
    """Requirement: docs/specs/issue-544/requirements.md R1, R2 AC 3–4."""
    skill = WRITING_SKILL.read_text(encoding="utf-8")
    assert CARD_HEADING[3:] in skill
    assert "nothing measures it" in skill
    assert "There is no word limit" in skill
    for rule in (
        "about 25 words",
        "one idea in each sentence",
        "more than three nouns",
    ):
        assert rule in skill, rule
    assert "A linking sentence is information" in skill
    assert "What `design.md` leaves out" in skill
    assert "Not for code comments" not in skill


def test_p7_the_design_template_has_the_new_shape() -> None:
    """Requirement: docs/specs/issue-544/requirements.md R3 AC 1, 5, 6."""
    text = _body(TEMPLATES / "design.md")
    assert _h2(text) == DESIGN_SECTIONS
    for gone in (
        "Overview",
        "Components & interfaces",
        "Data models",
        "Error handling",
    ):
        assert f"## {gone}" not in text, gone
    assert "code snippets" in text
    assert "no change" in text.lower()


def test_p8_the_pr_briefing_has_review_effort_and_a_guided_tour() -> None:
    """Requirement: docs/specs/issue-544/requirements.md R6."""
    sections = _h2(_body(TEMPLATES / "pr-briefing.md"))
    assert "Review effort" in sections
    assert "Guided tour" in sections
    assert not any(s.startswith("TL;DR") for s in sections)
    for path in (WORKFLOW, REVIEWING, TEMPLATES / "pr-briefing.md"):
        assert "where to focus first" not in path.read_text(encoding="utf-8").lower(), (
            path.name
        )


def test_p9_the_review_reference_carries_the_standing_checks() -> None:
    """Requirement: docs/specs/issue-544/requirements.md R3 AC 7, R4 AC 4."""
    text = REVIEWING.read_text(encoding="utf-8")
    assert "## Standing checks" in text
    standing = text.split("## Standing checks", 1)[1].split("\n## ", 1)[0]
    assert "production-code comment" in standing
    assert "design.md" in standing and "code-level detail" in standing
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "### Code comments" in workflow
    assert "Requirement:" in workflow.split("### Code comments", 1)[1][:2000]


def test_p10_archify_is_recommended_and_never_installed() -> None:
    """Requirement: docs/specs/issue-544/requirements.md R7; abuse case 4."""
    text = EXPLAINER_REFERENCE.read_text(encoding="utf-8")
    assert "archify" in text
    section = text[text.index("archify") - 400 : text.index("archify") + 800]
    assert "mermaid" in section
    assert not re.search(r"\binstall", section, re.IGNORECASE)
