"""Unit tests for the Codex adapter (issue-449).

Run with: pytest (from the cli/ directory).
"""

from the_loop.core.sessions import HARNESS_BINARIES
from the_loop.harness import (
    ADAPTER_TYPES,
    CodexAdapter,
    hosting_harnesses,
    hosts_sessions,
)


def test_registered_as_a_hosting_harness():
    assert ADAPTER_TYPES["codex"] is CodexAdapter
    assert hosts_sessions(CodexAdapter) is True
    assert "codex" in hosting_harnesses()
    assert HARNESS_BINARIES["codex"] == "codex"


def test_oneshot_argv_is_exec_with_flags_before_prompt():
    adapter = CodexAdapter(extra_args=["--full-auto"])
    assert adapter.oneshot_argv("review this") == [
        "exec",
        "--skip-git-repo-check",
        "--full-auto",
        "review this",
    ]


def test_oneshot_argv_appends_model():
    adapter = CodexAdapter()
    argv = adapter.oneshot_argv("p", model="gpt-5.6-sol")
    assert argv[-2:] == ["--model", "gpt-5.6-sol"]


def test_interactive_argv_drops_the_preassigned_id():
    # codex mints its own session id (openai/codex#13242): the dispatcher's id
    # must be accepted and ignored, never passed to the TUI.
    adapter = CodexAdapter(extra_args=["--sandbox", "workspace-write"])
    argv = adapter.interactive_argv("do the loop", "the-loop-uuid")
    assert "the-loop-uuid" not in argv
    assert argv == ["--sandbox", "workspace-write", "do the loop"]


def test_interactive_resume_argv_resumes_by_recency():
    adapter = CodexAdapter()
    argv = adapter.interactive_resume_argv("continue", "the-loop-uuid")
    assert argv[:2] == ["resume", "--last"]
    assert argv[-1] == "continue"
    assert "the-loop-uuid" not in argv


def test_effort_levels_map_to_config_overrides():
    adapter = CodexAdapter()
    assert adapter.effort_args("high") == ("-c", "model_reasoning_effort=high")
    assert adapter.effort_args("xhigh") == ("-c", "model_reasoning_effort=xhigh")
    assert adapter.effort_args("ultra") == ("-c", "model_reasoning_effort=ultra")
    # A level codex cannot express is not offered, never guessed (decision-124).
    assert adapter.effort_args("max") == ()


def test_prepare_environment_trusts_cwd_worktree_root_and_workspace_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    workspace = tmp_path / "workspace"
    clone = workspace / "github.com" / "o" / "r"
    (clone / ".git" / "worktrees" / "wt").mkdir(parents=True)
    wt = workspace / ".worktrees" / "wt"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {clone}/.git/worktrees/wt\n")

    result = CodexAdapter().prepare_environment(str(wt), root=str(workspace))
    assert result.ok, result.error
    text = (tmp_path / "codex-home" / "config.toml").read_text()
    import os as _os

    for key in (str(wt), str(clone), str(workspace)):
        assert f'[projects."{_os.path.realpath(key)}"]' in text
    assert text.count('trust_level = "trusted"') == len(
        [line for line in text.splitlines() if line.startswith("[projects.")]
    )

    # Idempotent: a second call appends nothing.
    again = CodexAdapter().prepare_environment(str(wt), root=str(workspace))
    assert again.ok and again.applied == []
    assert (tmp_path / "codex-home" / "config.toml").read_text() == text


def test_prepare_environment_never_rewrites_an_operator_decision(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    cwd = tmp_path / "repo"
    (cwd / ".git").mkdir(parents=True)
    import os as _os

    key = _os.path.realpath(str(cwd))
    (tmp_path / "config.toml").write_text(
        f'[projects."{key}"]\ntrust_level = "untrusted"\n'
    )
    result = CodexAdapter().prepare_environment(str(cwd))
    assert result.ok
    assert 'trust_level = "untrusted"' in (tmp_path / "config.toml").read_text()
