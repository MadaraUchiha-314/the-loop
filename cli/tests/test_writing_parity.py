"""Writing-contract parity (issue-165).

the-loop's artifacts are read by a human who has to approve them, and nothing in the
harness used to say how long they were allowed to be or how they should read. issue-165
added a writing contract: a bundled ``the-loop:writing`` skill, per-artifact prose budgets
declared in ``userInteraction.writingStyle``, and a budget marker in each template that
produces a human-read artifact.

Prose describing a rule does not execute it — that is what issue-124 and issue-148 both
cost. So the mechanical parts of the contract are asserted here:

======  =========================================================  =========================
P1      the writing skill exists and its front-matter parses       the skill is renamed or dropped
P2      every budgeted template declares a well-formed marker      a template ships with no budget
P3      marker values equal the schema's budget defaults,          the two numbers drift apart
        in both directions
P4      SKILL.md's own prose fits its own declared budget          the contract stops obeying itself
P5      no P0 writing tell appears in shipped prose                a chatbot tic reaches a user-facing doc
P6      each template's own prose fits the budget it declares      a budget the scaffold alone cannot meet
======  =========================================================  =========================

P6 exists because the first draft of this work item set ``tasks: 200`` against a template
whose own guidance prose was 274 words: every tasks.md would have opened over budget, and
an unreachable budget teaches authors to ignore the reachable ones. It also keeps the
templates themselves lean, which is the same goal one level up.

What is deliberately NOT asserted: whether a document is *well written*. R5.3 of
``docs/specs/issue-165/requirements.md`` draws that line — presence is mechanical,
quality is a review item — and the surveyed prior art
(https://github.com/conorbronsdon/avoid-ai-writing) reports false-positive rates above
60% on non-native speakers for exactly this kind of pattern matching. P5 is therefore
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

#: ``<!-- writing: budget=500 skill=the-loop:writing -->`` — invisible when the markdown
#: renders, greppable, and it sits where the author is already looking. ``budget`` must be
#: an integer: a malformed value fails P2 rather than being skipped, because a marker that
#: silently disables itself is the defect shape issue-124 was about.
_MARKER = re.compile(r"<!--\s*writing:\s*budget=(\d+)\s+skill=([\w:.-]+)[^>]*?-->")

#: template filename -> ``userInteraction.writingStyle.budgets`` key.
#:
#: Explicit rather than derived: ``testing-plan.md`` -> ``testingPlan`` needs a
#: kebab-to-camel convention nothing else in the repo has, and a mapping you can read is
#: worth more than one you have to infer. ``bugfix.md`` shares ``requirements``' budget
#: because the two are alternative names for ONE artifact (decision-045), not two.
BUDGETED_TEMPLATES: Dict[str, str] = {
    "requirements.md": "requirements",
    "bugfix.md": "requirements",
    "design.md": "design",
    "testing-plan.md": "testingPlan",
    "tasks.md": "tasks",
    "pr-briefing.md": "prBriefing",
    "decision.md": "decision",
    "capability.md": "capability",
}

#: Budget keys with no template behind them, so P3's reverse direction can tell "nobody
#: declared this" from "this legitimately has no file".
_NO_TEMPLATE = {
    "comment",  # ticket/PR comments are authored inline; there is no template to mark.
}

#: Files exempt from P5. The tells catalogue quotes the tells it bans — it is the one
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
_FENCED = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
#: EARS acceptance criteria are a contract, not prose (R4). They are excluded from the
#: count so the budget can never pressure an author into softening one.
_EARS = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:WHEN|IF|WHILE|WHERE)\b.*?\bSHALL\b", re.IGNORECASE
)


def prose_words(text: str) -> int:
    """Count the words a reader actually reads as prose.

    Front-matter, HTML comments, fenced blocks (code AND mermaid), headings, tables,
    blockquote callouts and EARS criteria are excluded. Counting them would make the
    budget punish the diagram it exists to encourage, and would set the writing rule
    against the requirements gate.
    """
    text = _FRONT_MATTER.sub("", text)
    text = _HTML_COMMENT.sub("", text)
    text = _FENCED.sub("", text)
    words = 0
    in_ears = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            in_ears = False
            continue
        # A criterion that wraps is still one criterion. Its continuation lines are
        # indented, so they are skipped until the blank line or the unindented line that
        # ends the item — otherwise the budget would count half of every wrapped SHALL and
        # quietly pressure an author into shortening a contract.
        if in_ears and line[:1].isspace():
            continue
        in_ears = bool(_EARS.match(stripped) or _EARS.match(stripped.lstrip("-*+ ")))
        if in_ears:
            continue
        if stripped.startswith(("#", ">", "|")):
            continue
        words += len(stripped.split())
    return words


def _writing_style_schema() -> Dict[str, Any]:
    schema = json.loads(HARNESS_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["userInteraction"]["properties"]["writingStyle"][
        "properties"
    ]


def _schema_budgets() -> Dict[str, int]:
    budgets = _writing_style_schema()["budgets"]["properties"]
    return {key: leaf["default"] for key, leaf in budgets.items()}


def _schema_skill_name() -> str:
    """The skill the markers must name — read, not hardcoded, so a rename is one edit."""
    return str(_writing_style_schema()["skill"]["default"])


#: Doc trees P5 does not scan.
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


@pytest.mark.parametrize("filename", sorted(BUDGETED_TEMPLATES))
def test_p2_budgeted_template_declares_its_budget(filename: str) -> None:
    """Every human-read artifact template carries a well-formed marker (R2.1)."""
    template = TEMPLATES / filename
    assert template.is_file(), f"budgeted template is missing: {template}"

    marker = _MARKER.search(template.read_text(encoding="utf-8"))
    assert marker, (
        f"{filename} declares no writing budget. Add "
        "`<!-- writing: budget=<N> skill=the-loop:writing -->` near the top."
    )
    assert int(marker.group(1)) > 0, (
        f"{filename}: a budgeted template needs a budget > 0"
    )
    expected = _schema_skill_name()
    assert marker.group(2) == expected, (
        f"{filename}: the marker names skill={marker.group(2)!r} but "
        f"writingStyle.skill defaults to {expected!r}"
    )


# ---------------------------------------------------------------------------- P3


def test_p3_markers_match_schema_defaults() -> None:
    """Template markers and schema defaults are two statements of one number (R5.1)."""
    budgets = _schema_budgets()

    for filename, key in sorted(BUDGETED_TEMPLATES.items()):
        assert key in budgets, f"{filename} maps to `{key}`, absent from the schema"
        marker = _MARKER.search((TEMPLATES / filename).read_text(encoding="utf-8"))
        assert marker, f"{filename}: no marker (P2 covers this)"
        assert int(marker.group(1)) == budgets[key], (
            f"{filename} declares budget={marker.group(1)} but "
            f"writingStyle.budgets.{key} defaults to {budgets[key]}"
        )


def test_p3_every_schema_budget_is_claimed() -> None:
    """Reverse direction: a budget nobody declares is a budget nobody honours."""
    claimed = set(BUDGETED_TEMPLATES.values()) | _NO_TEMPLATE
    for key, default in sorted(_schema_budgets().items()):
        if default == 0:  # 0 means "unbudgeted by design" (brainstorm, execution log)
            continue
        assert key in claimed, (
            f"writingStyle.budgets.{key} has no template in BUDGETED_TEMPLATES and is "
            "not listed in _NO_TEMPLATE — add one or the other"
        )


# ---------------------------------------------------------------------------- P4


def test_p4_skill_obeys_its_own_budget() -> None:
    """A writing contract that cannot keep to its own budget is not a contract (NFR)."""
    text = WRITING_SKILL.read_text(encoding="utf-8")
    marker = _MARKER.search(text)
    assert marker, "SKILL.md must declare its own budget — it is the worked example"

    budget = int(marker.group(1))
    actual = prose_words(text)
    assert actual <= budget, (
        f"skills/writing/SKILL.md is {actual} prose words against its own {budget}-word "
        "budget. Move detail to reference/tells.md rather than raising the number."
    )


# ---------------------------------------------------------------------------- P5


@pytest.mark.parametrize("filename", sorted(BUDGETED_TEMPLATES))
def test_p6_template_prose_fits_its_own_budget(filename: str) -> None:
    """A budget the empty scaffold cannot meet is a budget nobody can meet (R2.1)."""
    text = (TEMPLATES / filename).read_text(encoding="utf-8")
    marker = _MARKER.search(text)
    assert marker, f"{filename}: no marker (P2 covers this)"

    budget = int(marker.group(1))
    actual = prose_words(text)
    assert actual <= budget, (
        f"skills/the-loop/templates/{filename} is {actual} prose words against the "
        f"{budget}-word budget it declares. Either the template's guidance is too long or "
        "the budget is unreachable — an author starting from it would open over budget."
    )


# ---------------------------------------------------------------------------- P5


def test_p5_no_p0_tell_in_shipped_prose() -> None:
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
