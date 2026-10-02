"""Regressions for issue-449's Codex integration and operator findings."""

import json
import os
import subprocess
from http.client import RemoteDisconnected
from unittest.mock import Mock

import pytest

from test_harness_gate import load_gate, report
from the_loop import install
from the_loop.codex_support import (
    BEGIN,
    conversation_marker,
    prepare_instructions,
    rollout_path,
)
from the_loop.core.sessions import get_transcript
from the_loop.critics import _extract_output
from the_loop.ghapi import GhItem, GitHubApiError, GitHubClient
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.mcp import mcp_call
from the_loop.harness import CodexAdapter
from the_loop.harness.base import usage_from_output
from the_loop.harness_plugins import PluginConfig
from the_loop.migrations import (
    CURRENT_CONFIG_VERSION,
    migrate_cli_config,
    needs_migration,
)
from the_loop.poller.github import GitHubPollProvider
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef

LAUNCH = "00000000-1111-2222-3333-444444444444"
NATIVE = "99999999-1111-2222-3333-444444444444"
OTHER = "88888888-1111-2222-3333-444444444444"
REF = "github:octo/repo#449"


def write_rollout(root, cwd, native=NATIVE, marker=LAUNCH, extra=()):
    path = root / "sessions/2026/10/02" / f"rollout-2026-10-02-{native}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"type": "session_meta", "payload": {"id": native, "cwd": str(cwd)}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Work on the ticket. {conversation_marker(marker)}",
                    }
                ],
            },
        },
        *extra,
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path / "codex"


def test_resume_uses_the_launch_marker_even_after_an_operator_starts_a_new_chat(
    tmp_path, home
):
    original = write_rollout(home, tmp_path)
    write_rollout(home, tmp_path, OTHER, marker=OTHER)
    adapter = CodexAdapter()
    assert rollout_path(str(tmp_path), LAUNCH) == original.resolve()
    assert adapter.resolve_session_id(str(tmp_path), LAUNCH) == NATIVE
    assert adapter.interactive_resume_argv("continue", NATIVE) == [
        "resume",
        NATIVE,
        "continue",
    ]


@pytest.mark.parametrize("sid", ["../auth", "--last", "", "not-a-uuid"])
def test_rollout_lookup_rejects_unsafe_or_unknown_id(tmp_path, home, sid):
    write_rollout(home, tmp_path)
    assert rollout_path(str(tmp_path), sid) is None


@pytest.mark.parametrize("sid", [LAUNCH, NATIVE])
@pytest.mark.parametrize("cwd", [None, "", "."])
def test_rollout_lookup_requires_explicit_absolute_directory_metadata(
    tmp_path, home, monkeypatch, sid, cwd
):
    monkeypatch.chdir(tmp_path)
    path = write_rollout(home, tmp_path)
    entries = path.read_text().splitlines()
    metadata = json.loads(entries[0])
    if cwd is None:
        metadata["payload"].pop("cwd")
    else:
        metadata["payload"]["cwd"] = cwd
    entries[0] = json.dumps(metadata)
    path.write_text("\n".join(entries) + "\n")
    assert rollout_path(str(tmp_path), sid) is None


def test_rollout_lookup_refuses_a_wrong_cwd_ambiguous_marker_and_escaping_symlink(
    tmp_path, home
):
    original = write_rollout(home, tmp_path / "another-repo")
    assert rollout_path(str(tmp_path), LAUNCH) is None
    original.unlink()
    write_rollout(home, tmp_path)
    duplicate = write_rollout(home, tmp_path, OTHER)
    assert rollout_path(str(tmp_path), LAUNCH) is None
    duplicate.unlink()
    original = write_rollout(home, tmp_path)
    outside = tmp_path / "outside.jsonl"
    original.rename(outside)
    original.symlink_to(outside)
    assert rollout_path(str(tmp_path), LAUNCH) is None


def test_codex_transcript_route_normalizes_text_thinking_and_tool_results(
    tmp_path, home
):
    extra = [
        {
            "type": "response_item",
            "payload": {"type": "reasoning", "summary": [{"text": "Check the tests."}]},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "call_id": "c1",
                "name": "exec_command",
                "arguments": '{"cmd":"pytest"}',
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "passed",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "All tests passed."}],
            },
        },
    ]
    write_rollout(home, tmp_path, extra=extra)
    config = {"state": {"root": str(tmp_path / "state")}}
    SessionRegistry(layout_from_config(config).local_dir).register(
        Session(WorkItemRef.parse(REF), "codex", LAUNCH, str(tmp_path))
    )
    trace = get_transcript(REF, config=config, tail=4)
    assert trace["harnessSessionId"] == NATIVE
    assert trace["truncated"] and trace["totalLines"] == 6
    entries = trace["entries"]
    assert entries[0]["message"]["content"][0]["thinking"] == "Check the tests."
    assert entries[1]["message"]["content"][0]["id"] == "c1"
    assert entries[2]["message"]["content"][0]["tool_use_id"] == "c1"
    assert entries[3]["message"]["content"][0]["text"] == "All tests passed."
    assert "payload" in entries[3]  # retain the original event


def test_jsonl_critic_output_and_usage_ignore_progress_and_malformed_lines():
    events = [
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "intermediate"},
        },
        {"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 5}},
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Final review"},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 30,
                "output_tokens": 10,
            },
        },
    ]
    stdout = "progress\n" + "\n".join(json.dumps(e) for e in events) + "\n{broken"
    assert _extract_output(stdout, "json") == "Final review"
    assert _extract_output(stdout, "text") == "Final review"
    usage = usage_from_output(stdout)
    assert usage.present and usage.total_tokens == 110
    assert usage.cache_read_tokens == 30 and usage.input_tokens == 70
    assert usage.cost_usd == 0  # Codex supplies no dollar cost


def test_instruction_setup_preserves_operator_text_and_hook_choices(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Operator instructions.\n")
    hooks = tmp_path / ".codex/hooks.json"
    hooks.parent.mkdir()
    own_hook = {"hooks": [{"type": "command", "command": "operator-check"}]}
    hooks.write_text(json.dumps({"hooks": {"Stop": [own_hook]}}))
    first = prepare_instructions(str(tmp_path))
    assert first.ok and first.applied
    assert (tmp_path / "AGENTS.md").read_text().startswith("Operator instructions.\n")
    assert json.loads(hooks.read_text())["hooks"]["Stop"][0] == own_hook
    assert len(json.loads(hooks.read_text())["hooks"]["Stop"]) == 2
    second = prepare_instructions(str(tmp_path))
    assert second.ok and not second.applied


def test_native_override_instructions_are_used_without_changing_other_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("lower priority")
    override = tmp_path / "AGENTS.override.md"
    override.write_text("Operator override.\n")
    assert prepare_instructions(str(tmp_path)).ok
    assert "the-loop:codex:start" in override.read_text()
    assert (tmp_path / "AGENTS.md").read_text() == "lower priority"


def test_instruction_setup_rejects_an_escaping_symlink(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("keep me")
    (repo / "AGENTS.md").symlink_to(outside)
    assert not prepare_instructions(str(repo)).ok
    assert outside.read_text() == "keep me"


def test_plugins_opt_out_does_not_create_instructions(tmp_path, home):
    assert (
        CodexAdapter(plugins=PluginConfig(enabled=False))
        .prepare_environment(str(tmp_path))
        .ok
    )
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.parametrize("text", ["not valid toml [", 'projects = "bad"'])
def test_invalid_codex_config_is_not_overwritten(tmp_path, home, text):
    home.mkdir()
    config = home / "config.toml"
    config.write_text(text)
    assert (
        not CodexAdapter(plugins=PluginConfig(enabled=False))
        .prepare_environment(str(tmp_path))
        .ok
    )
    assert config.read_text() == text


def test_toml_escaping_and_symlinked_config_preserve_validity_and_mode(tmp_path, home):
    import tomllib

    home.mkdir()
    target = tmp_path / "dotfiles.toml"
    target.write_text('model = "operator-model"\n')
    target.chmod(0o640)
    (home / "config.toml").symlink_to(target)
    cwd = tmp_path / 'repo"with\\quotes'
    cwd.mkdir()
    assert (
        CodexAdapter(plugins=PluginConfig(enabled=False))
        .prepare_environment(str(cwd))
        .ok
    )
    assert (home / "config.toml").is_symlink()
    assert (
        tomllib.loads(target.read_text())["projects"][os.path.realpath(cwd)][
            "trust_level"
        ]
        == "trusted"
    )
    assert target.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("blocked", [True, False])
def test_codex_stop_hook_returns_valid_json_and_continues_only_for_gate_debt(
    tmp_path, monkeypatch, capsys, blocked
):
    gate = load_gate()
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    monkeypatch.setattr(gate, "run_check", lambda _: report(not blocked))
    monkeypatch.setattr(gate, "attempts_path", lambda *args: tmp_path / "attempts")
    assert gate.main(["gate", "codex"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result.get("decision") == "block") is blocked


def test_codex_stop_hook_outside_a_work_item_returns_empty_json(monkeypatch, capsys):
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    assert load_gate().main(["gate", "codex"]) == 0
    assert json.loads(capsys.readouterr().out) == {}


def test_codex_mcp_delegation_uses_codex_and_reads_its_final_json(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("the_loop.graph.hooks.mcp.shutil.which", lambda b: b)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": '{"ok":true,"result":"done"}',
                    },
                }
            ),
            "",
        )
    )
    monkeypatch.setattr("the_loop.graph.hooks.mcp.subprocess.run", run)
    ctx = HookContext(
        WorkItem(REF, "issue-449", tmp_path),
        {},
        "entry",
        tmp_path,
        params={"harness": "codex", "tool": "test_tool"},
    )
    result = mcp_call(ctx)
    assert result.status == "pass" and result.data["result"] == "done"
    assert run.call_args.args[0][:2] == ["codex", "exec"]
    ctx.params = {"tool": "test_tool"}
    ctx.config = {
        "harnesses": [{"name": "codex", "default": True, "args": ["-a", "never"]}]
    }
    assert mcp_call(ctx).status == "pass"
    argv = run.call_args.args[0]
    assert argv[:2] == ["codex", "exec"]
    # Interactive launch args never reach `codex exec`, which rejects `-a`.
    assert "-a" not in argv and "never" not in argv
    ctx.params = {"harness": "missing", "tool": "test_tool"}
    assert mcp_call(ctx).status == "block"
    assert run.call_count == 2


def test_deprecated_harness_arguments_migrate_even_at_current_schema_version():
    original = {
        "version": CURRENT_CONFIG_VERSION,
        "routing": {
            "harnessArgs": {
                "codex": ["--sandbox", "workspace-write"],
                "claude": ["old"],
            }
        },
        "harnesses": [{"name": "claude", "args": ["operator-choice"]}],
    }
    result = migrate_cli_config(original)
    assert result.changed
    # An undeclared harness is never invented: declaring codex would offer it.
    assert result.config["routing"]["harnessArgs"] == {
        "codex": ["--sandbox", "workspace-write"]
    }
    assert result.config["harnesses"] == [
        {"name": "claude", "args": ["operator-choice"]},
    ]
    assert not needs_migration(result.config)
    assert not migrate_cli_config(result.config).changed
    assert "claude" in original["routing"]["harnessArgs"]


def test_deprecated_harness_arguments_move_onto_a_bare_declaration():
    result = migrate_cli_config(
        {
            "version": CURRENT_CONFIG_VERSION,
            "routing": {"harnessArgs": {"codex": ["-a", "never"]}},
            "harnesses": ["claude", "codex"],
        }
    )
    assert "harnessArgs" not in result.config["routing"]
    assert result.config["harnesses"] == [
        "claude",
        {"name": "codex", "args": ["-a", "never"]},
    ]


def test_deprecated_harness_arguments_never_declare_a_harness():
    config = {
        "version": CURRENT_CONFIG_VERSION,
        "routing": {"harnessArgs": {"claude": ["x"], "codex": []}},
    }
    assert not needs_migration(config)
    result = migrate_cli_config(config)
    assert not result.changed
    assert "harnesses" not in result.config


def test_malformed_deprecated_harness_arguments_are_dropped_once():
    config = {"version": CURRENT_CONFIG_VERSION, "routing": {"harnessArgs": None}}
    assert needs_migration(config)
    result = migrate_cli_config(config)
    assert result.changed and "harnessArgs" not in result.config["routing"]
    assert not needs_migration(result.config)


@pytest.mark.parametrize(
    "query,retries", [("query { viewer { login } }", 2), ("mutation { something }", 1)]
)
def test_disconnected_graphql_retries_a_read_once_but_never_a_write(
    monkeypatch, query, retries
):
    requester = Mock()
    requester.graphql_query.side_effect = [
        RemoteDisconnected("stale socket"),
        ({}, {"data": {"ok": True}}),
    ]
    client = GitHubClient()
    monkeypatch.setattr(client, "_requester", lambda _: requester)
    if retries == 2:
        assert client.graphql(query, {}) == {"ok": True}
    else:
        with pytest.raises(GitHubApiError):
            client.graphql(query, {})
    assert requester.graphql_query.call_count == retries


def test_missing_arming_labels_are_observable_without_widening_the_gate(monkeypatch):
    events = []
    monkeypatch.setattr(
        "the_loop.poller.github.eventlog.emit",
        lambda kind, **fields: events.append((kind, fields)),
    )
    provider = GitHubPollProvider([], ["shared", "mine"])
    item = GhItem(449, "Codex", ["shared"], "", "", False)
    assert not provider._carries_every_label(item)
    assert events[0][0] == "poll.item_filtered"
    assert events[0][1]["missing_labels"] == ["mine"]
    # Reported once per change, not on every poll cycle.
    assert not provider._carries_every_label(item)
    assert len(events) == 1
    assert not provider._carries_every_label(GhItem(449, "Codex", [], "", "", False))
    assert len(events) == 2 and events[1][1]["missing_labels"] == ["mine", "shared"]


def test_codex_install_reports_missing_binary_and_prepares_native_user_surface(
    tmp_path,
):
    missing = install.Env(home=tmp_path, which=lambda _: None)
    steps = install.plan(["codex"], env=missing)
    assert steps[0].state == "failed" and "codex not found" in steps[0].detail
    present = install.Env(home=tmp_path, which=lambda b: b)
    steps = install.plan(["codex"], env=present)
    assert not (tmp_path / ".codex/AGENTS.md").exists()
    assert install.execute(steps, dry_run=True)[0].outcome == "planned"
    assert install.execute(steps, dry_run=False)[0].outcome == "applied"
    assert (tmp_path / ".codex/AGENTS.md").exists()
    assert (tmp_path / ".codex/hooks.json").exists()


def test_spawn_setup_uses_one_user_hook_definition_across_worktrees(tmp_path, home):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    adapter = CodexAdapter()
    assert adapter.prepare_environment(str(first)).ok
    hooks = home / "hooks.json"
    original = hooks.read_text()
    assert adapter.prepare_environment(str(second)).ok
    assert hooks.read_text() == original
    assert not (first / ".codex/hooks.json").exists()
    assert (first / "AGENTS.md").is_file() and (second / "AGENTS.md").is_file()


def _git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def test_spawn_setup_keeps_untracked_instructions_out_of_git(tmp_path, home):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    result = CodexAdapter().prepare_environment(str(repo))
    assert result.ok
    assert "the-loop:codex:start" in (repo / "AGENTS.md").read_text()
    assert "/AGENTS.md" in (repo / ".git/info/exclude").read_text().splitlines()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""


@pytest.mark.parametrize("filename", ["AGENTS.md", "AGENTS.override.md"])
@pytest.mark.parametrize("global_filename", ["AGENTS.md", "AGENTS.override.md"])
def test_spawn_setup_preserves_tracked_instructions_and_uses_global_file(
    tmp_path, home, filename, global_filename
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / filename).write_text("Project rules.\n")
    _git(repo, "add", filename)
    _git(repo, "commit", "-qm", "rules")
    home.mkdir()
    global_agents = home / global_filename
    global_agents.write_text("Operator rules.\n")
    result = CodexAdapter().prepare_environment(str(repo))
    assert result.ok
    assert (repo / filename).read_text() == "Project rules.\n"
    assert global_agents.read_text().startswith("Operator rules.\n")
    assert BEGIN in global_agents.read_text()
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        == ""
    )
    assert CodexAdapter().prepare_environment(str(repo)).ok
    assert global_agents.read_text().count(BEGIN) == 1
    exclude = repo / ".git/info/exclude"
    assert f"/{filename}" not in exclude.read_text().splitlines()


def test_a_worktree_main_root_at_home_is_never_trusted(tmp_path, home, monkeypatch):
    import tomllib

    fake_home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(fake_home))
    checkout = tmp_path / "wt"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {fake_home}/.git/worktrees/wt\n")
    adapter = CodexAdapter(plugins=PluginConfig(enabled=False))
    result = adapter.prepare_environment(str(checkout))
    assert result.ok
    assert any("too broad" in note for note in result.applied)
    projects = tomllib.loads((home / "config.toml").read_text())["projects"]
    assert str(fake_home) not in projects
    assert os.path.realpath(checkout) in projects
    main = tmp_path / "main"
    (checkout / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n")
    assert adapter.prepare_environment(str(checkout)).ok
    projects = tomllib.loads((home / "config.toml").read_text())["projects"]
    assert str(main) in projects


def test_a_stale_gate_from_another_install_is_replaced_not_duplicated(tmp_path, home):
    stale = {
        "type": "command",
        "command": "/old/python /gone/hooks/the-loop-gate.py codex",
    }
    operator = {"type": "command", "command": "operator-check"}
    home.mkdir()
    (home / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [{"hooks": [stale, operator]}, {"hooks": [dict(stale)]}]
                }
            }
        )
    )
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    assert CodexAdapter().prepare_environment(str(checkout)).ok
    groups = json.loads((home / "hooks.json").read_text())["hooks"]["Stop"]
    commands = [h["command"] for g in groups for h in g["hooks"]]
    gates = [c for c in commands if "the-loop-gate.py" in c]
    assert len(gates) == 1 and "/gone/" not in gates[0]
    assert "operator-check" in commands and len(groups) == 1


def test_codex_home_is_stripped_and_expanded_for_every_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", " ~/codex ")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    assert CodexAdapter().prepare_environment(str(checkout)).ok
    assert (tmp_path / "codex/config.toml").is_file()
    assert (tmp_path / "codex/hooks.json").is_file()


def test_a_rollout_whose_first_line_is_not_an_object_is_skipped(tmp_path, home):
    path = write_rollout(home, tmp_path)
    path.write_text("[1, 2]\n" + path.read_text())
    assert rollout_path(str(tmp_path), LAUNCH) is None


def test_a_resolved_rollout_is_not_searched_for_again(tmp_path, home, monkeypatch):
    original = write_rollout(home, tmp_path)
    assert rollout_path(str(tmp_path), LAUNCH) == original.resolve()

    def no_search(*args):
        raise AssertionError("searched the session store again")

    monkeypatch.setattr("the_loop.codex_support._find_rollout", no_search)
    assert rollout_path(str(tmp_path), LAUNCH) == original.resolve()


def test_parallel_codex_trust_writes_preserve_every_project(tmp_path, home):
    import tomllib
    from concurrent.futures import ThreadPoolExecutor

    adapter = CodexAdapter(plugins=PluginConfig(enabled=False))
    paths = [tmp_path / f"repo-{n}" for n in range(12)]
    for path in paths:
        path.mkdir()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: adapter.prepare_environment(str(p)), paths))
    assert all(result.ok for result in results)
    projects = tomllib.loads((home / "config.toml").read_text())["projects"]
    assert set(projects) == {os.path.realpath(p) for p in paths}


def test_codex_stop_attempt_cap_still_returns_valid_json(tmp_path, monkeypatch, capsys):
    gate = load_gate()
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    monkeypatch.setenv("THE_LOOP_GATE_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(gate, "run_check", lambda _: report(False))
    monkeypatch.setattr(gate, "attempts_path", lambda *args: tmp_path / "attempts")
    assert gate.main(["gate", "codex"]) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"
    assert gate.main(["gate", "codex"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert "after 1 attempts" in captured.err


def test_codex_post_tool_hook_recognizes_a_native_exec_command_push():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "hooks/the-loop-link-pr.py"
    spec = importlib.util.spec_from_file_location("codex_link_pr", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.should_discover(
        {"tool_name": "exec_command", "tool_input": {"cmd": "git push origin HEAD"}}
    )
    assert not module.should_discover(
        {"tool_name": "exec_command", "tool_input": {"cmd": "git status"}}
    )
