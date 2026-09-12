"""Assembling a :class:`Runtime` from the CLI config on disk.

Extracted from ``commands/graph_cmd.py`` when the ingress gained a second call
site (issue-113). It matters that there is only one of these: the runtime's
``config`` is what carries ``authorizedUsers`` to ``classify-feedback``, and a
second, subtly different assembly is how a gate ends up reading an empty
authorized-user list and failing closed forever on one path while working on the
other.

**The CLI reads no harness config** (issue-352, decision-123). Until then this
module opened the checkout's ``.the-loop/harness-config.yaml`` for a handful of
keys; every one of them now has another source, named where it is read below:
the spec directory is the CLI config's (or a flag), the phase label prefix is a
constant, the origin repository is the work item's own ref or the checkout's
``origin`` remote, and "has this repository adopted the-loop?" became "is this a
guest loop?" — a question about the work item, not about a file in the checkout.

The CLI config is read best-effort — a missing or malformed one yields defaults
rather than an error, because ``the-loop check`` must work in a repo that has
never seen the CLI config.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "DEFAULT_SPEC_DIR",
    "build_runtime",
    "load_cli_config_best_effort",
    "resolve_spec_root",
]

#: Where a repository keeps its per-work-item specs when nobody says otherwise.
#: Expressed here rather than at each call site because ``graphlink.py``,
#: ``core/graphs.py`` and this module must agree on it: they resolve the same
#: directory for the same work item, one to gate on and one to write into, and
#: two copies of a literal is how they came to disagree (issue-123).
DEFAULT_SPEC_DIR = "docs/specs"


def load_cli_config_best_effort() -> Dict[str, Any]:
    """The operator's CLI config, or ``{}`` — never fatal.

    ``the-loop check`` runs in CI checkouts that have no CLI config anywhere, and
    the graph must still evaluate there on defaults.
    """
    try:
        from .. import cli_config

        loaded = cli_config.load_cli_config(cli_config.default_cli_config_path()) or {}
    except Exception:  # noqa: BLE001 — the CLI config is optional for `check`
        return {}
    return loaded if isinstance(loaded, dict) else {}


def resolve_spec_root(
    cli_cfg: Optional[Mapping[str, Any]] = None, override: str = ""
) -> str:
    """Where specs live: an explicit override, else ``routing.graph.specDir``,
    else :data:`DEFAULT_SPEC_DIR`.

    One resolution for every reader — the daemon's coupling, ``the-loop check``,
    ``the-loop graph`` and the ``{specDir}`` critic placeholder — so the gate and
    the write land in the same directory. ``cli_cfg`` may be passed by a caller
    that has already loaded it; otherwise it is read here, best-effort.
    """
    if override:
        return str(override)
    cfg = cli_cfg if cli_cfg is not None else load_cli_config_best_effort()
    declared = ((cfg.get("routing") or {}).get("graph") or {}).get("specDir")
    return str(declared or DEFAULT_SPEC_DIR)


def build_runtime(
    root: Path,
    spec_root: Optional[str] = None,
    authorized_users: Optional[Sequence[str]] = None,
    pr_number: Optional[int] = None,
    pr_repo: str = "",
    loop: str = "",
    origin_repo: str = "",
):
    """A runtime for ``root``, configured from the CLI config.

    ``authorized_users`` is a **CLI-config** value the daemon has already parsed,
    honouring ``--config``, so re-reading the default path here could disagree
    with the config the process is actually running. It passes what it parsed.

    ``spec_root`` is an explicit choice — ``--spec-dir`` on the command line, or
    the coupling's already-resolved directory. Unset, :func:`resolve_spec_root`
    answers from the CLI config.

    ``origin_repo`` is ``<owner>/<repo>`` of the repository the ticket lives in
    (issue-183): the daemon passes the work item's own, and an in-session caller
    passes nothing, in which case the checkout's ``origin`` remote is asked
    (issue-352). Empty when neither knows — callers then fail closed rather than
    derive a ref for the wrong repository.

    ``pr_number`` selects the **inner** loop (issue-172): the runtime then walks
    ``pdlc-pr-loop`` with its state under the work item's
    ``pr-loops/pr-<n>/``, while every artifact gate still resolves against the
    work item's one spec chain. ``None`` — the default, and every caller before
    issue-172 — is the outer ``pdlc-work-item-loop``.

    ``pr_repo`` qualifies that pull request by repository (issue-183), for a
    work item whose contributions span several: the state then lives at
    ``pr-loops/<owner>__<repo>/pr-<n>/``, still under the ONE spec directory in
    the origin repository.

    ``loop`` names the **outer-path** graph to walk: the contribution loop
    (issue-185), for a work item the-loop joins as a contributor rather than
    owns, or the ad-hoc loop (issue-225), for a tactical task that runs no PDLC
    process. Meaningless with ``pr_number`` (a pull request's loop is always
    ``pdlc-pr-loop``). Only ``OUTER_PATH_LOOPS`` names are honoured — the value
    can originate in the agent-writable ``graph-state.json``, so anything else
    falls back to the default outer loop with a warning rather than reaching
    ``load_graph``.
    """
    from ..ghhost import github_host
    from ..ghhost import origin_repo as origin_of
    from .extensions import read_declaration
    from .hooks.loops import inner_loop_state_dir
    from .model import (
        GUEST_LOOPS,
        OUTER_PATH_LOOPS,
        PDLC_PR_LOOP,
        PDLC_WORK_ITEM_LOOP,
        load_graph,
    )
    from .runtime import Runtime

    cli_cfg = load_cli_config_best_effort()
    chosen = loop or PDLC_WORK_ITEM_LOOP
    if pr_number is None and chosen not in OUTER_PATH_LOOPS:
        # Fail closed to the default: `loop` can come from the agent-writable
        # state file, and an invented name must never choose the graph — nor
        # may the inner loop be addressed without the pr-loops state layout.
        # `OUTER_PATH_LOOPS` says both in one membership test (issue-225).
        logger.warning(
            "ignoring unknown outer loop %r; walking %s", chosen, PDLC_WORK_ITEM_LOOP
        )
        chosen = PDLC_WORK_ITEM_LOOP
    config: Dict[str, Any] = {
        "authorizedUsers": list(authorized_users or []),
        "integrations": cli_cfg.get("integrations") or {},
        # Whether this walk is a GUEST's (issue-185, issue-279; re-based in
        # issue-352). A contribution or a review joins a repository the-loop
        # does not own, and its machinery stays out of that repository's
        # history: the spec tree is kept out of git (`Runtime.start`) and the
        # plan is posted to the thread (`publish-artifact`), because the
        # repository offers no place to review a checked-in artifact. Until
        # issue-352 this was "has the repository adopted the-loop?", read from
        # its harness config — a file the CLI no longer opens.
        "guestLoop": pr_number is None and chosen in GUEST_LOOPS,
        # Which repository the ticket lives in (issue-183) — the origin
        # repository, where the outer loop runs and every inner loop's state is
        # kept. The caller's word first (the daemon knows the work item), the
        # checkout's `origin` remote second, unknown last.
        "originRepo": origin_repo or origin_of(root),
        # Which GitHub a ref minted here lives on (issue-311): the one resolver's
        # answer, taken once per runtime so `derive_ref` and `prRef` below agree
        # with every link and every `gh` call downstream of the ref. Resolved
        # with this checkout at hand, because in-session the origin remote is
        # `gh`'s own answer; a daemon passes no root and stops at its config.
        "githubHost": github_host(cli_cfg, repo_root=root),
        # The channels layer (issue-245): the `notify` hook broadcasts through
        # it, and the Slack channel's thread bindings live under `state.root` —
        # both must reach hooks or a graph notification would silently go to a
        # default state root instead of the operator's.
        "channels": cli_cfg.get("channels") or {},
        "state": cli_cfg.get("state") or {},
    }
    routing = cli_cfg.get("routing") or {}
    if not isinstance(routing, dict):
        routing = {}
    keywords = ((routing.get("control") or {}).get("keywords")) or {}
    if keywords.get("execute") is not None:
        # The `execute` keyword is operator-configurable like every other
        # control word (issue-177, owner review): the phase-selection gate must
        # look for what THIS deployment declared, not a constant.
        config["executeKeyword"] = str(keywords["execute"])
    # The DEFAULT the same gate offers for "how many sessions do this work
    # item's pull requests get?" (issue-260). The operator states it once,
    # per deployment; the checklist renders it pre-ticked, and the work item
    # overrides it or leaves it alone. Resolved here — legacy booleans and
    # typos included — so the checklist and the daemon read one vocabulary.
    from ..prsessions import session_per_pr_mode

    config["sessionPerPr"] = session_per_pr_mode(
        (routing.get("tmux") or {}).get("sessionPerPr")
    )
    if authorized_users is None and cli_cfg:
        # The `github` projection of the person entries (issue-309): the
        # gates read logins, whatever else an entry declares.
        from ..authz import resolve_authorized_users

        config["authorizedUsers"] = resolve_authorized_users(
            routing.get("authorizedUsers") or []
        )
    # The operator's own graph hooks (issue-248, issue-352): declared once in
    # the CLI config, parsed once here, applied to every runtime this function
    # builds — a machine that ran them on one ingress and not another would run
    # code on a path the operator thought they had closed.
    declaration = read_declaration(cli_cfg)
    resolved_spec_root = resolve_spec_root(cli_cfg, spec_root or "")
    if pr_number is not None:
        # One expression of the layout, shared with the hook that reads it back
        # (`await-inner-loops`) and with the repo-name validation it carries —
        # two copies of a path literal is how they came to disagree elsewhere.
        subpath = inner_loop_state_dir(Path(), pr_number, pr_repo).as_posix()
        # The ref an inner loop's hooks post to, when the caller passed none
        # (issue-194). It is the PULL REQUEST's, built here because this is the
        # only place that knows which pull request this runtime walks — and it
        # must never fall back to the work item's own ref, which would put a
        # pull request's review comments on the ticket.
        from .refs import ref_for

        config["prRef"] = ref_for(
            pr_repo or config["originRepo"], pr_number, host=config["githubHost"]
        )
        return Runtime(
            root,
            graph=load_graph(repo=root, name=PDLC_PR_LOOP, declaration=declaration),
            spec_root=resolved_spec_root,
            config=config,
            state_subpath=subpath,
        )
    return Runtime(
        root,
        graph=load_graph(repo=root, name=chosen, declaration=declaration),
        spec_root=resolved_spec_root,
        config=config,
    )
