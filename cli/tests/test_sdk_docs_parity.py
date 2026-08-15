"""SDK ↔ documentation parity (issue-212, T5).

The defect this guards against is issue-117's, one layer up. A public library surface rots
the same way a CLI does: a method is renamed, a namespace is added, a binary joins the
environment contract, and the page that told somebody how to use it stays as it was. The
review that would have caught it is the review nobody runs on a docs page.

Four assertions, both directions on both axes:

======  =============================================================  ==========================
P1      every public SDK symbol is documented                          shipping an undocumented API
P2      every namespace method reaches a real ``core`` callable        a rename in core, dangling
P3      every binary in REQUIREMENTS appears on the environment page   an undocumented expectation
P4      every binary on the environment page is in REQUIREMENTS        documenting a check that is gone
======  =============================================================  ==========================

Pure filesystem reads and introspection: no network, no subprocess. Skipped when ``docs/``
is absent, so a source distribution that ships ``cli/`` without the site still passes.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

from the_loop import sdk
from the_loop.sdk import REQUIREMENTS, client as client_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_DOCS = REPO_ROOT / "docs" / "sdk"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "docs").is_dir(),
    reason="documentation site not present (source distribution)",
)

#: The namespaces `TheLoop` exposes, and the core module each is a binding over.
NAMESPACE_MODULES: Dict[str, str] = {
    "work_items": "the_loop.core.workitems",
    "sessions": "the_loop.core.sessions",
    "graph": "the_loop.core.graphs",
    "events": "the_loop.core.events",
    "daemons": "the_loop.core.daemons",
    "attention": "the_loop.core.attention",
    "repo": "the_loop.core.repo",
    "settings": "the_loop.core.config",
}


def _docs_text() -> str:
    return "\n".join(
        page.read_text(encoding="utf-8") for page in sorted(SDK_DOCS.rglob("*.md"))
    )


def _namespace_classes() -> Dict[str, type]:
    return {
        name: getattr(client_mod, attribute)
        for name, attribute in (
            ("work_items", "WorkItems"),
            ("sessions", "Sessions"),
            ("graph", "Graph"),
            ("events", "Events"),
            ("daemons", "Daemons"),
            ("attention", "Attention"),
            ("repo", "Repo"),
            ("settings", "Settings"),
        )
    }


def _public_methods(cls: type) -> List[str]:
    return sorted(
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def test_p1_every_public_symbol_is_documented() -> None:
    """A public name nobody wrote up is an API only its author can use."""
    text = _docs_text()
    documented: Set[str] = set()

    for name in sdk.__all__:
        if name in text:
            documented.add(name)
    missing = sorted(set(sdk.__all__) - documented)

    for namespace, cls in _namespace_classes().items():
        for method in _public_methods(cls):
            # `loop.settings` + `update(...)` — the reference documents each namespace as
            # a heading and its methods in the table beneath.
            if f"`{method}(" not in text and f"| `{method}" not in text:
                missing.append(f"{namespace}.{method}")

    for member in (
        "router",
        "mcp_app",
        "lifespan",
        "mount",
        "reload",
        "status",
        "check_environment",
        "config",
        "config_path",
        "host_ingresses",
    ):
        if member not in text:
            missing.append(f"TheLoop.{member}")

    assert not missing, (
        "public but undocumented — add them under docs/sdk/: "
        + ", ".join(sorted(missing))
    )


def test_p2_every_namespace_method_reaches_core() -> None:
    """A rename in `core` must not leave the SDK with a method that raises at runtime.

    The SDK duplicates *signatures* on purpose — that is what makes the surface a
    contract — so this is the test that buys back the drift risk duplication introduces.
    """
    import importlib

    dangling = []
    for namespace, module_name in NAMESPACE_MODULES.items():
        module = importlib.import_module(module_name)
        cls = _namespace_classes()[namespace]
        for method in _public_methods(cls):
            source = inspect.getsource(getattr(cls, method))
            called = re.findall(r"core_\w+\.(\w+)\(", source)
            assert called, f"{namespace}.{method} delegates to nothing"
            for function in called:
                if not callable(getattr(module, function, None)):
                    dangling.append(f"{namespace}.{method} -> {module_name}.{function}")
    assert not dangling, "SDK methods pointing at functions core no longer has:\n  " + (
        "\n  ".join(dangling)
    )


def test_p3_every_required_binary_is_documented() -> None:
    """The environment contract is only a contract where somebody can read it."""
    text = (SDK_DOCS / "environment.md").read_text(encoding="utf-8")
    missing = sorted(
        requirement.default_binary
        for requirement in REQUIREMENTS
        if f"`{requirement.default_binary}`" not in text
    )
    assert not missing, (
        "in the_loop.sdk.environment.REQUIREMENTS but absent from "
        "docs/sdk/environment.md: " + ", ".join(missing)
    )


def test_p4_the_documented_table_names_no_binary_that_is_gone() -> None:
    """Documenting a check the SDK no longer performs sends readers at nothing."""
    text = (SDK_DOCS / "environment.md").read_text(encoding="utf-8")
    known = {requirement.default_binary for requirement in REQUIREMENTS}
    # Rows of the contract table: `| `<binary>` | …`
    documented = set(re.findall(r"^\| `([a-z0-9-]+)` \|", text, flags=re.MULTILINE))
    unknown = sorted(documented - known)
    assert not unknown, (
        "documented in the contract table but not in REQUIREMENTS: "
        + ", ".join(unknown)
    )
    assert documented == known, f"table rows {documented} != REQUIREMENTS {known}"
