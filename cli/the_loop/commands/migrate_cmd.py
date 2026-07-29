"""``the-loop migrate-config`` — apply a breaking CLI-config migration.

The migration itself lives in :mod:`the_loop.migrations` (deterministic and
idempotent). This command is the operator-facing surface for it, and the thing
``/the-loop:upgrade-the-loop`` shells out to, so an upgrade never hand-edits a
config the runtime already knows how to move.

It reads the file with the *raw* loader on purpose: :func:`load_cli_config`
refuses an un-migrated config, and refusing to load the very file you are trying
to migrate would be a locked door with the key inside.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .base import Command, register


@register
class MigrateConfigCommand(Command):
    name = "migrate-config"
    help = "Migrate a CLI config to the current schema version (idempotent)."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--path",
            default="",
            help="cli-config.yaml to migrate (default: the resolved CLI config)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="print the report and the migrated YAML without writing",
        )

    def run(self, args: argparse.Namespace) -> int:
        import yaml

        from .. import cli_config
        from ..migrations import migrate_cli_config

        path = Path(args.path) if args.path else cli_config.default_cli_config_path()
        if not path.is_file():
            print(f"error: {path} not found")
            return 2

        try:
            data = cli_config._load_cli_config_raw(path, strict=True)
        except Exception as exc:  # noqa: BLE001
            print(f"error: could not parse {path}: {exc}")
            return 2

        report = migrate_cli_config(data)
        print(report.render())
        if not report.changed:
            return 0

        rendered = yaml.safe_dump(report.config, sort_keys=False)
        if args.dry_run:
            print(f"\n--- {path} (preview, not written) ---")
            print(rendered)
            return 0

        # Keep the pre-migration file. A breaking migration the operator cannot
        # walk back from is a worse trade than one stray `.bak`.
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(rendered, encoding="utf-8")
        print(f"\nwrote {path} (previous version kept at {backup})")
        return 0
