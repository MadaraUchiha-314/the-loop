"""Static security assertions for the gateway tree (issue-496, T8 — design §Security
design: the gateway judges no human and builds no SQL from text)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

GATEWAY = Path(__file__).resolve().parents[1] / "the_loop" / "gateway"
FORBIDDEN = (
    "the_loop.webhook.dispatcher",
    "the_loop.authz",
    "webhook.dispatcher",
    "authz",
)


def _modules():
    return sorted(GATEWAY.rglob("*.py"))


def _imports(tree: ast.AST, module_path: Path):
    """Every imported module name, with relative imports resolved against the package."""
    package_parts = module_path.relative_to(GATEWAY.parent).with_suffix("").parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package_parts[:-1])
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                prefix = (
                    ".".join(["the_loop", *base[1:]])
                    if base and base[0] == "the_loop"
                    else ".".join(base)
                )
                name = f"{prefix}.{node.module}" if node.module else prefix
            else:
                name = node.module or ""
            yield name
            for alias in node.names:
                yield f"{name}.{alias.name}"


@pytest.mark.parametrize(
    "module", _modules(), ids=lambda p: str(p.relative_to(GATEWAY))
)
def test_the_gateway_imports_neither_the_dispatcher_nor_authz(module):
    """
    Feature: the gateway holds no allow-list, no grant and no control grammar
      Scenario: no gateway module imports webhook/dispatcher.py or authz.py
        Given every module under the_loop/gateway/
        When its import statements are read (relative ones resolved)
        Then none names the dispatcher or the authorization module — judging a human is
             the instance's job (R5.2, R5.6)

    Requirement: docs/specs/issue-496/design.md §Security design (import graph)
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    names = set(_imports(tree, module))
    offending = sorted(
        n
        for n in names
        if any(
            n == f
            or n.endswith("." + f.split(".")[-1])
            and "dispatcher" in n
            or n.endswith("authz")
            for f in FORBIDDEN
        )
    )
    assert not offending, f"{module.relative_to(GATEWAY)} imports {offending}"


@pytest.mark.parametrize(
    "module", _modules(), ids=lambda p: str(p.relative_to(GATEWAY))
)
def test_no_sql_is_built_from_an_f_string(module):
    """
    Feature: bound parameters only
      Scenario: no execute() in the gateway takes an f-string or a concatenation of a name
        Given every call to execute / executescript / executemany under the_loop/gateway/
        When its first argument is inspected
        Then it is a string literal, or a concatenation of string literals — never an
             f-string, a %-format, a .format() call or a joined variable

    Requirement: docs/specs/issue-496/design.md §Security design (SQL)
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (
            node.func.attr not in ("execute", "executescript", "executemany")
            or not node.args
        ):
            continue
        first = node.args[0]
        if not _literal_sql(first):
            bad.append(f"line {node.lineno}: {ast.dump(first)[:60]}")
    assert not bad, bad


def _literal_sql(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Name) and node.id == "_SCHEMA":
        return True  # the module-level DDL constant
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_sql(node.left) and _literal_sql(node.right)
    return False


def test_the_exposure_guard_is_the_services_rule():
    """The gateway's loopback test is the service's own (`api/config.is_loopback`), so
    the two processes cannot disagree about what loopback means."""
    source = (GATEWAY / "serve.py").read_text(encoding="utf-8")
    assert "from ..api.config import is_loopback" in source
    assert "listen.exposed" in source
