"""Unit tests for the SDK's construction and its capability surface (issue-212, T1)."""

import subprocess
import sys

import pytest
import yaml

from the_loop import sdk
from the_loop.sdk import TheLoop


def _config_file(tmp_path, document=None):
    path = tmp_path / "cli-config.yaml"
    path.write_text(
        yaml.safe_dump(
            document
            if document is not None
            else {
                "state": {"root": str(tmp_path / ".the-loop")},
                "service": {"hostIngresses": False, "mcp": {"enabled": False}},
            }
        )
    )
    return path


# ---------------------------------------------------------------- construction


def test_config_path_is_read_and_exposed(tmp_path):
    """R4.1: the ticket's shape — initialising the SDK is naming the config file."""
    path = _config_file(tmp_path)
    loop = TheLoop(config_path=path)
    assert loop.config_path == path
    assert loop.config["state"]["root"] == str(tmp_path / ".the-loop")


def test_no_argument_uses_the_standard_resolution_order(tmp_path, monkeypatch):
    """R4.2: the same order every other the-loop process resolves by."""
    path = _config_file(tmp_path)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    assert TheLoop().config_path == path


def test_a_config_document_can_be_supplied_directly(tmp_path):
    """R4.6: for tests, and for deployments assembling config from a secret store."""
    loop = TheLoop(config={"state": {"root": str(tmp_path)}})
    assert loop.config["state"]["root"] == str(tmp_path)


def test_config_and_config_path_together_are_refused(tmp_path):
    """A write has to have one destination, so a TheLoop reads one config."""
    with pytest.raises(ValueError, match="not both"):
        TheLoop(config_path=_config_file(tmp_path), config={})


def test_a_missing_config_raises_and_names_the_path(tmp_path):
    """R4.5: an embedded service fails its own startup rather than running on {}."""
    missing = tmp_path / "nowhere" / "cli-config.yaml"
    with pytest.raises(FileNotFoundError, match=str(missing)):
        TheLoop(config_path=missing)


def test_an_unparseable_config_raises_valueerror_naming_the_path(tmp_path):
    """R4.5: a broken file is loud at construction, not silent until first use."""
    path = tmp_path / "cli-config.yaml"
    path.write_text("routing: [unclosed\n")
    with pytest.raises(ValueError, match=str(path)):
        TheLoop(config_path=path)


def test_reload_picks_up_an_edited_file(tmp_path):
    """R4.3: the holder is level with the file for a non-HTTP caller too."""
    path = _config_file(tmp_path)
    loop = TheLoop(config_path=path)
    assert loop.config.get("routing", {}).get("defaultHarness") is None
    document = yaml.safe_load(path.read_text())
    document["routing"] = {"defaultHarness": "cursor"}
    path.write_text(yaml.safe_dump(document))
    assert loop.reload()["routing"]["defaultHarness"] == "cursor"


# ------------------------------------------------------------------ import cost


def test_importing_the_sdk_does_not_import_fastapi_or_mcp():
    """NFR2: a batch caller pays for `core`, not for a web framework.

    Run in a fresh interpreter — the test session has already imported both.
    """
    code = (
        "import sys; import the_loop.sdk; "
        "print('fastapi' in sys.modules, 'mcp' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False False"


# --------------------------------------------------------------- the namespaces


NAMESPACES = {
    "work_items": ["list", "get"],
    "sessions": [
        "list",
        "get",
        "transcript",
        "control",
        "reply",
        "ask",
        "register",
        "close",
    ],
    "graph": ["show", "check", "complete", "advance", "force", "skip"],
    "events": ["query", "types"],
    "daemons": ["list", "control"],
    "attention": ["list"],
    "repo": ["scenarios", "instructions", "critics", "critic_run"],
    "settings": ["get", "schema", "update"],
}


@pytest.mark.parametrize("namespace,methods", sorted(NAMESPACES.items()))
def test_every_namespace_exposes_its_operations(tmp_path, namespace, methods):
    """R1.2: the capability surface is grouped, present and callable."""
    loop = TheLoop(config_path=_config_file(tmp_path))
    obj = getattr(loop, namespace)
    for method in methods:
        assert callable(getattr(obj, method)), f"{namespace}.{method}"


def test_capability_calls_reach_core(tmp_path):
    """R1.3: delegation, not reimplementation — the SDK reads what core wrote."""
    from the_loop.state import layout_from_config, legacy_layout
    from the_loop.workitem import WorkItemStore

    path = _config_file(tmp_path)
    loop = TheLoop(config_path=path)
    layout = layout_from_config(loop.config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section("github:octo/repo#7", "control", {"command": "start"})

    assert [row["ref"] for row in loop.work_items.list()] == ["github:octo/repo#7"]
    assert loop.work_items.get("github:octo/repo#7")["control"]["command"] == "start"


def test_the_exception_contract_is_core_s(tmp_path):
    """R1.4: ValueError for a caller mistake, LookupError for a missing resource."""
    loop = TheLoop(config_path=_config_file(tmp_path))
    with pytest.raises(ValueError):
        loop.work_items.get("not-a-ref")
    with pytest.raises(LookupError):
        loop.work_items.get("github:octo/repo#404")


def test_lifecycle_writes_are_not_on_the_sdk(tmp_path):
    """Design: `status()` is the read half; start/stop/restart stay off the surface.

    They spawn and kill the-loop's own processes, which inside somebody's web service is
    either meaningless or actively wrong (`--with-upgrade` reaches the installer).
    """
    loop = TheLoop(config_path=_config_file(tmp_path))
    assert isinstance(loop.status(), dict)
    for absent in ("start", "stop", "restart", "schedule_restart"):
        assert not hasattr(loop, absent)


# ------------------------------------------------------------------ mount report


def test_mount_reports_what_it_attached(tmp_path):
    """R2.4: a mount that silently did less than expected is visible at startup."""
    from fastapi import FastAPI

    loop = TheLoop(config_path=_config_file(tmp_path))
    report = loop.mount(FastAPI(), prefix="/embedded")
    assert report["prefix"] == "/embedded"
    assert report["operations"] > 0
    # `service.mcp.enabled: false` in the fixture — asked for, not available.
    assert report["mcp"] == {"mounted": False, "path": ""}
    assert report["lifespan"] == "wrapped"
    assert report["hostIngresses"] is False


def test_host_ingresses_can_be_declined_at_the_call_site(tmp_path):
    """R3.6: several workers must not each start their own poller."""
    from fastapi import FastAPI

    path = _config_file(
        tmp_path,
        {
            "state": {"root": str(tmp_path / ".the-loop")},
            "service": {"mcp": {"enabled": False}},  # hostIngresses defaults true
        },
    )
    loop = TheLoop(config_path=path)
    assert loop.host_ingresses() is True
    assert loop.mount(FastAPI(), host_ingresses=False)["hostIngresses"] is False


@pytest.mark.parametrize("prefix", ["the-loop", "/the-loop/"])
def test_a_malformed_prefix_is_refused(tmp_path, prefix):
    """A prefix FastAPI would assert on is refused with a message that says why."""
    from fastapi import FastAPI

    loop = TheLoop(config_path=_config_file(tmp_path))
    with pytest.raises(ValueError, match="prefix"):
        loop.mount(FastAPI(), prefix=prefix)


def test_the_public_surface_is_declared(tmp_path):
    """NFR5: `__all__` is the semver'd contract, and every name in it resolves."""
    for name in sdk.__all__:
        assert hasattr(sdk, name), name
