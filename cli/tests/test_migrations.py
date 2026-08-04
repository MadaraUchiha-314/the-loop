"""The breaking config migrations (issue-109 R6a, issue-128).

A breaking change is only as good as its migration, so each is tested both
ways: an old config migrates to the expected new one, AND the runtime refuses
an un-migrated one.

Three so far — `ghBinary` (one `integrations` block replaced three copies),
`polling.stateFile` (the poller's ledger became one record per work item under
`state.root`, so a file path has nothing left to point at), and
`webhooks.ghWebhook.routing` (promoted to a top-level `routing`, because the
poller reads that same block and a key named `webhooks` said otherwise).
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
