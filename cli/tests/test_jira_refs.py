"""Jira work-item refs, spec ids and origin repositories (issue-475, PR 1).

A Jira ticket is a :class:`WorkItemRef` with its own scheme. These tests pin the
grammar (``jira:<site>/<KEY>-<n>``), the derived forms (ref, slug, url, spec
id), the inverse ``derive_ref`` and :func:`origin_repository` — the repository a
Jira item's spec chain and pull requests live in. The GitHub side of the same
seams is pinned, unmodified, by ``test_routing.py``, ``test_graph_refs.py``,
``test_graphlink.py`` and ``test_core_graphs.py``.

Requirement: docs/specs/issue-475/requirements.md R1.1–R1.5, R2.1–R2.2
"""

from __future__ import annotations

import pytest

from the_loop.core.graphs import work_item_id
from the_loop.graph.refs import derive_ref
from the_loop.graphlink import spec_id_for
from the_loop.sessions import WorkItemRef
from the_loop.sessions.refs import (
    SCHEMES,
    GitHubScheme,
    JiraScheme,
    UnknownJiraProject,
    origin_ref,
    origin_repository,
)

SITE = "acme.atlassian.net"
REF = f"jira:{SITE}/PROJ-123"

CONFIG = {
    "integrations": {
        "jira": {
            "site": SITE,
            "projects": {
                "PROJ": {"repository": "acme/web"},
                "OPS": {},  # mirror-only: a room, never a work-item source
            },
        }
    }
}


# -- the scheme table ------------------------------------------------------------


def test_schemes_are_looked_up_by_provider():
    assert isinstance(SCHEMES["github"], GitHubScheme)
    assert isinstance(SCHEMES["jira"], JiraScheme)
    assert {name: scheme.provider for name, scheme in SCHEMES.items()} == {
        "github": "github",
        "jira": "jira",
    }


# -- grammar and round trip (R1.1–R1.3) -----------------------------------------


def test_jira_ref_round_trips():
    ref = WorkItemRef.parse(REF)
    assert (ref.provider, ref.host, ref.owner, ref.repo, ref.number) == (
        "jira",
        SITE,
        "PROJ",
        "",
        123,
    )
    assert ref.ref == REF
    assert WorkItemRef.parse(ref.ref) == ref


def test_jira_ref_tolerates_surrounding_whitespace_and_lowercases_the_site():
    ref = WorkItemRef.parse("  jira:Acme.Atlassian.NET/PROJ-1 \n")
    assert ref.host == SITE and ref.ref == f"jira:{SITE}/PROJ-1"


@pytest.mark.parametrize(
    "ref",
    [
        "jira:acme.atlassian.net/A1_B-9",
        "jira:jira.corp.example:8443/OPS-1",
        "jira:acme.atlassian.net/ABCDEFGHIJ-9999999999",
    ],
)
def test_jira_ref_accepts_the_grammar(ref):
    assert WorkItemRef.parse(ref).ref == ref


@pytest.mark.parametrize(
    "bad",
    [
        "jira:",
        "jira:PROJ-123",  # no site
        "jira:acme/PROJ-123",  # not a host
        "jira:https://acme.atlassian.net/PROJ-123",  # scheme
        "jira:user@acme.atlassian.net/PROJ-123",  # user-info
        "jira:acme.atlassian.net/sub/PROJ-123",  # a path
        "jira:acme.atlassian.net/proj-123",  # lower-case key
        "jira:acme.atlassian.net/P-123",  # key too short
        "jira:acme.atlassian.net/ABCDEFGHIJK-1",  # key too long
        "jira:acme.atlassian.net/1PROJ-1",  # key not starting with a letter
        "jira:acme.atlassian.net/PR-OJ-1",  # stray separator
        "jira:acme.atlassian.net/PROJ-0",  # number not positive
        "jira:acme.atlassian.net/PROJ-007",  # leading zero
        "jira:acme.atlassian.net/PROJ-12345678901",  # number too long
        "jira:acme.atlassian.net/PROJ-",  # no number
        "jira:acme.atlassian.net/PROJ#123",  # GitHub's separator
        "jira:acme/proj#42",  # the old owner/repo#n shape
    ],
)
def test_jira_ref_rejects_bad_site_key_number(bad):
    with pytest.raises(ValueError, match=r"jira:<site>/<KEY>-<number>"):
        WorkItemRef.parse(bad)


# -- derived forms ------------------------------------------------------------------


def test_jira_slug_and_url():
    ref = WorkItemRef.parse(REF)
    assert ref.slug == "jira-acme.atlassian.net-PROJ-123"
    assert ref.url == "https://acme.atlassian.net/browse/PROJ-123"


def test_jira_slug_is_one_the_registry_lists(tmp_path):
    from the_loop.sessions.registry import _REGISTRY_FILE_RE

    assert _REGISTRY_FILE_RE.fullmatch(f"{WorkItemRef.parse(REF).slug}.json")


def test_a_jira_ref_built_by_hand_with_a_bad_site_has_no_url():
    ref = WorkItemRef(provider="jira", owner="PROJ", repo="", number=1, host="a b")
    assert ref.url == ""


def test_github_refs_keep_every_derived_form():
    """R1.4: the GitHub scheme is today's code, moved."""
    ref = WorkItemRef.parse("github:ghe.corp.example/octo/repo#15")
    assert ref.ref == "github:ghe.corp.example/octo/repo#15"
    assert ref.slug == "github-ghe.corp.example-octo-repo-15"
    assert ref.url == "https://ghe.corp.example/octo/repo/issues/15"
    assert WorkItemRef.parse("github:octo/repo#15").host == "github.com"


# -- spec ids (R2.1, R2.2) ---------------------------------------------------------


def test_jira_spec_id_carries_key_and_number():
    assert WorkItemRef.parse(REF).spec_id == "jira-proj-123"
    assert spec_id_for(WorkItemRef.parse(REF)) == "jira-proj-123"


def test_github_spec_id_is_unchanged():
    assert WorkItemRef.parse("github:octo/repo#7").spec_id == "issue-7"


def test_issue_project_key_never_collides_with_github():
    jira = WorkItemRef.parse(f"jira:{SITE}/ISSUE-7").spec_id
    github = WorkItemRef.parse("github:octo/repo#7").spec_id
    assert jira == "jira-issue-7" and github == "issue-7" and jira != github
    assert not str(jira).startswith("issue-")


def test_another_provider_has_no_spec_id():
    assert WorkItemRef.parse("gitlab:octo/repo#7").spec_id is None


def test_core_work_item_id_translates_a_jira_ref():
    assert work_item_id(REF) == "jira-proj-123"
    assert work_item_id("jira:acme/PROJ-1") == "jira:acme/PROJ-1"  # not a ref


# -- derive_ref: the inverse ----------------------------------------------------------


def test_derive_ref_inverts_a_jira_spec_id_with_the_configured_site():
    assert derive_ref("jira-proj-123", "", jira_site=SITE) == REF
    assert derive_ref("jira-a1_b-9", "", jira_site=SITE) == f"jira:{SITE}/A1_B-9"


def test_derive_ref_round_trips_a_jira_ref():
    ref = WorkItemRef.parse(REF)
    assert derive_ref(str(ref.spec_id), "acme/web", jira_site=SITE) == REF


@pytest.mark.parametrize(
    "item_id, site",
    [
        ("jira-proj-123", ""),  # no site configured: nothing to derive from
        ("jira-proj-123", "https://acme.atlassian.net"),  # not a bare host
        ("jira-proj-0", SITE),
        ("jira-p-1", SITE),  # key too short
        ("jira-proj-12a", SITE),
        ("jira-proj", SITE),
    ],
)
def test_derive_ref_refuses_what_it_cannot_invert(item_id, site):
    assert derive_ref(item_id, "acme/web", jira_site=site) == ""


def test_derive_ref_still_derives_github_ids():
    assert derive_ref("issue-5", "octo/repo", jira_site=SITE) == "github:octo/repo#5"


# -- origin_repository (R1.5, R8) ----------------------------------------------------


def test_origin_repository_of_a_github_ref_is_its_own():
    ref = WorkItemRef.parse("github:octo/repo#15")
    assert origin_repository(ref, CONFIG) == "octo/repo"
    assert origin_repository(ref, None) == "octo/repo"
    assert origin_ref(ref, None) == ref
    assert origin_ref(ref, None, number=16) == WorkItemRef.parse("github:octo/repo#16")


def test_origin_repository_of_a_mapped_jira_project():
    ref = WorkItemRef.parse(REF)
    assert origin_repository(ref, CONFIG) == "acme/web"
    pr = origin_ref(ref, CONFIG, number=9)
    assert pr.ref == "github:acme/web#9"


def test_origin_ref_of_a_jira_item_is_on_the_configured_github_host():
    config = {"integrations": {**CONFIG["integrations"], "github": {"host": "ghe.x"}}}
    pr = origin_ref(WorkItemRef.parse(REF), config, number=9)
    assert pr.ref == "github:ghe.x/acme/web#9"


@pytest.mark.parametrize(
    "ref, why",
    [
        (f"jira:{SITE}/OPS-1", "mirror-only"),
        (f"jira:{SITE}/OTHER-1", "not configured"),
        ("jira:evil.example.com/PROJ-1", "not the configured"),
    ],
)
def test_origin_repository_refuses_unmapped_jira_items(ref, why):
    with pytest.raises(UnknownJiraProject, match=why):
        origin_repository(WorkItemRef.parse(ref), CONFIG)


def test_origin_repository_refuses_without_any_jira_config():
    with pytest.raises(UnknownJiraProject):
        origin_repository(WorkItemRef.parse(REF), {})
    with pytest.raises(UnknownJiraProject):
        origin_repository(WorkItemRef.parse(REF), None)


def test_unknown_jira_project_is_a_value_error():
    """Every caller that already refuses a malformed ref refuses this too."""
    assert issubclass(UnknownJiraProject, ValueError)


def test_ref_on_unknown_site_sends_no_credential(monkeypatch):
    """Abuse case 8: a ref on a site this deployment is not configured for is
    refused before anything is resolved — no repository, no credential — and the
    refusal names the site, never a secret."""
    secret = "tok-should-never-appear"
    monkeypatch.setenv("JIRA_API_TOKEN", secret)
    config = {
        "integrations": {
            "jira": {
                **CONFIG["integrations"]["jira"],
                "api": {"tokenEnv": ["JIRA_API_TOKEN"]},
            }
        }
    }
    with pytest.raises(UnknownJiraProject) as raised:
        origin_ref(WorkItemRef.parse("jira:evil.example.com/PROJ-1"), config)
    assert "evil.example.com" in str(raised.value)
    assert secret not in str(raised.value)


def test_a_github_only_verb_refuses_a_jira_ref(tmp_path):
    from the_loop.core import github_ops

    with pytest.raises(ValueError, match="is a Jira work item"):
        github_ops.comment(REF, "hi", {"state": {"root": str(tmp_path)}})


# -- a moved Jira key (R2.3) ------------------------------------------------------------


def test_moved_jira_key_refuses_second_spec_folder(tmp_path):
    """A ticket moved from OLD-4 to NEW-9 keeps the folder it has: the new key's
    id would be a second identity for one work item, so it is refused with both
    paths named."""
    from the_loop.graphlink import SpecFolderConflict, spec_folder_for

    old = WorkItemRef.parse(f"jira:{SITE}/OLD-4")
    new = WorkItemRef.parse(f"jira:{SITE}/NEW-9")
    (tmp_path / "jira-old-4").mkdir()
    with pytest.raises(SpecFolderConflict) as raised:
        spec_folder_for(tmp_path, new, moved_from=[old])
    message = str(raised.value)
    assert str(tmp_path / "jira-old-4") in message
    assert str(tmp_path / "jira-new-9") in message
    assert not (tmp_path / "jira-new-9").exists()


def test_spec_folder_for_an_unmoved_or_fresh_ref(tmp_path):
    from the_loop.graphlink import spec_folder_for

    new = WorkItemRef.parse(f"jira:{SITE}/NEW-9")
    old = WorkItemRef.parse(f"jira:{SITE}/OLD-4")
    assert spec_folder_for(tmp_path, new) == tmp_path / "jira-new-9"
    # the old key never had a folder here: nothing to conflict with
    assert spec_folder_for(tmp_path, new, moved_from=[old]) == tmp_path / "jira-new-9"
    gh = WorkItemRef.parse("github:octo/repo#3")
    assert spec_folder_for(tmp_path, gh) == tmp_path / "issue-3"


def test_spec_folder_for_a_provider_without_a_convention_is_none(tmp_path):
    from the_loop.graphlink import spec_folder_for

    assert spec_folder_for(tmp_path, WorkItemRef.parse("gitlab:o/r#1")) is None
