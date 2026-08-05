"""``the-loop ui`` delegates to the frontend toolchain, fail-closed (issue-161, T13)."""

import argparse
import os

from the_loop.commands.service_cmd import UiCommand


def _args(verb: str) -> argparse.Namespace:
    return argparse.Namespace(_verb=verb)


def test_ui_without_a_ui_dir_is_an_error(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert UiCommand().run(_args("build")) == 1
    assert "no ui/ directory" in capsys.readouterr().err


def test_ui_without_npm_reports_skip(tmp_path, capsys, monkeypatch):
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "package.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("the_loop.commands.service_cmd.shutil.which", lambda _: None)
    assert UiCommand().run(_args("dev")) == 1
    assert "npm is not on PATH" in capsys.readouterr().err


def test_ui_runs_npm_with_a_fixed_argv(tmp_path, capsys, monkeypatch):
    """
    Feature: UI lifecycle delegation
      Scenario: the operator builds the UI
        Given a checkout with ui/ and npm on PATH
        When `the-loop ui build` runs
        Then it executes npm --prefix ui run build as an argv list (no shell)

    Requirement: docs/specs/issue-161/requirements.md R4.2, R6.2
    """
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "package.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "the_loop.commands.service_cmd.shutil.which", lambda _: "/usr/bin/npm"
    )
    calls = {}

    def fake_run(argv):
        calls["argv"] = argv

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("the_loop.commands.service_cmd.subprocess.run", fake_run)
    assert UiCommand().run(_args("build")) == 0
    assert calls["argv"][0] == "/usr/bin/npm"
    assert calls["argv"][1:3] == ["--prefix", str(tmp_path / "ui")]
    assert calls["argv"][-2:] == ["run", "build"]
    assert os.sep in calls["argv"][2]
