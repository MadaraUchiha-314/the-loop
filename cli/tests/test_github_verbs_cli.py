"""`the-loop comment` · `ticket` · `pr` · `sessions link-pr --discover` (issue-447, T3).

In-process (the suite's ``THE_LOOP_SERVICE_LOCAL=1``) over the fake client, which
stands in for the process-wide client every writer resolves. The routing choice
itself — the service when one answers, in-process with a note otherwise — is
tested on :func:`~the_loop.client.routing.harness_routed` directly.
"""

from __future__ import annotations

import io
import json
import subprocess

import pytest
import yaml

from ghfakes import FakeGitHubClient
from the_loop import cli_config
from the_loop.authz import SELF_COMMENT_MARKER
from the_loop.cli import main
from the_loop.client import routing
from the_loop.ghapi import GitHubClient
from the_loop.migrations import CURRENT_CONFIG_VERSION

REF = "github:octo/repo#5"
SHA = "b" * 40


@pytest.fixture(autouse=True)
def _no_config_override_leaks():
    """`main(["--config", …])` sets a process-wide override; clear it after."""
    yield
    cli_config.set_override(None)


@pytest.fixture
def fake(monkeypatch):
    client = FakeGitHubClient()
    monkeypatch.setattr(
        GitHubClient, "shared", classmethod(lambda cls, *a, **k: client)
    )
    return client


@pytest.fixture
def config(tmp_path):
    def write(**routing_block):
        path = tmp_path / "cli-config.yaml"
        data = {
            "version": CURRENT_CONFIG_VERSION,
            "state": {"root": str(tmp_path / ".the-loop")},
        }
        if routing_block:
            data["routing"] = routing_block
        path.write_text(yaml.safe_dump(data))
        return str(path)

    return write


def _register_argv(cwd):
    return [
        "sessions",
        "register",
        "--work-item",
        REF,
        "--harness",
        "claude",
        "--harness-session-id",
        "s1",
        "--cwd",
        str(cwd),
    ]


def _cli(config_path, *argv):
    return main(["--config", config_path, *argv])


# -- comment ---------------------------------------------------------------------


def test_comment_posts_the_marked_body_and_prints_its_url(fake, config, capsys):
    assert _cli(config(), "comment", "--work-item", REF, "--body", "Ready.") == 0
    assert fake.posted and SELF_COMMENT_MARKER in fake.posted[0][3]
    assert fake.comment_url in capsys.readouterr().out


def test_comment_reads_a_body_file_from_stdin(fake, config, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("line one\nline two\n"))
    assert _cli(config(), "comment", "--work-item", REF, "--body-file", "-") == 0
    assert "line one\nline two" in fake.posted[0][3]


def test_comment_needs_exactly_one_body(fake, config):
    with pytest.raises(SystemExit) as exc:
        _cli(config(), "comment", "--work-item", REF)
    assert exc.value.code == 2


def test_an_empty_comment_is_exit_2_before_a_request(fake, config, capsys):
    assert _cli(config(), "comment", "--work-item", REF, "--body", " ") == 2
    assert fake.calls == []
    assert "empty" in capsys.readouterr().err


def test_a_missing_body_file_is_exit_2(fake, config, tmp_path):
    missing = str(tmp_path / "nope.md")
    assert _cli(config(), "comment", "--work-item", REF, "--body-file", missing) == 2


def test_a_github_refusal_is_exit_1(fake, config, capsys):
    fake.missing.add(("octo", "repo", 5))
    assert _cli(config(), "comment", "--work-item", REF, "--body", "hi") == 1
    assert "Not Found" in capsys.readouterr().err


# -- ticket --------------------------------------------------------------------


def test_ticket_show_prints_json(fake, config, capsys):
    fake.states[("octo", "repo", 5)] = {"number": 5, "title": "T", "body": "B"}
    assert _cli(config(), "ticket", "show", REF) == 0
    data = json.loads(capsys.readouterr().out)
    assert (data["title"], data["body"], data["comments"]) == ("T", "B", [])
    assert "exitCode" not in data and "messages" not in data


def test_ticket_create_prints_the_new_ref(fake, config, capsys):
    argv = ["ticket", "create", "--repository", "octo/repo", "--title", "T"]
    argv += ["--body", "B", "--label", "loop:requirements-definition"]
    assert _cli(config(), *argv) == 0
    assert "github:octo/repo#42" in capsys.readouterr().out
    assert fake.created[0][4] == ["loop:requirements-definition"]


# -- pr --------------------------------------------------------------------------


def _git_checkout(path, branch):
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/repo.git",
        ],
        check=True,
    )


def test_pr_create_opens_from_the_checked_out_branch(
    fake, config, tmp_path, monkeypatch, capsys
):
    checkout = tmp_path / "checkout"
    _git_checkout(checkout, "claude/issue-5")
    monkeypatch.chdir(checkout)
    path = config()
    argv = ["pr", "create", "--work-item", REF, "--title", "T", "--body", "B"]
    assert _cli(path, *argv) == 1  # R1.10: no registered work item, nothing opened
    assert fake.opened == []
    _cli(path, *_register_argv(checkout))
    capsys.readouterr()
    assert _cli(path, *argv) == 0
    assert fake.opened[0]["head"] == "claude/issue-5"
    assert fake.opened[0]["base"] == "main"  # the repository's default branch
    captured = capsys.readouterr()
    assert "github:octo/repo#12" in captured.out
    assert "recorded github:octo/repo#12" in captured.out


def test_pr_create_on_a_detached_head_is_exit_2(fake, config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # not a checkout at all
    argv = ["pr", "create", "--work-item", REF, "--title", "T", "--body", "B"]
    assert _cli(config(), *argv) == 2
    assert fake.calls == []


def test_pr_status_prints_json(fake, config, capsys):
    fake.pulls[("octo", "repo", 12)] = {"state": "open", "head": {"sha": SHA}}
    fake.statuses[SHA] = [{"context": "ci", "state": "pending"}]
    assert _cli(config(), "pr", "status", "12", "--work-item", REF) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["conclusion"] == "pending"


def test_pr_status_of_a_bare_number_without_a_work_item_is_exit_2(fake, config):
    assert _cli(config(), "pr", "status", "12") == 2


def test_pr_threads_prints_json(fake, config, capsys):
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": False}]
    assert _cli(config(), "pr", "threads", "github:octo/repo#12") == 0
    assert json.loads(capsys.readouterr().out)["threads"][0]["id"] == "PRRT_1"


def test_pr_merge_obeys_the_operators_policy(fake, config, tmp_path, capsys):
    assert (
        _cli(config(mergeOnApproval=False), "pr", "merge", "github:octo/repo#12") == 1
    )
    assert fake.merged == []
    assert "mergeOnApproval" in capsys.readouterr().err
    path = config()
    argv = ["pr", "merge", "github:octo/repo#12", "--method", "squash"]
    assert _cli(path, *argv) == 1  # R1.10: no work item owns the PR
    _cli(path, *_register_argv(tmp_path))
    _cli(path, "sessions", "link-pr", "--work-item", REF, "--pull-request", "12")
    assert _cli(path, *argv) == 0
    assert fake.merged == [("octo", "repo", 12, "squash")]


def test_pr_merge_refuses_an_unknown_method(fake, config):
    with pytest.raises(SystemExit):
        _cli(config(), "pr", "merge", "github:octo/repo#12", "--method", "octopus")


# -- sessions link-pr --discover --------------------------------------------------


def test_link_pr_takes_a_pull_request_or_discover_not_both(fake, config):
    with pytest.raises(SystemExit):
        _cli(config(), "sessions", "link-pr", "--work-item", REF)
    with pytest.raises(SystemExit):
        _cli(
            config(),
            "sessions",
            "link-pr",
            "--work-item",
            REF,
            "--pull-request",
            "6",
            "--discover",
        )


def test_link_pr_discover_links_the_branchs_pull_request(
    fake, config, tmp_path, monkeypatch, capsys
):
    checkout = tmp_path / "checkout"
    _git_checkout(checkout, "claude/issue-5")
    monkeypatch.chdir(checkout)
    path = config()
    registry = str(tmp_path / "registry")
    argv = ["sessions", "register", "--work-item", REF, "--harness", "claude"]
    argv += ["--harness-session-id", "s1", "--cwd", str(checkout)]
    assert _cli(path, *argv, "--registry-dir", registry) == 0
    fake.heads[("octo", "repo", "claude/issue-5")] = [
        {"number": 12, "html_url": "https://github.com/octo/repo/pull/12"}
    ]
    capsys.readouterr()
    argv = ["sessions", "link-pr", "--work-item", REF, "--discover"]
    assert _cli(path, *argv, "--registry-dir", registry) == 0
    assert "recorded github:octo/repo#12" in capsys.readouterr().out
    assert fake.calls[-1][1]["branch"] == "claude/issue-5"


def test_link_pr_discover_on_a_detached_head_is_exit_2(
    fake, config, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert _cli(config(), "sessions", "link-pr", "--work-item", REF, "--discover") == 2


# -- harness_routed (R2) ---------------------------------------------------------


@pytest.mark.routed
def test_harness_routed_uses_a_running_service(monkeypatch):
    from the_loop import client

    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)
    monkeypatch.setattr(
        client, "_spawn_service", lambda: pytest.fail("must never auto-start")
    )
    seen = []
    result = routing.harness_routed(
        lambda connection: seen.append(connection) or {"via": "service"},
        lambda: {"via": "local"},
        config={},
    )
    assert result == {"via": "service"} and isinstance(seen[0], client.Client)


@pytest.mark.routed
def test_abuse_447_a5_the_in_process_fallback_is_never_silent(monkeypatch, capsys):
    from the_loop import client

    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: False)
    monkeypatch.setattr(
        client, "_spawn_service", lambda: pytest.fail("must never auto-start")
    )
    result = routing.harness_routed(
        lambda _c: pytest.fail("no service to route to"),
        lambda: {"via": "local"},
        config={},
    )
    assert result == {"via": "local"}
    assert routing.IN_PROCESS_NOTE in capsys.readouterr().err


@pytest.mark.routed
def test_a_routed_verb_maps_a_400_to_exit_2(monkeypatch, config, capsys):
    from the_loop import client

    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)

    def refuse(self, path, body):
        raise client.ApiError(400, "the comment is empty")

    monkeypatch.setattr(client.Client, "post", refuse)
    assert _cli(config(), "comment", "--work-item", REF, "--body", "x") == 2
    assert "the comment is empty" in capsys.readouterr().err


@pytest.mark.routed
def test_a_service_older_than_the_verb_falls_back_loudly(monkeypatch, capsys):
    """Review L6 — a running service without the route is not a hard error."""
    from the_loop import client

    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)

    def old_service(_connection):
        raise client.ApiError(404, "Not Found")

    result = routing.harness_routed(old_service, lambda: {"via": "local"}, config={})
    assert result == {"via": "local"}
    assert routing.STALE_SERVICE_NOTE in capsys.readouterr().err


@pytest.mark.routed
def test_a_real_404_from_the_service_is_not_swallowed(monkeypatch):
    from the_loop import client

    monkeypatch.setattr(client, "healthy", lambda *_a, **_k: True)

    def foreign(_connection):
        raise client.ApiError(404, "instance 'x' is not this one")

    with pytest.raises(client.ApiError):
        routing.harness_routed(foreign, lambda: pytest.fail("no fallback"), config={})


def test_discovery_ignores_an_origin_that_is_not_on_github(tmp_path):
    from the_loop.ghhost import origin_github_repo

    def reader(url):
        return lambda _root: url

    hosts = ["github.com"]
    assert (
        origin_github_repo(tmp_path, hosts, reader("https://github.com/Octo/App.git"))
        == "octo/app"
    )
    assert (
        origin_github_repo(tmp_path, hosts, reader("git@github.com:o/r.git")) == "o/r"
    )
    assert (
        origin_github_repo(tmp_path, hosts, reader("git@gitlab.com:team/app.git")) == ""
    )
    assert (
        origin_github_repo(tmp_path, hosts, reader("http://proxy@127.0.0.1:9/git/o/r"))
        == ""
    )
    assert origin_github_repo(tmp_path, hosts, reader("/srv/mirror/app")) == ""


def test_ticket_close_and_pr_resolve_thread(fake, config, tmp_path, capsys):
    path = config()
    _cli(path, *_register_argv(tmp_path))
    _cli(path, "sessions", "link-pr", "--work-item", REF, "--pull-request", "12")
    fake.threads[("octo", "repo", 12)] = [{"id": "PRRT_1", "isResolved": False}]
    argv = ["pr", "resolve-thread", "12", "--work-item", REF, "--thread", "PRRT_1"]
    assert _cli(path, *argv) == 0
    assert _cli(path, "ticket", "close", REF, "--reason", "not_planned") == 0
    assert fake.resolved == ["PRRT_1"]
    assert fake.closed == [("octo", "repo", 5, "not_planned")]


def test_link_pr_discover_passes_a_fork_head_owner(fake, config, tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    _git_checkout(checkout, "feat/x")
    monkeypatch.chdir(checkout)
    path = config()
    _cli(path, *_register_argv(checkout))
    fake.heads[("octo", "repo", "me:feat/x")] = [{"number": 21}]
    argv = [
        "sessions",
        "link-pr",
        "--work-item",
        REF,
        "--discover",
        "--head-owner",
        "me",
    ]
    assert _cli(path, *argv) == 0
    assert fake.calls[-1][1]["head_owner"] == "me"
