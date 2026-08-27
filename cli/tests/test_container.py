"""The container image's default config, judged by the code that will judge it (issue-236).

``container/cli-config.default.yaml`` is the whole of the container's opinion: four keys
that make the shipped service reachable through a published port and persist its state in
the volume. It is a checked-in data file rather than a heredoc inside the entrypoint for
exactly one reason — so these tests can put it through the **real** gates:
:func:`the_loop.configschema.validate`, :func:`the_loop.migrations.assert_current` and
:func:`the_loop.api.config.cors_config`, which are the three
``the_loop.core.config._reject_invalid`` runs before it writes, plus the exposure guard's
own predicate from ``the_loop.api.serve``.

A container default the service would refuse to boot on is therefore a red build, not a
support thread.

Pure filesystem reads: no container runtime, no network, no subprocess. Skipped when
``container/`` is absent, so a source distribution that ships ``cli/`` alone still passes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from the_loop import configschema
from the_loop.api.config import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_PORT,
    cors_config,
    is_loopback,
    service_config,
)
from the_loop.migrations import CURRENT_CONFIG_VERSION, assert_current
from the_loop.state import layout_from_config

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_DIR = REPO_ROOT / "container"
DEFAULT_CONFIG = CONTAINER_DIR / "cli-config.default.yaml"

pytestmark = pytest.mark.skipif(
    not CONTAINER_DIR.is_dir(),
    reason="container/ not present (source distribution)",
)

#: Where the image mounts its volume. Everything the container generates belongs under
#: it: a path outside is a file that vanishes with the container.
DATA_DIR = "/data"


@pytest.fixture(scope="module")
def seed() -> Dict[str, Any]:
    return yaml.safe_load(DEFAULT_CONFIG.read_text()) or {}


def test_seed_is_valid_against_the_packaged_schema(seed: Dict[str, Any]) -> None:
    assert configschema.validate(seed) == []


def test_seed_carries_the_current_config_version(seed: Dict[str, Any]) -> None:
    """R2.3 — the migration gate is what `POST /api/v1/config` clears before it writes.

    A seed one version behind would let the container boot and then refuse every save the
    dashboard made, naming an upgrade command the operator cannot run inside the image.
    """
    assert seed.get("version") == CURRENT_CONFIG_VERSION
    assert_current(seed)


def test_seed_clears_the_exposure_guard_explicitly(seed: Dict[str, Any]) -> None:
    """R1.3 — the pair ``the_loop.api.serve.main`` admits, asserted with its own predicate.

    A loopback bind inside a network namespace is reachable by nothing, so `0.0.0.0` is
    the only value that yields a service — and `exposed: true` is how the config says so
    out loud (decision-102). Both halves matter: either one alone refuses to boot.
    """
    conf = service_config(seed)
    assert not is_loopback(conf["host"])
    assert conf["exposed"] is True


def test_seed_keeps_the_package_default_port(seed: Dict[str, Any]) -> None:
    """The documented `-p 4114:4114` and `EXPOSE 4114` are the package's own default."""
    assert service_config(seed)["port"] == DEFAULT_PORT


def test_state_root_is_inside_the_volume(seed: Dict[str, Any]) -> None:
    """R2.4 — the event log, the records and the session handles persist with the config."""
    layout = layout_from_config(seed)
    for path in (
        layout.root,
        layout.portable_dir,
        layout.local_dir,
        layout.event_log,
    ):
        assert str(path).startswith(f"{DATA_DIR}/"), path


def test_seed_widens_no_cors_value(seed: Dict[str, Any]) -> None:
    """R3.1 / abuse case 2 — the container inherits the shipped allowlist, unchanged.

    The key is absent from the file, so this is a test that a *future* edit cannot add one
    without saying why: the hosted dashboard already reaches a container on the same
    machine because decision-077 put its origin in the package default.
    """
    assert "cors" not in (seed.get("service") or {})
    conf = cors_config(seed)
    assert tuple(conf["allowOrigins"]) == DEFAULT_ALLOWED_ORIGINS
    assert conf["allowCredentials"] is False


def test_seed_opens_no_ingress(seed: Dict[str, Any]) -> None:
    """R5.2 — the receiver, the poller and standing sessions stay opt-in.

    `the-loop start`'s contract is that a config which merely *describes* an ingress must
    not open a port or start a loop. An image that polled GitHub on first run would break
    it in the one place nobody is watching.
    """
    for block in ("webhooks", "polling", "standingSessions", "channels"):
        assert block not in seed, f"the container seed must not configure {block}"


def test_seed_is_only_the_keys_the_container_has_an_opinion_about(
    seed: Dict[str, Any],
) -> None:
    """Everything not listed here inherits the package default and cannot drift from it."""
    assert set(seed) == {"version", "state", "service"}
    assert set(seed["service"]) == {"host", "exposed"}


def test_seed_explains_the_two_lines_that_need_explaining(seed: Dict[str, Any]) -> None:
    """The comments survive every dashboard save (`core.config` splices YAML, it does not
    re-dump it), so they are the operator's in-place record of why the guard is cleared."""
    text = DEFAULT_CONFIG.read_text()
    assert "decision-102" in text
    assert "-p 127.0.0.1:4114:4114" in text
