"""Load the-loop's config schemas, and validate a document against one (issue-222).

Two jobs, both needed by the control-plane service and neither by anything that predates
it: **serve** the CLI config's schema to a client that renders a form from it, and
**validate** a document the service is about to write to the operator's config file.

Where the schemas come from
---------------------------

They ship as package data under ``the_loop/schemas/``, resolved relative to this module —
the same arrangement, for the same reason, that
:func:`the_loop.graph.model.shipped_graph_path` gives for the process graphs: a
``pip install the-loopy-one`` has no plugin checkout, so a schema resolved from
``${CLAUDE_PLUGIN_ROOT}`` is a schema the runtime may not have.

This does not reopen issue-220, whose rule is about **projects**: the-loop stops copying
its schemas into repositories it initializes. ``.the-loop/*.schema.json`` remains the
single *authored* home — the file an editor's modeline points at, the file
``scripts/validate_config.py`` runs against — and ``the_loop/schemas/`` is a build-time
copy of it inside the same distribution, held byte-identical by
``cli/tests/test_config_schema_parity.py``. Edit the one under ``.the-loop/``; copy it
here.

Why the validator is ours
-------------------------

``jsonschema`` is the obvious answer and stays the CI answer
(``scripts/validate_config.py``), but as a *runtime* dependency it would pull ``attrs``,
``referencing`` and the compiled ``rpds-py`` into a CLI whose dependency set is an
argument in itself, to be imported by every poller process in order to validate
nothing. The schemas being validated are the-loop's own, and they use sixteen keywords
between them. :data:`SUPPORTED` names all sixteen; :func:`validate` implements the ten
that constrain data and ignores the six that document it.

That trade is only safe because two tests hold it up: a **keyword guard** fails when a
schema grows a construct not in :data:`SUPPORTED`, and a **differential test** runs this
validator and the real ``jsonschema`` over the same corpus and requires them to agree.
Both live in ``cli/tests/test_configschema.py``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "CONSTRAINING",
    "SUPPORTED",
    "SchemaNotFound",
    "load_schema",
    "schema_path",
    "validate",
]

#: Where the packaged copies live, beside this module.
_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

#: Every keyword the-loop's own schemas use. The keyword-guard test asserts the schemas
#: use nothing outside this set, so "the schema grew a construct we do not check" fails a
#: test instead of silently passing a document.
SUPPORTED = frozenset(
    {
        # structural
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "properties",
        "items",
        # constraining — implemented by validate()
        "type",
        "enum",
        "required",
        "additionalProperties",
        "minimum",
        "maximum",
        "minItems",
        "uniqueItems",
        # documentation only — read by clients, ignored here
        "title",
        "description",
        "default",
        "examples",
    }
)

#: The subset :func:`validate` actually enforces. Separated from :data:`SUPPORTED` so the
#: guard test can say which of the two lists a new keyword needs to join.
CONSTRAINING = frozenset(
    {
        "type",
        "enum",
        "required",
        "additionalProperties",
        "properties",
        "items",
        "minimum",
        "maximum",
        "minItems",
        "uniqueItems",
    }
)

_JSON_TYPES: Dict[str, Tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}


class SchemaNotFound(RuntimeError):
    """A schema is missing from the installed package — a packaging fault."""


def schema_path(name: str = "cli-config") -> Path:
    """The packaged schema file for ``name`` (``cli-config``, ``collaborators``)."""
    candidate = _SCHEMA_DIR / f"{name}.schema.json"
    if candidate.is_file():
        return candidate
    raise SchemaNotFound(
        f"the shipped schema {name!r} is missing from the installed package "
        f"({candidate}). This is a packaging fault, not a configuration one — "
        "reinstall the-loopy-one."
    )


@lru_cache(maxsize=None)
def load_schema(name: str = "cli-config") -> Dict[str, Any]:
    """The named schema with every ``$ref`` resolved, ready to serve or validate.

    Resolution is deliberately narrow: the-loop's schemas contain exactly one kind of
    reference — ``<other>.schema.json#/$defs/<name>`` into a sibling packaged schema, plus
    same-document ``#/$defs/...`` — and nothing here follows a URL. A client rendering a
    form should not have to fetch a second document, and a service validating a write
    should not reach the network to do it.

    Cached because both callers are per-request and the file is ~56 KB. The returned dict
    is shared, so callers must not mutate it; the routes serialize it and the validator
    only reads.
    """
    root = json.loads(schema_path(name).read_text(encoding="utf-8"))
    return _resolve(root, root, name, set())


def _resolve(
    node: Any, root: Mapping[str, Any], name: str, seen: frozenset | set
) -> Any:
    """Replace every ``$ref`` in ``node`` with the schema it names.

    ``seen`` carries the refs currently being expanded, so a schema that referenced itself
    would raise instead of recursing forever. the-loop's schemas do not, and this is the
    cheapest way to keep that true.
    """
    if isinstance(node, list):
        return [_resolve(entry, root, name, seen) for entry in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        if ref in seen:
            raise SchemaNotFound(f"circular $ref {ref!r} in the {name} schema")
        target = _dereference(ref, root, name)
        merged = {k: v for k, v in node.items() if k != "$ref"}
        resolved = _resolve(target, root, name, set(seen) | {ref})
        if isinstance(resolved, dict):
            # Sibling keys win: a `$ref` next to a `description` means "that shape,
            # described this way", which is how the collaborators reference reads.
            return {**resolved, **merged}
        return resolved
    return {key: _resolve(value, root, name, seen) for key, value in node.items()}


def _dereference(ref: str, root: Mapping[str, Any], name: str) -> Any:
    document: Mapping[str, Any] = root
    location, _, pointer = ref.partition("#")
    if location:
        if not location.endswith(".schema.json") or "/" in location:
            raise SchemaNotFound(
                f"the {name} schema references {location!r}; only a sibling packaged "
                "schema may be referenced"
            )
        document = load_schema(location[: -len(".schema.json")])
    node: Any = document
    for token in [t for t in pointer.split("/") if t]:
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or token not in node:
            raise SchemaNotFound(f"unresolvable $ref {ref!r} in the {name} schema")
        node = node[token]
    return node


def validate(data: Any, schema: Optional[Mapping[str, Any]] = None) -> List[str]:
    """Every way ``data`` violates ``schema``, as ``"<key path>: <what is wrong>"``.

    An empty list means valid. Errors are returned rather than raised, and *all* of them
    are collected rather than the first, because the caller is a form: an operator who
    fixed one field only to be told about the next has been made to save three times to
    learn what one response could have said.

    ``schema`` defaults to the CLI config's.
    """
    errors: List[str] = []
    _check(data, schema if schema is not None else load_schema(), "", errors)
    return errors


def _label(path: str) -> str:
    return path or "(root)"


def _check(value: Any, schema: Any, path: str, errors: List[str]) -> None:
    if not isinstance(schema, Mapping) or not schema:
        return  # `true`-equivalent: no constraint

    declared = schema.get("type")
    types = [declared] if isinstance(declared, str) else list(declared or [])
    if types and not _matches_type(value, types):
        errors.append(
            f"{_label(path)}: expected {' or '.join(types)}, got {_kind(value)}"
        )
        return  # every other keyword here is typed; reporting them too is noise

    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(json.dumps(option) for option in schema["enum"])
        errors.append(f"{_label(path)}: {json.dumps(value)} is not one of {allowed}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum, maximum = schema.get("minimum"), schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{_label(path)}: {value} is below the minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{_label(path)}: {value} is above the maximum {maximum}")

    if isinstance(value, dict):
        _check_object(value, schema, path, errors)
    elif isinstance(value, (list, tuple)):
        _check_array(value, schema, path, errors)


def _check_object(
    value: Mapping[str, Any], schema: Mapping[str, Any], path: str, errors: List[str]
) -> None:
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in value:
            errors.append(f"{_label(path)}: missing required key {name!r}")
    extra = schema.get("additionalProperties", True)
    for key, entry in value.items():
        child = f"{path}.{key}" if path else str(key)
        if key in properties:
            _check(entry, properties[key], child, errors)
        elif extra is False:
            errors.append(f"{child}: unknown key")
        elif isinstance(extra, Mapping):
            _check(entry, extra, child, errors)


def _check_array(
    value: Sequence[Any], schema: Mapping[str, Any], path: str, errors: List[str]
) -> None:
    minimum = schema.get("minItems")
    if isinstance(minimum, int) and len(value) < minimum:
        errors.append(
            f"{_label(path)}: needs at least {minimum} item(s), got {len(value)}"
        )
    if schema.get("uniqueItems") and _has_duplicates(value):
        errors.append(f"{_label(path)}: entries must be unique")
    items = schema.get("items")
    if items is not None:
        for index, entry in enumerate(value):
            _check(entry, items, f"{path}[{index}]", errors)


def _has_duplicates(value: Sequence[Any]) -> bool:
    """Duplicate detection that survives unhashable entries (lists, dicts)."""
    seen: List[Any] = []
    for entry in value:
        if entry in seen:
            return True
        seen.append(entry)
    return False


def _matches_type(value: Any, types: Sequence[str]) -> bool:
    for declared in types:
        expected = _JSON_TYPES.get(str(declared))
        if expected is None:
            continue  # an unknown type name constrains nothing; the guard test catches it
        # bool is an int in Python and is not one in JSON Schema. Both directions matter:
        # `true` must not satisfy `integer`, and `1` must not satisfy `boolean`.
        if declared == "boolean":
            if isinstance(value, bool):
                return True
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, expected):
            return True
    return False


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__
