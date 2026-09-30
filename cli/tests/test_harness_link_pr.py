"""The PostToolUse hook that records the pull requests a session opened
(issue-370, made trigger-agnostic by issue-447).

The hook replaces a prose rule with a guarantee, so what it has to prove is
mostly about *not* acting: every degraded input is a silent exit 0 that runs
nothing. What it does do it does by **asking** — `sessions link-pr --discover`
lists the branch's open pull requests on GitHub — so it parses no tool's output
and knows nothing of `gh`.

Loaded by path like `the-loop-gate.py`, and for the same reason: it ships with
the plugin, not with the CLI.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "the-loop-link-pr.py"
HOOKS_JSON = Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"

WORK_ITEM = "github:octo/app#370"


def load_hook():
    spec = importlib.util.spec_from_file_location("the_loop_link_pr", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook():
    return load_hook()


@pytest.fixture
def runs(hook, monkeypatch):
    """Every argv the hook would have executed, with `the-loop` present."""
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(argv, cwd=None):
        calls.append(list(argv))
        return _Proc()

    monkeypatch.setattr(hook, "_run", fake_run)
    monkeypatch.setattr(hook.shutil, "which", lambda _: "/usr/bin/the-loop")
    return calls


def bash_payload(
    command="gh pr create --fill",
    stdout="https://github.com/octo/app/pull/412\n",
    **extra,
):
    payload = {
        "session_id": "sess-1",
        "cwd": "/checkout",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
    }
    payload.update(extra)
    return payload


def run_main(hook, monkeypatch, payload, capsys):
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        type("_In", (), {"read": staticmethod(lambda: json.dumps(payload))})(),
    )
    code = hook.main()
    return code, capsys.readouterr().out


# -- T9: it records what was created -------------------------------------------


DISCOVER = ["the-loop", "sessions", "link-pr", "--work-item", WORK_ITEM, "--discover"]


def test_the_stated_work_item_discovers_its_pull_requests(
    hook, runs, monkeypatch, capsys
):
    """T9, R4.1/R4.3; issue-447 R4.3 — `THE_LOOP_WORK_ITEM` is the first and
    best answer, and the hook asks GitHub rather than reading `gh`'s output."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    code, _ = run_main(hook, monkeypatch, bash_payload(), capsys)
    assert code == 0
    assert runs == [DISCOVER]


def test_a_recorded_link_is_told_to_the_agent(hook, monkeypatch, capsys):
    """issue-447 R4.3 — the CLI's own `recorded …` line reaches the transcript."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    monkeypatch.setattr(hook.shutil, "which", lambda _: "/usr/bin/the-loop")
    seen = {}

    def fake_run(argv, cwd=None):
        seen["cwd"] = cwd
        return type(
            "_P",
            (),
            {
                "returncode": 0,
                "stdout": "recorded github:octo/app#412 as delivering "
                + WORK_ITEM
                + "\n",
                "stderr": "",
            },
        )()

    monkeypatch.setattr(hook, "_run", fake_run)
    code, out = run_main(hook, monkeypatch, bash_payload(cwd="/"), capsys)
    assert code == 0 and "the-loop: recorded github:octo/app#412" in out
    assert seen["cwd"] == "/"  # the branch is the session's checkout's


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            bash_payload(command="git push -u origin claude/x"), id="git-push"
        ),
        pytest.param(
            bash_payload(command="git add -A && git commit -m x && git push"),
            id="push-in-a-chain",
        ),
        pytest.param(bash_payload(command="gh pr create --fill"), id="gh-pr-create"),
        pytest.param(bash_payload(command="hub pull-request -m x"), id="hub"),
        pytest.param(
            bash_payload(command="gh pr create --fill", stdout="no URL at all"),
            id="no-url-needed",
        ),
        pytest.param(
            {
                "session_id": "sess-1",
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {"title": "x"},
                "tool_response": {"html_url": "https://github.com/octo/lib/pull/7"},
            },
            id="mcp",
        ),
    ],
)
def test_anything_that_can_open_a_pull_request_triggers_discovery(
    hook, runs, monkeypatch, capsys, payload
):
    """issue-447 R4.3 — trigger-agnostic: a push, any `pr create`, an MCP tool."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    run_main(hook, monkeypatch, payload, capsys)
    assert runs == [DISCOVER]


def test_the_registry_answers_when_the_environment_does_not(
    hook, runs, monkeypatch, capsys
):
    """T9, R4.3 — harness session id first, then the working directory."""
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    rows = [
        {
            "workItem": {"ref": "github:octo/app#1"},
            "harnessSessionId": "other",
            "cwd": "/elsewhere",
            "status": "active",
        },
        {
            "workItem": {"ref": WORK_ITEM},
            "harnessSessionId": "sess-1",
            "cwd": "/checkout",
            "status": "active",
        },
    ]
    monkeypatch.setattr(hook, "_registered_sessions", lambda: rows)
    _, _ = run_main(hook, monkeypatch, bash_payload(), capsys)
    assert runs[-1][runs[-1].index("--work-item") + 1] == WORK_ITEM

    runs.clear()
    rows[1]["harnessSessionId"] = "not-this-session"
    _, _ = run_main(hook, monkeypatch, bash_payload(), capsys)
    assert runs[-1][runs[-1].index("--work-item") + 1] == WORK_ITEM  # matched on cwd

    runs.clear()
    rows[1]["cwd"] = "/somewhere-else"
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")
    assert runs == []  # no answer is silence, never a guess


def test_a_closed_session_record_never_claims_the_pull_request(
    hook, runs, monkeypatch, capsys
):
    """R4.3 — a finished work item's checkout must not adopt a new PR."""
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    monkeypatch.setattr(
        hook,
        "_registered_sessions",
        lambda: [
            {
                "workItem": {"ref": WORK_ITEM},
                "harnessSessionId": "sess-1",
                "cwd": "/checkout",
                "status": "closed",
            }
        ],
    )
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")
    assert runs == []


# -- T10: everything else is a silent no-op ------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(bash_payload(command="ls -la"), id="not-a-pr-command"),
        pytest.param(bash_payload(command="git status"), id="git-but-no-push"),
        pytest.param(bash_payload(command="gh pr create --dry-run"), id="dry-run"),
        pytest.param(
            bash_payload(
                command="the-loop pr create --work-item github:octo/app#370 --title x"
            ),
            id="the-loops-own-verb-links-itself",
        ),
        pytest.param({"tool_name": "Read"}, id="unrelated-tool"),
        pytest.param({}, id="empty-payload"),
    ],
)
def test_a_tool_call_that_created_nothing_runs_nothing(
    hook, runs, monkeypatch, capsys, payload
):
    """T10, R4.2/R4.4; issue-447 R4.4 — nothing that cannot open a PR, and
    not the-loop's own verb, which links the PR it opens."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    assert run_main(hook, monkeypatch, payload, capsys) == (0, "")
    assert runs == []


def test_dry_run_is_a_flag_not_a_word_in_the_title(hook, runs, monkeypatch, capsys):
    """T10 — the guard must not silently skip a real creation over its title text."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    run_main(
        hook,
        monkeypatch,
        bash_payload(command='gh pr create --title "support --dry-run"'),
        capsys,
    )
    assert runs == [DISCOVER]


def test_an_interrupted_creation_links_nothing(hook, runs, monkeypatch, capsys):
    """T10, R4.2 — an interrupted tool call is not an outcome."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = bash_payload()
    payload["tool_response"]["interrupted"] = True
    assert run_main(hook, monkeypatch, payload, capsys) == (0, "")
    assert runs == []


def test_malformed_stdin_is_not_an_error(hook, runs, monkeypatch, capsys):
    """T10, R4.2 — a payload the hook cannot read is a no-op, not an exit 2."""
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        type("_In", (), {"read": staticmethod(lambda: "{not json")})(),
    )
    assert hook.main() == 0
    assert runs == []


def test_a_missing_cli_is_a_no_op(hook, monkeypatch, capsys):
    """T10, R4.2 — the plugin must survive the CLI not being installed."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    monkeypatch.setattr(hook.shutil, "which", lambda _: None)
    calls: list[list[str]] = []
    monkeypatch.setattr(hook, "_run", lambda argv, cwd=None: calls.append(list(argv)))
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")
    assert calls == []


def test_a_failing_link_is_reported_by_saying_nothing(hook, monkeypatch, capsys):
    """R4.4 — best-effort: a failed link never interrupts the session."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    monkeypatch.setattr(hook.shutil, "which", lambda _: "/usr/bin/the-loop")
    monkeypatch.setattr(
        hook,
        "_run",
        lambda argv, cwd=None: type(
            "_P", (), {"returncode": 1, "stdout": "", "stderr": "nope"}
        )(),
    )
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")


# -- T15 / T13: the contract around it -----------------------------------------


def test_the_hook_is_stdlib_only_so_it_survives_a_missing_cli():
    """T15, R4.2 — same contract as the gate wrapper."""
    source = HOOK.read_text(encoding="utf-8")
    assert "import the_loop" not in source
    assert "from the_loop" not in source
    assert "shell=True" not in source


def test_abuse_447_a6_no_response_text_reaches_the_argv(
    hook, runs, monkeypatch, capsys
):
    """T15; issue-447 A6 — the argv is fixed words plus a validated ref, so
    nothing a tool printed can reach it, let alone a shell."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = bash_payload(
        stdout="https://github.com/octo/app;rm -rf ~/pull/412 $(evil) `x`"
    )
    run_main(hook, monkeypatch, payload, capsys)
    assert runs == [DISCOVER]


def test_an_injected_work_item_ref_is_refused(hook, runs, monkeypatch, capsys):
    """T15 — `THE_LOOP_WORK_ITEM` is validated, not trusted."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", "github:octo/app#370 --flag")
    monkeypatch.setattr(hook, "_registered_sessions", list)
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")
    assert runs == []


def test_the_plugin_declares_the_hook():
    """T13 — a hook nothing wires up is a file, not a guarantee."""
    declared = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    entries = declared["PostToolUse"]
    commands = [h["command"] for entry in entries for h in entry["hooks"]]
    assert any("the-loop-link-pr.py" in command for command in commands)
    assert any("create_pull_request" in entry["matcher"] for entry in entries)
    assert HOOK.exists()


# -- issue-447 review: segments, and the MCP call's own scope --------------------


@pytest.mark.parametrize(
    "command, expected",
    [
        ('git commit -m "add the-loop pr create" && git push', True),
        ("git push -u origin loop/447-the-loop-pr-create", True),
        ('git push origin HEAD && gh pr create --title "the-loop pr create"', True),
        ("the-loop --config c.yaml pr create --title t", False),
        ("echo git push", False),
        ("git pushx", False),
        ("GIT_TRACE=1 git -C /x push", True),
    ],
)
def test_the_trigger_is_decided_per_segment(hook, command, expected):
    """issue-447 R4.3/R4.4 — a message or branch that merely mentions the verb
    neither suppresses a real push nor triggers on its own."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    assert hook.should_discover(payload) is expected


def test_an_mcp_creation_is_discovered_on_its_own_head_and_repository(
    hook, runs, monkeypatch, capsys
):
    """issue-447 R4.3 — the PR an MCP tool opened need not be the checkout's."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "octo", "repo": "lib", "head": "me:feat/x"},
    }
    run_main(hook, monkeypatch, payload, capsys)
    assert runs == [
        DISCOVER
        + ["--branch", "feat/x", "--head-owner", "me", "--repository", "octo/lib"]
    ]


def test_abuse_447_a6_hostile_mcp_input_never_reaches_the_argv(
    hook, runs, monkeypatch, capsys
):
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "octo;rm", "repo": "lib", "head": "--exec=x"},
    }
    run_main(hook, monkeypatch, payload, capsys)
    assert runs == [DISCOVER]
