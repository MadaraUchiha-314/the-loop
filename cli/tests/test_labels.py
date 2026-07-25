"""Unit tests for the-loop's GitHub label plumbing (issue-98)."""

import subprocess

import pytest

from the_loop.labels import GitHubLabeler, LabelError, LabelSpec, default_specs
from the_loop.sessions import WorkItemRef

REF = WorkItemRef.parse("github:octo/repo#15")
PAUSED = "the-loop: paused"


class FakeGh:
    """Records argv and replays canned results, like the GhClient fakes."""

    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.results:
            code, out, err = self.results.pop(0)
        else:
            code, out, err = 0, "", ""
        return subprocess.CompletedProcess(cmd, code, out, err)


def labeler(gh, available=True):
    instance = GitHubLabeler(runner=gh)
    instance.is_available = lambda: available  # type: ignore[method-assign]
    return instance


def test_default_specs_use_the_configured_names():
    specs = default_specs("auto!", "paused!")
    assert [spec.name for spec in specs] == ["auto!", "paused!"]
    assert all(len(spec.color) == 6 and spec.description for spec in specs)


def test_default_specs_skip_an_empty_name():
    assert [spec.name for spec in default_specs("", "paused!")] == ["paused!"]


def test_ensure_creates_only_the_missing_labels():
    gh = FakeGh([(0, "bug\nthe-loop: auto-execute\n", "")])
    results = labeler(gh).ensure(
        "octo",
        "repo",
        default_specs("the-loop: auto-execute", PAUSED),
    )
    assert [r.changed for r in results] == [False, True]
    created = [c for c in gh.calls if "POST" in c]
    assert len(created) == 1
    assert f"name={PAUSED}" in created[0]
    assert "repos/octo/repo/labels" in created[0]


def test_ensure_is_idempotent_when_everything_exists():
    gh = FakeGh([(0, f"the-loop: auto-execute\n{PAUSED}\n", "")])
    results = labeler(gh).ensure(
        "octo", "repo", default_specs("the-loop: auto-execute", PAUSED)
    )
    assert not any(r.changed for r in results)
    assert not [c for c in gh.calls if "POST" in c]


def test_ensure_dry_run_writes_nothing():
    gh = FakeGh([(0, "", "")])
    results = labeler(gh).ensure(
        "octo", "repo", default_specs("", PAUSED), dry_run=True
    )
    assert results[0].detail.endswith("would create")
    assert not [c for c in gh.calls if "POST" in c]


def test_ensure_without_gh_is_a_hard_error():
    with pytest.raises(LabelError) as exc:
        labeler(FakeGh(), available=False).ensure(
            "octo", "repo", default_specs("", "p")
        )
    assert "not found on PATH" in str(exc.value)


def test_ensure_surfaces_an_api_failure():
    gh = FakeGh([(1, "", "HTTP 401: Bad credentials")])
    with pytest.raises(LabelError) as exc:
        labeler(gh).ensure("octo", "repo", default_specs("", PAUSED))
    assert "Bad credentials" in str(exc.value)


def test_ensure_rejects_a_bad_repo_before_shelling_out():
    gh = FakeGh()
    with pytest.raises(LabelError):
        labeler(gh).ensure("octo;rm -rf /", "repo", default_specs("", PAUSED))
    assert gh.calls == []


def test_ensure_rejects_a_control_character_in_a_label():
    gh = FakeGh()
    with pytest.raises(LabelError):
        labeler(gh).ensure("octo", "repo", [LabelSpec("bad\nname", "FFFFFF", "x")])
    assert gh.calls == []


def test_add_posts_to_the_issues_endpoint():
    gh = FakeGh()
    result = labeler(gh).add(REF, PAUSED)
    assert result.ok and result.changed
    assert gh.calls[0][1:] == [
        "api",
        "--method",
        "POST",
        "repos/octo/repo/issues/15/labels",
        "-f",
        f"labels[]={PAUSED}",
    ]


def test_remove_deletes_the_url_encoded_label():
    gh = FakeGh()
    result = labeler(gh).remove(REF, PAUSED)
    assert result.ok and result.changed
    assert gh.calls[0][-1] == "repos/octo/repo/issues/15/labels/the-loop%3A%20paused"


def test_remove_of_an_absent_label_is_success_without_change():
    gh = FakeGh([(1, "", "gh: HTTP 404: Label does not exist")])
    result = labeler(gh).remove(REF, PAUSED)
    assert result.ok and not result.changed
    assert result.detail == "label not present"


def test_label_write_failures_are_reported_never_raised():
    gh = FakeGh([(1, "", "HTTP 403: Resource not accessible")])
    result = labeler(gh).add(REF, PAUSED)
    assert result.ok is False
    assert "403" in result.error


def test_label_write_without_gh_is_reported_not_raised():
    result = labeler(FakeGh(), available=False).add(REF, PAUSED)
    assert result.ok is False
    assert "not found on PATH" in result.error


def test_a_non_github_work_item_cannot_be_labelled():
    gh = FakeGh()
    result = labeler(gh).add(WorkItemRef.parse("jira:octo/repo#15"), PAUSED)
    assert result.ok is False
    assert "not a GitHub work item" in result.error
    assert gh.calls == []


def test_labels_on_reads_the_current_label_set():
    gh = FakeGh(
        [(0, '{"labels": [{"name": "bug"}, {"name": "the-loop: paused"}]}', "")]
    )
    assert labeler(gh).labels_on(REF) == ["bug", PAUSED]


def test_labels_on_returns_none_when_it_cannot_read():
    assert labeler(FakeGh([(1, "", "boom")])).labels_on(REF) is None
    assert labeler(FakeGh(), available=False).labels_on(REF) is None
