"""A repository's own graph hooks — parsing, loading, attaching (issue-248).

Every test here builds a repository under ``tmp_path``, writes the hook module it
declares, and compiles a graph against it. Nothing reaches the network, nothing
spawns a process, and no checked-in fixture executes: the modules these tests load
are written by the tests themselves, three lines at a time.

The negatives are the point. A repository hook runs **in the-loop's process**, so
what it may not do is what the feature is: it cannot rescue a chain a shipped hook
blocked, cannot declare an outcome, cannot be loaded from outside the repository,
and cannot take a name that shadows a shipped hook.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph import extensions
from the_loop.graph.chain import run_chain
from the_loop.graph.contract import BLOCK, PASS, HookContext, HookResult, WorkItem
from the_loop.graph.model import GraphConfigError, compile_graph, load_graph
from the_loop.graph.registry import EXTENSION_PREFIX, collecting, hook

MODULE = """
from the_loop.graph import HookResult, hook


@hook("x-house-rules")
def house_rules(ctx):
    return HookResult.ok("x-house-rules", seen=ctx.node.get("id"))
"""

GRAPH = {
    "start": "work",
    "nodes": [
        {"id": "work", "entry": ["log-entry"], "exit": []},
        {"id": "done", "terminal": True},
    ],
    "edges": [{"from": "work", "to": "done", "on": "pass"}],
}


@pytest.fixture(autouse=True)
def _forget_loaded_modules():
    """Each test loads its own modules; the process cache must not leak across."""
    extensions.clear_module_cache()
    yield
    extensions.clear_module_cache()


def _repo(tmp_path: Path, module_body: str = MODULE, **hooks_block) -> Path:
    (tmp_path / ".the-loop" / "hooks").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".the-loop" / "hooks" / "house.py").write_text(module_body)
    return tmp_path


def _declaration(**hooks_block) -> extensions.Declaration:
    return extensions.read_declaration({"graph": {"hooks": hooks_block}})


def _context(node_id: str = "work", graph=None) -> HookContext:
    return HookContext(
        work_item=WorkItem(ref="github:octo/repo#1", id="issue-1", spec_dir=Path(".")),
        node={"id": node_id},
        boundary="exit",
        repo=Path("."),
        graph=graph,
    )


# ------------------------------------------------------------------- collector


def test_collector_takes_the_registration_instead_of_the_global_registry():
    with collecting() as table:
        hook("x-collected")(lambda ctx: HookResult.ok("x-collected"))
    assert "x-collected" in table
    from the_loop.graph.registry import is_registered

    assert not is_registered("x-collected")


def test_collector_refuses_a_name_without_the_extension_prefix():
    with pytest.raises(ValueError, match="must be named"):
        with collecting():
            hook("validate-artifacts")(lambda ctx: HookResult.ok("validate-artifacts"))


def test_a_shipped_hook_may_not_take_an_extension_name():
    with pytest.raises(ValueError, match="reserved"):
        hook(f"{EXTENSION_PREFIX}shipped")(lambda ctx: HookResult.ok("x-shipped"))


def test_the_collector_is_not_re_entrant():
    with pytest.raises(RuntimeError, match="already in progress"):
        with collecting():
            with collecting():
                pass


def test_the_collector_releases_on_failure():
    with pytest.raises(ValueError):
        with collecting():
            hook("nope")(lambda ctx: HookResult.ok("nope"))
    with collecting() as table:  # would raise "already in progress" if leaked
        assert table == {}


# ----------------------------------------------------------------- declaration


def test_declaration_reads_modules_and_attachments():
    declaration = _declaration(
        modules=[{"path": ".the-loop/hooks/house.py"}, {"module": "acme.hooks"}],
        attach=[{"hook": "x-house-rules", "node": "work", "with": {"level": 2}}],
    )
    assert [m.label() for m in declaration.modules] == [
        ".the-loop/hooks/house.py",
        "acme.hooks",
    ]
    assert declaration.attachments[0].boundary == "exit"
    assert declaration.attachments[0].params == {"level": 2}
    assert not declaration.empty


def test_an_absent_block_declares_nothing():
    assert extensions.read_declaration({}).empty
    assert extensions.read_declaration({"graph": {}}).empty
    assert extensions.read_declaration({"graph": {"hooks": {}}}).empty


def test_the_digest_follows_the_declaration():
    one = _declaration(modules=[{"path": "a.py"}])
    two = _declaration(modules=[{"path": "b.py"}])
    assert one.digest() != two.digest()
    assert one.digest() == _declaration(modules=[{"path": "a.py"}]).digest()


@pytest.mark.parametrize(
    "block, message",
    [
        ({"modules": {"path": "a.py"}}, "must be a list"),
        ({"modules": ["a.py"]}, "must be a mapping"),
        ({"modules": [{}]}, "exactly one"),
        ({"modules": [{"path": "a.py", "module": "a"}]}, "exactly one"),
        ({"modules": [{"module": "not a module"}]}, "importable dotted name"),
        ({"attach": [{"hook": "x-a"}]}, "needs"),
        ({"attach": [{"hook": "plain", "node": "work"}]}, "may only name"),
        (
            {"attach": [{"hook": "x-a", "node": "work", "boundary": "middle"}]},
            "boundary",
        ),
        ({"attach": [{"hook": "x-a", "node": "work", "with": []}]}, "not a mapping"),
    ],
)
def test_a_malformed_declaration_is_refused_at_parse_time(block, message):
    with pytest.raises(GraphConfigError, match=message):
        _declaration(**block)


def test_a_graph_block_that_is_not_a_mapping_is_refused():
    with pytest.raises(GraphConfigError, match="must be a mapping"):
        extensions.read_declaration({"graph": "hooks"})


# --------------------------------------------------------------------- loading


def test_load_returns_the_repositorys_table(tmp_path):
    repo = _repo(tmp_path)
    table = extensions.load_modules(
        repo, _declaration(modules=[{"path": ".the-loop/hooks/house.py"}])
    )
    assert list(table) == ["x-house-rules"]
    assert table["x-house-rules"](_context()).status == PASS


def test_a_module_outside_the_repository_is_refused(tmp_path):
    outside = tmp_path.parent / "elsewhere.py"
    outside.write_text(MODULE)
    repo = _repo(tmp_path)
    for raw in (str(outside), "../elsewhere.py"):
        with pytest.raises(GraphConfigError, match="absolute|outside the repository"):
            extensions.load_modules(repo, _declaration(modules=[{"path": raw}]))


def test_a_symlink_leaving_the_repository_is_refused(tmp_path):
    outside = tmp_path.parent / "linked.py"
    outside.write_text(MODULE)
    repo = _repo(tmp_path)
    link = repo / ".the-loop" / "hooks" / "linked.py"
    link.symlink_to(outside)
    with pytest.raises(GraphConfigError, match="outside the repository"):
        extensions.load_modules(
            repo, _declaration(modules=[{"path": ".the-loop/hooks/linked.py"}])
        )


def test_a_module_that_is_not_python_or_not_there_is_refused(tmp_path):
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("hello")
    with pytest.raises(GraphConfigError, match="not a .py file"):
        extensions.load_modules(repo, _declaration(modules=[{"path": "notes.txt"}]))
    with pytest.raises(GraphConfigError, match="does not exist"):
        extensions.load_modules(repo, _declaration(modules=[{"path": "gone.py"}]))


def test_a_module_that_raises_names_itself(tmp_path):
    repo = _repo(tmp_path, "raise RuntimeError('boom')\n")
    with pytest.raises(GraphConfigError, match="house.py.*could not be loaded"):
        extensions.load_modules(
            repo, _declaration(modules=[{"path": ".the-loop/hooks/house.py"}])
        )


def test_a_module_registering_nothing_is_refused(tmp_path):
    repo = _repo(tmp_path, "VALUE = 1\n")
    with pytest.raises(GraphConfigError, match="registered no hooks"):
        extensions.load_modules(
            repo, _declaration(modules=[{"path": ".the-loop/hooks/house.py"}])
        )


def test_a_module_registering_a_shipped_name_fails_to_load(tmp_path):
    repo = _repo(
        tmp_path,
        "from the_loop.graph import HookResult, hook\n\n"
        "@hook('validate-artifacts')\n"
        "def shadow(ctx):\n"
        "    return HookResult.ok('validate-artifacts')\n",
    )
    with pytest.raises(GraphConfigError, match="validate-artifacts"):
        extensions.load_modules(
            repo, _declaration(modules=[{"path": ".the-loop/hooks/house.py"}])
        )


def test_two_modules_registering_one_name_is_refused(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".the-loop" / "hooks" / "other.py").write_text(MODULE)
    with pytest.raises(GraphConfigError, match="two hook modules"):
        extensions.load_modules(
            repo,
            _declaration(
                modules=[
                    {"path": ".the-loop/hooks/house.py"},
                    {"path": ".the-loop/hooks/other.py"},
                ]
            ),
        )


def test_a_module_is_executed_once_per_process(tmp_path):
    repo = _repo(
        tmp_path,
        "from the_loop.graph import HookResult, hook\n"
        "import pathlib\n"
        "pathlib.Path(__file__).with_name('loads.txt').open('a').write('x')\n\n"
        "@hook('x-house-rules')\n"
        "def house(ctx):\n"
        "    return HookResult.ok('x-house-rules')\n",
    )
    declaration = _declaration(modules=[{"path": ".the-loop/hooks/house.py"}])
    extensions.load_modules(repo, declaration)
    extensions.load_modules(repo, declaration)
    assert (repo / ".the-loop" / "hooks" / "loads.txt").read_text() == "x"


# -------------------------------------------------------------------- attaching


def test_apply_appends_to_the_declared_boundary(tmp_path):
    repo = _repo(tmp_path)
    graph = extensions.apply(
        compile_graph(GRAPH),
        repo,
        _declaration(
            modules=[{"path": ".the-loop/hooks/house.py"}],
            attach=[{"hook": "x-house-rules", "node": "work", "boundary": "entry"}],
        ),
    )
    assert graph.node("work").entry == ("log-entry", {"hook": "x-house-rules"})
    assert graph.node("work").exit == ()
    assert graph.hook_for("x-house-rules") is graph.extension_hooks["x-house-rules"]


def test_apply_carries_the_params_through(tmp_path):
    repo = _repo(tmp_path)
    graph = extensions.apply(
        compile_graph(GRAPH),
        repo,
        _declaration(
            modules=[{"path": ".the-loop/hooks/house.py"}],
            attach=[{"hook": "x-house-rules", "node": "work", "with": {"level": 2}}],
        ),
    )
    assert graph.node("work").exit == ({"hook": "x-house-rules", "with": {"level": 2}},)


def test_apply_refuses_an_unknown_hook_or_node(tmp_path):
    repo = _repo(tmp_path)
    modules = [{"path": ".the-loop/hooks/house.py"}]
    with pytest.raises(GraphConfigError, match="no declared module registered"):
        extensions.apply(
            compile_graph(GRAPH),
            repo,
            _declaration(
                modules=modules, attach=[{"hook": "x-absent", "node": "work"}]
            ),
        )
    with pytest.raises(GraphConfigError, match="does not declare"):
        extensions.apply(
            compile_graph(GRAPH),
            repo,
            _declaration(
                modules=modules, attach=[{"hook": "x-house-rules", "node": "nope"}]
            ),
        )


def test_two_repositories_keep_their_own_implementations(tmp_path):
    first = _repo(tmp_path / "one")
    second = _repo(
        tmp_path / "two",
        "from the_loop.graph import HookResult, hook\n\n"
        "@hook('x-house-rules')\n"
        "def house(ctx):\n"
        "    return HookResult.blocked('x-house-rules', [])\n",
    )
    declaration = _declaration(
        modules=[{"path": ".the-loop/hooks/house.py"}],
        attach=[{"hook": "x-house-rules", "node": "work"}],
    )
    one = extensions.apply(compile_graph(GRAPH), first, declaration)
    two = extensions.apply(compile_graph(GRAPH), second, declaration)
    assert one.hook_for("x-house-rules")(_context()).status == PASS
    assert two.hook_for("x-house-rules")(_context()).status == BLOCK


def test_hook_for_falls_through_to_the_shipped_registry():
    graph = compile_graph(GRAPH)
    assert graph.hook_for("log-entry") is not None
    with pytest.raises(KeyError, match="unknown hook"):
        graph.hook_for("x-nothing")


# ----------------------------------------------------------------------- chain


def _graph_with(tmp_path: Path, body: str, node: str = "work"):
    repo = _repo(tmp_path, body)
    return extensions.apply(
        compile_graph(GRAPH),
        repo,
        _declaration(
            modules=[{"path": ".the-loop/hooks/house.py"}],
            attach=[{"hook": "x-house-rules", "node": node}],
        ),
    )


def test_a_repository_hook_runs_through_the_chain(tmp_path):
    graph = _graph_with(tmp_path, MODULE)
    outcome = run_chain(graph.node("work").exit, _context(graph=graph))
    assert outcome.status == PASS
    assert outcome.results[0].data["seen"] == "work"


def test_a_repository_hook_can_block(tmp_path):
    graph = _graph_with(
        tmp_path,
        "from the_loop.graph import HookResult, Message, hook\n\n"
        "@hook('x-house-rules')\n"
        "def house(ctx):\n"
        "    return HookResult.blocked('x-house-rules', [Message(text='no')])\n",
    )
    outcome = run_chain(graph.node("work").exit, _context(graph=graph))
    assert outcome.status == BLOCK
    assert "no" in outcome.render()


def test_a_raising_repository_hook_blocks(tmp_path):
    graph = _graph_with(
        tmp_path,
        "from the_loop.graph import hook\n\n"
        "@hook('x-house-rules')\n"
        "def house(ctx):\n"
        "    raise RuntimeError('boom')\n",
    )
    outcome = run_chain(graph.node("work").exit, _context(graph=graph))
    assert outcome.status == BLOCK
    assert outcome.blocking is not None and not outcome.blocking.retriable


def test_a_repository_hook_cannot_declare_an_outcome(tmp_path, caplog):
    graph = _graph_with(
        tmp_path,
        "from the_loop.graph import HookResult, hook\n\n"
        "@hook('x-house-rules')\n"
        "def house(ctx):\n"
        "    return HookResult.ok('x-house-rules', outcome='approved')\n",
    )
    with caplog.at_level("WARNING"):
        outcome = run_chain(graph.node("work").exit, _context(graph=graph))
    assert outcome.outcome == PASS
    assert "outcome" not in outcome.results[0].data
    assert "do not route" in caplog.text


def test_a_repository_hook_cannot_rescue_a_blocked_chain(tmp_path):
    """A SHIPPED hook short-circuits, so the appended one never runs (abuse case 1).

    `validate-artifacts` blocking on a missing `requirements.md` is the real
    shape of the attack: a repository hook returning `pass` after it cannot turn
    the node green, because the chain stopped before reaching it.
    """
    graph = _graph_with(tmp_path, MODULE)
    ctx = HookContext(
        work_item=WorkItem(
            ref="github:octo/repo#1", id="issue-1", spec_dir=tmp_path / "specs"
        ),
        node={"id": "work", "produces": ["requirements.md"]},
        boundary="exit",
        repo=tmp_path,
        graph=graph,
    )
    chain = ("validate-artifacts",) + graph.node("work").exit
    outcome = run_chain(chain, ctx)
    assert outcome.status == BLOCK
    assert [r.hook for r in outcome.results] == ["validate-artifacts"]


# ------------------------------------------------------------------ load_graph


def _adopt(repo: Path, block: str) -> None:
    (repo / ".the-loop").mkdir(parents=True, exist_ok=True)
    (repo / ".the-loop" / "harness-config.yaml").write_text(block)


HARNESS = """
version: "0.2.0"
graph:
  hooks:
    modules:
      - path: .the-loop/hooks/house.py
    attach:
      - hook: x-house-rules
        node: implementation
"""


def test_load_graph_attaches_a_repositorys_hooks(tmp_path):
    repo = _repo(tmp_path)
    _adopt(repo, HARNESS)
    graph = load_graph(repo=repo)
    assert graph.node("implementation").exit[-1] == {"hook": "x-house-rules"}


def test_load_graph_without_a_declaration_changes_nothing(tmp_path):
    plain = load_graph()
    assert (
        load_graph(repo=tmp_path).node("implementation").exit
        == plain.node("implementation").exit
    )
    assert load_graph(repo=tmp_path).extension_hooks == {}


def test_the_operator_kill_switch_imports_nothing(tmp_path):
    repo = _repo(tmp_path, "raise RuntimeError('this module must never run')\n")
    _adopt(repo, HARNESS)
    graph = load_graph(repo=repo, allow_repo_hooks=False)
    assert graph.extension_hooks == {}
    assert all(
        entry != {"hook": "x-house-rules"}
        for entry in graph.node("implementation").exit
    )


def test_a_broken_declaration_fails_the_load_rather_than_degrading(tmp_path):
    repo = _repo(tmp_path)
    _adopt(repo, HARNESS.replace("house.py", "missing.py"))
    with pytest.raises(GraphConfigError, match="does not exist"):
        load_graph(repo=repo)
