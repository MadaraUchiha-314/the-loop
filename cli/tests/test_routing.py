"""Unit tests for webhook→session routing: registry, router, adapters, dispatcher.

Spec: docs/specs/issue-15/ (requirements R2–R5).
"""

import json
import logging
import threading
import time
from pathlib import Path

import pytest

from the_loop import cli_config
from the_loop.control import ControlConfig
from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.sessions import (
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
)
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import (
    Deduper,
    RoutedEvent,
    Router,
    event_actor,
    event_body,
    event_carries_label,
    extract_work_items,
    pr_work_item,
)

LABEL = "the-loop: auto-execute"

REF = "github:octo/repo#15"


def make_session(ref=REF, harness="claude", session_id="sess-1", cwd="."):
    return Session(
        work_item=WorkItemRef.parse(ref),
        harness=harness,
        harness_session_id=session_id,
        cwd=str(Path(cwd).resolve()),
    )


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# -- session registry (R2) ----------------------------------------------------


def test_registry_work_item_ref_parse_roundtrip():
    ref = WorkItemRef.parse(REF)
    assert (ref.provider, ref.owner, ref.repo, ref.number) == (
        "github",
        "octo",
        "repo",
        15,
    )
    assert ref.ref == REF


@pytest.mark.parametrize(
    "bad", ["", "github:octo/repo", "octo/repo#1", "github:octo#2", "jira:"]
)
def test_registry_work_item_ref_rejects_garbage(bad):
    with pytest.raises(ValueError):
        WorkItemRef.parse(bad)


def test_registry_register_and_find_roundtrip(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    found = registry.find_by_work_item(REF)
    assert found is not None
    assert found.harness_session_id == "sess-1"
    assert found.status == "active"
    assert found.created_at  # timestamped
    # the on-disk artifact is a single human-inspectable JSON file
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["workItem"]["ref"] == REF


def test_registry_refuses_second_active_session_unless_forced(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session(session_id="old"))
    with pytest.raises(RegistryError):
        registry.register(make_session(session_id="new"))
    registry.register(make_session(session_id="new"), force=True)
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "new"


def test_registry_close_and_list(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.register(make_session(ref="github:octo/repo#16", session_id="s2"))
    assert registry.close(REF) is True
    assert registry.find_by_work_item(REF) is None  # closed != active
    assert {s.status for s in registry.list_sessions()} == {"active", "closed"}
    assert len(registry.list_sessions(status="active")) == 1
    # closing again is a no-op that reports nothing to close
    assert registry.close(REF) is False


def test_registry_reregister_after_close_is_allowed(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session(session_id="first"))
    registry.close(REF)
    registry.register(make_session(session_id="second"))
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "second"


def test_registry_touch_records_event_and_delivery(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.touch(REF, delivery_id="uuid-1")
    found = registry.find_by_work_item(REF)
    assert found is not None
    assert found.last_event_at
    assert "uuid-1" in found.recent_deliveries


def test_registry_skips_corrupt_file(tmp_path, caplog):
    """A file the registry *wrote* but can no longer read stays a loud warning."""
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    # Registry-shaped names (``<slug>.json``), so these reach the corruption path
    # rather than the not-mine skip added for issue-111.
    (tmp_path / "github-octo-repo-99.json").write_text("{not json")
    (tmp_path / "github-octo-repo-98.json").write_text(
        json.dumps({"harness": "claude"})
    )
    with caplog.at_level(logging.WARNING, logger="the-loop.sessions"):
        assert len(registry.list_sessions()) == 1  # corrupt entries skipped, no crash
    warnings = [r for r in caplog.records if "unreadable registry file" in r.message]
    assert len(warnings) == 2


def test_registry_ignores_files_it_did_not_write(tmp_path, caplog):
    """The sessions directory is shared state, not the registry's own (issue-111).

    ``<state.root>/sessions/`` holds the poll state beside the registry files
    (issue-106), so a listing must recognise its own files instead of reporting
    everyone else's as corrupt registry entries.
    """
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    (tmp_path / "poll-state.json").write_text(json.dumps({"items": {}}))
    with caplog.at_level(logging.DEBUG, logger="the-loop.sessions"):
        sessions = registry.list_sessions()
    assert [s.work_item.ref for s in sessions] == [REF]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    "ref",
    [
        "github:octo/repo#15",
        "github:octo/repo#1234567",
        "github:Octo-Corp/my.repo-2#3",
        "jira:some.owner/PROJ_x#42",
    ],
)
def test_registry_lists_every_name_it_can_write(tmp_path, ref):
    """The not-mine filter is a superset of what ``_write`` produces (issue-111).

    Driven from ``WorkItemRef.slug`` rather than literal filenames so a future
    change to the naming rule cannot silently hide live sessions from listings.
    """
    registry = SessionRegistry(tmp_path)
    item = WorkItemRef.parse(ref)
    registry.register(make_session(ref=ref))
    assert (tmp_path / f"{item.slug}.json").is_file()
    assert [s.work_item.ref for s in registry.list_sessions()] == [item.ref]


# -- durable session bindings (issue-172) -------------------------------------

PR_REF = "github:octo/repo#16"


def bound_ref(registry, source):
    """The ref ``source`` is bound to — asserted present, so a miss fails here."""
    target = registry.resolve_link(source)
    assert target is not None, f"no binding recorded for {source}"
    return target.ref


def test_registry_link_binds_a_ref_to_another_items_session(tmp_path):
    """The routing decision, on disk, readable by a process that did not make it."""
    registry = SessionRegistry(tmp_path)
    record = registry.link(PR_REF, REF)

    assert record is not None and record.session_ref.ref == REF
    assert (tmp_path / "github-octo-repo-16.link.json").is_file()
    # A fresh instance — the restart property, as a filesystem fact (R1.4).
    assert bound_ref(SessionRegistry(tmp_path), PR_REF) == REF


def test_registry_link_is_idempotent_and_keeps_created_at(tmp_path):
    """An unchanged binding is not rewritten (R1.3), a re-pointed one keeps its age."""
    registry = SessionRegistry(tmp_path)
    first = registry.link(PR_REF, REF)
    assert first is not None
    path = tmp_path / "github-octo-repo-16.link.json"
    before = path.read_text()

    assert registry.link(PR_REF, REF) is None  # same target: nothing to write
    assert path.read_text() == before

    repointed = registry.link(PR_REF, "github:octo/repo#20")
    assert repointed is not None
    assert repointed.session_ref.ref == "github:octo/repo#20"
    assert repointed.created_at == first.created_at  # how long it has been bound
    assert bound_ref(registry, PR_REF) == "github:octo/repo#20"


def test_registry_refuses_to_bind_a_ref_to_itself(tmp_path):
    """R1.5 — enforced in the store, so no caller has to remember to check."""
    registry = SessionRegistry(tmp_path)
    assert registry.link(REF, REF) is None
    assert registry.resolve_link(REF) is None
    assert list(tmp_path.glob("*.link.json")) == []


def test_registry_resolve_link_does_not_follow_a_chain(tmp_path):
    """Single-hop (R2.3): no cycle can be built, so no depth has to be bounded."""
    registry = SessionRegistry(tmp_path)
    registry.link(PR_REF, "github:octo/repo#20")
    registry.link("github:octo/repo#20", REF)

    assert bound_ref(registry, PR_REF) == "github:octo/repo#20"


def test_registry_treats_an_unparseable_binding_as_absent(tmp_path, caplog):
    """A hand-edited record must read as 'no binding', never reach a lookup.

    Both ends go back through ``WorkItemRef.parse``, so a ``sessionRef`` holding
    a path or a shell fragment fails there — and failing there means the caller
    falls back to deriving the linkage, which is the pre-issue-172 behaviour.
    """
    registry = SessionRegistry(tmp_path)
    (tmp_path / "github-octo-repo-16.link.json").write_text(
        json.dumps({"ref": PR_REF, "sessionRef": "../../etc/passwd"})
    )
    with caplog.at_level(logging.DEBUG, logger="the-loop.sessions"):
        assert registry.resolve_link(PR_REF) is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert registry.list_links() == []


def test_registry_binding_file_names_cannot_escape_the_directory(tmp_path):
    """The name is derived through ``WorkItemRef.slug``, which has no separators."""
    registry = SessionRegistry(tmp_path)
    registry.link("github:ghe.corp.example/octo/repo#16", REF)

    written = [p.name for p in tmp_path.glob("*.link.json")]
    assert written == ["github-ghe.corp.example-octo-repo-16.link.json"]
    assert all("/" not in name and ".." not in name for name in written)


def test_registry_bindings_are_invisible_to_the_session_listing(tmp_path, caplog):
    """R4.1 — the suffix keeps them out of the session-record namespace.

    ``_REGISTRY_FILE_RE`` wants a name ending ``-<number>.json``; a binding ends
    ``.link.json``. So nothing had to be taught about them: no phantom session,
    and no "skipping unreadable registry file" warning.
    """
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.link(PR_REF, REF)
    with caplog.at_level(logging.DEBUG, logger="the-loop.sessions"):
        sessions = registry.list_sessions()
    assert [s.work_item.ref for s in sessions] == [REF]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_registry_links_to_and_unlink(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.link(PR_REF, REF)
    registry.link("github:octo/repo#17", REF)
    registry.link("github:octo/repo#18", "github:octo/repo#20")

    assert sorted(link.source.ref for link in registry.links_to(REF)) == [
        PR_REF,
        "github:octo/repo#17",
    ]
    assert registry.unlink(PR_REF) is True
    assert registry.unlink(PR_REF) is False  # nothing left to remove
    assert [link.source.ref for link in registry.links_to(REF)] == [
        "github:octo/repo#17"
    ]


def test_registry_binding_survives_closing_the_session_it_names(tmp_path):
    """R4.4 — a closed session is reopenable, and the binding is still true.

    Removing bindings on close would lose them across exactly the close/reopen
    cycle they exist to survive. ``sessions reset`` is what removes one.
    """
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.link(PR_REF, REF)
    registry.close(REF)

    assert bound_ref(registry, PR_REF) == REF


# -- paused sessions (issue-106) ----------------------------------------------


def test_registry_pause_and_resume_round_trip(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    paused = registry.pause(REF)
    assert paused is not None and paused.is_paused
    # Persisted, so a daemon restart still sees it suspended.
    reread = SessionRegistry(tmp_path).find_by_work_item(REF)
    assert reread is not None and reread.status == "paused"
    assert registry.resume(REF) is not None
    resumed = registry.find_by_work_item(REF)
    assert resumed is not None and resumed.status == "active"


def test_registry_pause_is_a_no_op_when_there_is_nothing_running(tmp_path):
    registry = SessionRegistry(tmp_path)
    assert registry.pause(REF) is None  # no session at all
    registry.register(make_session())
    registry.pause(REF)
    assert registry.pause(REF) is None  # already paused
    assert registry.resume(REF) is not None
    assert registry.resume(REF) is None  # already active


def test_a_paused_session_still_owns_its_work_item(tmp_path):
    # Nothing may spawn a second session for a work item that has a paused one.
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.pause(REF)
    assert registry.find_by_work_item(REF) is not None
    with pytest.raises(RegistryError):
        registry.register(make_session(session_id="second"))


def test_a_paused_session_can_be_closed(tmp_path):
    # A pause must never outlive its work item.
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.pause(REF)
    assert registry.close(REF) is True
    assert registry.find_by_work_item(REF) is None
    closed = registry.find_by_work_item(REF, include_closed=True)
    assert closed is not None and closed.status == "closed"


def test_paused_sessions_are_listable(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.pause(REF)
    assert [s.status for s in registry.list_sessions(status="paused")] == ["paused"]
    assert registry.list_sessions(status="active") == []


# -- event router (R3) --------------------------------------------------------


def payload_issue_comment(number=15, body="hi"):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"body": body},
    }


def payload_pull_request(number=16, branch="claude/github-issue-15-x", body=""):
    return {
        "action": "synchronize",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": body,
        },
    }


def payload_workflow_run(branch="claude/github-issue-15-x", prs=(16,)):
    return {
        "action": "completed",
        "repository": {"full_name": "octo/repo"},
        "workflow_run": {
            "head_branch": branch,
            "conclusion": "failure",
            "pull_requests": [{"number": n} for n in prs],
        },
    }


def test_router_extracts_issue_comment_work_item():
    refs = extract_work_items("issue_comment", payload_issue_comment())
    assert [r.ref for r in refs] == [REF]


def test_a_work_item_on_github_enterprise_is_routed_as_such():
    """The host comes off the payload, not from an assumption (issue-130 review).

    Every real webhook carries the repository's ``html_url``. Reading it here is
    what lets a GitHub Enterprise work item be identified where it enters, so its
    ref, its state file name and its URL all name the host it actually lives on —
    rather than github.com, where it does not exist.
    """
    payload = payload_issue_comment()
    payload["repository"]["html_url"] = "https://ghe.corp.example/octo/repo"

    refs = extract_work_items("issue_comment", payload)
    assert [r.ref for r in refs] == ["github:ghe.corp.example/octo/repo#15"]
    assert refs[0].host == "ghe.corp.example"
    assert refs[0].url == "https://ghe.corp.example/octo/repo/issues/15"
    assert refs[0].slug == "github-ghe.corp.example-octo-repo-15"


def test_the_item_url_is_the_fallback_host_source():
    """The poller's synthesised payloads carry the item's URL, not the repo's."""
    payload = payload_issue_comment()
    payload["issue"]["html_url"] = "https://ghe.corp.example/octo/repo/issues/15"

    refs = extract_work_items("issue_comment", payload)
    assert [r.ref for r in refs] == ["github:ghe.corp.example/octo/repo#15"]


def test_a_payload_with_no_host_still_means_github_com():
    """What a ref without a host has always meant — unchanged, and unwritten."""
    refs = extract_work_items("issue_comment", payload_issue_comment())
    assert [r.ref for r in refs] == [REF]
    assert refs[0].host == "github.com"
    assert refs[0].slug == "github-octo-repo-15"


def test_router_extracts_pr_number_branch_issue_and_closing_keyword():
    payload = payload_pull_request(body="Closes #15")
    refs = {r.ref for r in extract_work_items("pull_request", payload)}
    # PR itself, the issue from the branch name, and the closing keyword (deduped)
    assert refs == {"github:octo/repo#16", REF}


# -- PR → linked issue resolution (issue-93) ----------------------------------


def payload_pr_conversation_comment(number=16, body="Closes #15", labels=()):
    """An ``issue_comment`` on a PR — GitHub's shape for a PR conversation
    comment: ``issue`` carries a ``pull_request`` key and the PR's body/labels."""
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {
            "number": number,
            "body": body,
            "labels": [{"name": name} for name in labels],
            "pull_request": {"html_url": "https://github.com/octo/repo/pull/16"},
        },
        "comment": {"body": "please rerun CI", "user": {"login": "octocat"}},
    }


def test_router_puts_linked_issue_before_the_pr_for_pr_events():
    payload = payload_pull_request(body="Closes #15")
    refs = [r.ref for r in extract_work_items("pull_request", payload)]
    # Linked issue first: it decides which session an unmatched event spawns for.
    assert refs == [REF, "github:octo/repo#16"]


def test_router_resolves_linked_issue_for_a_pr_conversation_comment():
    refs = [
        r.ref
        for r in extract_work_items("issue_comment", payload_pr_conversation_comment())
    ]
    assert refs == [REF, "github:octo/repo#16"]


def test_router_pr_conversation_comment_without_a_link_stays_its_own_item():
    payload = payload_pr_conversation_comment(body="no link here")
    refs = [r.ref for r in extract_work_items("issue_comment", payload)]
    assert refs == ["github:octo/repo#16"]


def test_router_honours_github_closing_issue_references():
    payload = payload_pr_conversation_comment(body="no keyword in the body")
    payload["issue"]["closingIssuesReferences"] = [{"number": 15}, {"number": None}]
    refs = [r.ref for r in extract_work_items("issue_comment", payload)]
    assert refs == [REF, "github:octo/repo#16"]


@pytest.mark.parametrize(
    "body",
    [
        "Fixes: #15",
        "Closes octo/repo#15",
        "Resolved GH-15",
        "fix https://github.com/octo/repo/issues/15",
    ],
)
def test_router_accepts_every_closing_keyword_form(body):
    payload = payload_pull_request(branch="feature/no-number", body=body)
    refs = [r.ref for r in extract_work_items("pull_request", payload)]
    assert refs == [REF, "github:octo/repo#16"]


@pytest.mark.parametrize(
    "body",
    ["Closes other/repo#15", "Closes https://github.com/other/repo/issues/15"],
)
def test_router_ignores_closing_references_to_another_repository(body):
    payload = payload_pull_request(branch="feature/no-number", body=body)
    refs = [r.ref for r in extract_work_items("pull_request", payload)]
    assert refs == ["github:octo/repo#16"]


def test_router_ignores_a_pr_closing_reference_to_itself():
    payload = payload_pull_request(number=16, branch="feature/x", body="Closes #16")
    refs = [r.ref for r in extract_work_items("pull_request", payload)]
    assert refs == ["github:octo/repo#16"]


def test_pr_work_item_names_the_ref_extraction_emits_last():
    """``pr_work_item`` and ``extract_work_items`` cannot disagree (issue-172).

    Both are built from the same three helpers, and this pins that: whatever
    ``extract_work_items`` puts last for a PR event is what a binding is written
    under. Checked on both PR shapes — a real ``pull_request`` and GitHub's
    ``issue_comment``-carrying-a-``pull_request``-key form.
    """
    for event, payload in (
        ("pull_request", payload_pull_request(body="Closes #15")),
        ("issue_comment", payload_pr_conversation_comment()),
    ):
        pr = pr_work_item(event, payload)
        assert pr is not None
        assert pr.ref == extract_work_items(event, payload)[-1].ref
        assert pr.ref == "github:octo/repo#16"


def test_pr_work_item_is_none_for_events_that_concern_no_pull_request():
    assert pr_work_item("issue_comment", payload_issue_comment()) is None
    assert pr_work_item("workflow_run", payload_workflow_run()) is None
    assert pr_work_item("pull_request", {"pull_request": {"number": 16}}) is None


def test_pr_work_item_carries_the_host_off_the_payload():
    payload = payload_pull_request(body="Closes #15")
    payload["repository"]["html_url"] = "https://ghe.corp.example/octo/repo"
    pr = pr_work_item("pull_request", payload)
    assert pr is not None
    assert pr.ref == "github:ghe.corp.example/octo/repo#16"


def test_router_extracts_workflow_run_prs_and_branch_issue():
    refs = {r.ref for r in extract_work_items("workflow_run", payload_workflow_run())}
    assert refs == {"github:octo/repo#16", REF}


def test_router_returns_nothing_for_unknown_event():
    assert extract_work_items("ping", {"zen": "ok"}) == []


def test_router_filters_disabled_event_types():
    router = Router(events=["workflow_run"])
    routed = router.route("issue_comment", payload_issue_comment(), "d-1")
    assert routed is None
    routed = router.route("workflow_run", payload_workflow_run(), "d-2")
    assert routed is not None and routed.event == "workflow_run"


def test_router_empty_event_filter_allows_all():
    router = Router(events=[])
    assert router.route("issue_comment", payload_issue_comment(), "d-1") is not None


def test_event_carries_label_from_labeled_action():
    payload = {"action": "labeled", "label": {"name": LABEL}, "issue": {"number": 15}}
    assert event_carries_label(payload, LABEL) is True
    other = {"action": "labeled", "label": {"name": "bug"}, "issue": {"number": 15}}
    assert event_carries_label(other, LABEL) is False


def test_event_carries_label_from_current_label_set():
    issue = {"action": "created", "issue": {"number": 15, "labels": [{"name": LABEL}]}}
    assert event_carries_label(issue, LABEL) is True
    pr = {"action": "synchronize", "pull_request": {"labels": [{"name": LABEL}]}}
    assert event_carries_label(pr, LABEL) is True


def test_event_carries_label_false_when_absent_or_unlabelled():
    assert event_carries_label({"issue": {"number": 15, "labels": []}}, LABEL) is False
    assert event_carries_label({"workflow_run": {}}, LABEL) is False  # no labels
    assert event_carries_label({"issue": {"labels": [{"name": LABEL}]}}, "") is False


def test_router_sets_labeled_flag():
    router = Router(events=[], auto_execute_label=LABEL)
    labeled = router.route(
        "issues",
        {
            "action": "labeled",
            "label": {"name": LABEL},
            "repository": {"full_name": "octo/repo"},
            "issue": {"number": 15},
        },
        "d-1",
    )
    assert labeled is not None and labeled.labeled is True
    plain = router.route("issue_comment", payload_issue_comment(), "d-2")
    assert plain is not None and plain.labeled is False


def _issue_comment_by(login, number=15):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"user": {"login": login}, "body": "hi"},
    }


def test_event_actor_extraction():
    assert event_actor("issue_comment", _issue_comment_by("alice")) == "alice"
    assert (
        event_actor(
            "pull_request_review",
            {"review": {"user": {"login": "bob"}}},
        )
        == "bob"
    )
    assert (
        event_actor("issues", {"sender": {"login": "carol"}, "action": "labeled"})
        == "carol"
    )
    # pure system events (CI) have no human actor
    assert event_actor("workflow_run", {"workflow_run": {}}) is None


def test_event_body_extraction():
    assert event_body("issue_comment", _issue_comment_by("alice")) == "hi"
    assert (
        event_body("pull_request_review_comment", {"comment": {"body": "nit: typo"}})
        == "nit: typo"
    )
    assert event_body("pull_request_review", {"review": {"body": "LGTM"}}) == "LGTM"
    # events with no reply text carry no body to check
    assert event_body("workflow_run", {"workflow_run": {}}) is None
    assert event_body("issues", {"issue": {"body": "issue body"}}) is None


def test_router_drops_event_from_unauthorized_actor():
    router = Router(events=[], authorized_users=["me"])
    assert router.route("issue_comment", _issue_comment_by("attacker"), "d-1") is None
    assert router.route("issue_comment", _issue_comment_by("me"), "d-2") is not None


def test_router_empty_allowlist_fails_closed_for_human_events():
    router = Router(events=[], authorized_users=[])  # nobody authorized
    assert router.route("issue_comment", _issue_comment_by("anyone"), "d-1") is None


def test_router_allows_actorless_ci_event_even_when_gated():
    router = Router(events=[], authorized_users=["me"])
    routed = router.route(
        "workflow_run",
        {
            "repository": {"full_name": "octo/repo"},
            "workflow_run": {"head_branch": "issue-15", "pull_requests": []},
        },
        "d-1",
    )
    assert routed is not None  # CI status carries no human instruction


def test_router_pr_close_bypasses_authz_for_cleanup():
    router = Router(events=[], authorized_users=["me"])
    routed = router.route(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": "octo/repo"},
            "sender": {"login": "attacker"},
            "pull_request": {"number": 20, "merged": True},
        },
        "d-1",
    )
    assert routed is not None  # lifecycle auto-close must still fire


def test_router_issue_close_bypasses_authz_for_cleanup():
    # issue-94: closing the ticket ends the session, so it is the same kind of
    # lifecycle signal PR-close already is — it injects no text and can only
    # close the-loop's own session.
    router = Router(events=[], authorized_users=["me"])
    routed = router.route(
        "issues",
        {
            "action": "closed",
            "repository": {"full_name": "octo/repo"},
            "sender": {"login": "attacker"},
            "issue": {"number": 15},
        },
        "d-1",
    )
    assert routed is not None


def test_router_still_guards_non_close_issue_events():
    # the exemption is narrow: only action == closed
    router = Router(events=[], authorized_users=["me"])
    assert (
        router.route(
            "issues",
            {
                "action": "labeled",
                "repository": {"full_name": "octo/repo"},
                "sender": {"login": "attacker"},
                "issue": {"number": 15},
            },
            "d-2",
        )
        is None
    )


def test_router_drops_its_own_self_marked_reply():
    from the_loop.authz import SELF_COMMENT_MARKER

    router = Router(events=[], authorized_users=["me"])
    own_reply = _issue_comment_by("me")
    own_reply["comment"]["body"] = f"will-fix, pushed a fix.\n\n{SELF_COMMENT_MARKER}"
    assert router.route("issue_comment", own_reply, "d-1") is None
    # a same-author comment with no marker is still routed normally
    assert router.route("issue_comment", _issue_comment_by("me"), "d-2") is not None


def test_router_drops_the_daemons_own_session_announcement():
    # issue-104: the announcement is posted with the operator's own credentials,
    # so the authorized-actor guard passes it — only the marker can stop it from
    # being dispatched back into the session it announces.
    from the_loop.announce import announcement_body
    from the_loop.sessions import Session, WorkItemRef

    session = Session(
        work_item=WorkItemRef.parse("github:octo/repo#15"),
        harness="claude",
        harness_session_id="s-1",
        cwd=".",
        tmux_target="loop-github-octo-repo-15",
    )
    router = Router(events=[], authorized_users=["me"])
    event = _issue_comment_by("me")
    event["comment"]["body"] = announcement_body(session)
    assert router.route("issue_comment", event, "d-1") is None


def test_router_deduper_is_bounded_lru():
    deduper = Deduper(maxsize=2)
    deduper.add("a")
    deduper.add("b")
    assert "a" in deduper and "b" in deduper
    deduper.add("c")  # evicts the oldest
    assert "a" not in deduper and "c" in deduper
    deduper.discard("b")
    assert "b" not in deduper


# -- dispatcher (R3.2/R3.3, R5) -----------------------------------------------


def make_dispatcher(tmp_path, tmux, **config_overrides):
    """A dispatcher whose observable seam is the injected FakeTmux (issue-156)."""
    registry = SessionRegistry(tmp_path / "sessions")
    # Pre-issue-106 spawn behaviour by default: these cover the spawn mechanics,
    # while the start-command gate has its own tests below.
    config_overrides.setdefault("control", ControlConfig(require_start_command=False))
    config = RoutingConfig(**config_overrides)
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
    )
    return registry, dispatcher


def routed_issue_comment(delivery="d-1", number=15, body="please fix"):
    payload = payload_issue_comment(number=number, body=body)
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def test_dispatcher_resumes_matched_session_with_rendered_prompt(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    dispatcher.handle(routed_issue_comment(body="the build is red"))
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()
    ref, prompt = tmux.delivers[0]
    assert ref == REF
    assert REF in prompt and "issue_comment" in prompt
    assert "the build is red" in prompt  # payload excerpt is embedded
    assert "UNTRUSTED" in prompt  # ...and marked as data, not instructions
    found = registry.find_by_work_item(REF)
    assert found is not None and found.last_event_at
    assert "d-1" in found.recent_deliveries


def test_dispatcher_serializes_events_for_one_session_in_order(tmp_path):
    tmux = FakeTmux(delay=0.03)
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    for i in range(3):
        dispatcher.handle(routed_issue_comment(delivery=f"d-{i}", body=f"event {i}"))
    assert wait_until(lambda: len(tmux.delivers) == 3)
    dispatcher.stop()
    bodies = [prompt for _, prompt in tmux.delivers]
    assert [f"event {i}" in body for i, body in enumerate(bodies)] == [True] * 3
    assert tmux.max_in_flight == 1  # same session never dispatches concurrently


def test_stop_reports_events_it_abandoned_undelivered(tmp_path):
    """A shutdown says what it dropped, so the poller can hand the budget back.

    The sentinel goes at the TAIL of the queue, so a graceful stop still
    delivers what is already queued. Only what the join timeout cuts off is
    reported — and on the poll path each of those had already spent one of its
    `polling.maxRetries` (issue-159).
    """
    tmux = FakeTmux()
    tmux.deliver_gate = threading.Event()  # wedges the worker inside d-1
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    try:
        dispatcher.handle(routed_issue_comment(delivery="d-1"))
        dispatcher.handle(routed_issue_comment(delivery="d-2"))
        dispatcher.handle(routed_issue_comment(delivery="d-3"))

        abandoned = dispatcher.stop(timeout=0.2)

        assert abandoned == ["d-2", "d-3"]  # d-1 is in flight, not queued
        assert tmux.delivers == []
    finally:
        tmux.deliver_gate.set()


def test_stop_reports_nothing_when_every_event_was_delivered(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    dispatcher.handle(routed_issue_comment(delivery="d-1"))
    assert wait_until(lambda: len(tmux.delivers) == 1)

    assert dispatcher.stop() == []


def test_dispatcher_dispatches_different_sessions_in_parallel(tmp_path):
    tmux = FakeTmux(delay=0.2)
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session(ref="github:octo/repo#1", session_id="s1"))
    registry.register(make_session(ref="github:octo/repo#2", session_id="s2"))
    dispatcher.handle(routed_issue_comment(delivery="d-1", number=1))
    dispatcher.handle(routed_issue_comment(delivery="d-2", number=2))
    assert wait_until(lambda: len(tmux.delivers) == 2)
    dispatcher.stop()
    assert tmux.max_in_flight == 2  # both sessions were in flight together


def test_dispatcher_drops_unmatched_event_by_default(tmp_path):
    tmux = FakeTmux()
    _, dispatcher = make_dispatcher(tmp_path, tmux)  # empty registry
    dispatcher.handle(routed_issue_comment())
    dispatcher.stop()
    assert tmux.delivers == [] and tmux.spawns == []


def test_dispatcher_spawns_and_registers_when_configured(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="always")
    dispatcher.handle(routed_issue_comment())
    assert wait_until(lambda: len(tmux.spawns) == 1)
    dispatcher.stop()
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id  # pre-assigned uuid
    assert found.tmux_target == "loop-github-octo-repo-15"


def routed_labeled_issue(delivery="l-1", number=15, labeled=True):
    payload = {
        "action": "labeled",
        "label": {"name": LABEL if labeled else "bug"},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
    }
    return RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=labeled,
    )


def test_dispatcher_labeled_mode_spawns_only_for_labeled_items(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="labeled")
    # An unlabelled unmatched event does nothing (owner scenario 1).
    dispatcher.handle(routed_labeled_issue(delivery="u-1", labeled=False))
    # A labelled one spawns + registers a session (owner scenario 2).
    dispatcher.handle(routed_labeled_issue(delivery="l-1", labeled=True))
    assert wait_until(lambda: len(tmux.spawns) == 1)
    dispatcher.stop()
    assert len(tmux.spawns) == 1  # only the labelled event spawned
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id  # pre-assigned uuid


def test_dispatcher_labeled_spawn_prompt_kicks_off_work_on(tmp_path):
    tmux = FakeTmux()
    _, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="labeled")
    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(tmux.spawns) == 1)
    dispatcher.stop()
    _, prompt, _, _ = tmux.spawns[0]
    assert "/the-loop:work-on" in prompt and REF in prompt


def test_dispatcher_always_mode_still_spawns_regardless_of_label(tmp_path):
    tmux = FakeTmux()
    _, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="always")
    dispatcher.handle(routed_labeled_issue(labeled=False))  # unlabelled
    assert wait_until(lambda: len(tmux.spawns) == 1)  # 'always' ignores the label
    dispatcher.stop()


def test_dispatcher_processes_duplicate_delivery_at_most_once(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    dispatcher.handle(routed_issue_comment(delivery="dup-1"))
    dispatcher.handle(routed_issue_comment(delivery="dup-1"))
    assert wait_until(lambda: len(tmux.delivers) >= 1)
    time.sleep(0.1)  # give a would-be duplicate time to (wrongly) dispatch
    dispatcher.stop()
    assert len(tmux.delivers) == 1


def test_dispatcher_skips_respawn_whose_adapter_is_unknown(tmp_path, caplog):
    # Delivery into a live tmux session is harness-agnostic; only a respawn
    # needs the adapter. A dead session for an unwired harness fails loudly
    # instead of spawning something else.
    tmux = FakeTmux()
    tmux.session_missing = True  # every delivery reads "session gone"
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session(harness="cursor"))  # no cursor adapter wired
    dispatcher.handle(routed_issue_comment())
    dispatcher.stop()
    assert tmux.spawns == []


def routed_pr_closed(
    delivery="c-1",
    number=16,
    branch="claude/github-issue-15-x",
    body="Closes #15",
    merged=True,
):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": body,
            "merged": merged,
        },
    }
    return RoutedEvent(
        event="pull_request",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("pull_request", payload),
        payload=payload,
    )


def test_pr_close_leaves_the_linked_issues_session_active(tmp_path):
    # issue-101: a work item can be delivered by several PRs, so one of them
    # merging is not the work item ending — only the item's own close is.
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())  # session for the issue #15
    dispatcher.handle(routed_pr_closed())  # PR #16 closes, links issue #15
    dispatcher.stop()
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"  # still working
    assert tmux.delivers == []  # a close is never delivered into the conversation


def test_pr_close_closes_a_session_registered_against_the_pr_itself(tmp_path):
    # The non-GitHub-ticketing path (Jira, …): the PR *is* the work item.
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session(ref="github:octo/repo#16", session_id="pr-sess"))
    dispatcher.handle(routed_pr_closed())
    dispatcher.stop()
    assert registry.find_by_work_item("github:octo/repo#16") is None  # auto-closed
    assert registry.list_sessions(status="closed")  # persisted as closed
    assert tmux.delivers == []


def test_a_second_pr_closing_ends_nothing_while_the_work_item_is_open(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())  # one session for the work item #15
    dispatcher.handle(routed_pr_closed(delivery="c-1", number=16))  # first PR
    dispatcher.handle(routed_pr_closed(delivery="c-2", number=17))  # second PR
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None  # #15 is still being worked
    assert registry.list_sessions(status="closed") == []


def test_a_malformed_close_payload_closes_nothing(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    broken = routed_pr_closed()
    broken.payload["pull_request"].pop("number")  # nothing names what closed
    dispatcher.handle(broken)
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None  # keep state under doubt


def test_dispatcher_pr_close_never_spawns(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="always")
    dispatcher.handle(routed_pr_closed())  # no session registered
    dispatcher.stop()
    assert tmux.spawns == []  # never spawn a session to handle a close


def test_dispatcher_still_resumes_on_pr_events_that_are_not_close(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    open_pr = routed_pr_closed(delivery="o-1", merged=False)
    open_pr.action = "synchronize"  # a non-close PR event still routes normally
    dispatcher.handle(open_pr)
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None  # not closed


def routed_issue_closed(delivery="ic-1", number=15):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number, "state_reason": "completed"},
    }
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def test_dispatcher_auto_closes_session_on_issue_close(tmp_path):
    # issue-94: a closed ticket ends the session instead of waking the agent.
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    dispatcher.handle(routed_issue_closed())
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is None  # auto-closed
    assert registry.list_sessions(status="closed")
    assert tmux.delivers == []  # never delivered into the conversation


def test_dispatcher_issue_close_never_spawns(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="always")
    dispatcher.handle(routed_issue_closed())
    dispatcher.stop()
    assert tmux.spawns == []


def test_dispatcher_still_resumes_on_issue_events_that_are_not_close(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    reopened = routed_issue_closed(delivery="ic-2")
    reopened.action = "reopened"
    dispatcher.handle(reopened)
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None


@pytest.mark.parametrize(
    "event,merged,expected",
    [
        ("issues", None, "issue-closed"),
        ("pull_request", True, "pr-merged"),
        ("pull_request", False, "pr-closed"),
    ],
)
def test_close_reason_names_why_the_work_item_ended(event, merged, expected):
    from the_loop.webhook.dispatcher import _close_reason, _is_close_event

    routed = (
        routed_issue_closed() if event == "issues" else routed_pr_closed(merged=merged)
    )
    assert _is_close_event(routed)
    assert _close_reason(routed) == expected


# -- delivery status for poll-path retry accounting (issue-80) ----------------


def test_delivery_status_done_inflight_unhandled(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux)
    registry.register(make_session())
    refs = [WorkItemRef.parse(REF)]

    # never sent / no id
    assert dispatcher.delivery_status("nope", refs) == "unhandled"
    assert dispatcher.delivery_status("", refs) == "unhandled"

    # in the in-memory dedup cache (enqueued/processing) -> inflight
    dispatcher.deduper.add("d-flight")
    assert dispatcher.delivery_status("d-flight", refs) == "inflight"

    # recorded in the session's durable recent_deliveries -> done (wins over cache)
    registry.touch(REF, delivery_id="d-done")
    dispatcher.deduper.add("d-done")
    assert dispatcher.delivery_status("d-done", refs) == "done"


def test_delivery_status_follows_a_binding(tmp_path):
    """A delivery that succeeded *through* a binding is `done`, not `unhandled`.

    The id is recorded on the bound session's record, and the refs the poller
    asks about are the PR's — so asking the registry directly would call a
    successful delivery unhandled, and the poller would re-forward the same
    comment until its retry budget was spent (issue-172 self-review).
    """
    registry, dispatcher = make_dispatcher(tmp_path, FakeTmux())
    registry.register(make_session())
    registry.link(PR_REF, REF)
    registry.touch(REF, delivery_id="d-bound")

    assert dispatcher.delivery_status("d-bound", [WorkItemRef.parse(PR_REF)]) == "done"


# -- `the-loop sessions` command (R2.2) ----------------------------------------


def run_cli(argv):
    from the_loop.cli import main

    return main(argv)


def test_sessions_command_is_registered():
    from the_loop.commands import iter_commands

    assert "sessions" in {c.name for c in iter_commands()}


def test_sessions_command_register_list_close_roundtrip(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    rc = run_cli(
        [
            "sessions",
            "register",
            "--work-item",
            REF,
            "--harness",
            "claude",
            "--harness-session-id",
            "sess-1",
            "--cwd",
            str(tmp_path),
            "--registry-dir",
            registry_dir,
        ]
    )
    assert rc == 0
    rc = run_cli(
        ["sessions", "list", "--registry-dir", registry_dir, "--format", "json"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out.splitlines()[-1])
    assert payload[0]["workItem"]["ref"] == REF
    assert payload[0]["status"] == "active"
    rc = run_cli(
        ["sessions", "close", "--work-item", REF, "--registry-dir", registry_dir]
    )
    assert rc == 0
    rc = run_cli(
        ["sessions", "list", "--registry-dir", registry_dir, "--format", "json"]
    )
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload[0]["status"] == "closed"


def test_sessions_command_duplicate_register_fails_without_force(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    base = [
        "sessions",
        "register",
        "--work-item",
        REF,
        "--harness",
        "claude",
        "--harness-session-id",
    ]
    tail = ["--cwd", str(tmp_path), "--registry-dir", registry_dir]
    assert run_cli(base + ["one"] + tail) == 0
    assert run_cli(base + ["two"] + tail) != 0  # refused: one item, one session
    assert run_cli(base + ["two"] + tail + ["--force"]) == 0


def test_sessions_command_close_missing_session_errors(tmp_path):
    rc = run_cli(
        [
            "sessions",
            "close",
            "--work-item",
            REF,
            "--registry-dir",
            str(tmp_path / "empty"),
        ]
    )
    assert rc != 0


def test_sessions_command_table_output(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    run_cli(
        [
            "sessions",
            "register",
            "--work-item",
            REF,
            "--harness",
            "cursor",
            "--harness-session-id",
            "chat-1",
            "--cwd",
            str(tmp_path),
            "--registry-dir",
            registry_dir,
        ]
    )
    capsys.readouterr()
    assert run_cli(["sessions", "list", "--registry-dir", registry_dir]) == 0
    out = capsys.readouterr().out
    assert "Work item" in out and REF in out and "cursor" in out


# -- config hot reload (issue-34 review) --------------------------------------


def test_dispatcher_reload_swaps_policy_and_templates_keeps_dedup(tmp_path):
    tmux = FakeTmux()
    registry, dispatcher = make_dispatcher(tmp_path, tmux, spawn_on_unmatched="never")
    dispatcher.deduper.add("keep-me")  # in-memory dedup must survive a reload
    tmpl = tmp_path / "evt.md"
    tmpl.write_text("RELOADED $work_item")

    dispatcher.reload(
        RoutingConfig(
            spawn_on_unmatched="always",
            registry_dir="ignored-on-reload",
            prompt_template=str(tmpl),
            control=ControlConfig(require_start_command=False),
        )
    )
    dispatcher.stop()

    # soft policy took effect
    assert dispatcher.config.spawn_on_unmatched == "always"
    assert dispatcher._spawn_refusal(routed_labeled_issue(labeled=False)) == ""
    # prompt template reloaded
    rendered = dispatcher._render_prompt(
        routed_issue_comment(), WorkItemRef.parse(REF), dispatcher._event_template
    )
    assert rendered.startswith("RELOADED github:octo/repo#15")
    # infrastructure preserved (change needs a restart)
    assert "keep-me" in dispatcher.deduper  # dedup cache kept
    assert dispatcher.registry is registry  # registryDir change ignored
    assert "claude" in dispatcher.adapters  # adapters rebuilt from harnessArgs


def test_read_gh_webhook_config_strict_vs_lenient(tmp_path, monkeypatch):
    from the_loop.commands import gh_webhook

    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cfg)

    # missing file: lenient => {}, strict => raises
    assert gh_webhook._read_gh_webhook_config(strict=False) == {}
    with pytest.raises(FileNotFoundError):
        gh_webhook._read_gh_webhook_config(strict=True)

    # unparseable: lenient => {} (keep defaults), strict => raises (keep previous)
    cfg.write_text("webhooks: [unclosed\n")
    assert gh_webhook._read_gh_webhook_config(strict=False) == {}
    with pytest.raises(Exception):
        gh_webhook._read_gh_webhook_config(strict=True)


def _write_webhook_config(path, policy, sessions_dir, events="[]"):
    """The receiver's block and the shared `routing` block — two top-level keys
    since issue-142, which is what the hot-reload has to read separately."""
    path.write_text(
        "webhooks:\n"
        "  ghWebhook:\n"
        f"    events: {events}\n"
        "routing:\n"
        f"  spawnOnUnmatched: {policy}\n"
        f"  registryDir: {sessions_dir}\n"
    )


def test_webhook_hot_reload_applies_on_next_event(tmp_path, monkeypatch):
    from the_loop.commands import gh_webhook

    cfg = tmp_path / "config.yaml"
    _write_webhook_config(cfg, "never", tmp_path / "sessions")
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cfg)

    on_event, dispatcher, _ = gh_webhook._build_routing(
        cli_config.load_routing_config(cfg), gh_webhook._read_gh_webhook_config()
    )
    assert dispatcher.config.spawn_on_unmatched == "never"

    # edit the config while "running"; the next received event applies it
    _write_webhook_config(cfg, "always", tmp_path / "sessions")
    on_event(
        "issues",
        {"repository": {"full_name": "octo/repo"}, "issue": {"number": 1}},
        "d-1",
    )
    dispatcher.stop()

    assert dispatcher.config.spawn_on_unmatched == "always"
