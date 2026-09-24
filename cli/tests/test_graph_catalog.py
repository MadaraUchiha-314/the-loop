"""Graphs of the operator's own — declaring, compiling, selecting (issue-343).

Every test writes the graph YAML it declares under ``tmp_path`` and, where the
loader needs one, a CLI config naming it through ``$THE_LOOP_CLI_CONFIG``. Nothing
reaches the network and no hook module is imported unless a test declares one.

The negatives are the point. A custom graph is selected by name from a value the
agent can write (``work-item-state.json``), so what must NOT select one — an
undeclared name, a path, a shipped family name — is what these tests pin first.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from the_loop.commands.graph_cmd import GraphCommand
from the_loop.control import ControlConfig, ControlStore
from the_loop.graph import extensions, hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.catalog import (
    Binding,
    Catalog,
    CustomGraph,
    compile_custom,
    parse_catalog,
    read_bindings,
    read_catalog,
)
from the_loop.graph.model import (
    PDLC_ADHOC_LOOP,
    PDLC_REVIEW_LOOP,
    PDLC_WORK_ITEM_LOOP,
    PHASE_VOCABULARY,
    SHIPPED_LOOPS,
    GraphConfigError,
    load_graph,
    resolve_outer_loop,
    slash_command,
)
from the_loop.graph.state import WorkItemState

NAME = "acme-triage-loop"
WORK_ITEM = "issue-343"
REF = "github:octo/repo#343"

TRIAGE = """
version: 1
start: triage
nodes:
  - id: triage
    phase: implementation
    actor: agent
    command: acme:triage
    entry: [set-phase-label]
    exit: []
  - id: complete
    phase: complete
    actor: agent
    terminal: true
    entry: [set-phase-label]
  - id: cleanup
    phase: cleanup
    actor: code
    terminal: true
    entry: [set-phase-label]
edges:
  - {from: triage, to: complete, on: pass}
"""

MODULE = """
from the_loop.graph import HookResult, hook


@hook("x-triage-rules")
def triage_rules(ctx):
    return HookResult.ok("x-triage-rules")
"""


@pytest.fixture(autouse=True)
def _forget_loaded_modules():
    extensions.clear_module_cache()
    yield
    extensions.clear_module_cache()


def _catalog(*entries: dict) -> Catalog:
    return read_catalog({"graphs": list(entries)})


def _bindings(block, *entries: dict) -> dict:
    """``routing.control.commands`` parsed against the declared ``entries`` —
    ``NAME`` alone when none are given."""
    return read_bindings(block, _catalog(*(entries or ({"name": NAME, "path": "a"},))))


def _control(commands: dict, *entries: dict) -> ControlConfig:
    """A control config binding ``commands`` over ``entries`` (``NAME`` alone by
    default), built as every daemon-side builder builds it."""
    graphs = list(entries or ({"name": NAME, "path": "t.yaml"},))
    return ControlConfig.from_mapping({"commands": commands}, graphs=graphs)


def _graph_file(tmp_path: Path, body: str = TRIAGE, name: str = "triage.yaml") -> Path:
    path = tmp_path / "graphs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.lstrip())
    return path


def _cli_config(tmp_path: Path, monkeypatch, body: str) -> Path:
    path = tmp_path / "cli-config.yaml"
    path.write_text('version: "0.10.0"\n' + body)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return path


def _declared(
    *,
    graph: str = "",
    control: str = "",
    commands: str = f"      triage: {{graph: {NAME}}}\n",
    guest: bool = False,
) -> str:
    """A CLI config body declaring ``NAME`` at the top level and binding
    ``commands`` to graphs under ``routing.control.commands``. ``graph`` and
    ``control`` are further lines under ``routing.graph`` / ``routing.control``."""
    body = f"graphs:\n  - name: {NAME}\n    path: graphs/triage.yaml\n"
    if guest:
        body += "    guest: true\n"
    body += "routing:\n"
    if graph:
        body += "  graph:\n" + graph
    return body + "  control:\n" + control + "    commands:\n" + commands


TRIAGE_DECLARED = _declared()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "checkout"
    (root / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return root


# -- R1: the declaration ------------------------------------------------------


def test_an_absent_declaration_is_an_empty_catalog():
    assert read_catalog({}).empty
    assert read_catalog({"routing": {"graph": {}}}).empty
    assert read_catalog({"graphs": []}).empty
    assert parse_catalog(None).empty


def test_a_declaration_parses_names_paths_and_guest():
    catalog = _catalog(
        {"name": NAME, "path": "a.yaml"},
        {"name": "acme-review", "path": "/abs/b.yaml", "guest": True},
    )
    assert catalog.names == (NAME, "acme-review")
    assert catalog.is_guest("acme-review") and not catalog.is_guest(NAME)
    assert catalog.get("nope") is None


def test_the_list_travels_to_the_routing_readers_as_routing_graphs(
    tmp_path, monkeypatch
):
    """The loader fans the top-level list into ``routing._graphs`` (as ``instance``
    travels as ``_instance``), for the readers handed the routing block alone."""
    from the_loop.cli_config import load_cli_config

    config = load_cli_config(_cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED))
    assert read_catalog({"routing": config["routing"]}).names == (NAME,)
    assert read_catalog(config).names == (NAME,)


@pytest.mark.parametrize(
    "entry, match",
    [
        ({"path": "a.yaml"}, "needs both"),
        ({"name": NAME}, "needs both"),
        ({"name": "Acme", "path": "a.yaml"}, "lowercase"),
        ({"name": "../evil", "path": "a.yaml"}, "lowercase"),
        ({"name": "pdlc-mine", "path": "a.yaml"}, "reserved"),
        ({"name": PDLC_ADHOC_LOOP, "path": "a.yaml"}, "reserved"),
        ({"name": NAME, "path": "a.yaml", "guest": "yes"}, "guest"),
        ({"name": NAME, "path": "a.yaml", "commands": ["triage"]}, "control.commands"),
        ({"name": NAME, "path": "a.yaml", "loop": "x"}, "unknown key"),
        ("acme", "must be a mapping"),
    ],
)
def test_catalog_refuses_a_malformed_entry(entry, match):
    """R1.2, R1.5 — and abuse case 6's reserved names."""
    with pytest.raises(GraphConfigError, match=match):
        _catalog(entry)


def test_catalog_refuses_a_non_list_declaration():
    with pytest.raises(GraphConfigError, match="must be a list"):
        read_catalog({"graphs": {"name": NAME}})


def test_catalog_refuses_a_duplicate_name():
    """R1.3"""
    with pytest.raises(GraphConfigError, match="twice"):
        _catalog({"name": NAME, "path": "a.yaml"}, {"name": NAME, "path": "b.yaml"})


@pytest.mark.parametrize(
    "word",
    [
        "stop",
        "pause",
        "resume",
        "execute",
        "cleanup",
        "add-collaborator",
        "remove-channel",
    ],
)
def test_binding_refuses_a_command_that_selects_no_loop(word):
    """R3.3 / abuse case 6 — rebinding `stop` would change what `stop` means."""
    with pytest.raises(GraphConfigError, match="does not select a loop"):
        _bindings({word: {"graph": NAME}})


@pytest.mark.parametrize("word", ["start", "contribute", "do", "review", "triage"])
def test_an_arming_command_or_a_new_word_may_be_bound(word):
    """R3.1"""
    assert _bindings({word: {"graph": NAME}}) == {word: Binding(word, NAME)}


def test_a_command_may_be_bound_to_a_shipped_loop():
    """R3.1 — `do` onto the work-item loop needs no graph of the operator's own."""
    assert _bindings({"do": {"graph": PDLC_WORK_ITEM_LOOP}}, *()) == {
        "do": Binding("do", PDLC_WORK_ITEM_LOOP)
    }
    assert read_bindings({"do": {"graph": PDLC_REVIEW_LOOP}}, Catalog()) == {
        "do": Binding("do", PDLC_REVIEW_LOOP)
    }


def test_a_new_word_may_carry_its_own_keyword():
    """R3.4 — normalised to single spaces, as every keyword is."""
    assert _bindings({"triage": {"graph": NAME, "keyword": "  @acme   triage "}}) == {
        "triage": Binding("triage", NAME, "@acme triage")
    }


@pytest.mark.parametrize(
    "block, match",
    [
        ({"triage": {"graph": "acme-undeclared"}}, "nor declared under `graphs`"),
        ({"triage": {"graph": PDLC_REVIEW_LOOP + "x"}}, "nor declared"),
        ({"triage": {"graph": "pdlc-pr-loop"}}, "nor declared"),
        ({"triage": {}}, "needs a `graph`"),
        ({"triage": {"graph": "  "}}, "needs a `graph`"),
        ({"triage": NAME}, "must be a mapping"),
        ({"triage": {"graph": NAME, "loop": "x"}}, "unknown key"),
        ({"Triage": {"graph": NAME}}, "lowercase"),
        ({"do": {"graph": NAME, "keyword": "@acme do"}}, "routing.control.keywords"),
        ({"triage": {"graph": NAME, "keyword": ""}}, "non-empty string"),
        ({"triage": {"graph": NAME, "keyword": 3}}, "non-empty string"),
        ([{"triage": NAME}], "must be a mapping of command"),
    ],
)
def test_binding_refuses_a_malformed_entry(block, match):
    """R3.1, R3.2 — a binding names a loop that exists, and only that."""
    with pytest.raises(GraphConfigError, match=match):
        _bindings(block)


def test_an_absent_commands_block_binds_nothing():
    assert read_bindings(None, Catalog()) == {}
    assert read_bindings({}, Catalog()) == {}


def test_a_path_resolves_against_the_config_directory(tmp_path, monkeypatch):
    """R1.4 — relative to the CLI config in effect, never to a checkout."""
    _cli_config(tmp_path, monkeypatch, "")
    assert CustomGraph(NAME, "graphs/t.yaml").resolved_path() == (
        tmp_path / "graphs" / "t.yaml"
    )
    assert CustomGraph(NAME, "/abs/t.yaml").resolved_path() == Path("/abs/t.yaml")
    assert CustomGraph(NAME, "~/t.yaml").resolved_path() == Path.home() / "t.yaml"


# -- R2: the compiler ---------------------------------------------------------


def test_the_phase_vocabulary_is_the_shipped_loops_phases():
    """R2.3 — pinned so a new shipped phase is added to the vocabulary with it."""
    phases = []
    for name in SHIPPED_LOOPS:
        for node in load_graph(name=name).ordered():
            if node.phase and node.phase not in phases:
                phases.append(node.phase)
    assert sorted(phases) == sorted(PHASE_VOCABULARY)


def test_a_declared_graph_loads_by_name_and_takes_the_declared_name(tmp_path):
    """R2.1, R2.2"""
    path = _graph_file(tmp_path)
    catalog = _catalog({"name": NAME, "path": str(path)})
    graph = load_graph(name=NAME, catalog=catalog)
    assert graph.name == NAME
    assert graph.start == "triage"
    assert [n.id for n in graph.ordered()] == ["triage", "complete", "cleanup"]


def test_a_graph_naming_itself_differently_is_refused(tmp_path):
    """R2.2"""
    path = _graph_file(tmp_path, "name: something-else\n" + TRIAGE)
    with pytest.raises(GraphConfigError, match="names itself"):
        compile_custom(CustomGraph(NAME, str(path)))


def test_a_graph_with_a_phase_outside_the_vocabulary_is_refused(tmp_path):
    """R2.3"""
    path = _graph_file(tmp_path, TRIAGE.replace("phase: implementation", "phase: qa"))
    with pytest.raises(GraphConfigError, match="not one of the-loop's phases"):
        compile_custom(CustomGraph(NAME, str(path)))


@pytest.mark.parametrize(
    "body, match",
    [
        (TRIAGE.replace("[set-phase-label]", "[no-such-hook]", 1), "unknown hook"),
        (TRIAGE.replace("to: complete", "to: nowhere"), "undeclared node"),
        (TRIAGE.replace("start: triage", "start: nowhere"), "start node"),
        (TRIAGE.replace("acme:triage", "acme triage; rm -rf"), "slash-command"),
        (TRIAGE.replace("acme:triage", "/the-loop:x"), "slash-command"),
    ],
)
def test_a_custom_graph_is_held_to_the_shipped_compiler(tmp_path, body, match):
    """R2.1, R2.5 — the same errors a shipped loop would raise, naming the graph."""
    path = _graph_file(tmp_path, body)
    with pytest.raises(GraphConfigError, match=match) as raised:
        compile_custom(CustomGraph(NAME, str(path)))
    assert NAME in str(raised.value)


@pytest.mark.parametrize(
    "body, match",
    [(None, "could not read"), (":\n- [", "not valid YAML"), ("- a\n", "mapping")],
)
def test_an_unreadable_graph_file_names_the_declaration(tmp_path, body, match):
    """R2.6"""
    path = tmp_path / "graphs" / "triage.yaml"
    if body is not None:
        _graph_file(tmp_path, body)
    with pytest.raises(GraphConfigError, match=match) as raised:
        compile_custom(CustomGraph(NAME, str(path)))
    assert NAME in str(raised.value)


def test_slash_command_renders_the_loops_own_and_a_namespaced_command():
    """R2.5"""
    assert slash_command("do-task") == "/the-loop:do-task"
    assert slash_command("acme:triage") == "/acme:triage"


def test_a_name_neither_shipped_nor_declared_is_refused(tmp_path):
    with pytest.raises(GraphConfigError, match="neither"):
        load_graph(name=NAME)
    with pytest.raises(GraphConfigError, match="neither"):
        load_graph(name="../../etc/passwd", catalog=Catalog())


def _hooked_repo(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / ".the-loop" / "hooks").mkdir(parents=True)
    (root / ".the-loop" / "hooks" / "triage.py").write_text(MODULE)
    return root


HOOKED = TRIAGE.replace("    exit: []", "    exit: [x-triage-rules]", 1)


def test_an_x_hook_in_a_custom_graph_binds_to_the_declared_module(tmp_path):
    """R2.4"""
    repo = _hooked_repo(tmp_path)
    catalog = _catalog({"name": NAME, "path": str(_graph_file(tmp_path, HOOKED))})
    declaration = extensions.read_declaration(
        {
            "routing": {
                "graph": {"hooks": {"modules": [{"path": ".the-loop/hooks/triage.py"}]}}
            }
        }
    )
    graph = load_graph(repo=repo, name=NAME, declaration=declaration, catalog=catalog)
    assert graph.node("triage").exit == ("x-triage-rules",)
    assert callable(graph.hook_for("x-triage-rules"))


def test_an_x_hook_without_a_declared_module_fails_the_load(tmp_path):
    """R2.4 — a gate the graph asked for either runs or is loudly absent."""
    catalog = _catalog({"name": NAME, "path": str(_graph_file(tmp_path, HOOKED))})
    with pytest.raises(GraphConfigError, match="x-triage-rules"):
        load_graph(repo=tmp_path, name=NAME, catalog=catalog)


def test_an_x_hook_no_declared_module_registers_fails_the_load(tmp_path):
    repo = _hooked_repo(tmp_path)
    body = HOOKED.replace("x-triage-rules", "x-absent")
    catalog = _catalog({"name": NAME, "path": str(_graph_file(tmp_path, body))})
    declaration = extensions.read_declaration(
        {
            "routing": {
                "graph": {"hooks": {"modules": [{"path": ".the-loop/hooks/triage.py"}]}}
            }
        }
    )
    with pytest.raises(GraphConfigError, match="x-absent"):
        load_graph(repo=repo, name=NAME, declaration=declaration, catalog=catalog)


def test_a_shipped_graph_still_may_not_name_an_x_hook():
    with pytest.raises(GraphConfigError, match="unknown hook"):
        from the_loop.graph.model import compile_graph

        compile_graph(
            {
                "nodes": [{"id": "a", "exit": ["x-anything"]}],
            }
        )


def test_repo_file_for_declared_name_is_ignored(tmp_path, caplog):
    """R8 / abuse case 5 — the operator's file loads; the repository's is named."""
    repo = tmp_path / "checkout"
    (repo / ".the-loop").mkdir(parents=True)
    (repo / ".the-loop" / f"{NAME}.yaml").write_text("start: evil\nnodes: []\n")
    catalog = _catalog({"name": NAME, "path": str(_graph_file(tmp_path))})
    with caplog.at_level("WARNING", logger="the-loop.graph"):
        graph = load_graph(repo=repo, name=NAME, catalog=catalog)
    assert graph.start == "triage"
    assert "top-level `graphs`" in caplog.text
    assert "cannot be overridden" in caplog.text


# -- R4: selection is fail-closed to declared names ----------------------------


@pytest.mark.parametrize(
    "recorded, declared, expected",
    [
        (NAME, (NAME,), NAME),
        (NAME, (), ""),
        ("acme-other", (NAME,), ""),
        ("../graphs/triage.yaml", (NAME,), ""),
        (PDLC_WORK_ITEM_LOOP, (NAME,), ""),
        (PDLC_REVIEW_LOOP, (NAME,), PDLC_REVIEW_LOOP),
        ("", (NAME,), ""),
    ],
)
def test_resolve_outer_loop_accepts_only_declared_names(recorded, declared, expected):
    """R4.2 / abuse case 1"""
    assert resolve_outer_loop(recorded, declared) == expected


def test_build_runtime_walks_a_declared_graph(tmp_path, monkeypatch, repo):
    """R4.3, R5.2"""
    _graph_file(tmp_path)
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    runtime = build_runtime(repo, loop=NAME)
    assert runtime.graph.name == NAME
    assert runtime.config["guestLoop"] is False


def test_a_guest_declaration_makes_the_runtime_a_guest(tmp_path, monkeypatch, repo):
    """R5.1"""
    _graph_file(tmp_path)
    _cli_config(tmp_path, monkeypatch, _declared(guest=True))
    assert build_runtime(repo, loop=NAME).config["guestLoop"] is True


def test_forged_state_loop_reads_as_default(tmp_path, monkeypatch, repo, caplog):
    """Abuse case 1 — an undeclared name in the state file never picks a file."""
    _graph_file(tmp_path)
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    with caplog.at_level("WARNING", logger="the-loop.graph"):
        runtime = build_runtime(repo, loop="acme-not-declared")
    assert runtime.graph.name == PDLC_WORK_ITEM_LOOP
    assert "acme-not-declared" in caplog.text


def test_a_declared_graph_that_fails_to_load_is_never_the_default(
    tmp_path, monkeypatch, repo
):
    """R4.4"""
    _graph_file(tmp_path, TRIAGE.replace("phase: implementation", "phase: qa"))
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    with pytest.raises(GraphConfigError, match="phase"):
        build_runtime(repo, loop=NAME)


def test_the_core_verbs_address_a_custom_item_from_its_state(
    tmp_path, monkeypatch, repo
):
    """R4.3 — `the-loop check` reads the recorded loop through the catalog."""
    from the_loop.core import graphs as core_graphs

    _graph_file(tmp_path)
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    spec = repo / "docs" / "specs" / WORK_ITEM
    state = WorkItemState.load(spec, WORK_ITEM)
    state.loop = NAME
    state.save(spec)
    report = core_graphs.check(str(repo), WORK_ITEM)
    assert [n["node"] for n in report["nodes"]] == ["triage", "complete", "cleanup"]


def test_graphlink_selects_the_recorded_loop_through_the_resolver(tmp_path):
    """R4.1, R4.2 — state first, then the control record's loop, then its command."""
    from the_loop.graphlink import GraphLink, GraphLinkConfig
    from the_loop.sessions import WorkItemRef

    store = ControlStore(tmp_path / "portable")
    control = _control({"triage": {"graph": NAME}})
    link = GraphLink(GraphLinkConfig(), control, control_store=store)
    ref = WorkItemRef.parse(REF)
    spec = tmp_path / "docs" / "specs" / WORK_ITEM
    spec.mkdir(parents=True)
    outer = lambda: link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref)  # noqa: E731

    store.record(ref, "start", actor="owner", loop=NAME)
    assert outer() == NAME
    # A record naming a loop the operator no longer declares reads as the default.
    store.record(ref, "start", actor="owner", loop="acme-gone")
    assert outer() == ""
    # A record without a loop selects by its command, as before.
    store.record(ref, "do", actor="owner")
    assert outer() == PDLC_ADHOC_LOOP
    # Once started, the state is the fact.
    state = WorkItemState.load(spec, WORK_ITEM)
    state.loop = NAME
    state.save(spec)
    store.record(ref, "do", actor="owner")
    assert outer() == NAME


def test_runtime_start_records_the_custom_loop(tmp_path, monkeypatch, repo):
    """R4.1 — the name the state freezes is the declared one."""
    _graph_file(tmp_path)
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    runtime = build_runtime(repo, loop=NAME, origin_repo="octo/repo")
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: None
    )
    runtime.start(WORK_ITEM, ref=REF)
    spec = repo / "docs" / "specs" / WORK_ITEM
    assert WorkItemState.load(spec, WORK_ITEM).loop == NAME


# -- R7: graph loops ----------------------------------------------------------


def _loops(tmp_path, capsys, fmt="json"):
    args = argparse.Namespace(repo=str(tmp_path), action="loops", format=fmt)
    code = GraphCommand().run(args)
    out = capsys.readouterr().out
    return code, (json.loads(out) if fmt == "json" else out)


def test_graph_loops_lists_shipped_and_declared_loops(tmp_path, monkeypatch, capsys):
    """R7.1, R7.3"""
    _graph_file(tmp_path)
    _cli_config(
        tmp_path,
        monkeypatch,
        _declared(
            commands=f"      triage: {{graph: {NAME}}}\n      do: {{graph: {NAME}}}\n"
        ),
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 0
    rows = {row["name"]: row for row in report["loops"]}
    assert set(SHIPPED_LOOPS) | {NAME} == set(rows)
    # The built-in words first, in the vocabulary's order, then the new ones.
    assert rows[NAME]["commands"] == ["the-loop do", "the-loop triage"]
    assert rows[NAME]["status"] == "ok"
    assert rows[NAME]["path"] == str(tmp_path / "graphs" / "triage.yaml")
    # `do` now selects the operator's loop, so the shipped row no longer claims it.
    assert rows[PDLC_ADHOC_LOOP]["commands"] == []
    assert rows[PDLC_WORK_ITEM_LOOP]["commands"] == ["the-loop start"]
    assert rows[PDLC_REVIEW_LOOP]["guest"] is True


def test_graph_loops_reports_a_broken_graph_and_exits_1(tmp_path, monkeypatch, capsys):
    """R7.2"""
    _graph_file(tmp_path, TRIAGE.replace("phase: implementation", "phase: qa"))
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    code, text = _loops(tmp_path, capsys, fmt="text")
    assert code == 1
    assert "compiles: NO" in text and "qa" in text


def test_graph_loops_imports_no_hook_module(tmp_path, monkeypatch, capsys):
    """R7.2 — a module that would raise on import is never imported by the report."""
    _graph_file(tmp_path, HOOKED)
    _cli_config(
        tmp_path,
        monkeypatch,
        _declared(
            graph="    hooks:\n      modules:\n        - module: acme_never_imported\n"
        ),
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 0
    row = next(r for r in report["loops"] if r["name"] == NAME)
    assert row["extensionHooks"] == ["x-triage-rules"]


def test_graph_loops_reports_an_unreadable_declaration(tmp_path, monkeypatch, capsys):
    _cli_config(tmp_path, monkeypatch, "graphs:\n  - name: pdlc-x\n    path: a\n")
    code, report = _loops(tmp_path, capsys)
    assert code == 1
    assert "reserved" in report["error"]


# -- review round 1 (independent reviewer) ------------------------------------


def test_graph_loops_compiles_in_a_fresh_process(tmp_path):
    """Review F1 — the report must register the shipped hooks itself; in-process
    tests had them imported already, which hid a report of 'unknown hook' for
    every real graph."""
    import os
    import subprocess
    import sys

    _graph_file(tmp_path)
    config = tmp_path / "cli-config.yaml"
    config.write_text('version: "0.10.0"\n' + TRIAGE_DECLARED)
    env = dict(os.environ, THE_LOOP_CLI_CONFIG=str(config))
    proc = subprocess.run(
        [sys.executable, "-m", "the_loop", "graph", "loops"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "compiles: ok" in proc.stdout


def test_graph_loops_reports_an_attachment_on_a_node_the_graph_lacks(
    tmp_path, monkeypatch, capsys
):
    """Review F3 — the R6.1 adoption failure is caught by the report, not at load."""
    _graph_file(tmp_path)
    _cli_config(
        tmp_path,
        monkeypatch,
        _declared(
            graph="    hooks:\n      attach:\n        - {hook: x-a, node: design}\n"
        ),
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 1
    row = next(r for r in report["loops"] if r["name"] == NAME)
    assert "scope the attachment" in row["error"]


def test_graph_loops_reports_x_hooks_with_no_module(tmp_path, monkeypatch, capsys):
    _graph_file(tmp_path, HOOKED)
    _cli_config(tmp_path, monkeypatch, TRIAGE_DECLARED)
    code, report = _loops(tmp_path, capsys)
    assert code == 1
    row = next(r for r in report["loops"] if r["name"] == NAME)
    assert "declares no module" in row["error"]


def test_graph_loops_reports_an_unparseable_config(tmp_path, monkeypatch, capsys):
    """Review F3 — a config that cannot be read is an error, not 'nothing declared'."""
    path = tmp_path / "cli-config.yaml"
    path.write_text("routing: [unclosed\n")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    code, report = _loops(tmp_path, capsys)
    assert code == 1 and report["error"]


def test_graph_loops_shows_the_configured_keyword(tmp_path, monkeypatch, capsys):
    """Review F9 — what a person types, and nothing for a disabled command."""
    _graph_file(tmp_path)
    _cli_config(
        tmp_path,
        monkeypatch,
        _declared(control="    keywords:\n      start: '@loop go'\n      review: ''\n"),
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 0
    rows = {row["name"]: row for row in report["loops"]}
    assert rows[PDLC_WORK_ITEM_LOOP]["commands"] == ["@loop go"]
    assert rows[PDLC_REVIEW_LOOP]["commands"] == []


@pytest.mark.parametrize(
    "graphs, match",
    [({}, "must be a list"), ("", "must be a list"), (False, "must be a list")],
)
def test_a_falsy_non_list_declaration_is_refused(graphs, match):
    """Review F6"""
    with pytest.raises(GraphConfigError, match=match):
        read_catalog({"graphs": graphs})


def test_a_non_string_path_is_refused():
    """Review F6"""
    with pytest.raises(GraphConfigError, match="each a string"):
        _catalog({"name": NAME, "path": ["graphs/t.yaml"]})


@pytest.mark.parametrize("word", ["graph", "check", "sessions", "events", "new"])
def test_a_new_word_may_not_be_one_of_the_loops_own_verbs(word):
    """Review F7 — a comment quoting `the-loop graph complete …` must not arm."""
    with pytest.raises(GraphConfigError, match="own verbs"):
        _bindings({word: {"graph": NAME}})


def test_an_overridden_start_applies_without_a_comment(tmp_path):
    """Review F2 — a CLI `sessions start` (a `start` record with no loop) and a
    spawn with no record at all both follow `start`'s current binding."""
    from the_loop.graphlink import GraphLink, GraphLinkConfig
    from the_loop.sessions import WorkItemRef

    store = ControlStore(tmp_path / "portable")
    control = _control({"start": {"graph": NAME}})
    link = GraphLink(GraphLinkConfig(), control, control_store=store)
    ref = WorkItemRef.parse(REF)
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    outer = lambda: link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref)  # noqa: E731

    assert outer() == NAME
    store.record(ref, "start", source="cli", actor="operator")
    assert outer() == NAME


def test_a_removed_override_falls_back_to_the_commands_shipped_loop(tmp_path):
    """Review F8 — a `do` armed onto a graph since removed walks the ad-hoc loop."""
    from the_loop.graphlink import GraphLink, GraphLinkConfig
    from the_loop.sessions import WorkItemRef

    store = ControlStore(tmp_path / "portable")
    link = GraphLink(GraphLinkConfig(), ControlConfig(), control_store=store)
    ref = WorkItemRef.parse(REF)
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    store.record(ref, "do", actor="owner", loop="acme-removed")
    assert (
        link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == PDLC_ADHOC_LOOP
    )


def test_the_slack_command_knows_the_operators_words():
    """Review F2 — `/the-loop triage #1` is a control verb, not an unknown one."""
    from the_loop.channels.commands import parse_invocation

    control = _control({"triage": {"graph": NAME}})
    invocation = parse_invocation("triage #12", control)
    assert invocation.family == "work-item"
    assert control.keyword(invocation.verb) == "the-loop triage"


# -- PR #425 review: top-level `graphs`, `routing.control.commands` -----------


def test_graph_loops_shows_a_new_words_own_keyword_and_a_shipped_rebinding(
    tmp_path, monkeypatch, capsys
):
    """A new word's `keyword` is what the report shows; a built-in re-pointed at
    another SHIPPED loop moves to that loop's row."""
    _graph_file(tmp_path)
    _cli_config(
        tmp_path,
        monkeypatch,
        _declared(
            commands=(
                f"      triage: {{graph: {NAME}, keyword: '@acme triage'}}\n"
                f"      do: {{graph: {PDLC_WORK_ITEM_LOOP}}}\n"
            )
        ),
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 0
    rows = {row["name"]: row for row in report["loops"]}
    assert rows[NAME]["commands"] == ["@acme triage"]
    assert rows[PDLC_WORK_ITEM_LOOP]["commands"] == ["the-loop start", "the-loop do"]
    assert rows[PDLC_ADHOC_LOOP]["commands"] == []


def test_graph_loops_reports_a_binding_to_an_undeclared_graph(
    tmp_path, monkeypatch, capsys
):
    _cli_config(
        tmp_path,
        monkeypatch,
        "routing:\n  control:\n    commands:\n      triage: {graph: acme-nope}\n",
    )
    code, report = _loops(tmp_path, capsys)
    assert code == 1
    assert "acme-nope" in report["error"]


def test_a_command_bound_to_the_default_loop_selects_the_default(tmp_path):
    """`do: {graph: pdlc-work-item-loop}` walks the work-item loop — the default
    outer loop reads as "" — never falling through to `do`'s ad-hoc loop."""
    from the_loop.graphlink import GraphLink, GraphLinkConfig
    from the_loop.sessions import WorkItemRef

    store = ControlStore(tmp_path / "portable")
    control = _control({"do": {"graph": PDLC_WORK_ITEM_LOOP}})
    link = GraphLink(GraphLinkConfig(), control, control_store=store)
    ref = WorkItemRef.parse(REF)
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    store.record(ref, "do", actor="owner", loop=PDLC_WORK_ITEM_LOOP)
    assert link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == ""
    store.record(ref, "do", source="cli", actor="operator")
    assert link._outer_loop_name(tmp_path, "docs/specs", WORK_ITEM, ref) == ""


def test_the_schema_accepts_the_documented_shape_and_refuses_the_old_one():
    """The owner's shape validates; the retired `routing.graph.graphs` does not."""
    from the_loop.configschema import validate

    good = {
        "version": "0.10.0",
        "graphs": [{"name": NAME, "path": "graphs/triage.yaml", "guest": False}],
        "routing": {
            "control": {
                "commands": {
                    "triage": {"graph": NAME, "keyword": "@acme triage"},
                    "do": {"graph": NAME},
                }
            }
        },
    }
    assert not validate(good)
    old = {
        "version": "0.10.0",
        "routing": {"graph": {"graphs": [{"name": NAME, "path": "a.yaml"}]}},
    }
    assert validate(old)
    missing_graph = {
        "version": "0.10.0",
        "routing": {"control": {"commands": {"triage": {"keyword": "x"}}}},
    }
    assert validate(missing_graph)
