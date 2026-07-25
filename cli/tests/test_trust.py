"""Unit tests for pre-seeding a harness's config before a spawn (issue-90).

Every test drives a **fake HOME** under ``tmp_path``: nothing here may read or
write the developer's real ``~/.claude.json``, which is the whole reason
``ClaudeTrustStore`` takes an injectable env/home.
"""

import json
import os
from pathlib import Path

import pytest

from the_loop.harness import build_adapters
from the_loop.harness.claude_code import ClaudeCodeAdapter
from the_loop.harness.cursor_agent import CursorAgentAdapter
from the_loop.trust import (
    ClaudeTrustStore,
    TrustConfig,
    TrustResult,
    args_request_bypass,
    is_too_broad,
    is_within,
)


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
    return ClaudeTrustStore(env={"HOME": str(home), **env})


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


# -- config layout -------------------------------------------------------------


def test_default_paths_follow_home(fake_home):
    store = store_for(fake_home)
    assert store.config_dir() == fake_home / ".claude"
    assert store.config_path() == fake_home / ".claude.json"
    assert store.settings_path() == fake_home / ".claude" / "settings.json"


def test_claude_config_dir_overrides_both_paths(tmp_path, fake_home):
    elsewhere = tmp_path / "cfg"
    store = store_for(fake_home, CLAUDE_CONFIG_DIR=str(elsewhere))
    assert store.config_dir() == elsewhere
    assert store.config_path() == elsewhere / ".claude.json"
    assert store.settings_path() == elsewhere / "settings.json"


def test_scoped_config_json_wins_when_it_exists(fake_home):
    scoped = fake_home / ".claude" / ".config.json"
    scoped.parent.mkdir(parents=True)
    scoped.write_text("{}")
    assert store_for(fake_home).config_path() == scoped


# -- project keys --------------------------------------------------------------


def test_project_key_is_the_exact_directory(tmp_path, fake_home):
    workdir = tmp_path / "work" / "item"
    workdir.mkdir(parents=True)
    assert ClaudeTrustStore.project_keys(str(workdir) + "/") == [str(workdir)]


def test_symlinked_directory_records_both_keys(tmp_path, fake_home):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    keys = ClaudeTrustStore.project_keys(str(link))
    assert keys == [str(link), str(real)]


def test_without_a_root_no_ancestor_key_is_ever_written(tmp_path, fake_home):
    """Trust-creep guard: widening to a parent must be an explicit `root`.

    Under `scope: directory` (and any setup with no workspace root) trusting a
    checkout must not trust its siblings — the caller opts into ancestor trust
    by passing a root, it never happens implicitly.
    """
    workdir = tmp_path / "workspace" / "worktrees" / "repo" / "slug"
    workdir.mkdir(parents=True)
    store = store_for(fake_home)
    assert store.trust(str(workdir)).ok

    projects = read_json(store.config_path())["projects"]
    assert list(projects) == [str(workdir)]
    for parent in Path(workdir).parents:
        assert str(parent) not in projects


# -- scope: workspace-root -----------------------------------------------------


def test_root_scope_trusts_the_root_and_onboards_the_checkout(tmp_path, fake_home):
    """The two keys scope differently — trust inherits, onboarding does not."""
    root = tmp_path / "workspace"
    workdir = root / ".worktrees" / "github.com" / "octo" / "repo" / "slug"
    workdir.mkdir(parents=True)
    store = store_for(fake_home)

    assert store.trust(str(workdir), str(root)).ok

    projects = read_json(store.config_path())["projects"]
    # trust on the root: the harness walks up, so every checkout beneath is covered
    assert projects[str(root)]["hasTrustDialogAccepted"] is True
    assert "hasCompletedProjectOnboarding" not in projects[str(root)]
    # onboarding is read from the exact project key, so it lands on the checkout
    assert projects[str(workdir)]["hasCompletedProjectOnboarding"] is True
    assert "hasTrustDialogAccepted" not in projects[str(workdir)]


def test_root_scope_is_idempotent_across_sibling_checkouts(tmp_path, fake_home):
    """The second work item under the same root re-uses its trust entry."""
    root = tmp_path / "workspace"
    first = root / "a"
    second = root / "b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    store = store_for(fake_home)
    store.trust(str(first), str(root))

    assert store.trust(str(second), str(root)).ok

    projects = read_json(store.config_path())["projects"]
    assert projects[str(root)]["hasTrustDialogAccepted"] is True
    # only the per-checkout onboarding key was added the second time
    assert projects[str(second)]["hasCompletedProjectOnboarding"] is True
    assert "hasTrustDialogAccepted" not in projects[str(second)]


def test_a_root_that_does_not_contain_the_cwd_is_ignored(tmp_path, fake_home):
    """A misconfigured root must never trust an unrelated tree."""
    root = tmp_path / "workspace"
    root.mkdir()
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    store = store_for(fake_home)

    assert store.trust(str(elsewhere), str(root)).ok

    projects = read_json(store.config_path())["projects"]
    assert str(root) not in projects
    assert projects[str(elsewhere)]["hasTrustDialogAccepted"] is True


def test_is_within_compares_components_not_string_prefixes(tmp_path):
    assert is_within("/ws", "/ws/a/b") is True
    assert is_within("/ws", "/ws") is True
    assert is_within("/ws", "/ws-other/a") is False
    assert is_within("/ws/a", "/ws") is False


def test_is_too_broad_rejects_root_and_home_only(tmp_path):
    home = tmp_path / "home"
    assert is_too_broad("/", home=str(home)) is True
    assert is_too_broad(str(home), home=str(home)) is True
    # a directory *under* home is a perfectly normal workspace root
    assert is_too_broad(str(home / "the-loop" / "workspace"), home=str(home)) is False


# -- trust writes --------------------------------------------------------------


def test_trust_creates_the_config_owner_only(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    store = store_for(fake_home)

    result = store.trust(str(workdir))

    assert result.ok and result.applied
    entry = read_json(store.config_path())["projects"][str(workdir)]
    assert entry["hasTrustDialogAccepted"] is True
    assert entry["hasCompletedProjectOnboarding"] is True
    assert store.config_path().stat().st_mode & 0o777 == 0o600


def test_trust_preserves_unrelated_keys_and_merges_the_entry(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    store = store_for(fake_home)
    store.config_path().write_text(
        json.dumps(
            {
                "userID": "keep-me",
                "projects": {
                    "/somewhere/else": {"allowedTools": ["Bash"]},
                    str(workdir): {"allowedTools": ["Read"], "mcpServers": {}},
                },
            }
        )
    )

    assert store.trust(str(workdir)).ok

    data = read_json(store.config_path())
    assert data["userID"] == "keep-me"
    assert data["projects"]["/somewhere/else"] == {"allowedTools": ["Bash"]}
    entry = data["projects"][str(workdir)]
    assert entry["allowedTools"] == ["Read"]  # merged, not replaced
    assert entry["mcpServers"] == {}
    assert entry["hasTrustDialogAccepted"] is True


def test_trust_is_idempotent_and_writes_nothing_the_second_time(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    store = store_for(fake_home)
    assert store.trust(str(workdir)).applied

    before = store.config_path().stat()
    again = store.trust(str(workdir))

    assert again.ok and again.applied == []
    after = store.config_path().stat()
    assert (after.st_mtime_ns, after.st_ino) == (before.st_mtime_ns, before.st_ino)


def test_trust_rejects_an_empty_directory(fake_home):
    result = store_for(fake_home).trust("")
    assert not result.ok
    assert "working directory" in result.error


def test_invalid_json_is_reported_and_left_byte_for_byte_untouched(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    store = store_for(fake_home)
    original = b"{ this is not json"
    store.config_path().write_bytes(original)

    result = store.trust(str(workdir))

    assert not result.ok and "not valid JSON" in result.error
    assert store.config_path().read_bytes() == original


def test_a_symlinked_config_is_written_through_not_replaced(tmp_path, fake_home):
    """A dotfiles-linked ~/.claude.json must survive: os.replace swaps names."""
    workdir = tmp_path / "wt"
    workdir.mkdir()
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    real = dotfiles / "claude.json"
    real.write_text(json.dumps({"userID": "keep-me"}))
    store = store_for(fake_home)
    store.config_path().symlink_to(real)

    assert store.trust(str(workdir)).ok

    assert store.config_path().is_symlink()  # link intact
    data = read_json(real)  # written through it
    assert data["userID"] == "keep-me"
    assert data["projects"][str(workdir)]["hasTrustDialogAccepted"] is True


def test_non_object_config_is_refused(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    store = store_for(fake_home)
    store.config_path().write_text("[1, 2, 3]")

    result = store.trust(str(workdir))

    assert not result.ok and "JSON object" in result.error
    assert store.config_path().read_text() == "[1, 2, 3]"


# -- bypass acceptance ---------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--dangerously-skip-permissions"],
        ["--permission-mode", "bypassPermissions"],
        ["--permission-mode=bypassPermissions"],
        ["--verbose", "--dangerously-skip-permissions", "--foo"],
    ],
)
def test_args_request_bypass_recognises_every_spelling(args):
    assert args_request_bypass(args) is True


@pytest.mark.parametrize(
    "args",
    [
        [],
        None,
        ["--permission-mode", "acceptEdits"],
        ["--permission-mode"],  # dangling flag, no value
        ["--dangerously-skip-permissions-not-really"],
    ],
)
def test_args_request_bypass_is_false_otherwise(args):
    assert args_request_bypass(args) is False


def test_accept_bypass_writes_both_the_setting_and_the_legacy_key(fake_home):
    store = store_for(fake_home)

    result = store.accept_bypass_permissions()

    assert result.ok and result.applied
    assert read_json(store.settings_path())["skipDangerousModePermissionPrompt"] is True
    assert read_json(store.config_path())["bypassPermissionsModeAccepted"] is True


def test_accept_bypass_is_idempotent(fake_home):
    store = store_for(fake_home)
    store.accept_bypass_permissions()
    assert store.accept_bypass_permissions().applied == []


# -- adapter integration -------------------------------------------------------


def test_claude_adapter_trusts_but_does_not_accept_bypass_by_default(
    tmp_path, fake_home
):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(extra_args=["--permission-mode", "acceptEdits"])

    result = adapter.prepare_environment(str(workdir))

    assert result.ok and result.applied
    store = store_for(fake_home)
    assert read_json(store.config_path())["projects"][str(workdir)][
        "hasTrustDialogAccepted"
    ]
    # the-loop never widens permissions the operator did not request
    assert not store.settings_path().exists()


def test_claude_adapter_accepts_bypass_when_the_args_ask_for_it(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(extra_args=["--dangerously-skip-permissions"])

    assert adapter.prepare_environment(str(workdir)).ok

    settings = read_json(store_for(fake_home).settings_path())
    assert settings["skipDangerousModePermissionPrompt"] is True


def test_accept_bypass_never_overrides_the_args(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(
        extra_args=["--dangerously-skip-permissions"],
        trust=TrustConfig(accept_bypass_permissions="never"),
    )

    assert adapter.prepare_environment(str(workdir)).ok
    assert not store_for(fake_home).settings_path().exists()


def test_accept_bypass_always_applies_without_the_args(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(trust=TrustConfig(accept_bypass_permissions="always"))

    assert adapter.prepare_environment(str(workdir)).ok
    assert store_for(fake_home).settings_path().exists()


def test_disabled_trust_writes_nothing_at_all(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(
        extra_args=["--dangerously-skip-permissions"],
        trust=TrustConfig(enabled=False),
    )

    result = adapter.prepare_environment(str(workdir))

    assert result.ok and result.applied == []
    assert list(fake_home.iterdir()) == []


def test_cursor_adapter_is_a_silent_noop(tmp_path, fake_home):
    workdir = tmp_path / "wt"
    workdir.mkdir()

    result = CursorAgentAdapter().prepare_environment(str(workdir))

    assert result.ok and result.applied == []
    assert list(fake_home.iterdir()) == []


def test_build_adapters_threads_the_trust_policy_through():
    policy = TrustConfig(enabled=False, accept_bypass_permissions="always")
    adapters = build_adapters({"claude": ["--foo"]}, policy)
    assert adapters["claude"].trust is policy
    assert adapters["cursor"].trust is policy


# -- config mapping ------------------------------------------------------------


def test_directory_scope_makes_the_adapter_drop_the_root(tmp_path, fake_home):
    """`scope: directory` ignores a root even when the dispatcher offers one."""
    root = tmp_path / "workspace"
    workdir = root / "wt"
    workdir.mkdir(parents=True)
    adapter = ClaudeCodeAdapter(trust=TrustConfig(scope="directory"))

    assert adapter.prepare_environment(str(workdir), str(root)).ok

    projects = read_json(store_for(fake_home).config_path())["projects"]
    assert str(root) not in projects
    assert projects[str(workdir)]["hasTrustDialogAccepted"] is True


def test_root_scope_is_the_adapter_default(tmp_path, fake_home):
    root = tmp_path / "workspace"
    workdir = root / "wt"
    workdir.mkdir(parents=True)

    assert ClaudeCodeAdapter().prepare_environment(str(workdir), str(root)).ok

    projects = read_json(store_for(fake_home).config_path())["projects"]
    assert projects[str(root)]["hasTrustDialogAccepted"] is True


def test_trust_config_defaults_and_mapping():
    assert TrustConfig.from_mapping({}) == TrustConfig(
        enabled=True, scope="workspace-root", accept_bypass_permissions="auto"
    )
    assert TrustConfig.from_mapping({"scope": "directory"}).scope == "directory"
    # an unknown scope degrades to the documented default, never to something
    # narrower-or-wider by accident
    assert TrustConfig.from_mapping({"scope": "yolo"}).scope == "workspace-root"
    assert TrustConfig(scope="workspace-root").roots_allowed is True
    assert TrustConfig(scope="directory").roots_allowed is False
    parsed = TrustConfig.from_mapping(
        {"enabled": False, "acceptBypassPermissions": "never"}
    )
    assert parsed == TrustConfig(enabled=False, accept_bypass_permissions="never")
    # an unknown mode degrades to the safe default rather than exploding
    assert (
        TrustConfig.from_mapping(
            {"acceptBypassPermissions": "yolo"}
        ).accept_bypass_permissions
        == "auto"
    )


def test_trust_result_merge_keeps_all_notes_and_the_first_error():
    merged = TrustResult(applied=["a"]).merge(
        TrustResult(ok=False, applied=["b"], error="boom")
    )
    assert merged.ok is False
    assert merged.applied == ["a", "b"]
    assert merged.error == "boom"
