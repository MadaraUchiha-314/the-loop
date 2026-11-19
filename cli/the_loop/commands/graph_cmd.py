"""``the-loop check`` and ``the-loop graph`` — the runtime's CLI surface.

The **core** check operation is pure: no network, no subprocess, no mutation
(R8.8) — which is what lets the same code run on every harness turn *and* in
CI. Since issue-161 the purity lives in :mod:`the_loop.core.graphs`; this
command routes through the control-plane service (the CLI's only execution
path for core capabilities, decision-058), and the one hop to loopback is
transport, not evaluation.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import Command, register
from .. import strings
from ..client.routing import routed, service_error
from ..core import graphs as core_graphs
from ..graph.state import explainer_experiments

logger = logging.getLogger("the-loop.graph")


def _report(exc: Exception) -> int:
    """A client-side failure as the CLI's ``(message, exit code)``.

    Graph commands print bare ``error: …`` on stdout (they predate the split),
    so the mapping is shared but the stream is theirs.
    """
    mapped = service_error(exc)
    if mapped is None:
        mapped = (strings.t("cli.graph.error", error=exc), 2)
    print(mapped[0])
    return mapped[1]


def _is_bad_request(exc: Exception) -> bool:
    """Whether ``exc`` is core saying "you asked for something invalid".

    A refused ``force`` looks the same either way: ``ValueError`` in-process,
    HTTP 400 over the service, because that is exactly how the API maps it.
    """
    from ..client import ApiError

    return isinstance(exc, ValueError) or (
        isinstance(exc, ApiError) and exc.status == 400
    )


def _detail(exc: Exception) -> str:
    from ..client import ApiError

    return exc.detail if isinstance(exc, ApiError) and exc.detail else str(exc)


def _show(
    root: Path, pr: "int | None" = None, pr_repo: str = "", spec_dir: str = ""
) -> Dict[str, Any]:
    """The repo's graph, its start node and its spec root — one round trip."""
    params: Dict[str, Any] = {"repo": str(root)}
    if pr is not None:
        params["pr"] = pr
    if pr_repo:
        params["prRepo"] = pr_repo
    if spec_dir:
        params["specDir"] = spec_dir
    return routed(
        lambda connection: connection.get("/graph", params=params),
        lambda: core_graphs.show(str(root), pr=pr, pr_repo=pr_repo, spec_dir=spec_dir),
    )


def _check(
    root: Path,
    work_item: str,
    recompute: bool = False,
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/check",
            {
                "repo": str(root),
                "workItem": work_item,
                "recompute": bool(recompute),
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.check(
            str(root),
            work_item,
            recompute=recompute,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        ),
    )


def _advance(
    root: Path,
    work_item: str,
    ref: str = "",
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/advance",
            {
                "repo": str(root),
                "workItem": work_item,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.advance(
            str(root), work_item, ref=ref, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir
        ),
    )


def _complete(
    root: Path,
    work_item: str,
    node: str = "",
    actor: str = "",
    ref: str = "",
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/complete",
            {
                "repo": str(root),
                "workItem": work_item,
                "node": node,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.complete(
            str(root),
            work_item,
            node=node,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        ),
    )


def _force(
    root: Path,
    work_item: str,
    to_node: str,
    reason: str,
    actor: str,
    ref: str,
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/force",
            {
                "repo": str(root),
                "workItem": work_item,
                "toNode": to_node,
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.force(
            str(root),
            work_item,
            to_node,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        ),
    )


def _skip(
    root: Path,
    work_item: str,
    nodes: List[str],
    reason: str,
    actor: str,
    ref: str,
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/skip",
            {
                "repo": str(root),
                "workItem": work_item,
                "nodes": list(nodes),
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.skip(
            str(root),
            work_item,
            nodes,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        ),
    )


def _repos(
    root: Path,
    work_item: str,
    repositories: "List[str] | None",
    ref: str = "",
    clear: bool = False,
    pr: "int | None" = None,
    pr_repo: str = "",
    spec_dir: str = "",
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/repos",
            {
                "repo": str(root),
                "workItem": work_item,
                "repositories": repositories,
                "clear": bool(clear),
                "ref": ref,
                "pr": pr,
                "prRepo": pr_repo,
                "specDir": spec_dir,
            },
        ),
        lambda: core_graphs.repos(
            str(root),
            work_item,
            repositories,
            ref=ref,
            clear=clear,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        ),
    )


def _discover_work_items(root: Path, spec_root: str) -> List[str]:
    base = root / spec_root
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def _split_at_pointer(nodes: List[Dict[str, Any]], current: str):
    """Split node reports into those up to the pointer and those beyond it.

    A node the work item has not reached yet is *expected* to be unmet — that is
    what "not done yet" looks like. Reporting it in the same voice as a genuine
    blocker is how a status view starts contradicting itself ("ok" printed above
    a wall of BLOCK lines), so the two are kept visually distinct.
    """
    for index, report in enumerate(nodes):
        if report["node"] == current:
            return nodes[: index + 1], nodes[index + 1 :]
    return list(nodes), []


def _fails(report: Dict[str, Any], fail_on: str) -> bool:
    """Whether this report should make the process exit non-zero.

    ``unmet`` — anything not satisfied, a human-wait included. What you want
    when you are *asking* where a work item stands.

    ``block`` — only a node an agent can actually fix. What an automated gate
    wants: a work item parked at a human-approval node is the normal state of an
    open PR, so failing CI for it would make the gate red by construction, and a
    gate that is always red is one people learn to merge past.

    A repository that is not there fails **both** modes, ahead of either rule.
    Since issue-238 ``graphs.check`` answers a non-resolving ``repo`` with
    ``repoResolved: false`` and an empty node list rather than raising — correct
    for the polled API, where a cleaned-up checkout is expected state, and a trap
    here: a report with no nodes has no *blocking* node either, so a mistyped
    ``--repo`` would take `--fail-on block` straight to exit 0. A gate that
    evaluated nothing has not passed.
    """
    if report.get("repoResolved") is False:
        return True
    if fail_on == "unmet":
        return not report["ok"]
    current = report.get("currentNode")
    for node in report.get("nodes") or []:
        if node.get("node") == current:
            return node.get("status") == "block"
        if node.get("status") == "block":
            return True  # an earlier node is broken; the pointer moved past it
    return False


def _render_table(reports, ahead=()) -> str:
    lines = []
    for report in reports:
        status = report["status"]
        mark = {"pass": "ok", "skip": "--", "wait": "wait", "block": "BLOCK"}.get(
            status, status.upper()
        )
        flag = strings.t("cli.graph.table.forced") if report.get("forced") else ""
        lines.append(f"  {mark:<6} {report['node']}{flag}")
        for message in report.get("messages") or []:
            lines.append(f"         · {message}")
    pending = [r for r in ahead if r["status"] not in ("pass", "skip")]
    if pending:
        lines.append(
            strings.t("cli.graph.table.not-reached", count=len(pending))
            + ", ".join(r["node"] for r in pending)
        )
    return "\n".join(lines)


@register
class CheckCommand(Command):
    name = "check"
    help = strings.t("cli.check.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "work_item",
            nargs="?",
            help=strings.t("cli.check.work-item.help"),
        )
        _add_repo_flag(parser)
        _add_spec_dir_flag(parser)
        parser.add_argument("--format", choices=["table", "json"], default="table")
        parser.add_argument(
            "--all",
            action="store_true",
            help=strings.t("cli.check.all.help"),
        )
        parser.add_argument(
            "--recompute",
            action="store_true",
            help=strings.t("cli.check.recompute.help"),
        )
        parser.add_argument(
            "--fail-on",
            choices=["unmet", "block"],
            default="unmet",
            help=strings.t("cli.check.fail-on.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        try:
            return self._report_on(args)
        except Exception as exc:  # noqa: BLE001 — every failure is a message
            return _report(exc)

    def _report_on(self, args: argparse.Namespace) -> int:
        note = ""
        if args.all:
            root = _resolve_root(args.repo)
            items = _discover_work_items(
                root, _show(root, spec_dir=args.spec_dir)["specRoot"]
            )
        elif args.work_item:
            root, note = _resolve_read_root(args.repo, args.work_item, args.spec_dir)
            items = [args.work_item]
        else:
            print(strings.t("cli.check.need-item"))
            return 2

        payload = []
        failing = 0
        for item in items:
            data = _check(root, item, recompute=args.recompute, spec_dir=args.spec_dir)
            payload.append(data)
            if _fails(data, args.fail_on):
                failing += 1

        if args.format == "json":
            print(json.dumps(payload if args.all else payload[0], indent=2))
        else:
            for report in payload:
                # Nothing was evaluated, so there is nothing to render but the
                # reason (issue-238). Without this the row reads "UNMET (at )"
                # with no findings under it, which looks like a work item with
                # no nodes rather than a repository that is not there.
                if report.get("repoResolved") is False:
                    print(
                        strings.t(
                            "cli.check.unread", work_item=report["workItem"], root=root
                        )
                    )
                    continue
                if report.get("archived"):
                    # Ended and cleaned up (issue-452): the archive is the
                    # answer, and there are no node findings to list.
                    _print_archived(report, note)
                    continue
                state = (
                    strings.t("cli.check.state-ok")
                    if report["ok"]
                    else strings.t("cli.check.state-unmet")
                )
                print(
                    strings.t(
                        "cli.check.row",
                        work_item=report["workItem"],
                        state=state,
                        node=report["currentNode"],
                    )
                )
                if not args.all:
                    # Which file the answer came from (issue-396). `--all` is a
                    # drift summary — one line per item, as before.
                    if note:
                        print(f"  {note}")
                    print(f"  {_state_line(report, recompute=args.recompute)}")
                # Only nodes at or before the pointer are findings; anything
                # beyond it is simply not done yet, and saying "BLOCK" about it
                # would make an ok work item read as a broken one.
                reached = []
                for entry in report["nodes"]:
                    reached.append(entry)
                    if entry["node"] == report["currentNode"]:
                        break
                unmet = [r for r in reached if r["status"] not in ("pass", "skip")]
                if unmet and (not args.all or not report["ok"]):
                    for entry in unmet[:1] if args.all else unmet:
                        print(f"  {entry['status'].upper():<6} {entry['node']}")
                        for message in entry["messages"]:
                            print(f"         · {message}")
                ahead = [
                    r
                    for r in report["nodes"][len(reached) :]
                    if r["status"] not in ("pass", "skip")
                ]
                if ahead and not args.all:
                    print(strings.t("cli.check.not-reached", count=len(ahead)))
            if args.all:
                print(
                    strings.t(
                        "cli.check.summary",
                        satisfied=len(payload) - failing,
                        total=len(payload),
                    )
                )
        return 1 if failing else 0


def _add_repo_flag(parser: argparse.ArgumentParser) -> None:
    """``--repo``: the repository root. Unset means *resolve it* (issue-396)."""
    parser.add_argument(
        "--repo",
        default="",
        help=strings.t("cli.graph.repo.help"),
    )


def _resolve_root(repo: str) -> Path:
    """The repository root a verb runs against: ``--repo``, else the working directory."""
    return Path(repo).resolve() if repo else Path(".").resolve()


def _resolve_read_root(repo: str, work_item: str, spec_dir: str) -> Tuple[Path, str]:
    """The root a **read** verb reports on, and how it was found (issue-396).

    Three tiers: an explicit ``--repo`` is used verbatim; a working directory
    that holds the work item's spec directory is used; failing both, a **ref**
    is looked up in the session registry the CLI config resolves, and the
    checkout the daemon recorded for its session is used — that is where the
    daemon's runtime wrote ``work-item-state.json``, and until this change the
    one place ``graph status`` could not find from another directory. The note
    names the registry as the source so the answer is attributable. Anything
    that does not resolve falls through to the working directory, where the
    ``state:`` line then shows the miss.

    Read verbs only (``graph status``, ``check <item>``): a mutating verb writes
    into the checkout it is pointed at, and that stays the operator's choice.
    """
    if repo:
        return Path(repo).resolve(), ""
    cwd = Path(".").resolve()
    from ..graph.bootstrap import resolve_spec_root

    spec_root = resolve_spec_root(override=spec_dir)
    if (cwd / spec_root / core_graphs.work_item_id(work_item)).is_dir():
        return cwd, ""
    checkout = _session_checkout(work_item)
    if checkout is None:
        return cwd, ""
    return checkout, strings.t("cli.graph.registry-note", checkout=checkout)


def _session_checkout(work_item: str) -> Optional[Path]:
    """The checkout the daemon recorded for ``work_item``'s session, if it is there.

    A pure read of the registry ``sessions list`` reads (``routing.registryDir``,
    else the state layout's ``local/``, off the CLI config ``--config`` selected).
    A closed record still answers — the operator asking after a finished item
    wants its checkout too, as ``sessions attach`` does. Only a ref can be looked
    up (the registry is keyed by ref); a bare id, a missing config, a missing or
    unreadable record, or a ``cwd`` that is no longer a directory all yield
    ``None``, never an error: this is a convenience on a read path.
    """
    from ..graph.bootstrap import load_cli_config_best_effort
    from ..sessions import SessionRegistry, WorkItemRef
    from ..state import layout_from_config

    try:
        ref = WorkItemRef.parse(work_item)
    except ValueError:
        return None
    try:
        config = load_cli_config_best_effort()
        routing = config.get("routing") or {}
        registry_dir = (
            str(routing.get("registryDir") or "")
            or layout_from_config(config).local_dir
        )
        session = SessionRegistry(registry_dir).find_by_work_item(
            ref, include_closed=True
        )
    except Exception as exc:  # noqa: BLE001 — a registry we cannot read is "no answer"
        logger.debug(
            "could not consult the session registry for %s: %s", work_item, exc
        )
        return None
    if session is None or not session.cwd:
        return None
    checkout = Path(session.cwd)
    if not checkout.is_dir():
        logger.debug(
            "%s's session recorded cwd %s, which is not a directory",
            work_item,
            checkout,
        )
        return None
    return checkout.resolve()


def _archived_lines(report: Dict[str, Any]) -> List[str]:
    """The table for an archived work item (issue-452).

    Ended upstream, its checkout cleaned up, answered from the terminal record
    the closure kept — or, when there is none, saying so rather than printing a
    start-node position. Every value printed here was filtered when it was
    recorded (``the_loop.archive``), so none of it can carry a terminal escape.
    """
    archived = report["archived"]
    node = str(report.get("currentNode") or "")
    head = strings.t(
        "cli.graph.archived.head",
        work_item=report["workItem"],
        outcome=archived.get("outcome")
        or strings.t("cli.graph.archived.unknown-outcome"),
    )
    lines = [head + (strings.t("cli.graph.archived.at", node=node) if node else "")]
    actor = str(archived.get("actor") or "") or strings.t(
        "cli.graph.archived.unnamed-actor"
    )
    lines.append(
        strings.t(
            "cli.graph.archived.ended",
            state=archived.get("state")
            or strings.t("cli.graph.archived.default-state"),
            actor=actor,
            at=archived.get("at") or "?",
            reason=archived.get("reason") or strings.t("cli.graph.archived.no-reason"),
        )
    )
    terminal = archived.get("terminal")
    if not isinstance(terminal, dict):
        lines.append(strings.t("cli.graph.archived.no-detail"))
        return lines
    if terminal.get("completedAt"):
        lines.append(
            strings.t("cli.graph.archived.completed", at=terminal["completedAt"])
        )
    selections = terminal.get("selections") or {}
    skipped = selections.get("skipped") or []
    opted = selections.get("optedIn") or []
    lines.append(
        strings.t("cli.graph.archived.selections")
        + (
            strings.t("cli.graph.archived.skipped", phases=", ".join(skipped))
            if skipped
            else strings.t("cli.graph.archived.none-skipped")
        )
        + (
            strings.t("cli.graph.archived.opted-in", phases=", ".join(opted))
            if opted
            else ""
        )
    )
    chosen = [
        f"{key} {selections[key]}"
        for key in ("harness", "model", "effort", "surface", "sessionPerPr")
        if selections.get(key)
    ]
    if selections.get("claudeArtifact") is True:
        chosen.append("claude-artifact")  # issue-471
    if selections.get("claudeDoc") is True:
        chosen.append("claude-doc")  # issue-536
    chosen += [
        f"explainer-{name}"
        for name in explainer_experiments(selections.get("explainerExperiments"))
    ]
    if chosen:
        lines.append(strings.t("cli.graph.archived.choices", choices=", ".join(chosen)))
    for pr in terminal.get("pullRequests") or []:
        url = f" {pr['url']}" if pr.get("url") else ""
        lines.append(
            strings.t(
                "cli.graph.archived.pull-request",
                ref=pr.get("ref"),
                state=pr.get("state") or "?",
                url=url,
            )
        )
    evidence = terminal.get("evidence") or []
    if terminal.get("specDir"):
        lines.append(
            strings.t("cli.graph.archived.evidence", spec_dir=terminal["specDir"])
            + (
                strings.t("cli.graph.archived.evidence-list", files=", ".join(evidence))
                if evidence
                else strings.t("cli.graph.archived.evidence-none")
            )
        )
    return lines


def _print_archived(report: Dict[str, Any], note: str = "") -> None:
    lines = _archived_lines(report)
    print(lines[0])
    if note:
        print(f"  {note}")
    print(f"  {_state_line(report)}")
    for line in lines[1:]:
        print(line)


def _state_line(report: Dict[str, Any], recompute: bool = False) -> str:
    """``state: <path>`` — which ``work-item-state.json`` the report is about.

    Printed found or not (issue-396): a report that fell back to the graph's
    start node used to be indistinguishable from a work item that genuinely
    sits there. When the state directory itself is absent the line says so and
    points at the two ways to reach the right checkout.
    """
    path = str(report.get("statePath") or "")
    if report.get("archived"):
        return strings.t("cli.graph.state.archived", path=path)
    if report.get("stateFound"):
        pointer = str(report.get("pointer") or "")
        if recompute and pointer and pointer != report.get("currentNode"):
            # The two answers to "where is it" disagree (issue-429): the
            # artifacts place the item further along than it was ever
            # advanced. Say both, or `check` and the stop gate read as if
            # they contradict each other.
            return strings.t(
                "cli.graph.state.pointer-differs", path=path, pointer=pointer
            )
        return strings.t("cli.graph.state.found", path=path)
    parent = Path(path).parent
    if not parent.is_dir():
        return strings.t("cli.graph.state.no-dir", path=path, parent=parent)
    if recompute:
        return strings.t("cli.graph.state.recompute", path=path)
    return strings.t("cli.graph.state.not-entered", path=path)


def _add_spec_dir_flag(parser: argparse.ArgumentParser) -> None:
    """``--spec-dir``: where this checkout keeps its specs (issue-352).

    The CLI reads no harness config, so a repository whose specs are not under
    ``docs/specs`` says so here — or, for a daemon, once in the CLI config's
    ``routing.graph.specDir``. Unset, that config key answers, else the default.
    """
    parser.add_argument(
        "--spec-dir",
        default="",
        dest="spec_dir",
        help=strings.t("cli.graph.spec-dir.help"),
    )


def _add_pr_flags(parser: argparse.ArgumentParser) -> None:
    """The two flags that select an INNER loop, on every verb that has them.

    ``--pr`` alone is a pull request in the **origin** repository — the one the
    ticket was created in (issue-172). ``--pr-repo`` qualifies it for a work item
    that contributes to several repositories (issue-183): the loop's state then
    lives at ``pr-loops/<owner>__<repo>/pr-<n>/``, still under the one spec
    directory in the origin repository. A repository does not identify a loop, so
    ``--pr-repo`` without ``--pr`` is refused.
    """
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help=strings.t("cli.graph.pr.help"),
    )
    parser.add_argument(
        "--pr-repo",
        default="",
        help=strings.t("cli.graph.pr-repo.help"),
    )


def _declared_hooks() -> Dict[str, Any]:
    """What the CLI config declares under ``routing.graph.hooks``, parsed but NOT loaded.

    Deliberately inert: the whole point is that an operator can see what would
    run **before** running it (R5.1) — the same shape as ``the-loop critic list``,
    which reports the other block of executable configuration the CLI config
    carries. A declaration is reported here, and only ``the-loop check`` imports
    it. Since issue-352 the declaration is the operator's, not a repository's: the
    CLI reads no harness config.
    """
    from ..graph import hooks as _hooks  # noqa: F401 — registers the built-ins
    from ..graph import read_declaration
    from ..graph.bootstrap import load_cli_config_best_effort
    from ..graph.registry import hook_names

    declaration = read_declaration(load_cli_config_best_effort())
    return {
        "shipped": hook_names(),
        "modules": [
            {"path": ref.path, "module": ref.dotted} for ref in declaration.modules
        ],
        "attach": [
            {
                "hook": a.hook,
                "node": a.node,
                "boundary": a.boundary,
                "with": dict(a.params),
                **({"loops": list(a.loops)} if a.loops else {}),
            }
            for a in declaration.attachments
        ],
    }


def _report_hooks(root: Path, fmt: str) -> int:
    report = _declared_hooks()
    if fmt == "json":
        print(json.dumps(report, indent=2))
        return 0
    shipped = report["shipped"]
    print(
        strings.t(
            "cli.graph.hooks.shipped", count=len(shipped), names=", ".join(shipped)
        )
    )
    modules, attach = report["modules"], report["attach"]
    if not modules and not attach:
        print(strings.t("cli.graph.hooks.none"))
        return 0
    print(
        strings.t(
            "cli.graph.hooks.declares", modules=len(modules), attachments=len(attach)
        )
    )
    for ref in modules:
        print(strings.t("cli.graph.hooks.module", module=ref["path"] or ref["module"]))
    for entry in attach:
        suffix = (
            strings.t("cli.graph.hooks.with", params=entry["with"])
            if entry["with"]
            else ""
        )
        if entry.get("loops"):
            suffix += strings.t("cli.graph.hooks.in", loops=", ".join(entry["loops"]))
        print(
            strings.t(
                "cli.graph.hooks.attach",
                hook=entry["hook"],
                node=entry["node"],
                boundary=entry["boundary"],
                suffix=suffix,
            )
        )
    print(strings.t("cli.graph.hooks.footer"))
    return 0


def _strict_cli_config() -> Dict[str, Any]:
    """The CLI config in effect, read STRICTLY: a file that cannot be parsed or
    validated raises, rather than reading as "nothing declared" — the report's
    whole job is to find a mistake before a work item does."""
    from .. import cli_config

    path = cli_config.default_cli_config_path()
    if not path.is_file():
        return {}
    loaded = cli_config.load_cli_config(path, strict=True) or {}
    return loaded if isinstance(loaded, dict) else {}


def _declared_loops() -> Dict[str, Any]:
    """Every loop this machine can walk: the shipped ones and the operator's own
    (the top-level ``graphs``, issue-343), each with the keywords that arm it —
    the shipped bindings, re-pointed or extended by ``routing.control.commands``.

    Each declared graph is compiled and checked the way a load checks it — the
    compiler's rules, the phase vocabulary, every attachment that applies to it
    naming a node it declares, its ``x-`` hooks having a module to come from —
    but **no hook module is imported**: whether a module really registers a name
    is settled only when a work item loads the graph. A configuration that cannot
    be read, a malformed declaration or a clashing keyword is reported as the one
    error, with no rows.
    """
    from ..control import ControlConfig
    from ..graph import hooks as _hooks  # noqa: F401 — registers the built-ins
    from ..graph.catalog import compile_custom, read_catalog
    from ..graph.extensions import read_declaration
    from ..graph.model import (
        GUEST_LOOPS,
        LOOP_FOR_CONTROL_COMMAND,
        PDLC_PR_LOOP,
        PDLC_WORK_ITEM_LOOP,
        SHIPPED_LOOPS,
        extension_hook_names,
    )

    try:
        cfg = _strict_cli_config()
        routing = cfg.get("routing") or {}
        catalog = read_catalog(cfg)
        declaration = read_declaration(cfg)
        control = ControlConfig.from_mapping(
            routing.get("control") or {}, graphs=cfg.get("graphs")
        )
    except Exception as exc:  # noqa: BLE001 — the report IS the error
        return {"loops": [], "error": str(exc)}

    def keywords(words: List[str]) -> List[str]:
        # What a person actually types: the configured keyword, and nothing for
        # a command the operator disabled.
        return [control.keyword(w) for w in words if control.keyword(w)]

    # Which words select which loop, after the operator's bindings: the shipped
    # mapping first, each binding then re-pointing a word or adding one.
    selects: Dict[str, str] = {"start": PDLC_WORK_ITEM_LOOP}
    selects.update(LOOP_FOR_CONTROL_COMMAND)
    selects.update(control.bindings)
    armed_by: Dict[str, List[str]] = {}
    for word, loop in selects.items():
        armed_by.setdefault(loop, []).append(word)
    rows: List[Dict[str, Any]] = []
    for name in SHIPPED_LOOPS:
        rows.append(
            {
                "name": name,
                "kind": "shipped",
                "commands": keywords(armed_by.get(name, [])),
                "guest": name in GUEST_LOOPS,
                "inner": name == PDLC_PR_LOOP,
                "status": "ok",
            }
        )
    for entry in catalog.entries:
        path = entry.resolved_path()
        row: Dict[str, Any] = {
            "name": entry.name,
            "kind": "declared",
            "commands": keywords(armed_by.get(entry.name, [])),
            "guest": entry.guest,
            "inner": False,
            "path": str(path),
        }
        try:
            graph = compile_custom(entry, path)
            problems = [
                f"`routing.graph.hooks.attach` puts {a.hook} on node {a.node!r}, "
                "which this graph does not declare — scope the attachment with "
                "`loops`"
                for a in declaration.attachments
                if a.applies_to(graph.name) and a.node not in graph.nodes
            ]
            named = extension_hook_names(graph)
            if named and not declaration.modules:
                problems.append(
                    f"names {', '.join(named)} but `routing.graph.hooks.modules` "
                    "declares no module to register them"
                )
            if problems:
                raise ValueError("; ".join(problems))
        except Exception as exc:  # noqa: BLE001 — a broken graph is a row, not a crash
            row.update(status="error", error=str(exc))
        else:
            row.update(status="ok", extensionHooks=named)
        rows.append(row)
    return {"loops": rows, "error": ""}


def _report_loops(fmt: str) -> int:
    report = _declared_loops()
    failed = bool(report["error"]) or any(
        row["status"] != "ok" for row in report["loops"]
    )
    if fmt == "json":
        print(json.dumps(report, indent=2))
        return 1 if failed else 0
    if report["error"]:
        print(strings.t("cli.graph.loops.unreadable", error=report["error"]))
        return 1
    for row in report["loops"]:
        commands = ", ".join(row["commands"]) or "—"
        traits = [row["kind"]]
        if row["guest"]:
            traits.append("guest")
        if row["inner"]:
            traits.append(strings.t("cli.graph.loops.inner-trait"))
        print(f"{row['name']}  ({', '.join(traits)})")
        print(strings.t("cli.graph.loops.armed-by", commands=commands))
        if row["kind"] == "declared":
            print(strings.t("cli.graph.loops.file", path=row["path"]))
            if row["status"] == "ok":
                hooks = ", ".join(row["extensionHooks"])
                print(
                    strings.t("cli.graph.loops.compiles-ok")
                    + (
                        strings.t("cli.graph.loops.names-hooks", hooks=hooks)
                        if hooks
                        else ""
                    )
                )
            else:
                print(strings.t("cli.graph.loops.compiles-no", error=row["error"]))
    if not any(row["kind"] == "declared" for row in report["loops"]):
        print(strings.t("cli.graph.loops.none-declared"))
    return 1 if failed else 0


@register
class GraphCommand(Command):
    name = "graph"
    help = strings.t("cli.graph.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        _add_repo_flag(parser)
        _add_spec_dir_flag(parser)
        sub = parser.add_subparsers(dest="action", required=True)

        show = sub.add_parser("show", help=strings.t("cli.graph.show.help"))
        show.add_argument("--format", choices=["text", "json"], default="text")
        _add_pr_flags(show)

        status = sub.add_parser("status", help=strings.t("cli.graph.status.help"))
        status.add_argument("work_item")
        _add_pr_flags(status)

        advance = sub.add_parser("advance", help=strings.t("cli.graph.advance.help"))
        advance.add_argument("work_item")
        advance.add_argument("--ref", default="", help=strings.t("cli.graph.ref.help"))
        _add_pr_flags(advance)

        complete = sub.add_parser(
            "complete",
            help=strings.t("cli.graph.complete.help"),
        )
        complete.add_argument("work_item")
        complete.add_argument(
            "--node",
            default="",
            help=strings.t("cli.graph.complete.node.help"),
        )
        complete.add_argument("--ref", default="", help=strings.t("cli.graph.ref.help"))
        complete.add_argument(
            "--actor", default="", help=strings.t("cli.graph.complete.actor.help")
        )
        _add_pr_flags(complete)

        forced = sub.add_parser(
            "force",
            help=strings.t("cli.graph.force.help"),
        )
        forced.add_argument("work_item")
        forced.add_argument(
            "--to", required=True, help=strings.t("cli.graph.force.to.help")
        )
        forced.add_argument(
            "--reason", required=True, help=strings.t("cli.graph.reason.help")
        )
        forced.add_argument(
            "--actor", default="", help=strings.t("cli.graph.force.actor.help")
        )
        forced.add_argument("--ref", default="")
        _add_pr_flags(forced)

        skip = sub.add_parser(
            "skip",
            help=strings.t("cli.graph.skip.help"),
        )
        skip.add_argument("work_item")
        skip.add_argument(
            "--node",
            action="append",
            required=True,
            dest="nodes",
            help=strings.t("cli.graph.skip.node.help"),
        )
        skip.add_argument(
            "--reason", required=True, help=strings.t("cli.graph.reason.help")
        )
        skip.add_argument(
            "--actor", default="", help=strings.t("cli.graph.skip.actor.help")
        )
        skip.add_argument("--ref", default="", help=strings.t("cli.graph.ref.help"))
        _add_pr_flags(skip)

        repos = sub.add_parser(
            "repos",
            help=strings.t("cli.graph.repos.help"),
        )
        repos.add_argument("work_item")
        # `--repository`, not `--repo`: the parent parser's `--repo` is the
        # repository ROOT, and one spelling for two meanings is a footgun in the
        # one verb where both appear on the same line.
        repos.add_argument(
            "--repository",
            action="append",
            dest="repositories",
            help=strings.t("cli.graph.repos.repository.help"),
        )
        repos.add_argument(
            "--clear",
            action="store_true",
            help=strings.t("cli.graph.repos.clear.help"),
        )
        repos.add_argument("--ref", default="", help=strings.t("cli.graph.ref.help"))
        _add_pr_flags(repos)

        sub.add_parser(
            "hooks",
            help=strings.t("cli.graph.hooks.help"),
        ).add_argument("--format", choices=["text", "json"], default="text")

        sub.add_parser(
            "loops",
            help=strings.t("cli.graph.loops.help"),
        ).add_argument("--format", choices=["text", "json"], default="text")

        run = sub.add_parser("run", help=strings.t("cli.graph.run.help"))
        run.add_argument("work_item")
        run.add_argument("--ref", default="")
        run.add_argument(
            "--max-nodes",
            type=int,
            default=20,
            help=strings.t("cli.graph.run.max-nodes.help"),
        )
        run.add_argument(
            "--dry-run",
            action="store_true",
            help=strings.t("cli.graph.run.dry-run.help"),
        )

    def run(self, args: argparse.Namespace) -> int:
        try:
            return self._dispatch(args)
        except Exception as exc:  # noqa: BLE001 — every failure is a message
            return _report(exc)

    def _dispatch(self, args: argparse.Namespace) -> int:
        spec_dir = getattr(args, "spec_dir", "") or ""
        # Only the READ verb resolves the checkout through the registry
        # (issue-396): a mutating verb writes into the checkout it is pointed
        # at, and that stays the operator's choice — `--repo` or the working
        # directory.
        note = ""
        if args.action == "status":
            root, note = _resolve_read_root(args.repo, args.work_item, spec_dir)
        else:
            root = _resolve_root(args.repo)
        if args.action == "hooks":
            return _report_hooks(root, args.format)
        if args.action == "loops":
            return _report_loops(args.format)

        if args.action == "show":
            graph = _show(root, pr=args.pr, pr_repo=args.pr_repo, spec_dir=spec_dir)
            if args.format == "json":
                # ``specRoot`` is a layout fact the runtime carries, not part of
                # the graph an operator asked to see, so it stays out of here.
                print(
                    json.dumps(
                        {k: v for k, v in graph.items() if k != "specRoot"}, indent=2
                    )
                )
                return 0
            print(
                strings.t(
                    "cli.graph.show.head",
                    version=graph["version"],
                    start=graph["start"],
                )
            )
            edges = graph["edges"]
            for node in graph["nodes"]:
                flags = []
                if node.get("required"):
                    flags.append("required")
                if node.get("optIn"):
                    # issue-188: `optIn` implies `skippable`, so print the more
                    # specific of the two — "skippable" alone would read as
                    # on-by-default, which is the opposite of what this node is.
                    flags.append("opt-in")
                elif node.get("skippable"):
                    flags.append("skippable")
                if node.get("actor") == "human":
                    flags.append("human")
                if node.get("terminal"):
                    flags.append("terminal")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                print(f"  {node['id']}{suffix}")
                for edge in edges:
                    if edge["from"] == node["id"]:
                        print(f"      --{edge['on']}--> {edge['to']}")
            return 0

        if args.action == "status":
            report = _check(
                root,
                args.work_item,
                pr=args.pr,
                pr_repo=args.pr_repo,
                spec_dir=spec_dir,
            )
            if report.get("archived"):
                _print_archived(report, note)
                return 0 if report["ok"] else 1
            reached, ahead = _split_at_pointer(report["nodes"], report["currentNode"])
            print(
                strings.t(
                    "cli.graph.status.at",
                    work_item=report["workItem"],
                    node=report["currentNode"],
                )
            )
            if note:
                print(f"  {note}")
            print(f"  {_state_line(report)}")
            print(_render_table(reached, ahead))
            return 0 if report["ok"] else 1

        if args.action == "advance":
            result = _advance(
                root,
                args.work_item,
                ref=args.ref,
                pr=args.pr,
                pr_repo=args.pr_repo,
                spec_dir=spec_dir,
            )
            print(f"{args.work_item}: {result['node']} → {result['status']}")
            for message in result["messages"]:
                print(f"  · {message}")
            return 0 if result["status"] in ("pass", "wait") else 1

        if args.action == "complete":
            # One JSON envelope on stdout, machine-readable (R1.3). A refusal
            # or a block is a *result* the agent acts on, not a CLI error —
            # exit 0 either way; non-zero is reserved for not being able to
            # answer at all.
            result = _complete(
                root,
                args.work_item,
                node=args.node,
                actor=args.actor,
                ref=args.ref,
                pr=args.pr,
                pr_repo=args.pr_repo,
                spec_dir=spec_dir,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.action == "skip":
            try:
                result = _skip(
                    root,
                    args.work_item,
                    args.nodes,
                    args.reason,
                    args.actor,
                    args.ref,
                    pr=args.pr,
                    pr_repo=args.pr_repo,
                    spec_dir=spec_dir,
                )
            except Exception as exc:  # noqa: BLE001
                # A refused declaration is the runtime's verdict, not a broken
                # CLI — same contract as a refused force.
                if not _is_bad_request(exc) and service_error(exc) is not None:
                    raise
                print(strings.t("cli.graph.refused", detail=_detail(exc)))
                return 2
            for node in result["declared"]:
                print(strings.t("cli.graph.skip.declared", node=node))
            for entry in result["rejected"]:
                print(
                    strings.t(
                        "cli.graph.skip.rejected",
                        token=entry["token"],
                        why=entry["why"],
                    )
                )
            for warning in result.get("warnings") or []:
                # Same voice as `force`'s: the declaration took effect, but part
                # of its paper trail did not (issue-194).
                print(strings.t("cli.graph.warning", warning=warning))
            if result["declared"]:
                print(strings.t("cli.graph.skip.note"))
            return 0 if result["declared"] else 1

        if args.action == "repos":
            try:
                result = _repos(
                    root,
                    args.work_item,
                    args.repositories,
                    ref=args.ref,
                    clear=args.clear,
                    pr=args.pr,
                    pr_repo=args.pr_repo,
                    spec_dir=spec_dir,
                )
            except Exception as exc:  # noqa: BLE001
                if not _is_bad_request(exc) and service_error(exc) is not None:
                    raise
                print(strings.t("cli.graph.refused", detail=_detail(exc)))
                return 2
            for entry in result["rejected"]:
                print(
                    strings.t(
                        "cli.graph.repos.rejected", repo=entry["repo"], why=entry["why"]
                    )
                )
            if result["rejected"]:
                # All or nothing: a partial declaration is a gate waiting on a
                # set nobody chose, so nothing was written.
                print(strings.t("cli.graph.repos.nothing-declared"))
                return 2
            reading = args.repositories is None and not args.clear
            if not result["declared"]:
                print(strings.t("cli.graph.repos.none"))
                return 0
            for name in result["declared"]:
                print(
                    strings.t("cli.graph.repos.repository", name=name)
                    if reading
                    else strings.t("cli.graph.repos.declared", name=name)
                )
            if not reading:
                print(strings.t("cli.graph.repos.note"))
            return 0

        if args.action == "run":
            return self._run_loop(root, args)

        if args.action == "force":
            try:
                result = _force(
                    root,
                    args.work_item,
                    args.to,
                    args.reason,
                    args.actor,
                    args.ref,
                    pr=args.pr,
                    pr_repo=args.pr_repo,
                    spec_dir=spec_dir,
                )
            except Exception as exc:  # noqa: BLE001
                # A refused force is the runtime's verdict, not a broken CLI —
                # it keeps its own word. Only a transport failure (unreachable
                # service) falls through to the shared "error:" mapping.
                if not _is_bad_request(exc) and service_error(exc) is not None:
                    raise
                print(strings.t("cli.graph.refused", detail=_detail(exc)))
                return 2
            print(
                strings.t(
                    "cli.graph.force.done",
                    work_item=result["workItem"],
                    from_node=result["fromNode"],
                    to_node=result["toNode"],
                )
            )
            print(strings.t("cli.graph.force.reason", reason=result["reason"]))
            for warning in result["warnings"]:
                print(strings.t("cli.graph.warning", warning=warning))
            print(strings.t("cli.graph.force.note"))
            return 0

        return 2

    @staticmethod
    def _run_loop(root: Path, args) -> int:
        """Advance until the work item waits, escalates or reaches a terminal node.

        Bounded by ``--max-nodes`` — a runaway loop is the one failure mode a
        deterministic driver can still have, so it gets an explicit ceiling
        rather than trust.
        """
        if args.dry_run:
            report = _check(root, args.work_item)
            reached, ahead = _split_at_pointer(report["nodes"], report["currentNode"])
            print(
                strings.t(
                    "cli.graph.run.dry-run",
                    work_item=args.work_item,
                    node=report["currentNode"],
                )
            )
            print(_render_table(reached, ahead))
            return 0 if report["ok"] else 1

        terminal = {n["id"] for n in _show(root)["nodes"] if n.get("terminal")}
        seen: List[str] = []
        for _ in range(max(1, args.max_nodes)):
            result = _advance(root, args.work_item, ref=args.ref)
            print(f"  {result['node']}: {result['status']}")
            for message in result["messages"]:
                print(f"      · {message}")
            if result["status"] in ("wait", "block", "escalated"):
                print(
                    strings.t(
                        "cli.graph.run.stopped",
                        work_item=args.work_item,
                        node=result["node"],
                        status=result["status"],
                    )
                )
                return 0 if result["status"] == "wait" else 1
            if result["node"] in terminal:
                print(strings.t("cli.graph.run.complete", work_item=args.work_item))
                return 0
            seen.append(result["node"])
            if seen.count(result["node"]) > 2:
                print(
                    strings.t(
                        "cli.graph.run.looping",
                        work_item=args.work_item,
                        node=result["node"],
                    )
                )
                return 1
        print(
            strings.t(
                "cli.graph.run.max-nodes",
                work_item=args.work_item,
                max_nodes=args.max_nodes,
            )
        )
        return 1
