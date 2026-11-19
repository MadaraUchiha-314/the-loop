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
from pathlib import Path
from typing import Any, Mapping, Sequence

from .base import Command, register
from .. import strings
from ..client.routing import routed, service_error
from ..core import repo as core_repo

logger = logging.getLogger("the-loop.critics")

_EXIT_OK = 0
_EXIT_ROUND_FAILED = 1
_EXIT_MISCONFIGURED = 2

_LIST_HEADERS = [
    strings.t("cli.critic.table.header.critic"),
    strings.t("cli.critic.table.header.harness"),
    strings.t("cli.critic.table.header.model"),
    strings.t("cli.critic.table.header.executable"),
    strings.t("cli.critic.table.header.available"),
    strings.t("cli.critic.table.header.enabled"),
]


def _render_table(rows: Sequence[Mapping[str, Any]]) -> str:
    cells = [
        [
            str(row["name"]),
            str(row["harness"] or "—"),
            str(row["model"] or "—"),
            str(row["binary"] or "—"),
            strings.t("cli.critic.table.yes")
            if row["available"]
            else strings.t("cli.critic.table.no"),
            strings.t("cli.critic.table.yes")
            if row["enabled"]
            else strings.t("cli.critic.table.no"),
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
    help = strings.t("cli.critic.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        lst = actions.add_parser(
            "list",
            help=strings.t("cli.critic.list.help"),
        )
        lst.add_argument(
            "--root", default=".", help=strings.t("cli.critic.list.root.help")
        )
        lst.add_argument(
            "--format",
            choices=("table", "json"),
            default="table",
            help=strings.t("cli.critic.list.format.help"),
        )
        lst.set_defaults(_action=self._list)

        policy = actions.add_parser(
            "policy",
            help=strings.t("cli.critic.policy.help"),
        )
        policy.add_argument(
            "--root", default=".", help=strings.t("cli.critic.policy.root.help")
        )
        policy.add_argument(
            "--format",
            choices=("text", "json"),
            default="text",
            help=strings.t("cli.critic.policy.format.help"),
        )
        policy.set_defaults(_action=self._policy)

        run = actions.add_parser(
            "run",
            help=strings.t("cli.critic.run.help"),
            description=strings.t("cli.critic.run.description"),
        )
        run.add_argument("critic", help=strings.t("cli.critic.run.critic.help"))
        run.add_argument(
            "--root", default=".", help=strings.t("cli.critic.run.root.help")
        )
        prompt = run.add_mutually_exclusive_group(required=True)
        prompt.add_argument("--prompt", help=strings.t("cli.critic.run.prompt.help"))
        prompt.add_argument(
            "--prompt-file",
            help=strings.t("cli.critic.run.prompt-file.help"),
        )
        run.add_argument(
            "--cwd",
            help=strings.t("cli.critic.run.cwd.help"),
        )
        run.add_argument(
            "--work-item", default="", help=strings.t("cli.critic.run.work-item.help")
        )
        run.add_argument(
            "--spec-dir",
            help=strings.t("cli.critic.run.spec-dir.help"),
        )
        run.add_argument(
            "--timeout",
            type=float,
            help=strings.t("cli.critic.run.timeout.help"),
        )
        run.add_argument(
            "--output-file", help=strings.t("cli.critic.run.output-file.help")
        )
        run.set_defaults(_action=self._run)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # ------------------------------------------------------------------ list

    def _list(self, args: argparse.Namespace) -> int:
        try:
            rows = routed(
                lambda connection: connection.get(
                    "/repo/critics", params={"repo": str(Path(args.root))}
                ),
                lambda: core_repo.critics(str(Path(args.root))),
            )
        except Exception as exc:  # noqa: BLE001 — mapped below
            return self._fail(exc)
        if args.format == "json":
            print(json.dumps(rows, indent=2))
            return _EXIT_OK
        if not rows:
            # An empty critics list is a valid configuration (self-review only),
            # so this is information, not a failure.
            print(strings.t("cli.critic.list.no-critics-configured-add-critics"))
            return _EXIT_OK
        print(_render_table(rows))
        return _EXIT_OK

    # ---------------------------------------------------------------- policy

    def _policy(self, args: argparse.Namespace) -> int:
        """The operator's review-round policy, defaulted — what the skill reads
        before it runs a single review round (issue-352 moved it here)."""
        try:
            policy = routed(
                lambda connection: connection.get(
                    "/repo/critics/policy", params={"repo": str(Path(args.root))}
                ),
                lambda: core_repo.review_policy(str(Path(args.root))),
            )
        except Exception as exc:  # noqa: BLE001 — mapped below
            return self._fail(exc)
        if args.format == "json":
            print(json.dumps(policy, indent=2))
            return _EXIT_OK
        for key, value in policy.items():
            print(f"{key}: {json.dumps(value)}")
        return _EXIT_OK

    # ------------------------------------------------------------------- run

    def _run(self, args: argparse.Namespace) -> int:
        """Render one critic round, executed by :mod:`the_loop.core.repo`.

        The prompt travels as **text**: ``--prompt-file`` is read here, in the
        caller's working directory, because that is where the operator's path
        means what they typed. Its absolute path rides along so
        ``{promptFile}`` still interpolates to the file the operator named;
        with only an inline prompt, core mints a scratch file instead.
        """
        root = str(Path(args.root))
        prompt_file = str(Path(args.prompt_file).resolve()) if args.prompt_file else ""
        try:
            prompt = Path(prompt_file).read_text() if prompt_file else args.prompt
        except OSError as exc:
            logger.error("could not read the prompt: %s", exc)
            return _EXIT_MISCONFIGURED
        try:
            result = routed(
                lambda connection: connection.post(
                    "/repo/critics/run",
                    {
                        "repo": root,
                        "name": args.critic,
                        "prompt": prompt,
                        "promptFile": prompt_file,
                        "workItem": args.work_item,
                        "specDir": args.spec_dir or "",
                        "timeout": args.timeout,
                        "cwd": args.cwd or "",
                    },
                ),
                lambda: core_repo.critic_run(
                    root,
                    args.critic,
                    prompt,
                    prompt_file,
                    work_item=args.work_item,
                    spec_dir=args.spec_dir or "",
                    timeout=args.timeout,
                    cwd=args.cwd or "",
                ),
            )
        except Exception as exc:  # noqa: BLE001 — mapped below
            return self._fail(exc)

        envelope = json.dumps(result, indent=2)
        print(envelope)  # stdout is the envelope and nothing else
        if args.output_file:
            self._write_envelope(Path(args.output_file), envelope)
        if not result.get("ok"):
            logger.error("critic round %r failed: %s", args.critic, result.get("error"))
            return _EXIT_ROUND_FAILED
        return _EXIT_OK

    @staticmethod
    def _fail(exc: Exception) -> int:
        """Always ``_EXIT_MISCONFIGURED``: nothing ran, so there is no round.

        An unknown critic, a broken entry and an unreachable service differ in
        cause and not in consequence — the envelope a caller parses was never
        produced, and exit 2 has always been how this command says so.
        """
        mapped = service_error(exc)
        logger.error("%s", mapped[0].removeprefix("error: ") if mapped else exc)
        return _EXIT_MISCONFIGURED

    @staticmethod
    def _write_envelope(path: Path, envelope: str) -> None:
        """Best-effort: the round already ran, so a write failure must not lose it."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(envelope + "\n")
        except OSError as exc:
            logger.warning("could not write the envelope to %s: %s", path, exc)
