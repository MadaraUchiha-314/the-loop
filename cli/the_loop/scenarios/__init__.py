"""Extract Gherkin scenarios from integration tests (language-agnostic).

the-loop requires every integration test to carry a **Gherkin-syntax docstring**
(``Feature:`` / ``Scenario:`` / ``Given``-``When``-``Then``) describing the scenario
under test, optionally linked to a ``requirements.md`` via a ``Requirement:`` line. This
module lets the harness (or a human) *query* those scenarios and present a tabular view
without running the tests — see ``the-loop scenarios``.

The extractor is intentionally text/line based rather than tied to one test framework, so
it works uniformly across Python docstrings, JS/TS block comments, Go comments, etc. — any
file where the Gherkin block appears near the test. Comment and docstring markers
(hash, slashes, stars, triple-quotes, C-style block comments) are stripped before matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Gherkin keywords we recognise (case-insensitive, after marker stripping).
_FEATURE_RE = re.compile(r"(?i)^feature:\s*(.*)$")
_SCENARIO_RE = re.compile(r"(?i)^scenario(?:\s+outline)?:\s*(.*)$")
_REQUIREMENT_RE = re.compile(r"(?i)^requirement:\s*(.*)$")
_STEP_RE = re.compile(r"(?i)^(given|when|then|and|but)\b.*$")

# Default globs used when neither --glob nor testing.integrationTestGlobs is set.
DEFAULT_GLOBS: List[str] = [
    "**/tests/integration/**/*.py",
    "**/*_integration_test.py",
    "**/*.integration.test.ts",
    "**/*.integration.test.js",
    "**/integration/**/*_test.go",
]


@dataclass
class Scenario:
    """A single Gherkin scenario discovered in a test file."""

    feature: str
    scenario: str
    requirement: str
    steps: List[str] = field(default_factory=list)
    file: str = ""
    line: int = 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "feature": self.feature,
            "scenario": self.scenario,
            "requirement": self.requirement,
            "steps": list(self.steps),
            "file": self.file,
            "line": self.line,
        }


def _strip_markers(raw: str) -> str:
    """Remove leading/trailing comment & docstring markers from a line."""
    text = raw.strip()
    # Leading comment/docstring markers: # // * """ ''' /* plus surrounding quotes.
    text = re.sub(r'^\s*(?:#+|//+|\*+|/\*+|"""|\'\'\')\s*', "", text)
    # Trailing docstring/comment closers.
    text = re.sub(r'\s*(?:"""|\'\'\'|\*/)\s*$', "", text)
    return text.strip()


def extract_from_text(text: str, *, file: str = "") -> List[Scenario]:
    """Extract all scenarios from a file's ``text``.

    A ``Feature:`` sets the feature for every following scenario until the next
    ``Feature:``. A ``Requirement:`` seen before a ``Scenario:`` attaches to that
    scenario; one seen within a scenario's step block attaches to the open scenario.
    """
    scenarios: List[Scenario] = []
    current_feature = ""
    carry_requirement = ""
    current: Optional[Scenario] = None

    def close() -> None:
        nonlocal current
        if current is not None:
            scenarios.append(current)
            current = None

    for idx, raw in enumerate(text.splitlines(), start=1):
        line = _strip_markers(raw)
        if not line:
            continue

        m = _FEATURE_RE.match(line)
        if m:
            close()
            current_feature = m.group(1).strip()
            carry_requirement = ""
            continue

        m = _SCENARIO_RE.match(line)
        if m:
            close()
            current = Scenario(
                feature=current_feature,
                scenario=m.group(1).strip(),
                requirement=carry_requirement,
                file=file,
                line=idx,
            )
            carry_requirement = ""
            continue

        m = _REQUIREMENT_RE.match(line)
        if m:
            value = m.group(1).strip()
            if current is not None and not current.requirement:
                current.requirement = value
            else:
                carry_requirement = value
            continue

        if current is not None and _STEP_RE.match(line):
            current.steps.append(line)

    close()
    return scenarios


def _iter_files(root: Path, globs: Iterable[str]) -> List[Path]:
    """Return the de-duplicated, sorted set of files matching any glob under ``root``."""
    seen: Dict[Path, None] = {}
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen.setdefault(path.resolve(), None)
    return list(seen.keys())


def collect_scenarios(
    root: Path, globs: Iterable[str], *, display_root: Optional[Path] = None
) -> List[Scenario]:
    """Collect scenarios from every file matching ``globs`` under ``root``.

    ``display_root`` (defaults to ``root``) controls how file paths are reported —
    relative to it when possible, else the absolute path.
    """
    base = (display_root or root).resolve()
    results: List[Scenario] = []
    for path in _iter_files(root, globs):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = str(path.relative_to(base))
        except ValueError:
            rel = str(path)
        results.extend(extract_from_text(text, file=rel))
    return results


__all__ = [
    "Scenario",
    "collect_scenarios",
    "extract_from_text",
    "DEFAULT_GLOBS",
]
