"""Prompts stay out of Python (issue-540, R3.1).

A tripwire, not a proof. It fails when a module under ``the_loop`` assigns a
multi-line string literal (or f-string) to a module-level name that says it is a
prompt: ``*PROMPT*``, ``*DIRECTIVE*``, ``*TEMPLATE*``, ``*NOTICE*`` or ``*NUDGE*``.
That is the shape every inline prompt had before the move. Prompt prose belongs in
``the_loop/prompts/<area>/<name>.md``, read with ``the_loop.prompts.load``.
"""

import ast
import re
from pathlib import Path

import the_loop

PACKAGE = Path(the_loop.__file__).resolve().parent
PROMPT_NAME = re.compile(r"PROMPT|DIRECTIVE|TEMPLATE|NOTICE|NUDGE", re.I)


def _string_value(node: ast.AST) -> str:
    """The literal text of a str constant or an f-string's constant parts."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _string_value(node.left) + _string_value(node.right)
    return ""


def offenders(source: str, label: str):
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not any(PROMPT_NAME.search(name) for name in names):
            continue
        if "\n" in _string_value(value).rstrip("\n"):
            found.append(f"{label}:{node.lineno} {names[0]}")
    return found


def test_no_module_defines_an_inline_multi_line_prompt():
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        found += offenders(
            path.read_text(encoding="utf-8"), str(path.relative_to(PACKAGE))
        )
    assert not found, (
        "inline prompt text — move it to the_loop/prompts/<area>/<name>.md and read "
        "it with the_loop.prompts.load:\n  " + "\n  ".join(found)
    )


def test_the_guard_fires_on_a_planted_prompt():
    planted = 'FOO_PROMPT = """\\\nYou are an agent.\nDo the thing.\n"""\n'
    assert offenders(planted, "planted.py") == ["planted.py:1 FOO_PROMPT"]
    planted_f = 'BAR_DIRECTIVE: str = f"""first {x}\nsecond"""\n'
    assert offenders(planted_f, "planted.py") == ["planted.py:1 BAR_DIRECTIVE"]


def test_the_guard_ignores_one_line_names_and_other_constants():
    clean = (
        'PROMPT_PATH = "skills/x.md"\n'
        'OTHER = """a\nb"""\n'
        'X_PROMPT = prompts.load("x/y")\n'
    )
    assert offenders(clean, "clean.py") == []
