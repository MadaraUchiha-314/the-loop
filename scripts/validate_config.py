#!/usr/bin/env python3
"""Validate the-loop config files against the JSON schema.

Used by the Makefile, the pre-commit hook and CI (same tooling everywhere).
Exits non-zero if any config is invalid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
    import yaml
except ImportError as exc:  # pragma: no cover
    print(
        f"missing dependency: {exc.name} (pip install pyyaml jsonschema)",
        file=sys.stderr,
    )
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent

# Two independent config surfaces (issue-63, decision-032): the PLUGIN config
# (per repo) and the CLI config (webhooks/polling/eventLog, not tied to a repo).
SCHEMA_TARGETS = [
    (
        ROOT / ".the-loop" / "config.schema.json",
        [
            ROOT / ".the-loop" / "config.yaml",
            # Templates are internal to the-loop and ship with the skill (issue #36).
            ROOT / "skills" / "the-loop" / "templates" / "config.yaml",
        ],
    ),
    (
        ROOT / ".the-loop" / "cli-config.schema.json",
        [
            ROOT / ".the-loop" / "cli-config.yaml",
            ROOT / "skills" / "the-loop" / "templates" / "cli-config.yaml",
        ],
    ),
]


def main() -> int:
    ok = True
    for schema_path, targets in SCHEMA_TARGETS:
        schema = json.loads(schema_path.read_text())
        for target in targets:
            rel = target.relative_to(ROOT)
            try:
                jsonschema.validate(yaml.safe_load(target.read_text()), schema)
            except jsonschema.ValidationError as exc:
                ok = False
                print(f"INVALID {rel}: {exc.message}", file=sys.stderr)
            else:
                print(f"VALID   {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
