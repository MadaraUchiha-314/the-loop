"""`the-loop models list|check` — the surface that makes a declaration true (issue-358).

What is asserted here is mostly *which combinations get asked about*: a bare model is a
candidate everywhere, a narrowed one is not, and an effort level is asked about every
harness because its mapping is the-loop's own claim about that harness's CLI.
"""

from __future__ import annotations

import argparse
import json
import time

import pytest

from the_loop.commands import models_cmd
from the_loop.modelprobe import OK, REFUSED, Verdict, VerdictCache

CONFIG = {
    "harnesses": [{"name": "claude", "default": True}, {"name": "cursor"}],
    "models": ["opus-5", {"name": "gpt-5.6-sol", "harnesses": ["cursor"]}],
    "effort": ["high", "xhigh"],
}


@pytest.fixture
def configured(monkeypatch, tmp_path):
    config = dict(CONFIG, state={"root": str(tmp_path)})
    monkeypatch.setattr(models_cmd, "_cli_config", lambda: config)
    return config


def _run(action, **kw):
    args = argparse.Namespace(format=kw.pop("format", "json"), **kw)
    return action(args)


def test_a_bare_model_is_asked_about_every_declared_harness(configured):
    pairs = models_cmd._combinations(configured)
    assert ("claude", "model", "opus-5") in pairs
    assert ("cursor", "model", "opus-5") in pairs


def test_a_narrowed_model_is_asked_about_only_its_harnesses(configured):
    pairs = models_cmd._combinations(configured)
    assert ("cursor", "model", "gpt-5.6-sol") in pairs
    assert ("claude", "model", "gpt-5.6-sol") not in pairs


def test_every_effort_mapping_is_asked_about(configured):
    """the-loop asserts the mapping, so the-loop has it checked — R2.7."""
    pairs = models_cmd._combinations(configured)
    for harness in ("claude", "cursor"):
        for level in ("high", "xhigh"):
            assert (harness, "effort", level) in pairs


def test_list_reports_what_is_cached_without_asking_anything(
    configured, tmp_path, capsys
):
    cache = VerdictCache(str(tmp_path / "local" / "model-verdicts.json"))
    cache.put(Verdict("claude", "model", "opus-5", "", OK, time.time()))

    _run(models_cmd.ModelsCommand()._list)
    printed = json.loads(capsys.readouterr().out)
    verdicts = {
        (r["harness"], r["kind"], r["name"]): r["verdict"] for r in printed["verdicts"]
    }
    assert verdicts[("claude", "model", "opus-5")] == OK
    assert verdicts[("cursor", "model", "opus-5")] == "unprobed"


def test_list_carries_the_loops_effort_vocabulary(configured, capsys):
    _run(models_cmd.ModelsCommand()._list)
    printed = json.loads(capsys.readouterr().out)
    assert printed["effortLevels"] == ["low", "medium", "high", "xhigh", "max"]


def test_a_refused_verdict_is_a_non_zero_exit(configured, tmp_path, capsys):
    """So a CI job or a start-up check can notice, rather than a spawn noticing."""
    cache = VerdictCache(str(tmp_path / "local" / "model-verdicts.json"))
    for harness in ("claude", "cursor"):
        for name in ("opus-5", "gpt-5.6-sol"):
            cache.put(Verdict(harness, "model", name, "", REFUSED, time.time()))
        for level in ("high", "xhigh"):
            cache.put(Verdict(harness, "effort", level, "", REFUSED, time.time()))

    assert _run(models_cmd.ModelsCommand()._list) == models_cmd._EXIT_REFUSED


def test_a_config_error_outranks_a_refusal(monkeypatch, tmp_path, capsys):
    """Two default harnesses is a mistake a spawn must never be the first to find."""
    broken = {
        "harnesses": [
            {"name": "claude", "default": True},
            {"name": "cursor", "default": True},
        ],
        "models": ["opus-5"],
        "state": {"root": str(tmp_path)},
    }
    monkeypatch.setattr(models_cmd, "_cli_config", lambda: broken)
    assert _run(models_cmd.ModelsCommand()._list) == models_cmd._EXIT_MISCONFIGURED
    assert "default" in capsys.readouterr().out


def test_nothing_declared_asks_nothing_and_succeeds(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        models_cmd, "_cli_config", lambda: {"state": {"root": str(tmp_path)}}
    )
    assert _run(models_cmd.ModelsCommand()._list) == models_cmd._EXIT_OK
    assert json.loads(capsys.readouterr().out)["verdicts"] == []
