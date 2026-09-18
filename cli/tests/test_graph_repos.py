"""`the-loop graph repos` — the agent declares where the code lands (issue-365).

Feature: one work item, several repositories

The declaration `await-inner-loops` reads (issue-183) had two homes before this
one, and both were wrong for the same reason in opposite directions: an
artifact's front matter (anyone who can edit a file answers it) and the
`phase-selection` checklist (asked at the one moment nobody can know the answer,
because `design.md` and `tasks.md` do not exist yet).

So it is the **agent's** verb, called once the task DAG says what the change
spans. What is tested here is the whole of the trust boundary — a value that
becomes a directory name under `pr-loops/` and a repository a gate waits on — plus
the property that makes it usable: the flags are the full set, not an append.
"""

from __future__ import annotations

import pytest

from the_loop.core import graphs
from the_loop.graph.state import WorkItemState


@pytest.fixture(autouse=True)
def _unbounded_instance(tmp_path, monkeypatch):
    """No `repositories` declared, so the bound is shape alone.

    Pinned rather than inherited: this repository's own CLI config declares
    `repositories`, and a test that picked it up would be asserting against
    whatever this checkout happens to be configured for.
    """
    config = tmp_path / "cli-config-empty.yaml"
    config.write_text("version: '0.10.0'\n", encoding="utf-8")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config))


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-15").mkdir(parents=True)
    return tmp_path


def _declared(repo) -> list:
    return WorkItemState.load(repo / "docs" / "specs" / "issue-15", "issue-15").repos


def test_declaring_writes_the_work_item_state(repo):
    """
    Feature: one work item, several repositories
    Scenario: the agent declares the repositories the change spans
      Given a work item whose task DAG touches two repositories
      When the agent declares them
      Then they are recorded in the work item's own state, in the order given
    Requirement: docs/specs/issue-365/requirements.md#R3.1
    """
    result = graphs.repos(str(repo), "issue-15", ["octo/app", "octo/infra"])
    assert result["declared"] == ["octo/app", "octo/infra"]
    assert _declared(repo) == ["octo/app", "octo/infra"]


def test_reading_it_back_writes_nothing(repo):
    graphs.repos(str(repo), "issue-15", ["octo/app"])
    assert graphs.repos(str(repo), "issue-15")["declared"] == ["octo/app"]
    assert _declared(repo) == ["octo/app"]


def test_the_flags_are_the_full_set_not_an_append(repo):
    """An agent that learns of a third repository states all three — so a
    declaration can be CORRECTED, which an append could never do."""
    graphs.repos(str(repo), "issue-15", ["octo/app", "octo/typo"])
    graphs.repos(str(repo), "issue-15", ["octo/app", "octo/infra"])
    assert _declared(repo) == ["octo/app", "octo/infra"]


def test_clear_declares_none(repo):
    graphs.repos(str(repo), "issue-15", ["octo/app"])
    result = graphs.repos(str(repo), "issue-15", clear=True)
    assert result["declared"] == [] and result["previous"] == ["octo/app"]
    assert _declared(repo) == []


def test_a_repeated_repository_is_declared_once(repo):
    graphs.repos(str(repo), "issue-15", ["octo/app", "octo/app"])
    assert _declared(repo) == ["octo/app"]


@pytest.mark.parametrize(
    "value",
    [
        "../etc",
        "..",
        "/etc/passwd",
        "octo/app;rm -rf /",
        "octo/../../etc",
        "octo",
        "",
        "octo/app\nocto/evil",
    ],
)
def test_abuse_a_value_that_is_not_a_repository_path_is_refused(repo, value):
    """
    Feature: one work item, several repositories
    Scenario: a declaration that would become a path is refused, not sanitized
      Given a value that is not `<owner>/<repo>`
      When it is declared
      Then nothing is written and the refusal names the entry
    Requirement: docs/specs/issue-365/requirements.md#R3.3

    The value becomes a directory name under `pr-loops/`, so it goes through
    `repo_state_key` — the boundary that refuses `.` and `..`, which the
    repository-name grammar alone admits — before anything else looks at it.
    """
    result = graphs.repos(str(repo), "issue-15", [value])
    assert result["declared"] == []
    assert result["rejected"] and result["rejected"][0]["repo"] == value
    assert _declared(repo) == []


def test_one_bad_entry_declares_nothing_at_all(repo):
    """All or nothing: a partial declaration is a gate waiting on a set nobody
    chose, and a half-applied correction is worse than a refused one."""
    graphs.repos(str(repo), "issue-15", ["octo/app"])
    result = graphs.repos(str(repo), "issue-15", ["octo/infra", "../etc"])
    assert result["declared"] == []
    assert _declared(repo) == ["octo/app"], "the previous declaration stands"


def test_a_repository_this_instance_never_declared_is_refused(
    repo, tmp_path, monkeypatch
):
    """Nothing routes events for an undeclared repository, so its inner loop
    would never start and the gate would wait forever. Refusing at declaration
    time, naming the set, is the difference between a message and a hang."""
    config = tmp_path / "cli-config.yaml"
    config.write_text(
        "version: '0.10.0'\nrepositories:\n  - octo/app\n", encoding="utf-8"
    )
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config))
    result = graphs.repos(str(repo), "issue-15", ["octo/elsewhere"])
    assert result["declared"] == []
    assert "repositories" in result["rejected"][0]["why"]


def test_an_instance_that_declared_nothing_bounds_nothing(repo):
    """`repositories` empty means the instance is unbounded (repos.py's own
    rule), so the declaration is bounded by shape alone."""
    assert graphs.repos(str(repo), "issue-15", ["any/where"])["declared"] == [
        "any/where"
    ]
