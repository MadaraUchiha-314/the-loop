# Adding a command

The CLI discovers its commands from a registry, so adding one is small and local.

## The contract

```python
# cli/the_loop/commands/hello.py
from __future__ import annotations

import argparse

from .base import Command, register


@register
class HelloCommand(Command):
    name = "hello"
    help = "Say hello (and show the shape of a command)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--name", default="world")

    def run(self, args: argparse.Namespace) -> int:
        print(f"hello, {args.name}")
        return 0
```

Then import it for its registration side effect:

```python
# cli/the_loop/commands/__init__.py
from . import hello  # noqa: F401,E402
```

That is all. `the-loop --help` picks it up, and commands are listed sorted by name for
stable help output.

| Member | Purpose |
|--------|---------|
| `name` | The subcommand. Must be non-empty and unique — a duplicate raises at import. |
| `help` | One line, shown in `the-loop --help`. |
| `add_arguments(parser)` | Register flags, or nested subparsers for a multi-action command. |
| `run(args) -> int` | Do the work. Return a **process exit code**; `0` is success. |

## Conventions worth following

- **Exit codes.** `0` success, `1` ran-but-negative, `2` could-not-run. Consistency is what
  makes the CLI scriptable — see [exit codes](/cli/commands/#exit-codes).
- **Which config?** Ask what the setting *describes*, not which command is asking. If it
  describes the operator's machine — ingress, routing, hosting, logging — it is the
  [CLI config](/config/cli/), and no repository may supply it. If it describes how work is
  done in a project, it is that project's [harness config](/config/harness-config), and a
  daemon command reads it too when it acts on that project. The split is
  [decision-032](/decisions/decision-032); the direction rule is
  [decision-044](/decisions/decision-044).
- **Read the harness config through `the_loop.harness_config`.** It is the only module
  that opens the file, it handles the pre-rename `config.yaml` fallback, and its `READS`
  tuple is where a new key gets declared. A test fails the build if a command reads the
  file itself or reads a key nobody declared.
- **Compute path defaults inside `add_arguments`, not at import.** `--config` is resolved
  just before `add_arguments` runs, so a default computed at import time would ignore it.
- **Emit events.** If the command makes decisions worth explaining later, call
  `eventlog.configure_from_file("<name>")` and append to the
  [event log](/config/cli/observability-options#event-log). Add each new type to the
  catalog — a unit test enforces that the emitted types and
  `the-loop events --types` agree.
- **Stay stdlib.** PyYAML is the one runtime dependency
  ([decision-038](/decisions/decision-038)). Anything more needs justifying in the work
  item's `design.md`.

## And write its page

A registered command with no page under `docs/cli/commands/` **fails the test suite**, in
both directions — an orphaned page for a command that no longer exists fails it too.

That is deliberate. Before this, three commands shipped and were never documented, because a
single flat `cli/README.md` had nowhere to put them. The rule now is mechanical rather than
remembered:

```bash
uv run --project cli python -m pytest cli/tests/test_docs_parity.py
```

Add `docs/cli/commands/<name>.md` and list it in
[the commands table](/cli/commands/). The same test guards the
[CLI config options](/config/cli/) against
[`.the-loop/cli-config.schema.json`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.the-loop/cli-config.schema.json),
so a new config key needs a documented option too.

## Tests

```bash
make test        # from the repository root
```

Integration tests carry a Gherkin docstring naming their scenario — see
[`scenarios`](/cli/commands/scenarios) and the
[testing reference](/operating-model/reference/testing).

## See also

- [Adding a hook](/cli/hooks) — the other extension point: a hook of your repository's own,
  run at a boundary the-loop's process graph already declares.
- [Commands](/cli/commands/) — what exists today.
- [cli](/capabilities/cli) — the capability doc, and the CLI's current behaviour.
