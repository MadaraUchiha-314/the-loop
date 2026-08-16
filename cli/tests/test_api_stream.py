"""Resolution of the `service.stream` block, and the stream's own primitives (issue-239).

The block governs `GET /api/v1/stream` — a **read** surface over the same records
`GET /api/v1/events` serves, held open. Three knobs and no more: everything else the
stream needs is a constant an operator would have no basis to choose, and lives in
:mod:`the_loop.api.stream`.

These are the unit-level tests (testing-plan T1). The connection itself is exercised in
``test_stream_integration.py``.
"""

import pytest

from the_loop.api.config import DEFAULT_STREAM_MAX_SUBSCRIBERS, stream_config


# -- service.stream resolution (task 1) -----------------------------------------


def test_defaults_serve_the_stream_with_a_bounded_subscriber_count():
    """
    Feature: the stream is on by default and bounded by default
      Scenario: no service.stream block is configured
        Given a CLI config with no stream block
        When the stream config resolves
        Then the stream is enabled, capped at the default subscriber count,
             and keeps connections alive on the default interval

    Requirement: docs/specs/issue-239/requirements.md R1.4, R5.2
    """
    conf = stream_config({})
    assert conf["enabled"] is True
    assert conf["maxSubscribers"] == DEFAULT_STREAM_MAX_SUBSCRIBERS
    assert conf["keepAliveSeconds"] == 15


def test_an_absent_block_is_the_defaults_not_the_off_switch():
    """A missing section means "unconfigured", never "disabled" — `enabled: false` is
    the off switch, and it has to be written."""
    assert stream_config(None)["enabled"] is True
    assert stream_config({"service": {}})["enabled"] is True


def test_enabled_false_is_the_off_switch():
    """
    Feature: a deployment can narrow itself to REST-only
      Scenario: the operator disables the stream
        Given service.stream.enabled is false
        When the stream config resolves
        Then the stream is disabled

    Requirement: docs/specs/issue-239/requirements.md R1.1
    """
    conf = stream_config({"service": {"stream": {"enabled": False}}})
    assert conf["enabled"] is False


def test_configured_values_win_key_by_key():
    conf = stream_config(
        {"service": {"stream": {"maxSubscribers": 3, "keepAliveSeconds": 45}}}
    )
    assert conf["maxSubscribers"] == 3
    assert conf["keepAliveSeconds"] == 45
    assert conf["enabled"] is True


@pytest.mark.parametrize("value", [0, -1, "nonsense", None])
def test_a_nonsense_subscriber_cap_clamps_up_rather_than_disabling_the_bound(value):
    """
    Feature: the subscriber bound cannot be configured away
      Scenario: maxSubscribers is zero, negative or unparseable
        Given a hand-edited service.stream.maxSubscribers
        When the stream config resolves
        Then the cap is at least one — never zero, never unbounded

    Requirement: docs/specs/issue-239/requirements.md R5.2 (abuse case 1)

    A cap of 0 would refuse every connection, and a cap that fell through to
    "unlimited" would be abuse case 1 handed a configuration switch. Both
    directions resolve to a usable, bounded number.
    """
    conf = stream_config({"service": {"stream": {"maxSubscribers": value}}})
    assert conf["maxSubscribers"] >= 1


def test_the_schema_refuses_an_unknown_key_under_stream():
    """
    Feature: a mistyped stream key is refused, not ignored
      Scenario: the operator writes an option that does not exist
        Given a CLI config with service.stream.maxSubscriber (singular)
        When it is validated against the packaged schema
        Then validation fails naming the key

    Requirement: docs/specs/issue-239/requirements.md R5.2

    `additionalProperties: false` is what makes a typo a loud failure instead of a
    silently-ignored bound.
    """
    from the_loop import configschema

    errors = configschema.validate({"service": {"stream": {"maxSubscriber": 4}}})
    assert any("maxSubscriber" in e for e in errors), (
        f"an unknown stream key must be named in the errors, got {errors}"
    )
    assert configschema.validate({"service": {"stream": {"maxSubscribers": 4}}}) == []
