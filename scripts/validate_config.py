#!/usr/bin/env python3
"""Validate the-loop config files against the JSON schema.

Used by the Makefile, the pre-commit hook and CI (same tooling everywhere).
Exits non-zero if any config is invalid.
"""

from __future__ import annotations

import json
import sys
import warnings
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

# Three independent config surfaces (issue-63/decision-032, issue-82/decision-035):
# the HARNESS (plugin) config (per repo), the collaborators file (per repo, people
# + notification channels), and the CLI config (not tied to a repo).
SCHEMA_TARGETS = [
    (
        ROOT / ".the-loop" / "harness-config.schema.json",
        [
            ROOT / ".the-loop" / "harness-config.yaml",
            # Templates are internal to the-loop and ship with the skill (issue #36).
            ROOT / "skills" / "the-loop" / "templates" / "harness-config.yaml",
        ],
    ),
    (
        ROOT / ".the-loop" / "collaborators.schema.json",
        [
            ROOT / ".the-loop" / "collaborators.yaml",
            ROOT / "skills" / "the-loop" / "templates" / "collaborators.yaml",
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

# cli-config.schema.json reuses the collaborator shape via a relative $ref into
# collaborators.schema.json (issue-82: same structure, enforced by one schema).
# Register that schema under its $id so the ref resolves locally, no network.
_COLLABORATORS_SCHEMA = json.loads(
    (ROOT / ".the-loop" / "collaborators.schema.json").read_text()
)
_SCHEMA_STORE = {_COLLABORATORS_SCHEMA["$id"]: _COLLABORATORS_SCHEMA}


def main() -> int:
    ok = True
    for schema_path, targets in SCHEMA_TARGETS:
        schema = json.loads(schema_path.read_text())
        for target in targets:
            rel = target.relative_to(ROOT)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                resolver = jsonschema.RefResolver(
                    base_uri=schema.get("$id", ""),
                    referrer=schema,
                    store=_SCHEMA_STORE,
                )
            try:
                jsonschema.validate(
                    yaml.safe_load(target.read_text()), schema, resolver=resolver
                )
            except jsonschema.ValidationError as exc:
                ok = False
                print(f"INVALID {rel}: {exc.message}", file=sys.stderr)
            else:
                print(f"VALID   {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
