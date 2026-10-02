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
