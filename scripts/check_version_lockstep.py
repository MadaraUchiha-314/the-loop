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

`uv.lock` is checked too, and is NOT a `version_files` entry: commitizen can only
rewrite a version on lines its pattern matches, and every one of the lockfile's ~70
`version = "…"` lines would match — so the lockfile is kept in step by re-running
`uv lock`, which the release workflow now folds into the bump commit (issue-407).
This check is what makes that fold visible when it does not happen: a lockfile that
still names the previous version of a workspace member fails here, on the PR, instead
of surfacing as a dirty tree on the next contributor's machine.

Stdlib-only, and parses just the keys it needs by regex so it runs on any Python the
workspace supports (tomllib is 3.11+).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CZ_TOML = ROOT / ".cz.toml"
UV_LOCK = ROOT / "uv.lock"

# A uv.lock `[[package]]` block, split on the blank line that ends it. Only the
# workspace's own members carry `source = { editable = … }`; every third-party package
# is a registry entry whose version is nobody's business here.
UV_PACKAGE_RE = re.compile(
    r'^\[\[package\]\]\nname = "(?P<name>[^"]+)"\nversion = "(?P<version>[^"]+)"\n'
    r'source = \{ editable = ',
    flags=re.MULTILINE,
)


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


def check_uv_lock(version: str, lock_text: str) -> list[str]:
    """Return problems for the workspace members recorded in `uv.lock`.

    `uv.lock` pins the version of each editable workspace member alongside the
    third-party packages it resolves. `cz bump` never touches it, so after a release
    the lockfile names the version the package had *before* the bump until someone
    re-runs `uv lock` — the drift issue-407 reported.
    """
    members = UV_PACKAGE_RE.findall(lock_text)
    if not members:
        return ["uv.lock: no editable workspace member found — has the layout changed?"]
    return [
        f"uv.lock: {name} locked at {locked}, expected {version} — run `uv lock`"
        for name, locked in members
        if locked != version
    ]


def main() -> int:
    version, entries = read_cz_config(CZ_TOML.read_text())
    problems = [problem for entry in entries for problem in check_entry(version, entry)]
    problems += check_uv_lock(version, UV_LOCK.read_text())
    for problem in problems:
        print(f"DRIFT   {problem}", file=sys.stderr)
    if problems:
        print(
            f"versioned artifacts out of lockstep with .cz.toml version {version} — "
            "`cz bump` would silently skip the drifted lines, and a stale uv.lock "
            "dirties the next checkout that resolves it.",
            file=sys.stderr,
        )
        return 1
    print(f"LOCKSTEP all {len(entries)} version_files and uv.lock carry {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
