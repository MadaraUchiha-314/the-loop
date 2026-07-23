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

# (schema, [config files]) pairs. The per-repo plugin config and the user-level CLI
# config (issue-63) each have their own schema; both are validated here.
SCHEMA_TARGETS = [
    (
        ROOT / ".the-loop" / "config.schema.json",
        [
            ROOT / ".the-loop" / "config.yaml",
            ROOT / ".the-loop" / "templates" / "config.yaml",
        ],
    ),
    (
        ROOT / ".the-loop" / "cli-config.schema.json",
        [
            ROOT / ".the-loop" / "templates" / "cli-config.yaml",
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
