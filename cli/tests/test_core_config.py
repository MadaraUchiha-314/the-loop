"""Unit tests for the core CLI-config surface (issue-222, T3).

Every rejection is asserted **twice** — the call raises, *and* the file on disk is
byte-identical to what it was — because "the service refused it" and "the service did not
half-write it" are different claims, and only the second one protects the operator's
daemon.
"""

from pathlib import Path

import pytest
import yaml

from the_loop import yamlpatch
from the_loop.core import config as core_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "cli-config.yaml"


@pytest.fixture()
def config_file(tmp_path) -> Path:
    path = tmp_path / ".the-loop" / "cli-config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _refusal_leaves_the_file_alone(
    path: Path, patch: dict, expected: type = ValueError
):
    before = path.read_bytes()
    with pytest.raises(expected) as excinfo:
        core_config.update_config(patch, path)
    assert path.read_bytes() == before
    return str(excinfo.value)


# -- reading -----------------------------------------------------------------------


def test_a_workstation_with_no_config_reads_as_empty_not_as_an_error(tmp_path):
    """
    Feature: reading the CLI config
      Scenario: the machine has never been configured
        Given no config file at the resolved path
        When the config is read
        Then it reports exists: false, an empty config, and the path it would write

    Requirement: docs/specs/issue-222/requirements.md R1.1, R1.2
    """
    path = tmp_path / "cli-config.yaml"
    assert core_config.get_config(path) == {
        "path": str(path),
        "exists": False,
        "version": "",
        "config": {},
    }


def test_reading_serves_the_document_as_authored(config_file):
    document = core_config.get_config(config_file)
    assert document["exists"] is True
    assert document["version"] == "0.4.0"
    assert document["config"] == yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    # `load_cli_config` would fan `integrations.github.cli.binary` out into private
    # `_ghBinary` keys; they are not in the schema and would fail the next save.
    assert "_ghBinary" not in yaml.safe_dump(document["config"])


def test_an_unparseable_config_is_an_error_not_an_empty_config(config_file):
    """
    Feature: reading the CLI config
      Scenario: the file is halfway through an edit
        Given a config file that is not valid YAML
        When the config is read
        Then it raises, rather than reporting that everything is at its default

    Requirement: docs/specs/issue-222/requirements.md R1.5
    """
    config_file.write_text("routing: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        core_config.get_config(config_file)


def test_the_schema_is_served_with_its_refs_resolved():
    schema = core_config.get_schema()
    assert schema["properties"]["collaborators"]["items"]["properties"]["handle"]


# -- writing -----------------------------------------------------------------------


def test_a_save_changes_the_named_key_and_keeps_the_comments(config_file):
    """
    Feature: saving a CLI config change
      Scenario: one value changes in a commented config
        Given the shipped config template on disk
        When routing.enabled is patched to true
        Then the file holds the new value, every comment, and nothing else changed

    Requirement: docs/specs/issue-222/requirements.md R2.1, R2.2
    """
    before = config_file.read_text(encoding="utf-8")
    result = core_config.update_config({"routing": {"enabled": True}}, config_file)

    assert result["written"] is True
    assert result["changed"] == ["routing.enabled"]
    assert result["restartRequired"] == []
    after = config_file.read_text(encoding="utf-8")
    assert yaml.safe_load(after)["routing"]["enabled"] is True
    assert _comments(after) == _comments(before)
    assert result["config"] == yaml.safe_load(after)


def test_an_empty_or_unchanged_patch_writes_nothing(config_file):
    """
    Feature: saving a CLI config change
      Scenario: the operator saves without changing anything
        Given a config file
        When an empty patch, or one re-sending existing values, is applied
        Then nothing is written and the response says so

    Requirement: docs/specs/issue-222/requirements.md R2.5
    """
    before = config_file.read_bytes()
    for patch in ({}, {"routing": {"enabled": False}}):
        result = core_config.update_config(patch, config_file)
        assert result["written"] is False
        assert result["changed"] == []
        assert config_file.read_bytes() == before

    # ...and an empty patch does not conjure a file on a machine that has none, which
    # the `version` a first save stamps would otherwise do.
    missing = config_file.parent / "absent.yaml"
    assert core_config.update_config({}, missing)["written"] is False
    assert not missing.exists()


def test_a_missing_file_is_created_with_its_modeline_and_version(tmp_path):
    """
    Feature: saving a CLI config change
      Scenario: the first save on a machine with no config
        Given no config file
        When a patch is saved
        Then the file is created, opening with the schema modeline and a version

    Requirement: docs/specs/issue-222/requirements.md R2.4
    """
    path = tmp_path / "nested" / "cli-config.yaml"
    result = core_config.update_config({"routing": {"enabled": True}}, path)

    assert result["written"] is True
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# yaml-language-server: $schema=")
    assert yaml.safe_load(text)["version"] == "0.4.0"
    assert yaml.safe_load(text)["routing"] == {"enabled": True}
    assert path.stat().st_mode & 0o777 == 0o600


def test_an_existing_file_keeps_its_mode(config_file):
    config_file.chmod(0o644)
    core_config.update_config({"routing": {"enabled": True}}, config_file)
    assert config_file.stat().st_mode & 0o777 == 0o644


def test_a_symlinked_config_is_written_through_rather_than_replaced(
    tmp_path, config_file
):
    """
    Feature: a save respects how the operator arranged their files
      Scenario: the resolved config path is a symlink to the real file
        Given ~/.the-loop/cli-config.yaml symlinked to a file in a repository
        When a change is saved
        Then the real file changes and the link is still a link

    Requirement: docs/specs/issue-222/requirements.md R2.7
    """
    link = tmp_path / "link-config.yaml"
    link.symlink_to(config_file)

    core_config.update_config({"routing": {"enabled": True}}, link)

    assert link.is_symlink()
    assert (
        yaml.safe_load(config_file.read_text(encoding="utf-8"))["routing"]["enabled"]
        is True
    )


def test_a_write_leaves_no_temporary_file_behind(config_file):
    core_config.update_config({"routing": {"enabled": True}}, config_file)
    assert [p.name for p in config_file.parent.iterdir()] == [config_file.name]


def test_a_bind_change_is_restart_required_and_a_routing_change_is_not(config_file):
    """
    Feature: a saved change says whether it is live
      Scenario: the operator changes the port, then a routing value
        Given a running service
        When service.port is saved, and then routing.enabled
        Then only the first is reported under restartRequired

    Requirement: docs/specs/issue-222/requirements.md R4.4, R4.5
    """
    port = core_config.update_config({"service": {"port": 4200}}, config_file)
    assert port["restartRequired"] == ["service.port"]

    cors = core_config.update_config(
        {"service": {"cors": {"allowOrigins": ["https://example.test"]}}}, config_file
    )
    assert cors["restartRequired"] == ["service.cors.allowOrigins"]

    routing = core_config.update_config({"routing": {"enabled": True}}, config_file)
    assert routing["restartRequired"] == []


# -- refusals ----------------------------------------------------------------------


def test_an_invalid_change_is_refused_and_the_file_is_untouched(config_file):
    """
    Feature: an invalid config never reaches disk
      Scenario: a patch would violate the schema
        Given a config file
        When a patch introduces an unknown key or a wrong type
        Then the call raises naming the key, and the file is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R3.1, R3.4, R3.5
    """
    assert "routing.nope" in _refusal_leaves_the_file_alone(
        config_file, {"routing": {"nope": True}}
    )
    assert "polling.intervalSeconds" in _refusal_leaves_the_file_alone(
        config_file, {"polling": {"intervalSeconds": "soon"}}
    )


def test_the_unbootable_cors_pairing_cannot_be_saved(config_file):
    """
    Feature: a save cannot leave the service unable to restart
      Scenario: every origin allowed, with credentials
        Given a config file
        When allowOrigins ["*"] and allowCredentials true are saved together
        Then the call raises and the file is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R3.3
    """
    message = _refusal_leaves_the_file_alone(
        config_file,
        {"service": {"cors": {"allowOrigins": ["*"], "allowCredentials": True}}},
    )
    assert "allowCredentials" in message


def test_a_config_below_the_current_version_is_refused_with_the_fix(config_file):
    """
    Feature: the migration gate holds on the write path too
      Scenario: an un-migrated config is edited from the UI
        Given a config declaring an older version
        When any change is saved
        Then the refusal names the upgrade command, and nothing is written

    Requirement: docs/specs/issue-222/requirements.md R3.2
    """
    config_file.write_text(
        "version: '0.1.0'\nrouting:\n  enabled: false\n", encoding="utf-8"
    )
    message = _refusal_leaves_the_file_alone(
        config_file, {"routing": {"enabled": True}}
    )
    assert "upgrade-the-loop" in message


def test_a_patch_that_is_not_an_object_is_refused(config_file):
    _refusal_leaves_the_file_alone(config_file, ["routing"])  # type: ignore[arg-type]


def test_an_unverifiable_splice_writes_nothing(config_file, monkeypatch):
    """
    Feature: an edit that cannot be proven is not written
      Scenario: the splicer cannot show it produced the intended document
        Given a config file
        When the splice fails verification
        Then SpliceError propagates and the file is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R2.8
    """
    monkeypatch.setattr(yamlpatch, "_dump_inline", lambda value: "0")
    _refusal_leaves_the_file_alone(
        config_file, {"routing": {"autoExecuteLabel": "x"}}, yamlpatch.SpliceError
    )


def _comments(text: str) -> list:
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]
