"""The ingress → process-graph coupling (issue-113).

The seam these tests pin down is a *bridge*, so most of them are about what it
refuses to do: skip when the work item has no spec, skip when nobody started it,
and — above all — never let a graph failure cost an event delivery.
"""

from __future__ import annotations

import pytest

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
    link._build_runtime = lambda cwd: runtime  # noqa: SLF001 — test seam
    return link


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


def test_a_work_item_with_no_spec_directory_is_skipped(tmp_path):
    """AC9 — no spec means the loop has not started this item; inventing a
    directory would fake that."""
    runtime = _FakeRuntime()
    link = _link(tmp_path, runtime)
    link.on_spawn(REF, str(tmp_path))
    assert runtime.started == []


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
    link._build_runtime = lambda cwd: runtime  # noqa: SLF001
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
    link._build_runtime = lambda cwd: runtime  # noqa: SLF001
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
