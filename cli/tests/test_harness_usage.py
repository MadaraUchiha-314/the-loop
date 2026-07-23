"""Unit tests for best-effort token/cost telemetry parsing (issue-37).

Run with: pytest (from the cli/ directory).
"""

import json

from the_loop.harness import DispatchResult, Usage
from the_loop.harness.base import _usage_from_output


def test_default_usage_is_absent():
    # A DispatchResult with no reported usage must read as "not present",
    # so telemetry never logs a misleading zero.
    result = DispatchResult(ok=True)
    assert result.usage.present is False
    assert result.usage.total_tokens == 0


def test_parses_claude_style_usage_and_cost():
    stdout = json.dumps(
        {
            "session_id": "abc",
            "total_cost_usd": 0.0123,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 42,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            },
        }
    )
    usage = _usage_from_output(stdout)
    assert usage.present is True
    assert usage.input_tokens == 100
    assert usage.output_tokens == 42
    assert usage.cache_read_tokens == 10
    assert usage.cache_write_tokens == 5
    assert usage.total_tokens == 157
    assert usage.cost_usd == 0.0123


def test_parses_camelcase_and_alt_token_keys():
    stdout = json.dumps(
        {
            "tokenUsage": {"promptTokens": 7, "completionTokens": 3},
            "costUsd": 1.5,
        }
    )
    usage = _usage_from_output(stdout)
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.cost_usd == 1.5
    assert usage.present is True


def test_missing_usage_is_not_present():
    usage = _usage_from_output(json.dumps({"session_id": "abc"}))
    assert usage.present is False
    assert usage.total_tokens == 0
    assert usage.cost_usd == 0.0


def test_cost_only_is_present():
    usage = _usage_from_output(json.dumps({"total_cost_usd": 0.5}))
    assert usage.present is True
    assert usage.cost_usd == 0.5
    assert usage.total_tokens == 0


def test_bool_token_value_is_rejected():
    # JSON has no int/bool distinction issues, but a stray boolean must not be
    # read as 1 (bool is an int subclass in Python).
    usage = _usage_from_output(json.dumps({"usage": {"input_tokens": True}}))
    assert usage.input_tokens == 0


def test_garbage_output_never_raises():
    for bad in ["", "not json", "[]", "null", "{"]:
        usage = _usage_from_output(bad)
        assert isinstance(usage, Usage)
        assert usage.present is False
