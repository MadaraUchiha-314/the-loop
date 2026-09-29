"""``the-loop hooks`` / ``hooks points`` (issue-344, R5): a report that imports nothing
and contacts nothing — and the daemons' refusal to start on a bad declaration (R3.6)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from the_loop import cli_config, lifecycle
from the_loop.cli import main
from the_loop.commands import iter_commands
from the_loop.lifecycle.contract import POINTS


@pytest.fixture(autouse=True)
def _fresh():
    lifecycle.reset()
    cli_config.set_override(None)
    yield
    lifecycle.reset()
    cli_config.set_override(None)


def _config(tmp_path, hooks, monkeypatch):
    path = tmp_path / "cli-config.yaml"
    path.write_text(json.dumps({"hooks": hooks}))
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return path


def test_hooks_is_registered():
    assert "hooks" in {c.name for c in iter_commands()}


def test_list_reports_the_declaration_without_importing_or_contacting(
    tmp_path, monkeypatch, capsys
):
    """R5.1: a module that would raise on import and a URL that would refuse a
    connection are reported, not run."""
    sentinel = tmp_path / "imported"
    (tmp_path / "boom.py").write_text(
        f"open({str(sentinel)!r}, 'w').write('x')\nraise RuntimeError('imported!')\n"
    )
    _config(
        tmp_path,
        [
            {
                "name": "house",
                "path": "boom.py",
                "required": True,
                "on": ["work_item_start"],
            },
            {
                "name": "tele",
                "module": "acme_no_such_module_344.tele",
                "enabled": False,
            },
            {
                "name": "remote",
                "url": "http://127.0.0.1:9/hooks",
                "tokenEnv": "T",
                "timeoutSeconds": 3,
            },
        ],
        monkeypatch,
    )
    assert main(["hooks"]) == 0
    out = capsys.readouterr().out
    assert "3 declared" in out and "nothing here has been imported or contacted" in out
    assert "house" in out and "path boom.py" in out and "required" in out
    assert "on: work_item_start" in out
    assert "DISABLED" in out
    assert (
        "url http://127.0.0.1:9/hooks" in out
        and "token $T" in out
        and "timeout 3s" in out
    )
    assert not sentinel.exists(), "the module was imported"


def test_list_json(tmp_path, monkeypatch, capsys):
    path = _config(
        tmp_path, [{"name": "a", "url": "https://hooks.example/x"}], monkeypatch
    )
    assert main(["hooks", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["config"] == str(path)
    assert (
        report["hooks"][0]["kind"] == "url"
        and report["hooks"][0]["timeoutSeconds"] == 10.0
    )
    assert "error" not in report


def test_list_with_nothing_declared(tmp_path, monkeypatch, capsys):
    _config(tmp_path, [], monkeypatch)
    assert main(["hooks"]) == 0
    assert "no lifecycle hooks declared" in capsys.readouterr().out


def test_a_bad_declaration_exits_one_naming_the_error(tmp_path, monkeypatch, capsys):
    _config(
        tmp_path,
        [{"name": "a", "module": "x.y", "on": ["session.spawned"]}],
        monkeypatch,
    )
    assert main(["hooks"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("error:") and "session.spawned" in out
    assert main(["hooks", "--format", "json"]) == 1
    assert "session.spawned" in json.loads(capsys.readouterr().out)["error"]


def test_an_unparseable_config_is_an_error_not_nothing_declared(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "cli-config.yaml"
    path.write_text("hooks: [\n")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    assert main(["hooks"]) == 1
    assert "error:" in capsys.readouterr().out


def test_points_lists_the_catalog(tmp_path, monkeypatch, capsys):
    _config(tmp_path, [], monkeypatch)
    assert main(["hooks", "points"]) == 0
    out = capsys.readouterr().out
    for point in POINTS:
        assert point in out
    assert "decisions: proceed, reason" in out
    assert main(["hooks", "points", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["points"]
    assert [r["point"] for r in rows] == list(POINTS)


# ------------------------------------------------------------ daemons (R3.6)


def test_a_daemon_refuses_to_start_on_a_bad_declaration(tmp_path, monkeypatch):
    """Abuse case 6 / R3.6: the poller and the receiver exit 1 before taking a lock."""
    from the_loop.poller import daemon as poller_daemon
    from the_loop.webhook import daemon as webhook_daemon

    _config(tmp_path, [{"name": "a", "path": "missing.py"}], monkeypatch)
    locks = []

    class _NeverLock:
        def __init__(self, *a, **k):
            locks.append(a)

    monkeypatch.setattr(poller_daemon, "RunLock", _NeverLock)
    monkeypatch.setattr(webhook_daemon, "RunLock", _NeverLock)
    monkeypatch.setattr(
        poller_daemon,
        "default_options",
        lambda once=False: SimpleNamespace(pidfile=str(tmp_path / "p.pid")),
    )
    monkeypatch.setattr(poller_daemon, "_build_providers", lambda *a, **k: None)
    poller_options: Any = SimpleNamespace(pidfile=str(tmp_path / "p.pid"), once=True)
    receiver_options: Any = SimpleNamespace(pidfile=str(tmp_path / "w.pid"))
    assert poller_daemon.run(poller_options) == 1
    assert webhook_daemon.run(receiver_options) == 1
    assert locks == [], "a daemon that cannot load its hooks never takes the lock"
