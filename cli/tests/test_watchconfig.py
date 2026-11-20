"""Unit tests for the `routing.watchdog` and `routing.asks` config (issue-551)."""

import pytest

from the_loop.watchconfig import AsksConfig, WatchdogConfig
from the_loop.webhook.dispatcher import RoutingConfig


def test_a_config_without_the_blocks_loads_with_the_defaults():
    """
    Feature: the watchdog and the ask deadline need no configuration
      Scenario: an operator's config predates issue-551
        Given a routing mapping with no `watchdog` and no `asks` block
        When it is loaded
        Then both blocks carry the documented defaults

    Requirement: docs/specs/issue-551/requirements.md NFR configuration
    """
    config = RoutingConfig.from_mapping({})
    assert config.watchdog == WatchdogConfig(
        enabled=True, idle_seconds=600, max_nudges=2, max_wait_seconds=3600
    )
    assert config.asks == AsksConfig(
        min_default_wait_seconds=1800, reminder_seconds=7200
    )


def test_the_blocks_are_read_from_the_mapping():
    config = RoutingConfig.from_mapping(
        {
            "watchdog": {
                "enabled": False,
                "idleSeconds": 120,
                "maxNudges": 0,
                "maxWaitSeconds": 900,
            },
            "asks": {"minDefaultWaitSeconds": 60, "reminderSeconds": 0},
        }
    )
    assert config.watchdog == WatchdogConfig(
        enabled=False, idle_seconds=120, max_nudges=0, max_wait_seconds=900
    )
    assert config.asks == AsksConfig(min_default_wait_seconds=60, reminder_seconds=0)


def test_a_partial_block_keeps_the_other_defaults():
    config = RoutingConfig.from_mapping({"watchdog": {"idleSeconds": 30}})
    assert config.watchdog == WatchdogConfig(idle_seconds=30)


@pytest.mark.parametrize("bad", [0, -1, 1.5, "600", True, None])
def test_a_value_the_schema_refuses_reads_as_the_default(bad):
    """The schema is the gate; a mapping that never met it must still not yield a
    zero or negative threshold, which would nudge on every tick."""
    watchdog = WatchdogConfig.from_mapping(
        {
            "idleSeconds": bad,
            "maxWaitSeconds": bad,
            "maxNudges": -1 if bad == 0 else bad,
        }
    )
    assert watchdog == WatchdogConfig()
    asks = AsksConfig.from_mapping(
        {"minDefaultWaitSeconds": bad, "reminderSeconds": -1 if bad == 0 else bad}
    )
    assert asks == AsksConfig()
