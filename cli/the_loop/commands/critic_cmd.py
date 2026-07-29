"""``the-loop critic list|run`` — the critic-review invocation surface (issue-108).

The running harness (Claude, say) needs to hand the work to a *different* harness
(cursor-agent, aider, a local runner) for a critic round and read back what it said.
``run`` does exactly that for ONE configured critic and prints ONE JSON envelope on
stdout — which is how the output gets back: the harness runs this command with its
ordinary shell tool and parses stdout.

Everything else about the review loop (how many rounds, when it converges, posting
findings with their attribution prefix and the loop-prevention marker) stays with the
harness following the skill's ``reference/reviewing.md``.

Repo-scoped, like ``scenarios`` and ``check``: it reads the harness config of the
project it is invoked in. It is not part of the daemon, so decision-032's "the plugin
config never feeds the CLI daemon" is untouched.

Spec: docs/specs/issue-108/  ·  Decision: 043
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import yaml

from .base import Command, register
from ..critics import (
    Critic,
    CriticConfigError,
    config_path,
    find_critic,
    load_critics,
    run_critic,
)

logger = logging.getLogger("the-loop.critics")

_EXIT_OK = 0
_EXIT_ROUND_FAILED = 1
_EXIT_MISCONFIGURED = 2

_LIST_HEADERS = ["Critic", "Harness", "Model", "Executable", "Available", "Enabled"]


def _spec_dir(root: Path, work_item: str) -> str:
    """``<workflow.specDir>/<work item>`` for the ``{specDir}`` placeholder."""
    if not work_item:
        return ""
    spec_root = "docs/specs"
    path = config_path(root)
    if path is not None:
        try:
            data = yaml.safe_load(path.read_text()) or {}
            spec_root = ((data.get("workflow") or {}).get("specDir")) or spec_root
        except Exception:  # noqa: BLE001 - a default is fine here
            logger.debug("could not read workflow.specDir from %s", path)
    return str(root / spec_root / work_item)


def _rows(critics: Sequence[Critic]) -> List[Dict[str, object]]:
    return [
        {
            "critic": critic.name,
            "harness": critic.harness,
            "model": critic.model,
            "binary": critic.binary,
            "available": critic.available,
            "enabled": critic.enabled,
            "error": critic.error,
        }
        for critic in critics
    ]


def _render_table(rows: Sequence[Dict[str, object]]) -> str:
    cells = [
        [
            str(row["critic"]),
            str(row["harness"] or "—"),
            str(row["model"] or "—"),
            str(row["binary"] or "—"),
            "yes" if row["available"] else "no",
            "yes" if row["enabled"] else "no",
        ]
        for row in rows
    ]
    widths = [len(h) for h in _LIST_HEADERS]
    for line in cells:
        for index, cell in enumerate(line):
            widths[index] = max(widths[index], len(cell))

    def fmt(values: Sequence[str]) -> str:
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    lines = [fmt(_LIST_HEADERS), "  ".join("-" * w for w in widths)]
    for row, line in zip(rows, cells):
        lines.append(fmt(line))
        if row["error"]:
            lines.append(f"         ! {row['error']}")
    return "\n".join(lines)


@register
class CriticCommand(Command):
    name = "critic"
    help = "List the configured critic harnesses and run one critic-review round"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        lst = actions.add_parser(
            "list",
            help="List reviews.critics[] with each one's executable and availability",
        )
        lst.add_argument("--root", default=".", help="Project root (default: .)")
        lst.add_argument(
            "--format",
            choices=("table", "json"),
            default="table",
            help="Output format (default: table).",
        )
        lst.set_defaults(_action=self._list)

        run = actions.add_parser(
            "run",
            help="Run ONE critic-review round and print its JSON envelope on stdout",
            description=(
                "Run one round with the named critic. Exactly one critic per "
                "invocation — there is deliberately no run-all mode."
            ),
        )
        run.add_argument("critic", help="The reviews.critics[] entry to run, by name.")
        run.add_argument("--root", default=".", help="Project root (default: .)")
        prompt = run.add_mutually_exclusive_group(required=True)
        prompt.add_argument("--prompt", help="The review prompt, inline.")
        prompt.add_argument(
            "--prompt-file",
            help="File holding the review prompt (preferred: prompts are long).",
        )
        run.add_argument(
            "--cwd",
            help="Directory to run the critic in (default: the critic's cwd, else --root).",
        )
        run.add_argument(
            "--work-item", default="", help="Work item id, e.g. issue-108."
        )
        run.add_argument(
            "--spec-dir",
            help="Spec directory for {specDir} (default: <specDir>/<work item>).",
        )
        run.add_argument(
            "--timeout",
            type=float,
            help="Override the critic's timeoutSeconds for this round.",
        )
        run.add_argument(
            "--output-file", help="Also write the JSON envelope to this path."
        )
        run.set_defaults(_action=self._run)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # ------------------------------------------------------------------ list

    def _list(self, args: argparse.Namespace) -> int:
        root = Path(args.root)
        try:
            critics = load_critics(root)
        except CriticConfigError as exc:
            logger.error("%s", exc)
            return _EXIT_MISCONFIGURED
        rows = _rows(critics)
        if args.format == "json":
            print(json.dumps(rows, indent=2))
            return _EXIT_OK
        if not rows:
            # An empty critics list is a valid configuration (self-review only),
            # so this is information, not a failure.
            print(
                "No critics configured — add reviews.critics[] to "
                ".the-loop/harness-config.yaml to run critic rounds."
            )
            return _EXIT_OK
        print(_render_table(rows))
        return _EXIT_OK

    # ------------------------------------------------------------------- run

    def _run(self, args: argparse.Namespace) -> int:
        root = Path(args.root)
        try:
            critic = find_critic(root, args.critic)
        except CriticConfigError as exc:
            logger.error("%s", exc)
            return _EXIT_MISCONFIGURED

        with tempfile.TemporaryDirectory(prefix="the-loop-critic-") as scratch:
            try:
                prompt, prompt_file = self._prompt_sources(args, Path(scratch))
            except OSError as exc:
                logger.error("could not read the prompt: %s", exc)
                return _EXIT_MISCONFIGURED
            cwd = args.cwd or critic.cwd or str(root)
            values = {
                "prompt": prompt,
                "promptFile": prompt_file,
                "model": critic.model,
                "workItem": args.work_item,
                "specDir": args.spec_dir or _spec_dir(root, args.work_item),
                "cwd": cwd,
            }
            try:
                result = run_critic(critic, values, cwd=cwd, timeout=args.timeout)
            except CriticConfigError as exc:
                # Nothing was spawned, so there is no round to report — the
                # envelope would be a record of something that never happened.
                logger.error("%s", exc)
                return _EXIT_MISCONFIGURED

        envelope = json.dumps(result.as_dict(), indent=2)
        print(envelope)  # stdout is the envelope and nothing else
        if args.output_file:
            self._write_envelope(Path(args.output_file), envelope)
        if not result.ok:
            logger.error("critic round %r failed: %s", critic.name, result.error)
            return _EXIT_ROUND_FAILED
        return _EXIT_OK

    @staticmethod
    def _prompt_sources(args: argparse.Namespace, scratch: Path) -> Tuple[str, str]:
        """The round's prompt as both text and a file path.

        Both placeholders always resolve: a critic CLI that only accepts a file
        works with ``--prompt``, and one that only accepts an argument works with
        ``--prompt-file``. The scratch file lives for the length of the round.
        """
        if args.prompt_file:
            path = Path(args.prompt_file)
            return path.read_text(), str(path)
        scratch_file = scratch / "critic-prompt.md"
        scratch_file.write_text(args.prompt)
        return args.prompt, str(scratch_file)

    @staticmethod
    def _write_envelope(path: Path, envelope: str) -> None:
        """Best-effort: the round already ran, so a write failure must not lose it."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(envelope + "\n")
        except OSError as exc:
            logger.warning("could not write the envelope to %s: %s", path, exc)
