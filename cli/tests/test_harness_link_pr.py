"""The PostToolUse hook that records a pull request the session opened (issue-370).

The hook replaces a prose rule with a guarantee, so what it has to prove is
mostly about *not* acting: every degraded input is a silent exit 0 that runs
nothing. The one thing it must do, it must do from the tool's **response** — the
URL the creation returned — never from the command string, which cannot tell a
successful `gh pr create` from a failed one.

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

    def fake_run(argv):
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


def test_the_stated_work_item_is_linked_to_the_created_pull_request(
    hook, runs, monkeypatch, capsys
):
    """T9, R4.1/R4.3 — `THE_LOOP_WORK_ITEM` is the first and best answer."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    code, out = run_main(hook, monkeypatch, bash_payload(), capsys)
    assert code == 0
    assert runs == [
        [
            "the-loop",
            "sessions",
            "link-pr",
            "--work-item",
            WORK_ITEM,
            "--pull-request",
            "412",
        ]
    ]
    assert "412" in out and WORK_ITEM in out


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


# -- T11: the cross-repository shape -------------------------------------------


def test_a_pull_request_in_another_repository_is_named_by_its_full_ref(
    hook, runs, monkeypatch, capsys
):
    """T11, R4.1 — a number alone cannot say which repository it is in."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = {
        "session_id": "sess-1",
        "cwd": "/checkout",
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"title": "x"},
        "tool_response": {"html_url": "https://github.com/octo/lib/pull/7"},
    }
    run_main(hook, monkeypatch, payload, capsys)
    assert runs[-1][-1] == "github:octo/lib#7"


def test_an_enterprise_host_is_carried_into_the_ref(hook):
    """R4.1 — github.com stays unwritten; anything else does not."""
    assert (
        hook.pull_request_argument(WORK_ITEM, ("ghe.corp.example", "octo", "lib", 7))
        == "github:ghe.corp.example/octo/lib#7"
    )
    assert (
        hook.pull_request_argument(WORK_ITEM, ("github.com", "octo", "app", 9)) == "9"
    )


# -- T10: everything else is a silent no-op ------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(bash_payload(command="ls -la"), id="not-a-pr-command"),
        pytest.param(bash_payload(command="gh pr create --dry-run"), id="dry-run"),
        pytest.param(bash_payload(stdout="failed: no commits"), id="no-url-returned"),
        pytest.param({"tool_name": "Read"}, id="unrelated-tool"),
        pytest.param({}, id="empty-payload"),
    ],
)
def test_a_tool_call_that_created_nothing_runs_nothing(
    hook, runs, monkeypatch, capsys, payload
):
    """T10, R4.2/R4.4 — the hook reads the result, so intent alone never links."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    assert run_main(hook, monkeypatch, payload, capsys) == (0, "")
    assert runs == []


def test_an_interrupted_creation_links_nothing(hook, runs, monkeypatch, capsys):
    """T10, R4.2 — an interrupted tool call's output is not an outcome."""
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
    monkeypatch.setattr(hook, "_run", lambda argv: calls.append(list(argv)))
    assert run_main(hook, monkeypatch, bash_payload(), capsys) == (0, "")
    assert calls == []


def test_a_failing_link_is_reported_by_saying_nothing(hook, monkeypatch, capsys):
    """R4.4 — best-effort: a failed link never interrupts the session."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    monkeypatch.setattr(hook.shutil, "which", lambda _: "/usr/bin/the-loop")
    monkeypatch.setattr(
        hook,
        "_run",
        lambda argv: type(
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


def test_a_payload_can_never_reach_a_shell(hook, runs, monkeypatch, capsys):
    """T15 — the extracted coordinates are validated before they reach an argv."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", WORK_ITEM)
    payload = bash_payload(
        stdout="https://github.com/octo/app;rm -rf ~/pull/412 https://github.com/octo/app/pull/412"
    )
    run_main(hook, monkeypatch, payload, capsys)
    assert runs[-1][-1] == "412"
    assert all(";" not in part for part in runs[-1])


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
