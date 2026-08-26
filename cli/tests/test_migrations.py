"""The breaking config migrations (issue-109 R6a, issue-128).

A breaking change is only as good as its migration, so each is tested both
ways: an old config migrates to the expected new one, AND the runtime refuses
an un-migrated one.

Five so far — `ghBinary` (one `integrations` block replaced three copies),
`polling.stateFile` (the poller's ledger became one record per work item under
`state.root`, so a file path has nothing left to point at),
`webhooks.ghWebhook.routing` (promoted to a top-level `routing`, because the
poller reads that same block and a key named `webhooks` said otherwise),
`integrations.slack` (the incoming webhook converged on the `channels.slack`
bot), and `collaborators` / `notifications` (issue-304 — the plainest case of
all: nothing ever read either block, so an operator who filled one in
configured nothing and was never told).
"""

from __future__ import annotations

import copy

import pytest

from the_loop.migrations import (
    CURRENT_CONFIG_VERSION,
    ConfigTooOld,
    assert_current,
    migrate_cli_config,
    needs_migration,
)

OLD = {
    "version": "0.1.0",
    "webhooks": {
        "ghWebhook": {
            "routing": {
                "control": {"ghBinary": "gh"},
                "reactions": {"enabled": True, "ghBinary": "gh"},
                "announce": {"enabled": True, "ghBinary": "gh"},
            }
        }
    },
}


def test_an_old_config_is_detected_by_version_and_by_key():
    assert needs_migration(OLD)
    assert needs_migration({"version": "0.1.0"})
    assert not needs_migration({"version": CURRENT_CONFIG_VERSION})


def test_the_runtime_refuses_an_unmigrated_config_and_names_the_fix():
    """R6a.6 — never silently ignore a value the operator deliberately set."""
    with pytest.raises(ConfigTooOld) as exc:
        assert_current(OLD)
    message = str(exc.value)
    assert "ghBinary" in message
    assert "integrations.github.cli.binary" in message
    assert "/the-loop:upgrade-the-loop" in message


def test_an_old_version_alone_is_also_refused():
    with pytest.raises(ConfigTooOld, match="0.1.0"):
        assert_current({"version": "0.1.0"})


def test_migration_moves_the_key_and_bumps_the_version():
    report = migrate_cli_config(OLD)
    assert report.changed
    # issue-142 promoted the block itself, so the migrated config reads it here.
    routing = report.config["routing"]
    assert "ghBinary" not in routing["control"]
    assert "ghBinary" not in routing["reactions"]
    assert "ghBinary" not in routing["announce"]
    assert report.config["integrations"]["github"]["cli"]["binary"] == "gh"
    assert report.config["version"] == CURRENT_CONFIG_VERSION
    assert_current(report.config)  # the migrated config is accepted


def test_migration_reports_every_move_rather_than_rewriting_silently():
    """R6a.7 — the operator sees what changed."""
    report = migrate_cli_config(OLD)
    rendered = report.render()
    assert rendered.count("ghBinary") == 3
    assert "version" in rendered


def test_migration_is_idempotent():
    once = migrate_cli_config(OLD)
    twice = migrate_cli_config(once.config)
    assert twice.changed is False
    assert twice.config == once.config


def test_disagreeing_values_are_surfaced_not_silently_picked():
    config = copy.deepcopy(OLD)
    config["webhooks"]["ghWebhook"]["routing"]["announce"]["ghBinary"] = "gh-enterprise"
    report = migrate_cli_config(config)
    assert any("disagreed" in n for n in report.notes)


def test_a_current_config_needs_no_migration():
    report = migrate_cli_config({"version": CURRENT_CONFIG_VERSION})
    assert not report.changed
    assert "nothing to migrate" in report.render()


class TestMigrateConfigCommand:
    """`the-loop migrate-config` — the surface `/upgrade` shells out to."""

    def _run(self, tmp_path, dry_run=False):
        import argparse

        import yaml

        from the_loop.commands.migrate_cmd import MigrateConfigCommand

        path = tmp_path / "cli-config.yaml"
        path.write_text(yaml.safe_dump(OLD), encoding="utf-8")
        cmd = MigrateConfigCommand()
        args = argparse.Namespace(path=str(path), dry_run=dry_run)
        return cmd.run(args), path

    def test_it_migrates_the_file_in_place_and_keeps_a_backup(self, tmp_path):
        import yaml

        code, path = self._run(tmp_path)
        assert code == 0
        migrated = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert migrated["version"] == CURRENT_CONFIG_VERSION
        assert migrated["integrations"]["github"]["cli"]["binary"] == "gh"
        # The migrated file is one the runtime will actually accept.
        assert_current(migrated)
        # A breaking migration you cannot walk back from is the worse trade.
        assert (tmp_path / "cli-config.yaml.bak").is_file()

    def test_dry_run_writes_nothing(self, tmp_path):
        import yaml

        code, path = self._run(tmp_path, dry_run=True)
        assert code == 0
        assert yaml.safe_load(path.read_text(encoding="utf-8")) == OLD
        assert not (tmp_path / "cli-config.yaml.bak").exists()

    def test_it_can_read_the_very_config_the_runtime_refuses(self, tmp_path):
        """The loader refuses un-migrated configs; the migrator must not.

        A door that only opens for a key locked inside it is no door.
        """
        import yaml

        from the_loop import cli_config

        path = tmp_path / "cli-config.yaml"
        path.write_text(yaml.safe_dump(OLD), encoding="utf-8")
        with pytest.raises(ConfigTooOld):
            cli_config.load_cli_config(path)
        code, _ = self._run(tmp_path)
        assert code == 0

    def test_it_is_idempotent(self, tmp_path):
        code, path = self._run(tmp_path)
        assert code == 0
        import argparse

        from the_loop.commands.migrate_cmd import MigrateConfigCommand

        second = MigrateConfigCommand().run(
            argparse.Namespace(path=str(path), dry_run=False)
        )
        assert second == 0

    def test_a_missing_file_is_an_error_not_a_crash(self, tmp_path):
        import argparse

        from the_loop.commands.migrate_cmd import MigrateConfigCommand

        code = MigrateConfigCommand().run(
            argparse.Namespace(path=str(tmp_path / "nope.yaml"), dry_run=False)
        )
        assert code == 2


# -- issue-128: polling.stateFile ------------------------------------------------

WITH_STATE_FILE = {
    "version": CURRENT_CONFIG_VERSION,
    "state": {"root": ".the-loop"},
    "polling": {"intervalSeconds": 30, "stateFile": ".the-loop/poll-state.json"},
}


def test_a_config_still_pointing_at_a_poll_state_file_is_detected():
    assert needs_migration(WITH_STATE_FILE) is True


def test_the_runtime_refuses_a_stale_state_file_and_names_the_replacement():
    # Honouring it is not an option: a poller writing somewhere other than where
    # the operator pointed it is how a whole comment thread gets re-forwarded.
    with pytest.raises(ConfigTooOld) as excinfo:
        assert_current(WITH_STATE_FILE)
    message = str(excinfo.value)
    assert "polling.stateFile" in message
    assert "state.root" in message
    assert "/the-loop:upgrade-the-loop" in message


def test_migration_removes_the_state_file_and_says_the_old_one_is_still_read():
    report = migrate_cli_config(WITH_STATE_FILE)
    assert report.changed is True
    assert "polling" in report.config
    assert "stateFile" not in report.config["polling"]
    assert report.config["polling"]["intervalSeconds"] == 30
    assert any("stateFile" in move for move in report.moves)
    assert_current(report.config)  # the migrated config is accepted


def test_the_state_file_migration_is_idempotent():
    once = migrate_cli_config(WITH_STATE_FILE).config
    twice = migrate_cli_config(once)
    assert twice.changed is False
    assert twice.config == once


# -- issue-142: webhooks.ghWebhook.routing → routing -----------------------------
#
# The block was never webhook-only: the poller reads it verbatim for dispatch, and
# `the-loop sessions` reads it a third time. Promoting it makes the config's shape
# say what a comment used to have to.

WITH_NESTED_ROUTING = {
    "version": "0.3.0",
    "webhooks": {
        "ghWebhook": {
            "port": 8787,
            "routing": {"enabled": True, "authorizedUsers": ["operator"]},
        }
    },
}


def test_a_config_still_nesting_routing_under_the_receiver_is_detected():
    assert needs_migration(WITH_NESTED_ROUTING) is True


def test_the_runtime_refuses_nested_routing_and_names_the_replacement():
    """Ignoring it would change WHICH logins may drive the daemon, in silence."""
    with pytest.raises(ConfigTooOld) as excinfo:
        assert_current(WITH_NESTED_ROUTING)
    message = str(excinfo.value)
    assert "webhooks.ghWebhook.routing" in message
    assert "`routing`" in message
    assert "/the-loop:upgrade-the-loop" in message


def test_migration_promotes_the_block_verbatim_and_keeps_the_receiver_keys():
    report = migrate_cli_config(WITH_NESTED_ROUTING)
    assert report.changed is True
    assert report.config["routing"] == {
        "enabled": True,
        "authorizedUsers": ["operator"],
    }
    assert "routing" not in report.config["webhooks"]["ghWebhook"]
    assert report.config["webhooks"]["ghWebhook"]["port"] == 8787
    assert any("webhooks.ghWebhook.routing" in move for move in report.moves)
    assert_current(report.config)  # the migrated config is accepted


def test_an_emptied_receiver_block_is_removed_rather_than_left_as_a_husk():
    report = migrate_cli_config(
        {"version": "0.3.0", "webhooks": {"ghWebhook": {"routing": {"enabled": True}}}}
    )
    assert report.config["routing"] == {"enabled": True}
    assert "webhooks" not in report.config


def test_the_routing_migration_is_idempotent():
    once = migrate_cli_config(WITH_NESTED_ROUTING)
    twice = migrate_cli_config(once.config)
    assert twice.changed is False
    assert twice.config == once.config


def test_a_half_migrated_config_prefers_the_new_block_and_reports_what_it_dropped():
    """Both blocks present: the top-level one wins WHOLE, key by key.

    Never a union — merging two `authorizedUsers` lists would silently re-admit a
    login the operator had removed from the block they were maintaining.
    """
    report = migrate_cli_config(
        {
            "version": "0.3.0",
            "routing": {"authorizedUsers": ["current"]},
            "webhooks": {
                "ghWebhook": {
                    "routing": {"authorizedUsers": ["stale"], "enabled": True}
                }
            },
        }
    )
    assert report.config["routing"]["authorizedUsers"] == ["current"]
    assert report.config["routing"]["enabled"] is True  # not declared twice: adopted
    assert any("authorizedUsers" in note and "stale" in note for note in report.notes)
    assert "webhooks" not in report.config
    assert_current(report.config)


# --- integrations.slack retired (issue-245, PR #267 review) ---------------------

WITH_SLACK_INTEGRATION = {
    "version": "0.4.0",
    "integrations": {
        "github": {"transport": "auto"},
        "slack": {"transport": "sdk", "urlEnv": "THE_LOOP_SLACK_WEBHOOK_URL"},
    },
}


def test_a_config_still_declaring_the_slack_integration_is_detected():
    assert needs_migration(WITH_SLACK_INTEGRATION) is True


def test_the_runtime_refuses_the_slack_integration_and_names_channels():
    with pytest.raises(ConfigTooOld) as exc:
        assert_current(WITH_SLACK_INTEGRATION)
    message = str(exc.value)
    assert "integrations.slack" in message and "channels.slack" in message


def test_migration_removes_the_slack_integration_and_points_at_the_bot():
    report = migrate_cli_config(WITH_SLACK_INTEGRATION)
    assert report.changed is True
    assert "slack" not in report.config.get("integrations", {})
    assert report.config["integrations"]["github"] == {"transport": "auto"}
    assert any("channels.slack" in move for move in report.moves)
    assert any("bot" in note for note in report.notes)
    assert_current(report.config)


def test_migrating_a_slack_only_integrations_block_leaves_no_husk():
    report = migrate_cli_config(
        {"version": "0.4.0", "integrations": {"slack": {"transport": "webhook"}}}
    )
    assert "integrations" not in report.config
    assert_current(report.config)


def test_the_slack_integration_migration_is_idempotent():
    once = migrate_cli_config(WITH_SLACK_INTEGRATION)
    twice = migrate_cli_config(once.config)
    assert twice.changed is False
    assert twice.config == once.config


# --- the unread collaborator / notification blocks retired (issue-304) ----------

#: A 0.5.0 config carrying both retired blocks, filled in the way an operator who
#: believed they were configuring notifications would have filled them, plus the
#: neighbours that must survive untouched — including the two allow-lists that are the
#: only places human identity is declared.
WITH_UNREAD_BLOCKS = {
    "version": "0.5.0",
    "state": {"root": ".the-loop"},
    "routing": {"enabled": True, "authorizedUsers": ["octocat"]},
    "collaborators": [
        {
            "handle": "@octocat",
            "kind": "individual",
            "roles": ["engineer", "approver"],
            "notifications": {
                "enabled": True,
                "channels": [
                    {
                        "type": "slack",
                        "enabled": True,
                        "via": "mcp",
                        "config": {"channel-list": ["#the-loop-daemon"]},
                    }
                ],
            },
        }
    ],
    "notifications": {
        "enabled": True,
        "events": {"dispatch-failed": ["engineer"], "session-died": ["engineer"]},
    },
    "channels": {"slack": {"enabled": True, "authorizedUsers": ["U024BE7LH"]}},
}


def test_a_config_still_declaring_the_unread_blocks_is_detected():
    assert needs_migration(WITH_UNREAD_BLOCKS) is True


def test_a_config_that_lies_about_its_version_is_still_detected():
    """
    Feature: detection is by key, not by the version the file claims
      Scenario: a hand-edited config stamps the current version but keeps the block
        Given a config declaring the current version and a `collaborators` list
        When it is checked
        Then it still needs migration, and the runtime still refuses it

    Requirement: docs/specs/issue-304/requirements.md abuse case A1
    """
    lying = {"version": CURRENT_CONFIG_VERSION, "collaborators": []}
    assert needs_migration(lying) is True
    with pytest.raises(ConfigTooOld):
        assert_current(lying)


@pytest.mark.parametrize("key", ["collaborators", "notifications"])
def test_the_runtime_refuses_an_unread_block_and_names_channels_slack(key):
    """
    Feature: a removed block stops the daemon rather than loading half-configured
      Scenario: a config still declares a block nothing ever read
        Given a config carrying `collaborators` or `notifications`
        When the runtime checks it
        Then it refuses, naming the key, `channels.slack`, both allow-lists and the
             upgrade command

    Requirement: docs/specs/issue-304/requirements.md R2.2, abuse case A2
    """
    with pytest.raises(ConfigTooOld) as exc:
        assert_current({"version": "0.5.0", key: {} if key == "notifications" else []})
    message = str(exc.value)
    assert f"`{key}`" in message
    assert "channels.slack" in message
    assert "routing.authorizedUsers" in message
    assert "upgrade-the-loop" in message


def test_migration_removes_both_blocks_and_leaves_everything_else_alone():
    """
    Feature: the migration is a deterministic key removal
      Scenario: a 0.5.0 config with both retired blocks is migrated
        Given a config also carrying state, routing and channels
        When it is migrated
        Then both blocks are gone, the version is bumped, both removals are reported,
             and every neighbouring key is byte-identical to what went in

    Requirement: docs/specs/issue-304/requirements.md R3.1, R3.2, abuse case A3
    """
    before = copy.deepcopy(WITH_UNREAD_BLOCKS)
    report = migrate_cli_config(WITH_UNREAD_BLOCKS)

    assert report.changed is True
    assert "collaborators" not in report.config
    assert "notifications" not in report.config
    assert report.config["version"] == CURRENT_CONFIG_VERSION
    assert len([m for m in report.moves if "issue-304" in m]) == 2
    # Untouched: the poller's root, and the only two places identity is declared.
    assert report.config["state"] == before["state"]
    assert report.config["routing"] == before["routing"]
    assert report.config["channels"] == before["channels"]
    assert WITH_UNREAD_BLOCKS == before  # the input is never mutated
    assert_current(report.config)


def test_a_filled_in_block_is_told_where_to_configure_the_channel():
    """R3.4 — "removed" and "removed, and here is where it went" are different
    messages to somebody who set the value."""
    report = migrate_cli_config(WITH_UNREAD_BLOCKS)
    assert any(
        "channels.slack" in note and "per-person routing is not built" in note
        for note in report.notes
    )


def test_an_empty_block_is_removed_without_a_lecture():
    """The shipped default was `collaborators: []` / `events: {}`. Telling that
    operator to go and set a Slack bot up is noise, and a noisy report goes unread."""
    report = migrate_cli_config(
        {"version": "0.5.0", "collaborators": [], "notifications": {"events": {}}}
    )
    assert report.changed is True
    assert report.notes == []


def test_the_unread_block_migration_is_idempotent():
    """R3.3 — safe to wire into an upgrade command an operator may re-run."""
    once = migrate_cli_config(WITH_UNREAD_BLOCKS)
    twice = migrate_cli_config(once.config)
    assert twice.changed is False
    assert twice.config == once.config
