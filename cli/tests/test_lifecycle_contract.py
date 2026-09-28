"""The lifecycle hook contract (issue-344, R1, R2): six typed points, facts a hook
reads, decisions a hook may change, and one base class with a method per point."""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
from pathlib import Path

import pytest

from the_loop.lifecycle import contract
from the_loop.lifecycle.contract import (
    POINTS,
    Context,
    DecisionTypeError,
    LifecycleHooks,
    PhaseChanged,
    SessionSpawn,
    SessionSpawned,
    WaitingForInput,
    WorkItemComplete,
    WorkItem,
    WorkItemStart,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_catalog_is_the_six_lifecycle_points():
    assert list(POINTS) == [
        "work_item_start",
        "session_spawn",
        "session_spawned",
        "waiting_for_input",
        "phase_changed",
        "work_item_complete",
    ]
    assert POINTS["work_item_start"] is WorkItemStart
    assert POINTS["session_spawn"] is SessionSpawn
    assert POINTS["session_spawned"] is SessionSpawned
    assert POINTS["waiting_for_input"] is WaitingForInput
    assert POINTS["phase_changed"] is PhaseChanged
    assert POINTS["work_item_complete"] is WorkItemComplete


def test_every_point_has_a_base_method_taking_its_context():
    """R1.4: the catalog and the SDK base class cannot drift apart."""
    for point, cls in POINTS.items():
        assert cls.POINT == point
        method = getattr(LifecycleHooks, point, None)
        assert method is not None, f"LifecycleHooks lacks {point}"
        params = list(inspect.signature(method).parameters)
        assert params == ["self", "ctx"]
        assert method.__annotations__["ctx"] in (cls, cls.__name__)


def test_no_base_method_outside_the_catalog_looks_like_a_point():
    """A method on the base class that is not a point would be a silent attach point."""
    public = {
        name
        for name, member in inspect.getmembers(LifecycleHooks, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public - set(POINTS) == {"handles"}


def test_every_field_is_a_fact_or_a_decision_with_a_json_type():
    for cls in POINTS.values():
        for f in dataclasses.fields(cls):
            assert f.type in ("str", "bool", "List[str]", "WorkItem", str, bool), (
                cls,
                f.name,
            )
            assert isinstance(f.metadata.get("decision", False), bool)


@pytest.mark.parametrize(
    "cls, decisions",
    [
        (WorkItemStart, ("proceed", "reason")),
        (SessionSpawn, ("prompt", "proceed", "reason")),
        (SessionSpawned, ("announce",)),
        (WaitingForInput, ("question", "summary")),
        (PhaseChanged, ("notify",)),
        (WorkItemComplete, ("announce",)),
    ],
)
def test_each_point_names_its_decisions(cls, decisions):
    """R2.5: the decision table in the docs is this table."""
    assert cls.decisions() == decisions


def test_to_params_round_trips_through_json():
    ctx = SessionSpawn(
        work_item=WorkItem.from_ref("github:octo/repo#1"),
        endpoint=WorkItem.from_ref("github:octo/repo#1"),
        harness="claude",
        cwd="/srv/checkout",
        model="opus",
        effort="high",
        harness_args=["--flag"],
        respawn=False,
        loop="pdlc-work-item-loop",
        prompt="boot",
    )
    params = json.loads(json.dumps(ctx.to_params()))
    assert params["work_item"]["ref"] == "github:octo/repo#1"
    assert params["work_item"]["repository"] == "octo/repo"
    assert params["endpoint"]["ref"] == "github:octo/repo#1"
    assert params["harness_args"] == ["--flag"]
    assert params["prompt"] == "boot"
    assert params["proceed"] is True
    rebuilt = SessionSpawn.from_params(params)
    assert rebuilt == ctx


def test_from_params_ignores_unknown_keys_and_fills_defaults():
    ctx = WorkItemStart.from_params({"work_item": "github:o/r#1", "bogus": 1})
    assert ctx.work_item.ref == "github:o/r#1", (
        "a bare ref string is accepted on the wire"
    )
    assert ctx.work_item.owner == "o"
    assert ctx.proceed is True
    assert ctx.reason == ""


def test_apply_copies_decisions_only():
    """Abuse case 2: a result may change decisions, never facts."""
    ctx = WorkItemStart(
        work_item=WorkItem.from_ref("github:o/r#1"), loop="pdlc-work-item-loop"
    )
    changed = ctx.apply(
        {"proceed": False, "reason": "no", "work_item": "github:evil/r#9", "loop": "x"}
    )
    assert changed == ("proceed", "reason")
    assert ctx.proceed is False
    assert ctx.reason == "no"
    assert ctx.work_item.ref == "github:o/r#1"
    assert ctx.loop == "pdlc-work-item-loop"


def test_apply_reports_only_what_actually_changed():
    ctx = SessionSpawned(work_item=WorkItem.from_ref("github:o/r#1"), announce=True)
    assert ctx.apply({"announce": True}) == ()
    assert ctx.apply({"announce": False}) == ("announce",)


@pytest.mark.parametrize(
    "cls, field, value",
    [
        (WorkItemStart, "proceed", "yes"),
        (WorkItemStart, "proceed", 1),
        (WorkItemStart, "reason", 5),
        (SessionSpawn, "prompt", None),
        (SessionSpawn, "prompt", ["a"]),
        (PhaseChanged, "notify", "false"),
    ],
)
def test_a_wrong_typed_decision_is_refused_not_coerced(cls, field, value):
    """R2.4 / abuse case 2."""
    ctx = cls(work_item=WorkItem.from_ref("github:o/r#1"))
    with pytest.raises(DecisionTypeError) as exc:
        ctx.apply({field: value})
    assert field in str(exc.value)


def test_a_refused_apply_leaves_the_context_untouched():
    ctx = SessionSpawn(work_item=WorkItem.from_ref("github:o/r#1"), prompt="boot")
    with pytest.raises(DecisionTypeError):
        ctx.apply({"proceed": False, "prompt": 3})
    assert ctx.proceed is True
    assert ctx.prompt == "boot"


def test_copy_decisions_from_takes_another_contexts_decisions():
    original = WaitingForInput(
        work_item=WorkItem.from_ref("github:o/r#1"), question="q", summary="s"
    )
    returned = dataclasses.replace(
        original, question="q2", work_item=WorkItem.from_ref("github:x/y#2")
    )
    changed = original.copy_decisions_from(returned)
    assert changed == ("question",)
    assert original.question == "q2"
    assert original.work_item.ref == "github:o/r#1"


def test_copy_decisions_from_refuses_another_point():
    ctx = WorkItemStart(work_item=WorkItem.from_ref("github:o/r#1"))
    with pytest.raises(TypeError):
        ctx.copy_decisions_from(
            SessionSpawned(work_item=WorkItem.from_ref("github:o/r#1"))
        )


def test_handles_reports_the_methods_a_subclass_overrides():
    class Two(LifecycleHooks):
        def work_item_start(self, ctx):
            return None

        def phase_changed(self, ctx):
            return None

    hooks = Two()
    assert hooks.handles("work_item_start")
    assert hooks.handles("phase_changed")
    assert not hooks.handles("session_spawn")
    assert not hooks.handles("not-a-point")
    assert LifecycleHooks().handles("work_item_start") is False


def test_base_methods_pass_through():
    hooks = LifecycleHooks()
    for point, cls in POINTS.items():
        assert (
            getattr(hooks, point)(cls(work_item=WorkItem.from_ref("github:o/r#1")))
            is None
        )


def test_context_base_cannot_be_instantiated_as_a_point():
    with pytest.raises(TypeError):
        Context()


def test_describe_lists_facts_and_decisions_for_the_report():
    rows = contract.describe()
    assert [row["point"] for row in rows] == list(POINTS)
    start = rows[0]
    assert "work_item" in start["facts"]
    assert start["decisions"] == ["proceed", "reason"]
    assert start["fires"]


def test_every_point_is_documented():
    """R1.4: the lifecycle page carries one heading per point."""
    page = REPO_ROOT / "docs" / "cli" / "lifecycle-hooks.md"
    if not page.is_file():
        pytest.skip("documentation site not present (source distribution)")
    text = page.read_text(encoding="utf-8")
    headings = set(re.findall(r"^###\s+`([a-z_]+)`", text, re.M))
    missing = set(POINTS) - headings
    assert not missing, f"points without a `### `point`` heading: {sorted(missing)}"


INTERFACE_PAGES = (
    ("docs", "cli", "lifecycle-hooks.md"),
    ("docs", "specs", "issue-344", "design.md"),
)


@pytest.mark.parametrize("parts", INTERFACE_PAGES, ids=lambda parts: "/".join(parts))
def test_every_context_object_is_documented_field_for_field(parts):
    """The lifecycle page and the design spec each list every context as a class block
    (sherma's convention, asked for on PR #432): every field of every point, no field
    the code does not have, and every decision marked as one."""
    page = REPO_ROOT.joinpath(*parts)
    if not page.is_file():
        pytest.skip("documentation site not present (source distribution)")
    text = page.read_text(encoding="utf-8")
    for cls in POINTS.values():
        start = text.find(f"class {cls.__name__}(Context):")
        assert start != -1, f"{cls.__name__} has no class block on {page.name}"
        block = text[start : text.find("```", start)]
        documented = set(re.findall(r"^\s{4}([a-z_]+):", block, re.M))
        actual = {f.name for f in dataclasses.fields(cls)}
        assert documented == actual, (
            f"{cls.__name__}: documented {sorted(documented - actual)} extra, "
            f"missing {sorted(actual - documented)}"
        )
        for name in cls.decisions():
            line = re.search(rf"^\s{{4}}{name}:.*$", block, re.M)
            assert line and "# decision" in line.group(0), (
                f"{cls.__name__}.{name} is a decision but its line does not say so"
            )
        for name in cls.facts():
            line = re.search(rf"^\s{{4}}{name}:.*$", block, re.M)
            assert line and "# decision" not in line.group(0), (
                f"{cls.__name__}.{name} is a fact but its line says decision"
            )


@pytest.mark.parametrize("parts", INTERFACE_PAGES, ids=lambda parts: "/".join(parts))
def test_base_class_signatures_are_documented(parts):
    """Both pages show ``LifecycleHooks`` with one method per point, typed as the code
    types it, so an author reads the exact signature they override."""
    page = REPO_ROOT.joinpath(*parts)
    if not page.is_file():
        pytest.skip("documentation site not present (source distribution)")
    text = page.read_text(encoding="utf-8")
    start = text.find("class LifecycleHooks:")
    assert start != -1, f"no LifecycleHooks block on {page.name}"
    block = text[start : text.find("```", start)]
    for point, cls in POINTS.items():
        name = cls.__name__
        assert f"def {point}(self, ctx: {name}) -> Optional[{name}]" in block, (
            f"{page.name}: LifecycleHooks.{point} is missing or its signature drifted"
        )
    documented = set(re.findall(r"^\s{4}def ([a-z_]+)\(self, ctx", block, re.M))
    assert documented == set(POINTS), f"{page.name}: {sorted(documented ^ set(POINTS))}"


# ------------------------------------------------------------------ the work item


def test_the_work_item_is_a_modelled_entity_not_a_string():
    """PR #432 review: ``work_item`` is the core entity — its ref taken apart, with the
    tracker, the host, the repository, the browser URL and the-loop's id."""
    item = WorkItem.from_ref("github:octo/repo#15", kind="issue")
    assert item.ref == "github:octo/repo#15"
    assert (item.provider, item.host, item.owner, item.repo) == (
        "github",
        "github.com",
        "octo",
        "repo",
    )
    assert item.repository == "octo/repo"
    assert item.number == 15
    assert item.kind == "issue"
    assert item.url == "https://github.com/octo/repo/issues/15"
    assert item.id == "issue-15"
    assert bool(item) and not bool(WorkItem())


def test_a_pull_request_work_item_links_to_the_pull_request():
    item = WorkItem.from_ref("github:octo/repo#15", kind="pull-request")
    assert item.url == "https://github.com/octo/repo/pull/15"


def test_an_enterprise_work_item_names_its_host():
    item = WorkItem.from_ref("github:ghe.corp.example/octo/repo#3", id="issue-3")
    assert item.host == "ghe.corp.example"
    assert item.repository == "ghe.corp.example/octo/repo"
    assert item.url == "https://ghe.corp.example/octo/repo/issues/3"


def test_the_work_item_travels_as_one_json_object():
    item = WorkItem.from_ref("github:octo/repo#15", kind="issue")
    wire = json.loads(json.dumps(item.to_params()))
    assert wire["ref"] == "github:octo/repo#15" and wire["number"] == 15
    assert WorkItem.from_params(wire) == item
    assert (
        WorkItem.from_params({"ref": "github:o/r#1", "bogus": 1}).ref == "github:o/r#1"
    )


@pytest.mark.parametrize(
    "bad", [{"number": "15"}, {"number": True}, {"ref": 15}, {"kind": None}]
)
def test_a_wrong_typed_work_item_field_is_refused(bad):
    with pytest.raises(TypeError):
        WorkItem.from_params(bad)
    with pytest.raises(TypeError):
        WorkItemStart.from_params({"work_item": bad})


def test_a_work_item_that_is_neither_an_object_nor_a_string_is_refused():
    with pytest.raises(TypeError):
        WorkItemStart.from_params({"work_item": 15})


def test_a_bare_id_yields_an_opaque_work_item_never_a_fault():
    """The graph verbs run on the id a person typed (``the-loop check issue-1``); the
    hooks still fire, with what is known: the id, and nothing invented."""
    item = WorkItem.from_ref("issue-1")
    assert (item.ref, item.id) == ("issue-1", "issue-1")
    assert (item.provider, item.host, item.repository, item.number, item.url) == (
        "",
        "",
        "",
        0,
        "",
    )
    assert bool(item)
    assert (
        WorkItemStart.from_params({"work_item": "not a ref"}).work_item.ref
        == "not a ref"
    )


@pytest.mark.parametrize("parts", INTERFACE_PAGES, ids=lambda parts: "/".join(parts))
def test_the_work_item_entity_is_documented_field_for_field(parts):
    """Both pages show ``WorkItem`` as a class block with exactly the code's fields."""
    page = REPO_ROOT.joinpath(*parts)
    if not page.is_file():
        pytest.skip("documentation site not present (source distribution)")
    text = page.read_text(encoding="utf-8")
    start = text.find("class WorkItem:")
    assert start != -1, f"no WorkItem block on {page.name}"
    block = text[start : text.find("```", start)]
    documented = re.findall(r"^\s{4}([a-z_]+):", block, re.M)
    actual = [f.name for f in dataclasses.fields(WorkItem)]
    assert documented == actual, f"{page.name}: {documented} != {actual}"
    for cls in POINTS.values():
        cls_block = text[text.find(f"class {cls.__name__}(Context):") :]
        cls_block = cls_block[: cls_block.find("```")]
        line = re.search(r"^\s{4}work_item:\s+(\w+)", cls_block, re.M)
        assert line and line.group(1) == "WorkItem", (
            f"{page.name}: {cls.__name__}.work_item"
        )
