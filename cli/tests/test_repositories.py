"""Unit tests for issue-348: the repositories this instance works with are declared
once, at the top level, and every ingress reads that one list.

Spec: docs/specs/issue-348/{requirements,design,testing-plan}.md (rows T1, T11).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from the_loop import repos

DECLARED = [
    "expertise-help/slim-gym",
    "jchou2/devbox",
    "ghe.corp.example/team/service",
]


def config_map(declared=DECLARED, **extra):
    cfg = {"repositories": list(declared)}
    cfg.update(extra)
    return cfg


# -- the declaration (R1.1, R1.4, R1.5) ---------------------------------------------


def test_the_declared_set_is_the_top_level_key():
    declared = repos.declared_repositories(config_map())
    assert [d.declared for d in declared] == DECLARED
    assert {d.source for d in declared} == {"repositories"}


def test_the_set_is_deduplicated_by_key():
    """First writing wins, so the slug the operator wrote first is the one used."""
    declared = repos.declared_repositories(
        config_map(["octo/app", "github.com/octo/app", "OCTO/APP", "octo/lib"])
    )
    assert [d.declared for d in declared] == ["octo/app", "octo/lib"]


def test_a_declared_entry_keeps_the_operators_own_slug():
    """What reaches ``gh --repo`` is their string, never a normalisation (R1.5)."""
    declared = repos.declared_repositories(config_map(["ghe.corp.example/team/svc"]))
    assert declared[0].declared == "ghe.corp.example/team/svc"
    assert declared[0].key == "ghe.corp.example/team/svc"


# -- the grammar (R1.2) -------------------------------------------------------------


def test_a_bare_entry_takes_this_instances_host():
    declared = repos.declared_repositories(config_map(["octo/app"]))
    assert declared[0].host == "github.com"
    assert declared[0].key == "github.com/octo/app"


def test_a_bare_entry_takes_a_configured_enterprise_host():
    cfg = config_map(["octo/app"], integrations={"github": {"host": "ghe.corp"}})
    declared = repos.declared_repositories(cfg)
    assert declared[0].key == "ghe.corp/octo/app"
    assert declared[0].declared == "octo/app"  # still the operator's own string


def test_a_qualified_entry_keeps_its_host():
    declared = repos.declared_repositories(config_map(["ghe.corp/team/svc"]))
    assert declared[0].host == "ghe.corp"


# -- a fault only ever shrinks the set (R1.3, A6, A8) -------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-path",
        "a/b/c/d",
        "",
        "   ",
        "../../etc/passwd",
        "octo/app; rm -rf /",
        "$(id)/app",
        "https://github.com/octo/app",
        "octo//app",
    ],
)
def test_a_malformed_entry_is_skipped(bad):
    """A6 — a value that is not `[host/]owner/repo` never becomes a candidate."""
    declared = repos.declared_repositories(config_map([bad, "o/r"]))
    assert [d.declared for d in declared] == ["o/r"]


def test_an_over_segmented_entry_is_skipped():
    assert repos.declared_repositories(config_map(["a/b/c/d"])) == ()


@pytest.mark.parametrize("broken", ["not-a-list", {"octo": "app"}, 7])
def test_a_broken_section_narrows_rather_than_widens(broken):
    """A8 — an unreadable declaration contributes nothing; it never widens."""
    assert repos.declared_repositories({"repositories": broken}) == ()
    assert repos.repository_bounds({"repositories": broken}) is None


def test_a_missing_config_is_not_an_error():
    assert repos.declared_repositories(None) == ()
    assert repos.repository_keys(None) == set()


# -- the two shapes a caller asks for (R2.3) ----------------------------------------


def test_repository_keys_is_the_declared_set_as_keys():
    cfg = config_map()
    assert repos.repository_keys(cfg) == {
        d.key for d in repos.declared_repositories(cfg)
    }


def test_repository_bounds_is_none_when_nothing_is_declared():
    """ "Declared nothing" and "declared, and this is not in it" are opposite answers
    at an ingress, so an empty set is never the way either is expressed."""
    assert repos.repository_bounds({}) is None
    assert repos.repository_bounds({"repositories": []}) is None


def test_repository_bounds_is_a_set_when_something_is():
    assert repos.repository_bounds(config_map(["octo/app"])) == {"github.com/octo/app"}


# -- the hosts do not admit one another (A7) ----------------------------------------


def test_an_enterprise_host_does_not_admit_its_github_com_namesake():
    """A7 — same owner, same name, different GitHub: two keys, neither in the other."""
    bounds = repos.repository_bounds(config_map(["ghe.corp/octo/app"]))
    assert bounds is not None and bounds == {"ghe.corp/octo/app"}
    assert "github.com/octo/app" not in bounds


# -- the kickoff target no longer declares anything (D2) ----------------------------


def test_kickoff_repo_no_longer_declares_a_repository():
    """It POINTS AT a declared repository now; the migration adds it to the list."""
    cfg = {"channels": {"slack": {"kickoff": {"repo": "octo/app"}}}}
    assert repos.declared_repositories(cfg) == ()


def test_a_polling_source_no_longer_declares_a_repository():
    cfg = {"polling": {"sources": [{"provider": "github", "repos": ["octo/app"]}]}}
    assert repos.declared_repositories(cfg) == ()


# -- the builder is nobody's dependency (R1.6) --------------------------------------


def test_the_builder_imports_without_channels():
    """The webhook router is stdlib-only and I/O-free; it can only read the declared
    set if reading it does not drag a channel's config parser in."""
    code = (
        "import sys; import the_loop.repos as r; "
        "assert r.repository_bounds({'repositories': ['o/r']}); "
        "print(sorted(m for m in sys.modules if m.startswith('the_loop.channels')))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]", out.stdout
