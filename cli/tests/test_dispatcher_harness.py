"""A work item's frozen harness reaching (or not reaching) its session (issue-440).

Feature: the session a work item gets is spawned on the harness its
`phase-selection` reply froze — and on the default whenever that record names a
harness this machine cannot, or was never told to, host.
"""

from __future__ import annotations

import time

import pytest

from conftest import FakeTmux, StubInteractiveAdapter, _freeze_legacy_graph
from the_loop.control import ControlConfig, ControlStore
from the_loop.harness import CursorAgentAdapter
from the_loop.modelchoice import launch_args
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#440"


class _Claude(StubInteractiveAdapter):
    name = "claude"
    model_flag = "--model"


class _Codex(StubInteractiveAdapter):
    name = "codex"
    default_binary = "codex-stub"
    model_flag = "--model"


def _config(tmp_path, **over):
    config = {
        "state": {"root": str(tmp_path / "state")},
        "harnesses": [
            {
                "name": "claude",
                "default": True,
                "args": ["--dangerously-skip-permissions"],
            },
            {"name": "codex", "args": ["--full-auto"]},
            {"name": "cursor"},
        ],
        "models": ["opus-5", {"name": "gpt-5.6-sol", "harnesses": ["codex"]}],
    }
    config.update(over)
    return config


def _dispatcher(tmp_path, cli_config=None):
    registry = SessionRegistry(tmp_path / "sessions")
    cli_config = cli_config if cli_config is not None else _config(tmp_path)
    args = launch_args(cli_config, {})
    dispatcher = Dispatcher(
        registry=registry,
        adapters={
            "claude": _Claude(extra_args=args.get("claude") or []),
            "codex": _Codex(extra_args=args.get("codex") or []),
            "cursor": CursorAgentAdapter(extra_args=args.get("cursor") or []),
        },
        config=RoutingConfig(
            control=ControlConfig(require_start_command=False),
            spawn_on_unmatched="always",
            portable_dir=str(tmp_path / "state" / "portable"),
        ),
        tmux_runner=FakeTmux(),
        cli_config=cli_config,
    )

    class _Link:
        def adopt(self, *a, **k):
            pass

        def on_arm(self, *a, **k):
            return False

        def context(self, *a, **k):
            return None

        def on_event(self, *a, **k):
            return None

        def on_spawn(self, *a, **k):
            pass

        def on_close(self, *a, **k):
            pass

    setattr(dispatcher, "graphlink", _Link())
    return registry, dispatcher


def _freeze(tmp_path, **frozen):
    store = ControlStore(str(tmp_path / "state" / "portable"))
    _freeze_legacy_graph(store, REF, {"nodes": [], **frozen})


def _comment():
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 440},
        "comment": {"body": "go", "user": {"login": "octo"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-1",
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def _spawned(registry, dispatcher):
    dispatcher.handle(_comment())
    deadline = time.time() + 3
    while time.time() < deadline and registry.find_by_work_item(REF) is None:
        time.sleep(0.01)
    dispatcher.stop()
    session = registry.find_by_work_item(REF)
    assert session is not None
    return session


def test_a_frozen_harness_is_what_the_session_spawns_on(tmp_path):
    """
    Feature: a work item runs on the harness it chose
      Scenario: codex frozen with a codex-only model
        Given the gate froze harness codex and model gpt-5.6-sol
        When the work item's first session is spawned
        Then it is a codex session, launched on codex's own declared arguments
             plus the model, and recorded as codex

    Requirement: docs/specs/issue-440/requirements.md R3.1, R3.3
    """
    _freeze(tmp_path, harness="codex", model="gpt-5.6-sol")
    registry, dispatcher = _dispatcher(tmp_path)
    session = _spawned(registry, dispatcher)
    assert session.harness == "codex"
    assert session.model == "gpt-5.6-sol"
    # Abuse case 4: claude's permission flag does not travel with the choice.
    assert session.harness_args == ["--full-auto", "--model", "gpt-5.6-sol"]


def test_no_frozen_harness_spawns_on_the_default(tmp_path):
    registry, dispatcher = _dispatcher(tmp_path)
    session = _spawned(registry, dispatcher)
    assert session.harness == "claude"
    assert session.harness_args == ["--dangerously-skip-permissions"]


@pytest.mark.parametrize(
    "forged",
    [
        "cursor",  # declared, but cannot host a session
        "pi",  # neither declared nor an adapter
        "/bin/sh",  # a path
    ],
)
def test_abuse_a_forged_frozen_harness_spawns_on_the_default(tmp_path, forged):
    """Abuse case 3 / R3.2: the record is agent-writable, so it is re-validated."""
    _freeze(tmp_path, harness=forged)
    registry, dispatcher = _dispatcher(tmp_path)
    assert dispatcher._harness_for(WorkItemRef.parse(REF)) == "claude"
    assert _spawned(registry, dispatcher).harness == "claude"


def test_an_undeclared_harness_with_an_adapter_is_not_spawned_onto(tmp_path):
    """R3.2: an adapter alone is not enough — the operator must declare it."""
    _freeze(tmp_path, harness="codex")
    config = _config(tmp_path)
    config["harnesses"] = [h for h in config["harnesses"] if h["name"] != "codex"]
    registry, dispatcher = _dispatcher(tmp_path, cli_config=config)
    assert dispatcher._harness_for(WorkItemRef.parse(REF)) == "claude"


def test_the_default_skips_a_default_true_that_cannot_host(tmp_path):
    """R4.1/R4.2: the daemon's default is the gate's, by the same rule."""
    config = _config(tmp_path)
    config["harnesses"] = [{"name": "cursor", "default": True}, {"name": "codex"}]
    _, dispatcher = _dispatcher(tmp_path, cli_config=config)
    assert dispatcher._default_harness() == "claude"  # routing.defaultHarness
    config["harnesses"] = [{"name": "codex", "default": True}, {"name": "claude"}]
    _, dispatcher = _dispatcher(tmp_path, cli_config=config)
    assert dispatcher._default_harness() == "codex"


def test_a_live_session_keeps_its_harness(tmp_path):
    """R3.4: a conversation cannot move harness, so a live claude session is
    delivered into as it is — the frozen codex applies to the next fresh one."""
    _freeze(tmp_path, harness="codex")
    registry, dispatcher = _dispatcher(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s-1",
            cwd=str(tmp_path),
            tmux_target="loop-octo-repo-440",
            harness_args=["--dangerously-skip-permissions"],
        )
    )
    endpoint = registry.find_by_work_item(REF)
    assert endpoint is not None
    assert dispatcher._choice_drifted(endpoint) is False
