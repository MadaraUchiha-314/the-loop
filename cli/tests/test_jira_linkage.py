"""PR → Jira linkage (issue-475, design §C9, abuse case 7).

A Jira key in a pull request's head branch or title links the pull request to a
Jira work item only when the key's project maps to the pull request's own
repository **and** the Jira ref is registered. Never from the body; never with
Jira unconfigured.
"""

from __future__ import annotations

from jirafakes import cloud_config

from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.router import (
    SOURCE_JIRA_KEY,
    JiraLinkage,
    Router,
    extract_work_items,
    jira_linkage,
    work_item_sources,
)

SITE = "acme.atlassian.net"
JIRA = WorkItemRef.parse(f"jira:{SITE}/PROJ-7")
PR = "github:acme/web#48"


def _payload(branch="feat/PROJ-7-login", title="Fix login", body="", repo="acme/web"):
    return {
        "action": "opened",
        "repository": {"full_name": repo},
        "pull_request": {
            "number": 48,
            "head": {"ref": branch},
            "title": title,
            "body": body,
        },
        "sender": {"login": "ada"},
    }


def _linkage(*registered: WorkItemRef, config=None) -> JiraLinkage:
    known = {ref.ref for ref in registered}
    return JiraLinkage(
        config=config if config is not None else cloud_config(),
        is_registered=lambda ref: ref.ref in known,
    )


def _refs(payload, linkage):
    return [item.ref for item in extract_work_items("pull_request", payload, linkage)]


def test_a_registered_key_in_the_branch_links_the_pr_to_the_jira_work_item():
    sources = work_item_sources("pull_request", _payload(), _linkage(JIRA))
    assert list(sources) == [JIRA.ref, PR]
    assert sources[JIRA.ref][1] == {SOURCE_JIRA_KEY}


def test_a_registered_key_in_the_title_links_too():
    payload = _payload(branch="topic", title="PROJ-7: fix the login page")
    assert _refs(payload, _linkage(JIRA)) == [JIRA.ref, PR]


def test_pr_naming_unregistered_jira_key_does_not_link():
    # Configured project, this repository — but no session registered for it.
    assert _refs(_payload(), _linkage()) == [PR]
    # A crafted branch cannot reach the registry check's answer for another key.
    crafted = _payload(branch="PROJ-8/PROJ-7x-PROJ-70", title="PROJ-0 PROJ-07")
    assert _refs(crafted, _linkage(JIRA)) == [PR]


def test_pr_in_other_repository_does_not_link():
    # Registered, but PROJ maps to acme/web and the PR is in acme/other.
    assert _refs(_payload(repo="acme/other"), _linkage(JIRA)) == [
        "github:acme/other#48"
    ]


def test_a_mirror_only_or_unconfigured_project_does_not_link():
    ops = WorkItemRef.parse(f"jira:{SITE}/OPS-3")
    other = WorkItemRef.parse(f"jira:{SITE}/NOPE-3")
    payload = _payload(branch="OPS-3-and-NOPE-3")
    assert _refs(payload, _linkage(ops, other)) == [PR]


def test_a_key_in_the_pr_body_never_links():
    payload = _payload(branch="topic", title="Fix login", body="Fixes PROJ-7")
    assert _refs(payload, _linkage(JIRA)) == [PR]


def test_without_jira_configured_no_key_links():
    assert _refs(_payload(), None) == [PR]
    assert jira_linkage({}, registry=None) is None


def test_a_registry_check_that_raises_links_nothing():
    def boom(ref):
        raise OSError("disk gone")

    linkage = JiraLinkage(config=cloud_config(), is_registered=boom)
    assert _refs(_payload(), linkage) == [PR]


def test_jira_linkage_reads_live_sessions_from_the_registry(tmp_path):
    registry = SessionRegistry(tmp_path)
    linkage = jira_linkage(cloud_config(), registry)
    assert _refs(_payload(), linkage) == [PR]
    registry.register(
        Session(work_item=JIRA, harness="claude", harness_session_id="s", cwd="/w")
    )
    assert _refs(_payload(), linkage) == [JIRA.ref, PR]


def test_the_repository_bound_keeps_a_linked_jira_ref():
    router = Router(
        authorized_users=["ada"],
        repositories={"github.com/acme/web"},
        jira_linkage=_linkage(JIRA),
    )
    routed = router.route("pull_request", _payload(), "d-1")
    assert routed is not None
    assert [item.ref for item in routed.work_items] == [JIRA.ref, PR]
