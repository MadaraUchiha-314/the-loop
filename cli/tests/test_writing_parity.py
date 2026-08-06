"""Writing-contract parity (issue-165).

the-loop's artifacts are read by a human who has to approve them, and nothing in the
harness used to say how they should read. issue-165 added a writing contract: a bundled
``the-loop:writing`` skill, the ``userInteraction.writingStyle`` policy it reads, and a
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
P3      the pointer names the skill the schema declares            the two drift apart
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

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / "skills"
WRITING_SKILL = SKILLS / "writing" / "SKILL.md"
WRITING_TELLS = SKILLS / "writing" / "reference" / "tells.md"
TEMPLATES = SKILLS / "the-loop" / "templates"
HARNESS_SCHEMA = REPO_ROOT / ".the-loop" / "harness-config.schema.json"

pytestmark = pytest.mark.skipif(
    not SKILLS.is_dir(),
    reason="plugin skills not present (source distribution)",
)

#: The pointer each human-read template carries: an HTML comment naming the skill that
#: governs it. Invisible when the markdown renders, greppable, and it sits where the
#: author is already looking. A comment rather than visible prose because the template's
#: own text is a cost to every reader of every artifact made from it.
_POINTER = re.compile(r"<!--[^>]*?`(the-loop:[\w.-]+)`\s+skill", re.DOTALL)

#: Templates producing an artifact a human reads and approves. ``execution-log.md`` and
#: ``brainstorm.md`` are excluded on purpose: the log is an append-only record and the
#: brainstorm is a scratchpad, so neither is written *at* a reviewer. ``bugfix.md`` is
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


def _writing_style_schema() -> Dict[str, Any]:
    schema = json.loads(HARNESS_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["userInteraction"]["properties"]["writingStyle"][
        "properties"
    ]


def _schema_skill_name() -> str:
    """The skill the pointers must name — read, not hardcoded, so a rename is one edit."""
    return str(_writing_style_schema()["skill"]["default"])


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
        "resolves as `the-loop:writing`, which is what `writingStyle.skill` names"
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
    """The templates and the schema are two statements of one name (R5.1)."""
    expected = _schema_skill_name()
    for filename in HUMAN_READ_TEMPLATES:
        pointer = _POINTER.search((TEMPLATES / filename).read_text(encoding="utf-8"))
        assert pointer, f"{filename}: no pointer (P2 covers this)"
        assert pointer.group(1) == expected, (
            f"{filename} names skill={pointer.group(1)!r} but writingStyle.skill "
            f"defaults to {expected!r}"
        )


def test_p3_the_schema_declares_no_length_limits() -> None:
    """Budgets were rejected on PR #168; a re-added cap must be a deliberate decision.

    Not a style preference — the reason is recorded in decision-061: scope is not known
    in advance, so a fixed number is wrong for half the work items. If a future work item
    wants length limits back, it changes this test and says why, rather than reintroducing
    them by accident alongside an unrelated schema edit.
    """
    style = _writing_style_schema()
    assert "budgets" not in style, (
        "userInteraction.writingStyle.budgets is back. Length limits were removed "
        "deliberately (decision-061) — re-adding them is a decision to record, not a "
        "detail to slip in."
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
