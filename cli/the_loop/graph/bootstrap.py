"""Assembling a :class:`Runtime` from the configs on disk.

Extracted from ``commands/graph_cmd.py`` when the ingress gained a second call
site (issue-113). It matters that there is only one of these: the runtime's
``config`` is what carries ``authorizedUsers`` to ``classify-feedback``, and a
second, subtly different assembly is how a gate ends up reading an empty
authorized-user list and failing closed forever on one path while working on the
other.

Both configs are read best-effort — a missing or malformed one yields defaults
rather than an error, because ``the-loop check`` must work in a repo that has
never seen the CLI config, and the daemon must work in a checkout that has no
harness config.

The harness half is read through :mod:`the_loop.harness_config`, the CLI's only
reader of that file (issue-121, decision-044). ``load_harness_config`` stays
exported here because it is this package's established name for it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .. import harness_config
from ..harness_config import load as load_harness_config

logger = logging.getLogger("the-loop.graph")

__all__ = ["build_runtime", "load_harness_config"]


def build_runtime(
    root: Path,
    spec_root: Optional[str] = None,
    authorized_users: Optional[Sequence[str]] = None,
    pr_number: Optional[int] = None,
    pr_repo: str = "",
    loop: str = "",
):
    """A runtime for ``root``, configured from the harness and CLI configs.

    Both overrides exist, for **different** reasons — a distinction worth keeping
    apart, because stating one reason for both is what produced issue-123:

    * ``authorized_users`` is a **CLI-config** value. The daemon has already parsed its
      own CLI config, honouring ``--config``, so re-reading the default path here could
      disagree with the config the process is actually running. It passes what it parsed.
    * ``spec_root`` is a **harness-config** value, read from ``root`` itself. There is no
      ``--config`` ambiguity to protect against, so the repository's own
      ``workflow.specDir`` is the answer unless a caller deliberately overrides it —
      ``routing.graph.specDir``, for a checkout that carries no harness
      config. Until issue-123 that key was never unset, so this fall-through was
      unreachable on the daemon path and no watched repository's value was ever honoured.

    ``pr_number`` selects the **inner** loop (issue-172): the runtime then walks
    ``pdlc-pr-loop`` with its state under the work item's
    ``pr-loops/pr-<n>/``, while every artifact gate still resolves against the
    work item's one spec chain. ``None`` — the default, and every caller before
    issue-172 — is the outer ``pdlc-work-item-loop``.

    ``pr_repo`` qualifies that pull request by repository (issue-183), for a
    work item whose contributions span several: the state then lives at
    ``pr-loops/<owner>__<repo>/pr-<n>/``, still under the ONE spec directory in
    the origin repository. ``""`` — the default, and every caller before
    issue-183 — means the pull request is in the origin repository and keeps the
    shipped path.

    ``loop`` names the **outer-path** graph to walk: the contribution loop
    (issue-185), for a work item the-loop joins as a contributor rather than
    owns, or the ad-hoc loop (issue-225), for a tactical task that runs no PDLC
    process. Meaningless with ``pr_number`` (a pull request's loop is always
    ``pdlc-pr-loop``). Only ``OUTER_PATH_LOOPS`` names are honoured — the value
    can originate in the agent-writable ``graph-state.json``, so anything else
    falls back to the default outer loop with a warning rather than reaching
    ``load_graph``.
    """
    from .hooks.loops import inner_loop_state_dir
    from .model import OUTER_PATH_LOOPS, PDLC_PR_LOOP, PDLC_WORK_ITEM_LOOP, load_graph
    from .runtime import Runtime

    harness = load_harness_config(root)
    workflow = harness.get("workflow") or {}
    config: Dict[str, Any] = {
        "phaseLabelPrefix": workflow.get("phaseLabelPrefix", "loop:"),
        "notifications": harness.get("notifications") or {},
        "authorizedUsers": list(authorized_users or []),
        "integrations": {},
        # Whether this repository has adopted the-loop at all (issue-185, PR #187
        # review). A contribution can join a repository that never ran setup:
        # every key above already degrades to a default, but the *distinction*
        # drives behaviour of its own — an uninitialized repository's spec tree
        # is kept out of git (`Runtime.start`) and its plan is posted to the
        # thread (`publish-artifact`), because the repository offers no place to
        # review a checked-in artifact.
        "repoInitialized": harness_config.initialized(root),
        # Which repository the ticket lives in (issue-183) — the origin
        # repository, where the outer loop runs and every inner loop's state is
        # kept. A fact about this repository, and one a daemon watching N of
        # them cannot know for each. (Where the outer loop is *collaborated on*
        # is deliberately NOT here: that is the work item's own choice, frozen
        # at `phase-selection` — owner's call on PR #184.)
        "originRepo": harness_config.origin_repo(harness),
    }
    try:
        from .. import cli_config

        cli_cfg = cli_config.load_cli_config(cli_config.default_cli_config_path()) or {}
    except Exception:  # noqa: BLE001 — the CLI config is optional for `check`
        cli_cfg = {}
    if isinstance(cli_cfg, dict):
        config["integrations"] = cli_cfg.get("integrations") or {}
        # The channels layer (issue-245): the `notify` hook broadcasts through
        # it, and the Slack channel's thread bindings live under `state.root` —
        # both must reach hooks or a graph notification would silently go to a
        # default state root instead of the operator's.
        config["channels"] = cli_cfg.get("channels") or {}
        config["state"] = cli_cfg.get("state") or {}
        # The `execute` keyword is operator-configurable like every other
        # control word (issue-177, owner review): the phase-selection gate must
        # look for what THIS deployment declared, not a constant.
        routing = ((cli_cfg.get("webhooks") or {}).get("ghWebhook") or {}).get(
            "routing"
        ) or {}
        keywords = ((routing.get("control") or {}).get("keywords")) or {}
        if keywords.get("execute") is not None:
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
        if authorized_users is None:
            config["authorizedUsers"] = routing.get("authorizedUsers") or []
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

        config["prRef"] = ref_for(pr_repo or config["originRepo"], pr_number)
        return Runtime(
            root,
            graph=load_graph(repo=root, name=PDLC_PR_LOOP),
            spec_root=str(spec_root or harness_config.spec_dir(harness)),
            config=config,
            state_subpath=subpath,
        )
    chosen = loop or PDLC_WORK_ITEM_LOOP
    if chosen not in OUTER_PATH_LOOPS:
        # Fail closed to the default: `loop` can come from the agent-writable
        # state file, and an invented name must never choose the graph — nor
        # may the inner loop be addressed without the pr-loops state layout.
        # `OUTER_PATH_LOOPS` says both in one membership test (issue-225).
        logger.warning(
            "ignoring unknown outer loop %r; walking %s", chosen, PDLC_WORK_ITEM_LOOP
        )
        chosen = PDLC_WORK_ITEM_LOOP
    return Runtime(
        root,
        graph=load_graph(repo=root, name=chosen),
        spec_root=str(spec_root or harness_config.spec_dir(harness)),
        config=config,
    )
