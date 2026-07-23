#!/usr/bin/env python3
"""Check that every `version_files` target carries the commitizen version.

commitizen's `cz bump` rewrites a `version_files` entry by REPLACING the current
version string on lines matching the entry's pattern — a file that drifted away from
the current version is silently left behind at release time (exactly how the plugin
manifests sat at 0.1.0 while releases reached 0.7.0 — issue #46). This guard runs in
pre-commit and CI (same hooks — RULE: no local-vs-CI drift) so drift is caught at
commit time, not discovered after a release.

For each `path:pattern` entry in `.cz.toml` the check requires that at least one line
matches the pattern and that EVERY matching line contains the current version — so a
file with two version fields (marketplace.json) can't be half-updated.

Stdlib-only, and parses just the two `[tool.commitizen]` keys it needs by regex so it
runs on any Python the workspace supports (tomllib is 3.11+).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CZ_TOML = ROOT / ".cz.toml"


def read_cz_config(text: str) -> tuple[str, list[str]]:
    """Extract `version` and `version_files` from .cz.toml."""
    version_match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    if not version_match:
        raise ValueError('no `version = "…"` found in .cz.toml')
    files_match = re.search(r"^version_files = \[(.*?)^\]", text, flags=re.MULTILINE | re.DOTALL)
    if not files_match:
        raise ValueError("no `version_files = [...]` found in .cz.toml")
    # TOML basic strings; unescape \" so JSON-quoted patterns compare literally.
    entries = [
        entry.replace('\\"', '"')
        for entry in re.findall(r'"((?:[^"\\]|\\.)*)"', files_match.group(1))
    ]
    return version_match.group(1), entries


def check_entry(version: str, entry: str) -> list[str]:
    """Return problems for one `path[:pattern]` version_files entry."""
    path, _, pattern = entry.partition(":")
    target = ROOT / path
    if not target.is_file():
        return [f"{path}: file not found"]
    matcher = re.compile(pattern) if pattern else None
    matching = [
        (n, line)
        for n, line in enumerate(target.read_text().splitlines(), start=1)
        if matcher is None or matcher.search(line)
    ]
    if not matching:
        return [f"{path}: no line matches pattern {pattern!r}"]
    return [
        f"{path}:{n}: expected version {version} on {line.strip()!r}"
        for n, line in matching
        if version not in line
    ]


def main() -> int:
    version, entries = read_cz_config(CZ_TOML.read_text())
    problems = [problem for entry in entries for problem in check_entry(version, entry)]
    for problem in problems:
        print(f"DRIFT   {problem}", file=sys.stderr)
    if problems:
        print(
            f"version_files out of lockstep with .cz.toml version {version} — "
            "`cz bump` would silently skip the drifted lines.",
            file=sys.stderr,
        )
        return 1
    print(f"LOCKSTEP all {len(entries)} version_files carry {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
