"""A work item's model and effort reaching (or not reaching) an argv (issue-358).

Feature: the session a work item gets is launched on the model it chose — and never
on one it did not, whatever a comment, a label or a hand-edited state file says.

Most of this file is the abuse table from `requirements.md` § Security considerations.
The property every case protects is one sentence: **a reply picks a key into the
operator's declared list, and the argv is built from the operator's own config.**
"""

from __future__ import annotations

import time


from conftest import FakeTmux, StubInteractiveAdapter, _freeze_legacy_graph
from the_loop.control import ControlConfig, ControlStore
from the_loop.modelprobe import REFUSED, Verdict, VerdictCache
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#358"


class _Adapter(StubInteractiveAdapter):
    name = "claude"
    model_flag = "--model"
    _EFFORT_ARGS = {"xhigh": ("--effort", "xhigh")}


def _config(tmp_path, **over):
    config = {
        "state": {"root": str(tmp_path / "state")},
        "harnesses": [
            {
                "name": "claude",
                "default": True,
                "args": ["--dangerously-skip-permissions"],
            }
        ],
        "models": ["opus-5", "fable-5.1"],
        "effort": ["high", "xhigh"],
    }
    config.update(over)
    return config


def _dispatcher(tmp_path, cli_config=None, **over):
    registry = SessionRegistry(tmp_path / "sessions")
    over.setdefault("control", ControlConfig(require_start_command=False))
    over.setdefault("spawn_on_unmatched", "always")
    over.setdefault("portable_dir", str(tmp_path / "state" / "portable"))
    over.setdefault("harness_args", {"claude": ["--dangerously-skip-permissions"]})
    tmux = FakeTmux()
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": _Adapter()},
        config=RoutingConfig(**over),
        tmux_runner=tmux,
        cli_config=cli_config if cli_config is not None else _config(tmp_path),
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
    return registry, dispatcher, tmux


def _freeze(tmp_path, model="", effort=""):
    store = ControlStore(str(tmp_path / "state" / "portable"))
    _freeze_legacy_graph(store, REF, {"model": model, "effort": effort, "nodes": []})
    return store


def _comment(delivery="d-1", body="looks good"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 358},
        "comment": {"body": body, "user": {"login": "octo"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def _wait(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# -- resolution -----------------------------------------------------------------


def test_a_frozen_choice_reaches_the_argv_in_order(tmp_path):
    _freeze(tmp_path, model="fable-5.1", effort="xhigh")
    registry, dispatcher, tmux = _dispatcher(tmp_path)

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None
    assert adapter.extra_args == [
        "--dangerously-skip-permissions",
        "--model",
        "fable-5.1",
        "--effort",
        "xhigh",
    ]


def test_a_work_item_that_chose_nothing_gets_the_shared_adapter_untouched(tmp_path):
    """R6.1 — most work items, and they must be launched exactly as before."""
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is dispatcher.adapters["claude"]


def test_the_choice_is_recorded_on_the_session(tmp_path):
    _freeze(tmp_path, model="fable-5.1", effort="xhigh")
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    dispatcher.handle(_comment())
    assert _wait(lambda: registry.find_by_work_item(REF) is not None)
    dispatcher.stop()

    session = registry.find_by_work_item(REF)
    assert session is not None
    assert session.model == "fable-5.1" and session.effort == "xhigh"
    assert "--model" in session.harness_args


def test_a_model_the_harness_refuses_is_never_spawned_onto(tmp_path):
    """R7.4 — the failure surfaces as the operator's own arguments, not a dead pane."""
    _freeze(tmp_path, model="fable-5.1")
    config = _config(tmp_path)
    cache = VerdictCache(str(tmp_path / "state" / "local" / "model-verdicts.json"))
    cache.put(Verdict("claude", "model", "fable-5.1", "", REFUSED, time.time()))

    registry, dispatcher, tmux = _dispatcher(tmp_path, cli_config=config)
    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None
    assert "--model" not in adapter.extra_args


# -- abuse ----------------------------------------------------------------------


def test_abuse_a_forged_frozen_choice_is_ignored(tmp_path):
    """A4. The portable record is agent-writable, so it is re-validated on the way
    in: a model nobody declared cannot be smuggled into an argv by editing state."""
    _freeze(tmp_path, model="smuggled-9")
    registry, dispatcher, tmux = _dispatcher(tmp_path)

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None and adapter is dispatcher.adapters["claude"]
    assert "smuggled-9" not in " ".join(adapter.extra_args)


def test_abuse_the_argv_contains_only_what_config_and_the_adapter_produced(tmp_path):
    """A3. Every element is traceable: the operator's own args, then the adapter's
    flag plus a declared name. Nothing else has a path into this list."""
    _freeze(tmp_path, model="opus-5")
    registry, dispatcher, tmux = _dispatcher(tmp_path)

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None
    assert set(adapter.extra_args) <= {
        "--dangerously-skip-permissions",  # the operator's
        "--model",  # the adapter's
        "opus-5",  # a declared name
    }


def test_abuse_a_label_named_after_a_model_selects_nothing(tmp_path):
    """A5. No label is read anywhere in this path — the objection that moved this
    feature off labels in the first place."""
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    payload = {
        "action": "labeled",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 358, "labels": [{"name": "model: fable-5.1"}]},
        "label": {"name": "model: fable-5.1"},
    }
    routed = RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id="d-label",
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )
    dispatcher.handle(routed)
    assert _wait(lambda: tmux.spawns)
    dispatcher.stop()

    session = registry.find_by_work_item(REF)
    assert session is not None
    assert session.model == "" and "fable-5.1" not in " ".join(session.harness_args)


def test_abuse_a_declaration_withdrawn_stops_reaching_the_argv(tmp_path):
    """The other half of A4: state that was legitimate stops being so the moment the
    operator stops declaring it. Re-validated on every read, never trusted once."""
    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, tmux = _dispatcher(
        tmp_path, cli_config=_config(tmp_path, models=["opus-5"])
    )

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is dispatcher.adapters["claude"]


def test_an_unreadable_frozen_record_launches_on_the_operators_arguments(tmp_path):
    """R4.5 — every fault resolves to the operator's stated configuration."""
    registry, dispatcher, tmux = _dispatcher(tmp_path)

    class _Exploding:
        def frozen_graph(self, work_item):
            raise OSError("state is on fire")

    setattr(dispatcher, "control_store", _Exploding())
    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is dispatcher.adapters["claude"]


# -- the drift safety net -------------------------------------------------------


def test_a_session_running_on_the_wrong_arguments_is_re_launched(tmp_path):
    """R4.3 — deliver by respawning onto the right argv, resuming the conversation,
    rather than pasting into a session running on something else."""
    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s-1",
            cwd=str(tmp_path),
            tmux_target="loop-octo-repo-358",
            model="opus-5",
            harness_args=["--dangerously-skip-permissions", "--model", "opus-5"],
        )
    )
    endpoint = registry.find_by_work_item(REF)
    assert endpoint is not None
    assert dispatcher._choice_drifted(endpoint) is True


def test_a_session_recorded_before_this_feature_is_left_alone(tmp_path):
    """The difference between a safety net and a stampede on upgrade: a record with
    no `harnessArgs` is not evidence of drift, so it is not respawned for it."""
    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s-1",
            cwd=str(tmp_path),
            tmux_target="loop-octo-repo-358",
        )
    )
    endpoint = registry.find_by_work_item(REF)
    assert endpoint is not None
    assert dispatcher._choice_drifted(endpoint) is False


def test_a_session_already_on_the_right_arguments_is_delivered_into(tmp_path):
    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, tmux = _dispatcher(tmp_path)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s-1",
            cwd=str(tmp_path),
            tmux_target="loop-octo-repo-358",
            model="fable-5.1",
            harness_args=["--dangerously-skip-permissions", "--model", "fable-5.1"],
        )
    )
    endpoint = registry.find_by_work_item(REF)
    assert endpoint is not None
    assert dispatcher._choice_drifted(endpoint) is False


# -- migration ------------------------------------------------------------------


def test_an_install_that_declared_nothing_behaves_exactly_as_before(tmp_path):
    """R6.1-R6.2 — upgrading must cost an operator who never wanted this nothing."""
    registry, dispatcher, tmux = _dispatcher(tmp_path, cli_config={})
    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is dispatcher.adapters["claude"]


def test_the_deprecated_routing_harness_args_still_launch_a_session(tmp_path):
    """R2.12 — the warn-never-fail shim: an un-migrated config must not brick a daemon."""
    _freeze(tmp_path, model="opus-5")
    config = _config(tmp_path)
    config.pop("harnesses")  # nothing declares args in its new home
    registry, dispatcher, tmux = _dispatcher(tmp_path, cli_config=config)

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None
    assert adapter.extra_args == [
        "--dangerously-skip-permissions",  # read from routing.harnessArgs
        "--model",
        "opus-5",
    ]


def test_abuse_a_model_narrowed_to_another_harness_cannot_be_forced_onto_this_one(
    tmp_path,
):
    """A4, third form. `harnesses:` is the operator's narrowing, so it is enforced
    where the argv is built and not only where the checklist is rendered: the gate
    decides what can be picked, but a frozen record is a file an agent can write."""
    _freeze(tmp_path, model="gpt-5.6-sol")
    config = _config(tmp_path)
    config["harnesses"].append({"name": "cursor"})
    config["models"] = ["opus-5", {"name": "gpt-5.6-sol", "harnesses": ["cursor"]}]
    registry, dispatcher, tmux = _dispatcher(tmp_path, cli_config=config)

    adapter = dispatcher._adapter_for(WorkItemRef.parse(REF), "claude")
    assert adapter is not None and adapter is dispatcher.adapters["claude"]
    assert "gpt-5.6-sol" not in " ".join(adapter.extra_args)


# -- the choices are read from the work item's own file (issue-368) ------------


def _checkout(tmp_path, **fields):
    """A checkout whose work item froze ``fields`` in its own state file."""
    from the_loop.graph.state import WorkItemState

    spec = tmp_path / "co" / "docs" / "specs" / "issue-358"
    spec.mkdir(parents=True, exist_ok=True)
    state = WorkItemState(work_item=REF)
    for key, value in fields.items():
        setattr(state, key, value)
    state.save(spec)
    return str(tmp_path / "co")


def _with_session(tmp_path, registry, cwd):
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="s-1",
            cwd=cwd,
        ),
        force=True,
    )


def test_the_choice_is_read_from_the_work_items_own_state(tmp_path):
    """R4.3 — the checkout the session record names, not a second copy."""
    registry, dispatcher, _ = _dispatcher(tmp_path)
    _with_session(tmp_path, registry, _checkout(tmp_path, model="fable-5.1"))
    assert dispatcher._resolved_choice(WorkItemRef.parse(REF), "claude") == (
        "fable-5.1",
        "",
    )


def test_the_session_per_pr_mode_is_read_from_the_same_file(tmp_path):
    """R4.3 — one file answers both questions the daemon asks per work item."""
    registry, dispatcher, _ = _dispatcher(tmp_path)
    _with_session(tmp_path, registry, _checkout(tmp_path, session_per_pr="always"))
    assert dispatcher._tmux_for(WorkItemRef.parse(REF)).session_per_pr == "always"


def test_an_undeclared_model_in_the_state_file_buys_nothing(tmp_path):
    """Abuse case 1 — the state file is agent-writable, so it is re-validated."""
    registry, dispatcher, _ = _dispatcher(tmp_path)
    _with_session(tmp_path, registry, _checkout(tmp_path, model="gpt-9"))
    assert dispatcher._resolved_choice(WorkItemRef.parse(REF), "claude") == ("", "")


def test_a_fourth_session_per_pr_mode_routes_by_the_operators_default(tmp_path):
    """Abuse case 2 — a fourth mode never reaches TmuxConfig."""
    registry, dispatcher, _ = _dispatcher(tmp_path)
    _with_session(tmp_path, registry, _checkout(tmp_path, session_per_pr="sometimes"))
    tmux = dispatcher._tmux_for(WorkItemRef.parse(REF))
    assert tmux.session_per_pr == dispatcher.config.tmux.session_per_pr


def test_a_work_item_frozen_before_the_change_is_routed_by_its_portable_record(
    tmp_path,
):
    """R4.4 — read old, write new: an item in flight keeps its routing."""
    import json

    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, _ = _dispatcher(tmp_path)
    # Its state file has none of the keys, because it was frozen before they existed.
    _with_session(tmp_path, registry, _checkout(tmp_path))
    assert dispatcher._resolved_choice(WorkItemRef.parse(REF), "claude") == (
        "fable-5.1",
        "",
    )
    # …and the legacy copy is never rewritten.
    record = json.loads(
        (tmp_path / "state" / "portable" / "github-octo-repo-358.json").read_text()
    )
    assert record["graph"]["model"] == "fable-5.1"


def test_the_state_file_wins_over_a_legacy_portable_copy(tmp_path):
    """R4.3 before R4.4: the fallback is for a file that says nothing at all."""
    _freeze(tmp_path, model="fable-5.1")
    registry, dispatcher, _ = _dispatcher(tmp_path)
    _with_session(tmp_path, registry, _checkout(tmp_path, model="opus-5"))
    assert dispatcher._resolved_choice(WorkItemRef.parse(REF), "claude") == (
        "opus-5",
        "",
    )


def test_no_checkout_and_no_record_resolves_to_the_operators_defaults(tmp_path):
    """Fail closed: a read never fails a delivery."""
    _, dispatcher, _ = _dispatcher(tmp_path)
    assert dispatcher._resolved_choice(WorkItemRef.parse(REF), "claude") == ("", "")
    assert (
        dispatcher._tmux_for(WorkItemRef.parse(REF)).session_per_pr
        == dispatcher.config.tmux.session_per_pr
    )
