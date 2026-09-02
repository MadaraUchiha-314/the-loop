"""The ingress → process-graph coupling (issue-113, issue-123).

The seam these tests pin down is a *bridge*, so most of them are about what it
refuses to do: skip when the work item has no spec, skip when nobody started it,
and — above all — never let a graph failure cost an event delivery.

Issue-123 added the other half: *where* it looks for that spec. The directory is
the work item's own repository's to declare (`workflow.specDir`, decision-044),
with the CLI key left as a deliberate override — so these also pin which source
wins, that the gate and the runtime resolve one value, and that a value read from
a checkout cannot point outside it.
"""

from __future__ import annotations

import json

import pytest

from the_loop import eventlog
from the_loop.control import ControlConfig, ControlStore
from the_loop.graphlink import GraphLink, GraphLinkConfig, comments_from, spec_id_for
from the_loop.sessions import WorkItemRef
from the_loop.webhook.dispatcher import RoutingConfig
from the_loop.webhook.router import RoutedEvent

REF = WorkItemRef.parse("github:octo/repo#113")


class _FakeRuntime:
    """Stands in for graph.Runtime — records calls, or raises on demand."""

    def __init__(self, raises: bool = False):
        self.started = []
        self.advanced = []
        #: ``(cwd, spec_dir)`` per runtime the link built — the seam issue-123
        #: pins: the directory handed to the runtime must be the one the skip
        #: decision was made on.
        self.built = []
        self.raises = raises

    def start(self, work_item_id, ref=""):
        if self.raises:
            raise RuntimeError("a hook exploded")
        self.started.append((work_item_id, ref))
        return None

    def advance(self, work_item_id, ref="", event=None):
        if self.raises:
            raise RuntimeError("a hook exploded")
        self.advanced.append((work_item_id, ref, event))
        return None


def _git_repo(path, origin="https://github.com/octo/repo.git"):
    """A real checkout with an origin remote, as a spawned session runs in."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", origin], check=True
    )
    return path


@pytest.fixture()
def repo(tmp_path):
    """A checkout of the work item's OWN repo — what a spawned session runs in.

    The origin remote is not decoration: the link refuses to drive a graph in a
    checkout that does not belong to the work item (issue-113 A6).
    """
    _git_repo(tmp_path)
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    return tmp_path


def _link(repo, runtime, **cfg):
    config = GraphLinkConfig(**{"enabled": True, **cfg})
    link = GraphLink(config, control=ControlConfig(enabled=False))

    def _build(cwd, spec_dir, pr_number=None, pr_repo="", loop=""):
        runtime.built.append((cwd, spec_dir))
        return runtime

    link._build_runtime = _build  # noqa: SLF001 — test seam
    return link


def _harness_config(root, spec_dir):
    """Give ``root`` a harness config declaring ``workflow.specDir``."""
    directory = root / ".the-loop"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "harness-config.yaml").write_text(
        f"workflow:\n  specDir: {spec_dir}\n", encoding="utf-8"
    )
    return root


def _events(tmp_path):
    """Configure the module-level event log at a fresh file and return its path."""
    path = tmp_path / "events.jsonl"
    eventlog.configure(source="test", path=path)
    return path


def _records(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _comment_event(body="looks good", author="octocat"):
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d1",
        work_items=[REF],
        payload={"comment": {"body": body, "user": {"login": author}}},
    )


# -- spec_id_for (T2) ------------------------------------------------------------


def test_spec_id_for_a_github_ref():
    assert spec_id_for(REF) == "issue-113"


def test_spec_id_for_another_provider_is_none():
    """Only GitHub's `issue-<n>` convention is known; guessing would be worse."""
    assert spec_id_for(WorkItemRef.parse("jira:acme/proj#42")) is None


def test_spec_id_cannot_escape_the_spec_root():
    """A5 — the id comes from a parsed int, so no ref can traverse out."""
    item_id = spec_id_for(REF)
    assert item_id is not None
    assert "/" not in item_id and ".." not in item_id


# -- comments_from (T3) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        ("issue_comment", {"comment": {"body": "b", "user": {"login": "octocat"}}}),
        (
            "pull_request_review_comment",
            {"comment": {"body": "b", "user": {"login": "octocat"}}},
        ),
        (
            "pull_request_review",
            {"review": {"body": "b", "user": {"login": "octocat"}}},
        ),
    ],
)
def test_comments_from_each_commenting_event_shape(event, payload):
    routed = RoutedEvent(
        event=event,
        action="created",
        delivery_id="d",
        work_items=[REF],
        payload=payload,
    )
    assert comments_from(routed) == [{"author": "octocat", "body": "b"}]


def test_a_comment_without_an_author_is_dropped():
    """B1 — classify-feedback filters on the author, so an unattributed body
    must never reach it; passing one with an empty author would be handing the
    gate text it cannot authorize."""
    routed = RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d",
        work_items=[REF],
        payload={"comment": {"body": "approve this", "user": {}}},
    )
    assert comments_from(routed) == []


def test_an_unrelated_event_yields_no_comments():
    routed = RoutedEvent(
        event="check_run",
        action="completed",
        delivery_id="d",
        work_items=[REF],
        payload={},
    )
    assert comments_from(routed) == []


# -- GraphLink skip paths (T4) ---------------------------------------------------


def test_a_disabled_link_does_nothing(repo):
    runtime = _FakeRuntime()
    link = _link(repo, runtime, enabled=False)
    link.on_spawn(REF, str(repo))
    link.on_event(REF, str(repo), _comment_event())
    assert runtime.started == [] and runtime.advanced == []


def test_a_work_item_with_no_spec_directory_is_still_started(tmp_path):
    """issue-273 — the outer loop's ONE required node, `phase-selection`, runs
    before any spec exists, so gating the start on `docs/specs/<id>/` routed it
    around every work item that begins life as a plain ticket. AC9's original
    reading ("no spec means the loop has not started this item") is answered by
    `_awaiting_start`, not by a directory the gated work itself creates."""
    _git_repo(tmp_path)
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime)
    link.on_spawn(REF, str(tmp_path))
    assert runtime.started == [("issue-113", REF.ref)]


def test_an_advance_still_requires_the_spec_directory(tmp_path):
    """The exemption is `start` and `context` only (issue-273). `advance` cannot be
    the first thing that happens to a work item, so a missing directory there still
    means the graph was never placed here — and this module's asymmetry (no input
    moves an unplaced work item forward) survives the fix."""
    _git_repo(tmp_path)
    runtime = _FakeRuntime()
    _link(tmp_path, runtime).on_event(REF, str(tmp_path), _comment_event())
    assert runtime.advanced == []


def test_a_non_github_ref_is_skipped(repo):
    runtime = _FakeRuntime()
    link = _link(repo, runtime)
    link.on_spawn(WorkItemRef.parse("jira:acme/proj#42"), str(repo))
    assert runtime.started == []


def test_an_item_nobody_started_is_skipped(repo):
    """AC4/A3 — otherwise every labelled-but-unstarted item in the operator's
    repos enters node one and fires its entry hooks."""
    runtime = _FakeRuntime()
    link = GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=True, require_start_command=True),
        control_store=ControlStore(repo / "control.json"),
    )
    link._build_runtime = (  # noqa: SLF001
        lambda cwd, spec_dir, pr_number=None, pr_repo="", loop="": runtime
    )
    link.on_spawn(REF, str(repo))
    link.on_event(REF, str(repo), _comment_event())
    assert runtime.started == [] and runtime.advanced == []


def test_a_started_item_is_coupled(repo):
    runtime = _FakeRuntime()
    store = ControlStore(repo / "control.json")
    store.record(REF, "start", actor="octocat")
    link = GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=True, require_start_command=True),
        control_store=store,
    )
    link._build_runtime = (  # noqa: SLF001
        lambda cwd, spec_dir, pr_number=None, pr_repo="", loop="": runtime
    )
    link.on_spawn(REF, str(repo))
    assert runtime.started == [("issue-113", REF.ref)]


# -- GraphLink behaviour (T4) ----------------------------------------------------


def test_on_spawn_starts_the_graph(repo):
    runtime = _FakeRuntime()
    _link(repo, runtime).on_spawn(REF, str(repo))
    assert runtime.started == [("issue-113", REF.ref)]


def test_on_event_advances_with_the_comment_attached(repo):
    """AC5 — the whole point: HookContext.event finally has a writer."""
    runtime = _FakeRuntime()
    _link(repo, runtime).on_event(REF, str(repo), _comment_event(body="approved"))
    assert runtime.advanced == [
        (
            "issue-113",
            REF.ref,
            {"comments": [{"author": "octocat", "body": "approved"}]},
        )
    ]


def test_on_event_without_comments_still_advances(repo):
    """A merged PR or a green check is a state change the gate may route on."""
    runtime = _FakeRuntime()
    routed = RoutedEvent(
        event="check_run",
        action="completed",
        delivery_id="d",
        work_items=[REF],
        payload={},
    )
    _link(repo, runtime).on_event(REF, str(repo), routed)
    assert runtime.advanced == [("issue-113", REF.ref, {"comments": []})]


def test_a_runtime_failure_is_swallowed(repo):
    """AC11 — hooks run lint, subprocesses and outbound HTTP; none of those
    failing is a reason to drop a delivery."""
    runtime = _FakeRuntime(raises=True)
    link = _link(repo, runtime)
    link.on_spawn(REF, str(repo))  # must not raise
    link.on_event(REF, str(repo), _comment_event())  # must not raise


# -- config (T5) -----------------------------------------------------------------


def test_routing_config_parses_the_graph_block():
    routing = RoutingConfig.from_mapping(
        {"graph": {"enabled": False, "specDir": "specs"}}, None
    )
    assert routing.graph.enabled is False
    assert routing.graph.spec_dir == "specs"


def test_the_graph_block_defaults_to_enabled():
    assert RoutingConfig.from_mapping({}, None).graph.enabled is True


@pytest.mark.parametrize("data", [{}, {"graph": {}}, {"graph": {"specDir": None}}])
def test_the_graph_block_leaves_spec_dir_unset_by_default(data):
    """R1.3 — an always-set default is what made the repository's value
    unreachable: `build_runtime` treats an explicit spec_root as an override, so
    a non-empty default meant `workflow.specDir` was never consulted."""
    assert RoutingConfig.from_mapping(data, None).graph.spec_dir == ""


# -- dispatcher call sites (T6) --------------------------------------------------


class _RecordingLink:
    def __init__(self):
        self.spawned = []
        self.events = []

    def on_spawn(self, work_item, cwd):
        self.spawned.append((work_item.ref, cwd))

    def on_event(self, work_item, cwd, routed):
        self.events.append((work_item.ref, cwd, routed.event))


def test_the_dispatcher_builds_a_graph_link_from_its_routing_config(tmp_path):
    """AC10 — built in the shared dispatcher, so both ingresses get it."""
    from the_loop.sessions import SessionRegistry
    from the_loop.webhook.dispatcher import Dispatcher

    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping({"graph": {"specDir": "specs"}}, None),
    )
    assert isinstance(dispatcher.graphlink, GraphLink)
    assert dispatcher.graphlink.config.spec_dir == "specs"


def test_a_reload_rebuilds_the_graph_link(tmp_path):
    """The coupling must be switchable without a restart, like every other
    dispatch knob a hot reload covers."""
    from the_loop.sessions import SessionRegistry
    from the_loop.webhook.dispatcher import Dispatcher

    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={},
        config=RoutingConfig.from_mapping({}, None),
    )
    assert dispatcher.graphlink.config.enabled is True
    dispatcher.reload(RoutingConfig.from_mapping({"graph": {"enabled": False}}, None))
    assert dispatcher.graphlink.config.enabled is False


# -- the checkout must belong to the work item's repo (T10) ----------------------


def test_a_checkout_of_another_repo_is_never_coupled(tmp_path):
    """AC14/A6 — `issue-15` names a *directory*, not a repository. Without this
    check, an event about ANY repo's issue #15 drives docs/specs/issue-15 in
    whatever checkout the daemon happens to sit in — which with the default
    `spawnWorkdir: "."` is the operator's own repo."""
    _git_repo(tmp_path, origin="https://github.com/someone-else/other.git")
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime)

    link.on_spawn(REF, str(tmp_path))
    link.on_event(REF, str(tmp_path), _comment_event())

    assert runtime.started == [] and runtime.advanced == []


def test_the_work_items_own_checkout_is_coupled(tmp_path):
    _git_repo(tmp_path, origin="git@github.com:octo/repo.git")
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_spawn(REF, str(tmp_path))

    assert runtime.started == [("issue-113", REF.ref)]


def test_a_checkout_with_no_origin_is_skipped(tmp_path):
    """Fail closed: an unverifiable checkout is not a matching one."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_spawn(REF, str(tmp_path))

    assert runtime.started == []


def test_a_directory_that_is_not_a_checkout_is_skipped(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_spawn(REF, str(tmp_path))

    assert runtime.started == []


# -- where the specs are: the repository decides (issue-123) ---------------------


def test_the_repositorys_spec_dir_is_honoured(tmp_path):
    """R1.1 — a daemon watches N repositories and cannot hold one layout for all
    of them; where a repository keeps its specs is its own to declare
    (decision-044)."""
    _git_repo(tmp_path)
    _harness_config(tmp_path, "specs")
    (tmp_path / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime)

    link.on_spawn(REF, str(tmp_path))

    assert runtime.started == [("issue-113", REF.ref)]
    assert runtime.built == [(str(tmp_path), "specs")]


def test_a_checkout_with_no_harness_config_uses_the_default(repo):
    """R1.2 — the overwhelmingly common case must not move."""
    runtime = _FakeRuntime()
    link = _link(repo, runtime)

    link.on_spawn(REF, str(repo))

    assert runtime.started == [("issue-113", REF.ref)]
    assert runtime.built == [(str(repo), "docs/specs")]


def test_the_cli_key_overrides_the_repositorys_value(tmp_path):
    """R1.3 — the key survives as a deliberate escape hatch (a checkout with no
    harness config whose specs are elsewhere), not as a silent default."""
    _git_repo(tmp_path)
    _harness_config(tmp_path, "specs")
    (tmp_path / "ops-specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime, spec_dir="ops-specs")

    link.on_spawn(REF, str(tmp_path))

    assert runtime.started == [("issue-113", REF.ref)]
    assert runtime.built == [(str(tmp_path), "ops-specs")]


def test_the_gate_reads_the_same_directory_the_runtime_will(tmp_path):
    """R2.1 — the skip decision and the runtime resolve **one** value. A repo
    that declares `specs` and still has an old `docs/specs` must not be gated on
    the stale one and then written to the declared one.

    Driven by an `advance`, which is the action the gate still applies to since
    issue-273; the `start` beside it pins the other half — the value threaded into
    the runtime is the declared one, so a graph that starts writes its state where
    the gate would have looked."""
    _git_repo(tmp_path)
    _harness_config(tmp_path, "specs")
    (tmp_path / "docs" / "specs" / "issue-113").mkdir(parents=True)
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime)

    link.on_event(REF, str(tmp_path), _comment_event())

    assert runtime.advanced == [], "the gate must use the declared directory"
    assert runtime.built == []

    link.on_spawn(REF, str(tmp_path))

    assert runtime.built == [(str(tmp_path), "specs")]


def test_an_unparseable_harness_config_falls_back_to_the_default(repo):
    """A repository someone is halfway through editing still gets its graph
    driven — `harness_config.load` degrades to `{}` and the default applies."""
    (repo / ".the-loop").mkdir(parents=True, exist_ok=True)
    (repo / ".the-loop" / "harness-config.yaml").write_text("workflow: [unclosed\n")
    runtime = _FakeRuntime()
    link = _link(repo, runtime)

    link.on_spawn(REF, str(repo))

    assert runtime.built == [(str(repo), "docs/specs")]


@pytest.mark.parametrize("declared", ["../elsewhere", "/etc", "docs/../../escape"])
def test_a_spec_dir_that_escapes_the_checkout_is_refused(tmp_path, declared):
    """R4.3 — the value now comes from a repository, so it must not be able to
    select a write target elsewhere on the operator's machine."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git_repo(checkout)
    _harness_config(checkout, declared)
    (tmp_path / "elsewhere" / "issue-113").mkdir(parents=True)
    (tmp_path / "escape" / "issue-113").mkdir(parents=True)
    events = _events(tmp_path)
    runtime = _FakeRuntime()
    link = _link(checkout, runtime)

    link.on_spawn(REF, str(checkout))

    assert runtime.started == [] and runtime.built == []
    skipped = [r for r in _records(events) if r["event"] == "graph.skipped"]
    assert [r["reason"] for r in skipped] == ["spec-dir-outside-checkout"]
    assert [r["spec_dir"] for r in skipped] == [declared], (
        "the record must name the refused value — a refusal whose value the "
        "operator cannot see is one they cannot fix"
    )


def test_a_foreign_checkouts_harness_config_is_never_read(tmp_path, monkeypatch):
    """R4.1/R4.2 — ownership is proved via the `origin` remote *before* anything
    in the checkout is read. Resolving specDir from a directory the daemon has
    not proved belongs to the work item would reopen the ⟵ direction
    decision-044 closes."""
    from the_loop import graphlink as graphlink_mod

    _git_repo(tmp_path, origin="https://github.com/someone-else/other.git")
    _harness_config(tmp_path, "specs")
    (tmp_path / "specs" / "issue-113").mkdir(parents=True)
    reads = []
    monkeypatch.setattr(
        graphlink_mod.harness_config,
        "load",
        lambda root: reads.append(root) or {},
    )
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_spawn(REF, str(tmp_path))

    assert runtime.started == []
    assert reads == [], "a foreign checkout's harness config must not be read"


# -- a skipped work item is visible in `the-loop events` (issue-123) -------------


def test_a_skipped_work_item_is_recorded_in_the_event_log(tmp_path):
    """R3.1 — a work item that is labelled, armed and delivered to but whose graph
    never moves is worth one line in `the-loop events`. At `logger.debug` it was
    invisible while the delivery still counted as a success.

    Driven by an `advance` since issue-273: `start` no longer refuses a work item
    for having no spec directory, so it no longer has this skip to record."""
    _git_repo(tmp_path)
    events = _events(tmp_path)
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_event(REF, str(tmp_path), _comment_event())

    skipped = [r for r in _records(events) if r["event"] == "graph.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["work_item"] == REF.ref
    assert skipped[0]["action"] == "advance"
    assert skipped[0]["reason"] == "no-spec-dir"
    assert skipped[0]["spec_dir"] == "docs/specs"
    assert skipped[0]["level"] != "debug", (
        "the record must be visible in `the-loop events` without a flag"
    )


def test_a_start_with_no_spec_directory_records_no_skip(tmp_path):
    """issue-273 — the two `graph.skipped` records at spawn (`context`, then
    `start`) were the whole visible signature of the bug: the gate that must run
    before any work never ran, and the operator's only clue was a pair of skips.
    Neither action refuses on this ground any more."""
    _git_repo(tmp_path)
    events = _events(tmp_path)
    runtime = _FakeRuntime()

    link = _link(tmp_path, runtime)
    link.context(REF, str(tmp_path))
    link.on_spawn(REF, str(tmp_path))

    assert [r for r in _records(events) if r["event"] == "graph.skipped"] == [], (
        "no-spec-dir must not refuse the node that runs before any spec exists"
    )


def test_the_skip_record_names_the_action_that_was_refused(tmp_path):
    """`start` and `advance` fail for different reasons in the operator's head;
    the record has to say which one did not happen."""
    _git_repo(tmp_path)
    events = _events(tmp_path)
    runtime = _FakeRuntime()

    _link(tmp_path, runtime).on_event(REF, str(tmp_path), _comment_event())

    assert [r["action"] for r in _records(events) if r["event"] == "graph.skipped"] == [
        "advance"
    ]


def test_graph_skipped_is_in_the_event_catalog():
    """R3.2 — `the-loop events --types` is what agents read to know what exists."""
    assert "graph.skipped" in eventlog.EVENT_TYPES


def test_the_quiet_skip_paths_stay_quiet(repo, tmp_path):
    """Design C6 — a record per delivery for a coupling the operator switched off
    (or for an item the dispatcher already logged as `awaiting-start`) is noise,
    and noise is what makes a log unread."""
    events = _events(tmp_path)
    runtime = _FakeRuntime()

    _link(repo, runtime, enabled=False).on_spawn(REF, str(repo))
    GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=True, require_start_command=True),
        control_store=ControlStore(repo / "control.json"),
    ).on_spawn(REF, str(repo))
    _link(repo, runtime).on_spawn(WorkItemRef.parse("jira:acme/proj#42"), str(repo))

    assert [r for r in _records(events) if r["event"] == "graph.skipped"] == []


# -- envelope re-attribution (issue-309, decision-103 D4) --------------------------


def _routed_comment(login, body):
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d",
        work_items=[REF],
        payload={"comment": {"body": body, "user": {"login": login}}},
    )


def _relayed(named_login):
    from the_loop.channels import envelope as env

    return env.stamp(
        "> approved",
        env.Envelope(
            "gate.feedback", "slack", actor={"github": named_login, "slack": "U1"}
        ),
    )


def test_an_envelope_reattributes_only_between_authorized_people():
    """The poster must be authorized AND the named login must be — both, or the
    poster stays the author. An envelope narrows, never widens."""
    body = _relayed("dana").strip()
    authorized = ["operator", "dana"]
    assert comments_from(_routed_comment("operator", body), authorized) == [
        {"author": "dana", "body": body}
    ]
    # A3: a collaborator (not authorized) forging the same envelope names nobody.
    assert comments_from(_routed_comment("collab", body), authorized) == [
        {"author": "collab", "body": body}
    ]
    # Naming someone outside the list rewrites nothing either.
    stranger = _relayed("stranger").strip()
    assert comments_from(_routed_comment("operator", stranger), authorized) == [
        {"author": "operator", "body": stranger}
    ]
    # No authorized list at all: the pre-issue-309 behaviour, verbatim.
    assert comments_from(_routed_comment("operator", body)) == [
        {"author": "operator", "body": body}
    ]


def test_graphlink_threads_its_authorized_users_into_the_attribution(
    tmp_path, monkeypatch
):
    seen = {}

    class FakeRuntime:
        def advance(self, item, ref="", event=None):
            seen["event"] = event
            return None

    link = GraphLink(
        GraphLinkConfig(enabled=True), authorized_users=["operator", "dana"]
    )
    monkeypatch.setattr(
        link,
        "_guarded",
        lambda action, wi, cwd, call, **k: call(FakeRuntime(), "issue-113"),
    )
    link.on_event(REF, str(tmp_path), _routed_comment("operator", _relayed("dana")))
    assert seen["event"]["comments"][0]["author"] == "dana"
