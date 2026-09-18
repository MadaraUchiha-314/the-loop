"""One configured root for everything the-loop's CLI generates, organised by
what the files *are* (issue-106, issue-128).

Before issue-106, each generated file carried its own default path — the session
registry at ``.the-loop/sessions``, the poll state at
``.the-loop/poll-state.json``, the event log at ``.the-loop/logs/events.jsonl``,
the receiver pidfile at ``.the-loop/gh-webhook.pid``. Four defaults, four places
to change, and no single directory an operator could back up, relocate or wipe.
``state.root`` became that directory.

Issue-128 asked the next question — *which of it can I carry to another
machine?* — and the answer reorganised the layout. The old one grouped files by
**who wrote them** (registry / control / poller), which is why there were three
shapes, a nested ``control/`` directory and a ``.gitignore`` recipe that needed
two negations to express one idea. This one groups them by **what they are**:

===================  =========================================  ==========
portable state       ``<root>/portable/<slug>.json``            travels
session handles      ``<root>/local/<slug>.json``               local
event log            ``<root>/logs/events.jsonl``               local
poller log           ``<root>/logs/poller.out``                 local
receiver pidfile     ``<root>/gh-webhook.pid``                  local
poller pidfile       ``<root>/poll.pid``                        local
poller heartbeat     ``<root>/poll-status.json``                local
===================  =========================================  ==========

One file per work item on each side. ``portable/`` holds what an authorized user
armed **and** what the poller has already seen — facts about the world, true
whoever runs the daemon, and not derivable from GitHub. ``local/`` holds the
handle to a harness conversation on *this* machine. So "track the portable
half" is one directory, and two machines conflict only if they worked the same
work item (the old single ``poll-state.json`` guaranteed a conflict).

**Defaults only.** ``routing.registryDir`` still overrides the local directory
verbatim. ``polling.stateFile`` is gone (a file where there is now a directory);
:mod:`the_loop.migrations` retires it loudly rather than ignoring it.

Upgrades never lose state: :data:`LegacyLayout` records where each store used to
live, and the stores read the old location when the new record has no such
section yet, so the first run after an upgrade neither re-baselines a watched
thread nor forgets what was armed. Writes always go to the new layout.

Spec: docs/specs/issue-106/design.md §5, docs/specs/issue-128/design.md §2, §9.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("the-loop.state")

__all__ = [
    "ATTRIBUTES",
    "ATTRIBUTE_KINDS",
    "Attribute",
    "DEFAULT_STATE_ROOT",
    "MACHINE_FILE",
    "OPERATOR_FILE",
    "REPOSITORY_FILE",
    "GENERATED_PATHS",
    "GeneratedPath",
    "LegacyLayout",
    "StateLayout",
    "layout_from_config",
    "legacy_layout",
    "rival_roots",
]

DEFAULT_STATE_ROOT = ".the-loop"


@dataclass(frozen=True)
class StateLayout:
    """The generated-file layout under one root directory."""

    root: str = DEFAULT_STATE_ROOT

    @property
    def root_path(self) -> Path:
        return Path(self.root or DEFAULT_STATE_ROOT)

    @property
    def portable_dir(self) -> str:
        """Work-item records: control + poll state, one file per work item."""
        return str(self.root_path / "portable")

    @property
    def portable_index(self) -> str:
        """The portable directory's index — derived, rewritten on every record write."""
        return str(self.root_path / "portable" / "index.json")

    @property
    def local_dir(self) -> str:
        """Session records — handles to harness conversations on this machine."""
        return str(self.root_path / "local")

    @property
    def verdict_cache(self) -> str:
        """Availability verdicts: which models and effort levels each harness on
        THIS machine will actually accept (issue-358). Machine-local by
        construction — a verdict is a fact about this box's harness installation,
        so it never travels in a repository and is never agent-writable."""
        return str(self.root_path / "local" / "model-verdicts.json")

    @property
    def event_log(self) -> str:
        return str(self.root_path / "logs" / "events.jsonl")

    @property
    def pidfile(self) -> str:
        return str(self.root_path / "gh-webhook.pid")

    @property
    def poll_pidfile(self) -> str:
        """The poller's pidfile — and the single-instance lock held on it (issue-159)."""
        return str(self.root_path / "poll.pid")

    @property
    def poll_status(self) -> str:
        """The poller's heartbeat: when it started, and what its last cycle did."""
        return str(self.root_path / "poll-status.json")

    @property
    def poller_log(self) -> str:
        """Where a daemonized poller's stdout/stderr go (issue-191)."""
        return str(self.root_path / "logs" / "poller.out")

    @property
    def self_diagnosis(self) -> str:
        """What self-diagnosis has already reported/abandoned (issue-242)."""
        return str(self.root_path / "self-diagnosis.json")

    @property
    def channels_dir(self) -> str:
        """Channel conversation state — thread bindings + read cursors (issue-245)."""
        return str(self.root_path / "channels")

    @property
    def standing_dir(self) -> str:
        """Standing-session records — one per declared name (issue-277).

        Under ``local/`` because it is the same kind of thing as a session
        record and for the same reason: a conversation id, a tmux name and a
        directory that exist on one machine. In its own subdirectory rather than
        beside the work-item records, because the two namespaces are separate by
        design — a standing session is addressed by name, never by ref.
        """
        return str(self.root_path / "local" / "standing")


@dataclass(frozen=True)
class LegacyLayout:
    """Where the stores lived before issue-128 split them by portability.

    Read-only, and read only when the new record has no such section: the stores
    consult it so an upgrade neither re-baselines every watched thread nor
    forgets what an authorized user armed. Nothing writes here any more, so a
    work item converges on the new layout the first time it is touched — and an
    operator can delete the old paths once ``the-loop sessions list`` looks
    right. Deliberately not part of :class:`StateLayout`: these are not paths
    the-loop generates, they are paths it *remembers*.
    """

    sessions_dir: str  # <root>/sessions/       — session records
    control_dir: str  # <root>/sessions/control/ — control records
    poll_state: str  # <root>/sessions/poll-state.json
    pre_106_poll_state: str = ".the-loop/poll-state.json"


def legacy_layout(layout: StateLayout) -> LegacyLayout:
    """The pre-issue-128 locations under the same root."""
    sessions = layout.root_path / "sessions"
    return LegacyLayout(
        sessions_dir=str(sessions),
        control_dir=str(sessions / "control"),
        poll_state=str(sessions / "poll-state.json"),
    )


@dataclass(frozen=True)
class GeneratedPath:
    """One thing the CLI writes, and whether it means anything on another machine.

    ``why`` is not decoration. An entry whose author cannot say *why* it is local
    has probably put a machine handle inside something that is otherwise a fact
    about the world — which is the mistake this declaration exists to catch,
    while the path is being invented and the answer is still cheap.
    """

    name: str  # human label, used in prose and test failures
    attr: str  # the StateLayout property this derives from
    default: str  # the documented path, e.g. "<root>/local/<slug>.json"
    portable: bool  # does it mean anything on another machine?
    holds: str
    why: str


#: Every generated path, classified (issue-128, decision-046). Inert data: nothing
#: reads it at runtime. It is pinned by ``cli/tests/test_state_portability.py``,
#: which fails when :class:`StateLayout` grows a path no entry claims — so a new
#: generated file cannot be added without answering "does this travel?" — and when
#: ``docs/cli/state.md`` classifies one differently.
GENERATED_PATHS: Tuple[GeneratedPath, ...] = (
    GeneratedPath(
        name="work-item record",
        attr="portable_dir",
        default="<root>/portable/<slug>.json",
        portable=True,
        holds=(
            "control (the last start|stop|pause|resume, its actor and time) and "
            "poll (seenComments, commentAttempts, the spawn ledger, lastPolledAt)"
        ),
        why=(
            "statements about the work item and about what GitHub already told "
            "us — true whoever runs the daemon. Neither is derivable upstream: "
            "nothing on GitHub records that a stop was honoured, and a machine "
            "without the poll half treats every watched thread as first-sight."
        ),
    ),
    GeneratedPath(
        name="work-item index",
        attr="portable_index",
        default="<root>/portable/index.json",
        portable=True,
        holds=(
            "one entry per record beside it: ref, url, file name, which sections "
            "it holds"
        ),
        why=(
            "it describes portable records, so it travels with them or describes "
            "a directory that is not there. Derived on every write and read by "
            "nothing, so a copy is never wrong for long and two machines "
            "conflicting on it may resolve to either side."
        ),
    ),
    GeneratedPath(
        name="model availability verdicts",
        attr="verdict_cache",
        default="<root>/local/model-verdicts.json",
        portable=False,
        holds=(
            "one verdict per (harness, model-or-effort name): ok, refused or "
            "unknown, the argv it was taken against, and when it was taken "
            "(issue-358)"
        ),
        why=(
            "a fact about THIS machine's harness installation and this account's "
            "model access, not about the work. Copied elsewhere it would withhold "
            "a model another box can run perfectly well, or offer one it cannot — "
            "and it is re-measurable in a second, so there is nothing to carry. "
            "Machine-local also keeps it out of reach of an agent session, which "
            "matters because a verdict can only ever WITHHOLD a declared choice"
        ),
    ),
    GeneratedPath(
        name="session record",
        attr="local_dir",
        default="<root>/local/<slug>.json",
        portable=False,
        holds=(
            "harnessSessionId, cwd, runner, tmuxTarget, status, recentDeliveries, "
            "and (issue-172) pullRequests — every PR delivering this work item "
            "with its own tmux session and conversation. One file per work item"
        ),
        why=(
            "a handle to a conversation and a directory that exist on one machine. "
            "Copied elsewhere it is not merely useless: find_by_work_item counts it "
            "as live, so the duplicate guard refuses the spawn the new machine needs "
            "and events are routed to a conversation that is not there. It also "
            "carries an absolute path from the operator's filesystem and a resumable "
            "session id, neither of which belongs in a repository."
        ),
    ),
    GeneratedPath(
        name="event log",
        attr="event_log",
        default="<root>/logs/events.jsonl",
        portable=False,
        holds="one JSON object per line: every accept, drop, route, spawn, failure",
        why=(
            "a record of what this machine did, appended to continuously. Two machines "
            "appending to one tracked file conflict on every line, and the trail is "
            "read where it was written."
        ),
    ),
    GeneratedPath(
        name="receiver pidfile",
        attr="pidfile",
        default="<root>/gh-webhook.pid",
        portable=False,
        holds="the pid of the running gh-webhook receiver",
        why="a process id is meaningless on another host, and stale within a reboot.",
    ),
    GeneratedPath(
        name="poller pidfile",
        attr="poll_pidfile",
        default="<root>/poll.pid",
        portable=False,
        holds="the pid of the running poller — and the lock proving it is the only one",
        why=(
            "a process id is meaningless on another host, and stale within a reboot. "
            "It is also the flock the single-instance guard is held on (issue-159), "
            "which the kernel releases with the process — a fact about this machine "
            "and nothing else."
        ),
    ),
    GeneratedPath(
        name="poller heartbeat",
        attr="poll_status",
        default="<root>/poll-status.json",
        portable=False,
        holds=(
            "startedAt, lastCycleAt and the last cycle's counters — what "
            "`the-loop status` reports beyond liveness. No pid: naming the "
            "process is the pidfile lock's job (issue-205)"
        ),
        why=(
            "clock readings from one machine's poller. Carried elsewhere they describe "
            "a process that is not there — and it is never the source of truth for "
            "liveness anyway (that is the lock), so a copy answers nothing."
        ),
    ),
    GeneratedPath(
        name="poller log",
        attr="poller_log",
        default="<root>/logs/poller.out",
        portable=False,
        holds="a daemonized poller's stdout and stderr, appended to continuously",
        why=(
            "the same reason as the event log: two machines appending to one tracked "
            "file conflict on every line, and the output is read where it was written. "
            "Rotation is the host's job (logrotate), so it also grows without bound."
        ),
    ),
    GeneratedPath(
        name="self-diagnosis ledger",
        attr="self_diagnosis",
        default="<root>/self-diagnosis.json",
        portable=False,
        holds=(
            "which failure fingerprints this machine already reported (with the "
            "issue URL), abandoned, or is still retrying, and when it last posted "
            "(the rolling daily cap) — issue-242"
        ),
        why=(
            "a record of what THIS machine's event log already produced. Carried to "
            "another machine it would suppress reports for failures that machine "
            "never diagnosed — its log is different — and the sibling .lock file "
            "guarding concurrent scans is kernel state that cannot travel at all."
        ),
    ),
    GeneratedPath(
        name="standing-session record",
        attr="standing_dir",
        default="<root>/local/standing/<name>.json",
        portable=False,
        holds=(
            "per standing session (issue-277): harness, harnessSessionId, cwd, "
            "tmuxTarget, status, and the Slack channel/thread its chat runs in"
        ),
        why=(
            "the same machine handles the work-item session record carries — a "
            "resumable conversation id, a tmux session name and an absolute path "
            "— for a session that is not even nominally about a shared work item. "
            "Copied elsewhere, `standing start` would resume a conversation that "
            "does not exist there and bind replies to a thread its bot never "
            "posted."
        ),
    ),
    GeneratedPath(
        name="channel conversation state",
        attr="channels_dir",
        default="<root>/channels/<channel>.json",
        portable=False,
        holds=(
            "per channel type: thread bindings (which Slack thread carries which "
            "work item's conversation) and per-thread read cursors (the last "
            "reply THIS deployment mirrored and delivered) — issue-245"
        ),
        why=(
            "handles into one deployment's conversations, and a ledger of what it "
            "already processed. Carried elsewhere the cursors would suppress "
            "replies the other machine never mirrored, and the thread ids name "
            "conversations its bot may not even be a member of. It also names "
            "Slack member and channel ids, which do not belong in a repository."
        ),
    ),
)


#: The three files that hold something about ONE work item, and who owns what
#: is in them (issue-368). ``GENERATED_PATHS`` above answers "does this *file*
#: travel?"; this answers the question that had no answer at all — "where does
#: this *attribute* go?" — which is why attributes drifted: a pull request was
#: recorded only in a file that never travels, a Slack thread only in a
#: machine-wide one, and a harness session id was checked into a repository.
#:
#: The rule is the **party** each fact belongs to, because who may write a file
#: decides what may be in it:
REPOSITORY_FILE = "docs/specs/<id>/work-item-state.json"
OPERATOR_FILE = "<root>/portable/<slug>.json"
MACHINE_FILE = "<root>/local/<slug>.json"

#: What kind of thing an attribute is, and the one file each kind may live in.
#: A kind is not a category for its own sake: it is the argument for the file.
ATTRIBUTE_KINDS: Dict[str, Tuple[str, str]] = {
    "pointer": (
        REPOSITORY_FILE,
        "where the graph stands. Must survive a machine change, a session "
        "change and a multi-day human review, and be reviewable in a diff; "
        "re-derived from the artifacts, so a stale copy costs a recompute "
        "(decision-041).",
    ),
    "human-decision": (
        REPOSITORY_FILE,
        "a choice an authorized human froze about this work item. A "
        "declaration with provenance, honoured only within what the compiled "
        "graph and the operator's config allow (issue-177's rule).",
    ),
    "repository-entity": (
        REPOSITORY_FILE,
        "something that exists upstream in a REPOSITORY because of this work "
        "item — a pull request, its inner loop. The repository's branch may "
        "name it, and `the-loop check` in CI must see it without a registry.",
    ),
    "workspace-entity": (
        OPERATOR_FILE,
        "something that exists in the OPERATOR's workspace because of this "
        "work item — a channel thread. Its identifiers are the operator's "
        "(channel id, member id, permalink) and must not enter a repository; "
        "it must also outlive the checkout, which `cleanup` removes.",
    ),
    "operator-ledger": (
        OPERATOR_FILE,
        "what an authorized human told this deployment, or what it has "
        "already seen: armed, the roster, seen comments, the closure. "
        "Proposable by nobody but an authorized human, and needed after the "
        "checkout is gone.",
    ),
    "machine-handle": (
        MACHINE_FILE,
        "a conversation id, a tmux name, a path, a read cursor: useless or "
        "harmful anywhere else (decision-046).",
    ),
    "derived": (
        "",
        "rebuilt from its sources on every write and read to gate nothing, so "
        "a stale copy is cosmetic (decision-047). Lives wherever its reader "
        "is.",
    ),
}


@dataclass(frozen=True)
class Attribute:
    """One top-level key of one per-work-item file, and why it is there."""

    file: str  # one of the three constants above
    key: str  # the key as it is written
    kind: str  # a key of ATTRIBUTE_KINDS
    holds: str


#: Every top-level key the three files carry. Inert data, like
#: ``GENERATED_PATHS``: nothing reads it at runtime. It is pinned by
#: ``cli/tests/test_state_portability.py``, which fails when a file grows a key
#: no entry claims, when an entry names a kind the rule does not allow in that
#: file, and when ``docs/cli/state.md`` and this declaration disagree — so the
#: next attribute cannot be added without answering "whose is this?".
ATTRIBUTES: Tuple[Attribute, ...] = (
    # -- the repository's file ------------------------------------------------
    Attribute(REPOSITORY_FILE, "version", "derived", "the file's shape"),
    Attribute(REPOSITORY_FILE, "workItem", "pointer", "which work item this is"),
    Attribute(REPOSITORY_FILE, "loop", "pointer", "which shipped loop it walks"),
    Attribute(
        REPOSITORY_FILE,
        "phase",
        "pointer",
        "the phase the walk is in — what the `loop:<phase>` label says (issue-378)",
    ),
    Attribute(REPOSITORY_FILE, "currentNode", "pointer", "where the pointer is"),
    Attribute(
        REPOSITORY_FILE,
        "nodes",
        "pointer",
        "per node: attempts, outcome, entered/exited, the last block, forced",
    ),
    Attribute(
        REPOSITORY_FILE, "completions", "pointer", "the claims sessions have made"
    ),
    Attribute(REPOSITORY_FILE, "parked", "pointer", "the gate it is waiting at"),
    Attribute(
        REPOSITORY_FILE, "forced", "human-decision", "every forced move, audited"
    ),
    Attribute(
        REPOSITORY_FILE,
        "decisions",
        "human-decision",
        "each gate's outcome with its provenance",
    ),
    Attribute(
        REPOSITORY_FILE, "skips", "human-decision", "declared skips with provenance"
    ),
    Attribute(REPOSITORY_FILE, "optIns", "human-decision", "selected opt-in phases"),
    Attribute(
        REPOSITORY_FILE,
        "surface",
        "human-decision",
        "where the outer loop is iterated (issue-183)",
    ),
    Attribute(
        REPOSITORY_FILE,
        "sessionPerPr",
        "human-decision",
        "how many sessions its pull requests get (issue-260)",
    ),
    Attribute(
        REPOSITORY_FILE, "model", "human-decision", "what it runs on (issue-358)"
    ),
    Attribute(
        REPOSITORY_FILE, "effort", "human-decision", "at what effort (issue-358)"
    ),
    Attribute(
        REPOSITORY_FILE,
        "repos",
        "human-decision",
        "the repositories it contributes to (issue-183, issue-365)",
    ),
    Attribute(
        REPOSITORY_FILE,
        "pullRequests",
        "repository-entity",
        "each pull request delivering it: ref, repository, number, url, "
        "inner-loop directory, upstream state, when and by whom it was linked",
    ),
    # -- the operator's file --------------------------------------------------
    Attribute(OPERATOR_FILE, "ref", "operator-ledger", "which work item this is"),
    Attribute(OPERATOR_FILE, "url", "derived", "the same fact as a link"),
    Attribute(
        OPERATOR_FILE,
        "control",
        "operator-ledger",
        "the last start|stop|pause|resume|cleanup, who asked, when, which instance",
    ),
    Attribute(
        OPERATOR_FILE,
        "poll",
        "operator-ledger",
        "seen comments, the retry ledgers, the spawn ledger, when it was last "
        "listed, the cached title",
    ),
    Attribute(
        OPERATOR_FILE,
        "pullRequests",
        "operator-ledger",
        "the same poll ledger for each pull request delivering it, keyed by "
        "ref — so one work item is one record (issue-368)",
    ),
    Attribute(
        OPERATOR_FILE,
        "collaborators",
        "operator-ledger",
        "who an authorized user invited onto this work item",
    ),
    Attribute(
        OPERATOR_FILE,
        "collaborationChannels",
        "operator-ledger",
        "the channels an authorized user declared this work item is worked in "
        "(issue-375) — the operator's workspace's ids, and a statement only an "
        "authorized human can make",
    ),
    Attribute(
        OPERATOR_FILE,
        "ended",
        "operator-ledger",
        "the item ended upstream: state, kind, reason, when, which ingress, who",
    ),
    Attribute(
        OPERATOR_FILE,
        "channels",
        "workspace-entity",
        "per channel type: the thread carrying this work item's conversation, "
        "when and how it opened, and its permalink",
    ),
    Attribute(
        OPERATOR_FILE,
        "graph",
        "derived",
        "RETIRED (issue-368): the frozen selection, read for a work item frozen "
        "before the change and never written again",
    ),
    Attribute(
        OPERATOR_FILE,
        "sealed",
        "derived",
        "a tombstone kept while a pre-issue-128 tree still holds something",
    ),
    # -- the machine's file ---------------------------------------------------
    Attribute(MACHINE_FILE, "version", "derived", "the record's shape"),
    Attribute(MACHINE_FILE, "workItem", "machine-handle", "whose sessions these are"),
    Attribute(
        MACHINE_FILE,
        "sessions",
        "machine-handle",
        "one entry per ref this machine holds a session for — the work item's "
        "own and one per pull request: harness, conversation id, cwd, tmux "
        "target, status, recent deliveries, and what it was launched as",
    ),
    Attribute(
        MACHINE_FILE,
        "channels",
        "machine-handle",
        "per channel type: the last reply THIS deployment mirrored in each "
        "thread bound to the work item",
    ),
)


def layout_from_config(config: Optional[dict]) -> StateLayout:
    """Read ``state.root`` from a loaded CLI config (best-effort, never raises).

    A config that came through :func:`the_loop.cli_config.load_cli_config` carries an
    **absolute** root, anchored on the config file (issue-339): every process that reads
    that file resolves the same directory, whatever its working directory. A mapping
    built by hand — a test's literal, an SDK caller's dict — has no file to anchor on and
    keeps the relative default it always had.
    """
    state = ((config or {}).get("state")) or {}
    root = str(state.get("root") or "").strip()
    return StateLayout(root=root or DEFAULT_STATE_ROOT)


def rival_roots(layout: StateLayout) -> Tuple[str, ...]:
    """Other directories that also hold a poller heartbeat (issue-339, R4.2).

    The two candidates are the branches
    :func:`the_loop.cli_config.default_cli_config_path` can fall through to — ``./.the-loop``
    and ``~/.the-loop`` — which is where a pre-fix split left its second copy of the state.
    Reported, never repaired: merging, copying or deleting state is destructive and the
    operator's call. An unreadable candidate is skipped, because an observation must
    never be what makes ``status`` fail.
    """
    resolved = Path(os.path.abspath(layout.root_path))
    found = []
    for candidate in _root_candidates():
        try:
            path = Path(os.path.abspath(candidate))
            if path != resolved and (path / "poll-status.json").is_file():
                found.append(str(path))
        except OSError:  # unreadable or unstattable — not an answer we can give
            continue
    return tuple(dict.fromkeys(found))


def _root_candidates() -> Tuple[Path, ...]:
    """``./.the-loop`` and ``~/.the-loop``, skipping a home that cannot be resolved.

    ``Path.home()`` raises when the environment has no home to speak of — a systemd
    unit without ``HOME``, exactly where a daemon runs — and this is an observation, so
    it drops the candidate instead of the answer.
    """
    candidates = [Path(DEFAULT_STATE_ROOT)]
    try:
        candidates.append(Path.home() / DEFAULT_STATE_ROOT)
    except (RuntimeError, OSError):
        logger.debug("no home directory to check for a second state root")
    return tuple(candidates)
