#!/usr/bin/env python3
"""Validate a commit message against Conventional Commits v1.0.0.

Wired as a pre-commit `commit-msg` stage hook so every commit is checked locally
(https://www.conventionalcommits.org/en/v1.0.0/). Merge/revert/fixup/squash
messages are allowed through.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = [
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
]
HEADER_RE = re.compile(r"^(" + "|".join(TYPES) + r")(\([^)]+\))?(!)?: .+")
ALLOWED_PREFIXES = ("Merge ", "Revert ", "fixup!", "squash!")


def first_meaningful_line(message: str) -> str:
    for line in message.splitlines():
        if line.strip() == "" or line.startswith("#"):
            continue
        return line
    return ""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_commit_msg.py <commit-msg-file>", file=sys.stderr)
        return 2
    header = first_meaningful_line(Path(argv[1]).read_text(encoding="utf-8"))
    if header.startswith(ALLOWED_PREFIXES) or HEADER_RE.match(header):
        return 0
    print("ERROR: commit message is not a Conventional Commit.", file=sys.stderr)
    print(f"  header:   {header!r}", file=sys.stderr)
    print("  expected: <type>[optional scope][!]: <description>", file=sys.stderr)
    print(f"  types:    {', '.join(TYPES)}", file=sys.stderr)
    print("  see https://www.conventionalcommits.org/en/v1.0.0/", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
