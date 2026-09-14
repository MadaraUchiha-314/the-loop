"""Unit tests for availability probing (issue-358, R7).

The rule under test everywhere here: **a declaration may narrow, only the probe may
confirm.** Nothing in this module may make a choice offerable that the harness refuses,
and nothing outside it may introduce a choice the operator never declared.
"""

import json
import time

import pytest

from the_loop.harness import ClaudeCodeAdapter, CursorAgentAdapter
from the_loop.modelprobe import (
    OK,
    REFUSED,
    UNKNOWN,
    VERDICT_TTL_SECONDS,
    Verdict,
    VerdictCache,
    digest,
    offerable,
    probe,
    resolved_args,
)


class FakeAdapter(ClaudeCodeAdapter):
    """An adapter whose one-shot run is decided by the test, not by a binary."""

    def __init__(self, *, exit_code=0, stdout="{}", available=True, **kw):
        super().__init__(**kw)
        self.exit_code = exit_code
        self.stdout = stdout
        self._available = available
        self.calls = []

    def is_available(self):
        return self._available


@pytest.fixture
def run_recorder(monkeypatch):
    """Capture the argv every probe runs, and decide its outcome."""
    calls = []

    def fake_run(argv, adapter, timeout):
        calls.append(list(argv))
        if not adapter.is_available():
            raise OSError("no such binary")
        return adapter.exit_code, adapter.stdout

    monkeypatch.setattr("the_loop.modelprobe._run", fake_run)
    return calls


# -- probe ----------------------------------------------------------------------


def test_a_model_the_harness_accepts_is_ok(run_recorder):
    verdict = probe("model", "fable-5.1", FakeAdapter())
    assert verdict.verdict == OK
    assert verdict.harness == "claude" and verdict.name == "fable-5.1"


def test_a_model_the_harness_rejects_is_refused(run_recorder):
    verdict = probe("model", "nope-1", FakeAdapter(exit_code=1, stdout="unknown model"))
    assert verdict.verdict == REFUSED


def test_a_harness_that_cannot_be_run_is_unknown_not_refused(run_recorder):
    """An unprobeable harness must not remove a capability the operator declared."""
    verdict = probe("model", "fable-5.1", FakeAdapter(available=False))
    assert verdict.verdict == UNKNOWN


def test_the_probe_sends_the_loops_own_prompt_and_the_resolved_args(run_recorder):
    probe("model", "fable-5.1", FakeAdapter())
    argv = run_recorder[0]
    assert "--model" in argv and "fable-5.1" in argv
    # The prompt is a the-loop constant. No work-item text is ever sent (the
    # requirements' egress rule), so nothing here may come from a payload.
    from the_loop.modelprobe import PROBE_PROMPT

    assert PROBE_PROMPT in argv


def test_an_effort_level_a_harness_cannot_express_is_refused_without_running(
    run_recorder,
):
    """Nothing to probe, and nothing to offer — but never a silent 'ran without it'."""
    verdict = probe("effort", "high", FakeAdapter())
    assert verdict.verdict == REFUSED
    assert run_recorder == []


# -- the cache ------------------------------------------------------------------


def test_a_verdict_round_trips(tmp_path):
    cache = VerdictCache(str(tmp_path / "v.json"))
    cache.put(Verdict("claude", "model", "opus-5", "abc", OK, time.time()))
    stored = cache.get("claude", "model", "opus-5")
    assert stored is not None and stored.verdict == OK


def test_a_changed_argv_invalidates_the_verdict(tmp_path):
    cache = VerdictCache(str(tmp_path / "v.json"))
    cache.put(Verdict("claude", "model", "opus-5", "abc", REFUSED, time.time()))
    same = cache.get("claude", "model", "opus-5", args_digest="abc")
    assert same is not None and same.verdict == REFUSED
    assert cache.get("claude", "model", "opus-5", args_digest="different") is None


def test_a_verdict_probed_with_the_old_cursor_flag_no_longer_withholds(tmp_path):
    """issue-360: the `-m` era's `refused` verdicts expire on their own.

    Every cursor model probed before the flag was fixed came back `refused` —
    `cursor-agent` exited non-zero on `-m` before it had an opinion about any
    name — and a standing `refused` withholds the choice from the checklist. No
    migration is needed because the verdict records the argv it was taken
    against: the digest of `("-m", name)` is not the digest of
    `("--model", name)`, so the stale answer stops applying the moment the
    adapter is fixed, and the next `models check` asks again.
    """
    cache = VerdictCache(str(tmp_path / "v.json"))
    name = "gpt-5.6-sol"
    cache.put(
        Verdict("cursor", "model", name, digest(("-m", name)), REFUSED, time.time())
    )

    assert not offerable(
        "model", name, "cursor", cache, args_digest=digest(("-m", name))
    )

    now = resolved_args("model", name, CursorAgentAdapter())
    assert now == ("--model", name)
    assert offerable("model", name, "cursor", cache, args_digest=digest(now))


def test_a_stale_verdict_is_not_returned(tmp_path):
    cache = VerdictCache(str(tmp_path / "v.json"))
    old = time.time() - VERDICT_TTL_SECONDS - 1
    cache.put(Verdict("claude", "model", "opus-5", "abc", REFUSED, old))
    assert cache.get("claude", "model", "opus-5") is None


def test_an_unreadable_cache_is_empty_not_an_error(tmp_path):
    path = tmp_path / "v.json"
    path.write_text("{{{ not json")
    assert VerdictCache(str(path)).get("claude", "model", "opus-5") is None


# -- offerable ------------------------------------------------------------------


def test_ok_is_offerable_and_refused_is_not(tmp_path):
    cache = VerdictCache(str(tmp_path / "v.json"))
    cache.put(Verdict("claude", "model", "opus-5", "", OK, time.time()))
    cache.put(Verdict("claude", "model", "nope-1", "", REFUSED, time.time()))
    assert offerable("model", "opus-5", "claude", cache)
    assert not offerable("model", "nope-1", "claude", cache)


def test_an_unprobed_choice_is_offerable(tmp_path):
    """`unknown` stays offerable (R7.6): no probe must not mean no capability."""
    cache = VerdictCache(str(tmp_path / "v.json"))
    assert offerable("model", "opus-5", "claude", cache)


def test_a_verdict_is_per_harness(tmp_path):
    """The cache is a matrix — which is what lets `models` be a plain list of names."""
    cache = VerdictCache(str(tmp_path / "v.json"))
    cache.put(Verdict("claude", "model", "gpt-5.6-sol", "", REFUSED, time.time()))
    cache.put(Verdict("cursor", "model", "gpt-5.6-sol", "", OK, time.time()))
    assert not offerable("model", "gpt-5.6-sol", "claude", cache)
    assert offerable("model", "gpt-5.6-sol", "cursor", cache)


# -- abuse ----------------------------------------------------------------------


def test_abuse_a_forged_verdict_cannot_introduce_a_choice(tmp_path):
    """A7. The cache may withhold; it may never add. Resolution is always against
    what the operator declared, so a hand-edited verdict for an undeclared model
    buys nothing."""
    path = tmp_path / "v.json"
    path.write_text(
        json.dumps(
            {
                "verdicts": [
                    {
                        "harness": "claude",
                        "kind": "model",
                        "name": "smuggled-9",
                        "argsDigest": "",
                        "verdict": OK,
                        "checkedAt": time.time(),
                    }
                ]
            }
        )
    )
    cache = VerdictCache(str(path))
    # The cache happily reports it...
    assert offerable("model", "smuggled-9", "claude", cache)
    # ...but it is not a declared model, so nothing downstream will resolve it.
    from the_loop.modelchoice import declared_models

    assert "smuggled-9" not in declared_models({"models": ["opus-5"]})
