"""``the-loop hooks`` — what the CLI config's ``hooks`` block would run (issue-344).

Deliberately inert, like ``the-loop graph hooks`` and ``the-loop critic list``: the
modules a declaration names run **inside the-loop's process**, so an operator gets to
read what would run — which modules, which hooks, which of the catalogued events each
pattern matches — before any entry point imports it. Parsing is the whole job here;
``the-loop start``, the receiver, the poller and every command that records events
are what load it, and a declaration that cannot load fails there.

Spec: docs/specs/issue-344/  ·  Decision: 124
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .base import Command, register
from .. import cli_config, lifecycle_hooks

_EXIT_OK = 0
_EXIT_MISCONFIGURED = 2


def _report() -> Dict[str, Any]:
    """Parse the CLI config's ``hooks`` block. Imports nothing."""
    path = cli_config.default_cli_config_path()
    data = cli_config.load_cli_config(path) if path.is_file() else {}
    declaration = lifecycle_hooks.read_declaration(data)
    root = Path(path).resolve().parent if path.is_file() else Path.cwd().resolve()
    return {
        "config": str(path),
        "root": str(root),
        "attachPoints": len(lifecycle_hooks.attach_points()),
        "shipped": {
            name: shipped.description
            for name, shipped in sorted(lifecycle_hooks.SHIPPED.items())
        },
        "modules": [
            {"path": ref.path, "module": ref.dotted} for ref in declaration.modules
        ],
        "attach": [
            {
                "hook": a.hook,
                "on": list(a.patterns),
                "events": list(a.events),
                "with": dict(a.params),
            }
            for a in declaration.attachments
        ],
    }


def _print_text(report: Dict[str, Any]) -> None:
    print(
        f"attach points: {report['attachPoints']} event types "
        f"(`the-loop events --types`; {lifecycle_hooks.OWN_DOMAIN}* excluded)"
    )
    shipped = report["shipped"]
    print(f"shipped lifecycle hooks ({len(shipped)}): {', '.join(shipped)}")
    modules, attach = report["modules"], report["attach"]
    if not modules and not attach:
        print(
            f"\nno lifecycle hooks declared (`{lifecycle_hooks.CONFIG_KEY}` in the "
            f"CLI config, {report['config']})"
        )
        return
    print(
        f"\nthe CLI config declares {len(modules)} module(s) and "
        f"{len(attach)} attachment(s) — nothing here has been imported:"
    )
    for ref in modules:
        where = f"  (resolved against {report['root']})" if ref["path"] else ""
        print(f"  module  {ref['path'] or ref['module']}{where}")
    for entry in attach:
        suffix = f"  with: {entry['with']}" if entry["with"] else ""
        print(
            f"  attach  {entry['hook']} → {len(entry['events'])} event(s) "
            f"[{', '.join(entry['on'])}]{suffix}"
        )
    print(
        "\na declaration that cannot load fails the entry point that loads it "
        "(`the-loop start`, the receiver, the poller, and any command that records "
        "events) rather than being skipped."
    )


@register
class HooksCommand(Command):
    name = "hooks"
    help = "Report the lifecycle hooks the CLI config declares, without importing them."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--format", choices=["text", "json"], default="text", help="output format"
        )

    def run(self, args: argparse.Namespace) -> int:
        try:
            report = _report()
        except (lifecycle_hooks.HooksConfigError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return _EXIT_MISCONFIGURED
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            _print_text(report)
        return _EXIT_OK
