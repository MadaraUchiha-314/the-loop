"""``the-loop hooks`` — reports the declaration without importing it (issue-344, R6)."""

from __future__ import annotations

import json
from pathlib import Path

from the_loop import lifecycle_hooks as lh
from the_loop.cli import main
from the_loop.commands import iter_commands

#: A module that would leave a mark if anything imported it.
TRAP = """
import pathlib
pathlib.Path(__file__).with_suffix(".imported").write_text("imported")
from the_loop.graph import hook


@hook("x-trap")
def trap(event):
    return None
"""


def _config(tmp_path: Path, monkeypatch, body: str) -> Path:
    path = tmp_path / "cli-config.yaml"
    path.write_text('version: "0.9.0"\n' + body)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return path


def test_hooks_is_registered():
    assert "hooks" in {c.name for c in iter_commands()}


def test_hooks_reports_without_importing(tmp_path, monkeypatch, capsys):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "trap.py").write_text(TRAP)
    _config(
        tmp_path,
        monkeypatch,
        "hooks:\n  modules:\n    - path: hooks/trap.py\n    - module: acme.hooks\n"
        "  lifecycle:\n    - hook: x-trap\n      on: [session.spawned, graph.*]\n"
        "    - hook: forward-event\n      on: work_item.*\n      with: {url: https://x/y}\n",
    )
    assert main(["hooks"]) == 0
    out = capsys.readouterr().out
    assert f"attach points: {len(lh.attach_points())} event types" in out
    assert "shipped lifecycle hooks (1): forward-event" in out
    assert (
        "declares 2 module(s) and 2 attachment(s) — nothing here has been imported"
        in out
    )
    assert f"module  hooks/trap.py  (resolved against {tmp_path.resolve()})" in out
    assert "module  acme.hooks\n" in out
    assert "attach  x-trap → " in out and "[session.spawned, graph.*]" in out
    assert (
        "attach  forward-event → 2 event(s) [work_item.*]  with: {'url': 'https://x/y'}"
        in out
    )
    assert not (tmp_path / "hooks" / "trap.imported").exists()

    assert main(["hooks", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["attachPoints"] == len(lh.attach_points())
    assert list(report["shipped"]) == ["forward-event"]
    assert report["modules"] == [
        {"path": "hooks/trap.py", "module": ""},
        {"path": "", "module": "acme.hooks"},
    ]
    assert report["attach"][0]["on"] == ["session.spawned", "graph.*"]
    assert "graph.advanced" in report["attach"][0]["events"]
    assert report["attach"][1]["events"] == ["work_item.ended", "work_item.reopened"]
    assert not (tmp_path / "hooks" / "trap.imported").exists()


def test_hooks_reports_an_empty_declaration(tmp_path, monkeypatch, capsys):
    _config(tmp_path, monkeypatch, "")
    assert main(["hooks"]) == 0
    out = capsys.readouterr().out
    assert "no lifecycle hooks declared (`hooks` in the CLI config" in out


def test_hooks_exits_2_on_a_malformed_block(tmp_path, monkeypatch, capsys):
    _config(
        tmp_path,
        monkeypatch,
        "hooks:\n  lifecycle:\n    - hook: x-a\n      on: sessoin.*\n",
    )
    assert main(["hooks"]) == 2
    err = capsys.readouterr().err
    assert "error:" in err and "'sessoin.*' matches no event type" in err
