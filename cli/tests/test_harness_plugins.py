"""Unit tests for enabling the-loop's own plugin before a spawn (issue-143).

Same rule as ``test_trust.py``: every test drives a **fake HOME** under
``tmp_path``, because the file under test is the developer's real
``~/.claude/settings.json``.
"""

import json
import os
from pathlib import Path

import pytest

from the_loop.harness import build_adapters
from the_loop.harness.claude_code import ClaudeCodeAdapter
from the_loop.harness.cursor_agent import CursorAgentAdapter
from the_loop.harness_plugins import (
    DEFAULT_MARKETPLACE_REPO,
    MARKETPLACE_NAME,
    PLUGIN_KEY,
    ClaudePluginStore,
    PluginConfig,
)
from the_loop.trust import ClaudeTrustStore, TrustConfig


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """A HOME nothing else writes to, exported so bare stores pick it up."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    return home


def store_for(home, **env):
    return ClaudePluginStore(ClaudeTrustStore(env={"HOME": str(home), **env}))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


# -- the write itself ----------------------------------------------------------


def test_enable_writes_the_marketplace_and_the_plugin(fake_home):
    """The exact shape issue-143 asks for, in the user settings file."""
    store = store_for(fake_home)
    result = store.enable(DEFAULT_MARKETPLACE_REPO)

    assert result.ok
    assert result.applied
    settings = read_json(fake_home / ".claude" / "settings.json")
    assert settings["extraKnownMarketplaces"] == {
        MARKETPLACE_NAME: {
            "source": {"source": "github", "repo": DEFAULT_MARKETPLACE_REPO}
        }
    }
    assert settings["enabledPlugins"] == {PLUGIN_KEY: True}
    assert PLUGIN_KEY == "the-loop@the-loop"


def test_enable_merges_into_existing_settings(fake_home):
    """Everything already in the file survives — this is the operator's config."""
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "skipDangerousModePermissionPrompt": True,
                "enabledPlugins": {"other@shop": True},
                "extraKnownMarketplaces": {
                    "shop": {"source": {"source": "github", "repo": "acme/shop"}}
                },
            }
        )
    )

    assert store_for(fake_home).enable(DEFAULT_MARKETPLACE_REPO).ok

    settings = read_json(settings_path)
    assert settings["skipDangerousModePermissionPrompt"] is True
    assert settings["enabledPlugins"] == {"other@shop": True, PLUGIN_KEY: True}
    assert set(settings["extraKnownMarketplaces"]) == {"shop", MARKETPLACE_NAME}


def test_enable_is_idempotent(fake_home):
    """A daemon spawns constantly; the second call must not touch the file."""
    store = store_for(fake_home)
    assert store.enable(DEFAULT_MARKETPLACE_REPO).applied

    settings_path = fake_home / ".claude" / "settings.json"
    before = settings_path.read_bytes()
    second = store.enable(DEFAULT_MARKETPLACE_REPO)

    assert second.ok
    assert second.applied == []
    assert settings_path.read_bytes() == before


def test_claude_config_dir_is_honoured(tmp_path, fake_home):
    """Path resolution is delegated to the trust store, not re-implemented."""
    elsewhere = tmp_path / "cfg"
    store = store_for(fake_home, CLAUDE_CONFIG_DIR=str(elsewhere))

    assert store.settings_path() == elsewhere / "settings.json"
    assert store.enable(DEFAULT_MARKETPLACE_REPO).ok
    assert PLUGIN_KEY in read_json(elsewhere / "settings.json")["enabledPlugins"]


# -- never overwrite the operator's own choices --------------------------------


def test_an_existing_marketplace_entry_is_left_alone(fake_home):
    """A fork, a local checkout, a marketplace of their own: all stay."""
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    mine = {"source": {"source": "github", "repo": "someone/their-fork"}}
    settings_path.write_text(json.dumps({"extraKnownMarketplaces": {"the-loop": mine}}))

    assert store_for(fake_home).enable(DEFAULT_MARKETPLACE_REPO).ok

    settings = read_json(settings_path)
    assert settings["extraKnownMarketplaces"][MARKETPLACE_NAME] == mine
    assert settings["enabledPlugins"] == {PLUGIN_KEY: True}


def test_a_deliberately_disabled_plugin_stays_disabled(fake_home):
    """`false` is a decision. Flipping it back on would be the-loop overruling it."""
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"enabledPlugins": {PLUGIN_KEY: False}}))

    assert store_for(fake_home).enable(DEFAULT_MARKETPLACE_REPO).ok
    assert read_json(settings_path)["enabledPlugins"][PLUGIN_KEY] is False


def test_a_non_object_container_is_reported_and_left_untouched(fake_home):
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    raw = json.dumps({"enabledPlugins": ["the-loop@the-loop"]})
    settings_path.write_text(raw)

    result = store_for(fake_home).enable(DEFAULT_MARKETPLACE_REPO)

    assert not result.ok
    assert "enabledPlugins" in result.error
    assert settings_path.read_text() == raw


def test_an_unparseable_settings_file_is_never_overwritten(fake_home):
    settings_path = fake_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{ not json")

    result = store_for(fake_home).enable(DEFAULT_MARKETPLACE_REPO)

    assert not result.ok
    assert settings_path.read_text() == "{ not json"


@pytest.mark.parametrize(
    "repo",
    [
        "https://github.com/MadaraUchiha-314/the-loop",
        "MadaraUchiha-314/the-loop; rm -rf /",
        "../../etc/passwd",
        "MadaraUchiha-314",
        "a/b/c",
    ],
)
def test_a_malformed_marketplace_repo_writes_nothing(fake_home, repo):
    """Fail closed: junk never lands in the operator's settings file."""
    result = store_for(fake_home).enable(repo)

    assert not result.ok
    assert "marketplaceRepo" in result.error
    assert not (fake_home / ".claude" / "settings.json").exists()


def test_an_empty_marketplace_repo_enables_without_registering(fake_home):
    """The escape hatch for an operator who registers the marketplace themselves."""
    result = store_for(fake_home).enable("")

    assert result.ok
    settings = read_json(fake_home / ".claude" / "settings.json")
    assert settings["enabledPlugins"] == {PLUGIN_KEY: True}
    assert "extraKnownMarketplaces" not in settings


# -- config --------------------------------------------------------------------


def test_plugin_config_defaults_and_overrides():
    assert PluginConfig.from_mapping({}) == PluginConfig(
        enabled=True, marketplace_repo=DEFAULT_MARKETPLACE_REPO
    )
    assert PluginConfig.from_mapping({"enabled": False}).enabled is False
    assert (
        PluginConfig.from_mapping({"marketplaceRepo": "me/mine"}).marketplace_repo
        == "me/mine"
    )


# -- adapter wiring ------------------------------------------------------------


def test_the_adapter_enables_the_plugin_before_a_spawn(tmp_path, fake_home):
    workdir = tmp_path / "checkout"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter()

    result = adapter.prepare_environment(str(workdir))

    assert result.ok
    settings = read_json(fake_home / ".claude" / "settings.json")
    assert settings["enabledPlugins"] == {PLUGIN_KEY: True}
    # …alongside the trust write, which is a different file entirely.
    assert (
        read_json(fake_home / ".claude.json")["projects"][str(workdir)][
            "hasTrustDialogAccepted"
        ]
        is True
    )


def test_the_two_pre_spawn_steps_are_independently_switchable(tmp_path, fake_home):
    """Trust off must not take the plugin write with it, and vice versa."""
    workdir = tmp_path / "checkout"
    workdir.mkdir()
    settings = fake_home / ".claude" / "settings.json"
    config = fake_home / ".claude.json"

    # trust off, plugins on — the plugin write still happens, and only it.
    assert (
        ClaudeCodeAdapter(trust=TrustConfig(enabled=False))
        .prepare_environment(str(workdir))
        .ok
    )
    assert PLUGIN_KEY in read_json(settings)["enabledPlugins"]
    assert not config.exists()

    # plugins off, trust on — the trust write still happens, and only it.
    settings.unlink()
    assert (
        ClaudeCodeAdapter(plugins=PluginConfig(enabled=False))
        .prepare_environment(str(workdir))
        .ok
    )
    assert config.exists()
    assert not settings.exists()


def test_plugins_disabled_writes_nothing(tmp_path, fake_home):
    workdir = tmp_path / "checkout"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(
        trust=TrustConfig(enabled=False), plugins=PluginConfig(enabled=False)
    )

    result = adapter.prepare_environment(str(workdir))

    assert result.ok
    assert result.applied == []
    assert not (fake_home / ".claude" / "settings.json").exists()


def test_a_custom_marketplace_repo_reaches_the_settings_file(tmp_path, fake_home):
    workdir = tmp_path / "checkout"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(plugins=PluginConfig(marketplace_repo="me/my-loop"))

    assert adapter.prepare_environment(str(workdir)).ok

    settings = read_json(fake_home / ".claude" / "settings.json")
    assert settings["extraKnownMarketplaces"][MARKETPLACE_NAME]["source"] == {
        "source": "github",
        "repo": "me/my-loop",
    }


def test_cursor_has_no_plugin_surface_and_stays_a_no_op(tmp_path, fake_home):
    workdir = tmp_path / "checkout"
    workdir.mkdir()

    result = CursorAgentAdapter(plugins=PluginConfig()).prepare_environment(
        str(workdir)
    )

    assert result.ok
    assert result.applied == []
    assert not (fake_home / ".claude" / "settings.json").exists()


def test_build_adapters_passes_the_policy_through():
    plugins = PluginConfig(enabled=False, marketplace_repo="me/mine")
    adapters = build_adapters({}, None, plugins)
    assert adapters["claude"].plugins is plugins
    assert adapters["cursor"].plugins is plugins
    # Existing callers that pass only args/trust keep the defaults.
    assert build_adapters({}, None)["claude"].plugins == PluginConfig()
