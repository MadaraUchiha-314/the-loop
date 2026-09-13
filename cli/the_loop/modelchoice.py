"""Which model and how much effort a work item's session runs on — the vocabulary.

Issue-358. Two lists of **names** and the rules that turn a name into argv. It lives in
a module of its own for the reason :mod:`the_loop.prsessions` does: it has two readers
that cannot see each other — :mod:`the_loop.webhook.dispatcher`, which builds the argv a
session is launched with, and :mod:`the_loop.graph.hooks.selection`, the `phase-selection`
gate, which offers the choice on the ticket and freezes the answer. The hook cannot import
the dispatcher (``dispatcher -> graphlink -> graph`` is a cycle), and a second copy of the
resolution rule is exactly how the checklist and the daemon come to disagree about what
``fable-5.1`` means.

**Who owns which name.** A *model* name is the **provider's** identifier — ``opus-5``,
``fable-5.1``, ``gpt-5.6-sol`` — so the-loop copies it verbatim, never normalises it, and
never parses it for a vendor (decision-124). An *effort* level is a **the-loop** concept
that harnesses spell differently, so the-loop owns the vocabulary (:data:`EFFORT_LEVELS`)
and the adapter translates. Opposite answers to "who owns the name", each for its reason.

**A declaration may narrow, only the probe may confirm.** A bare model name is a candidate
for every declared harness; a ``harnesses:`` list on it restricts where it is offered (and
what gets probed). Neither makes it *offerable* — that is :mod:`the_loop.modelprobe`'s
verdict, measured by asking the harness. So nothing here attributes a model to a harness;
it only says which combinations are worth asking about.

Nothing in this module runs a process or touches the network: it reads mappings and
returns tuples. That is what lets every rule here be unit-tested with no harness
installed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger("the-loop.modelchoice")

__all__ = [
    "EFFORT_LEVELS",
    "Finding",
    "config_findings",
    "MODELS_KEY",
    "EFFORT_KEY",
    "HARNESSES_KEY",
    "NAME_RE",
    "candidate_harnesses",
    "declared_effort",
    "declared_harnesses",
    "declared_models",
    "effective_args",
    "effort_args",
    "harness_args",
    "model_args",
]

#: The three top-level sections (issue-358, owner review on PR #359). They sit beside
#: `repositories` and `critics` rather than under `routing`, because `routing` configures
#: how an event reaches a session while these configure the machine's installed tooling.
HARNESSES_KEY = "harnesses"
MODELS_KEY = "models"
EFFORT_KEY = "effort"

#: the-loop's own effort vocabulary, identical across harnesses. The operator declares
#: which of these an instance offers; the *translation* to a given harness is that
#: harness's adapter (``effort_args``), never the operator's config.
#:
#: These five are Claude's own ``output_config.effort`` levels — ``xhigh`` is the
#: default in Claude Code — so the-loop's vocabulary is a superset rather than an
#: invention, and a harness with fewer levels simply does not offer the ones it
#: cannot express. That is the normalisation doing its job: one set of words for
#: the human, per-harness truth underneath, and every mapping probe-validated.
EFFORT_LEVELS: Tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

#: A model name's grammar. Deliberately narrow: a name is passed to a harness's model flag
#: **verbatim**, so the grammar is what makes copying a provider's own spelling safe — a
#: name can never be a flag, a path, or a shell fragment. It admits what providers
#: actually use (``opus-5``, ``fable-5.1``, ``gpt-5.6-sol``, ``claude-opus-5:beta``).
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _entries(config: Optional[Mapping[str, Any]], key: str) -> List[Any]:
    """The raw list under ``key``, or ``[]`` for anything that is not a list.

    Fail-closed in the *shrinking* direction, the rule :mod:`the_loop.repos` follows: a
    malformed section contributes nothing, so a fault can only ever remove a choice — it
    can never invent one.
    """
    raw = (config or {}).get(key)
    if not isinstance(raw, (list, tuple)):
        if raw is not None:
            logger.warning(
                "%s: expected a list, got %s; ignoring it", key, type(raw).__name__
            )
        return []
    return list(raw)


def _model_name(entry: Any) -> str:
    """The model name an entry declares, or ``""`` when it declares none.

    Two accepted shapes, both in house style: a bare string (the common case) and a
    mapping carrying ``name`` plus an optional ``harnesses`` (for narrowing).
    """
    if isinstance(entry, str):
        name = entry.strip()
    elif isinstance(entry, Mapping):
        raw = entry.get("name")
        name = raw.strip() if isinstance(raw, str) else ""
    else:
        return ""
    return name if NAME_RE.match(name) else ""


def declared_models(config: Optional[Mapping[str, Any]]) -> List[str]:
    """The model names this instance offers, in declaration order, deduplicated."""
    names: List[str] = []
    for entry in _entries(config, MODELS_KEY):
        name = _model_name(entry)
        if not name:
            logger.debug("models: ignoring an entry that declares no usable name")
            continue
        if name not in names:
            names.append(name)
    return names


def declared_effort(config: Optional[Mapping[str, Any]]) -> List[str]:
    """The effort levels this instance offers, in :data:`EFFORT_LEVELS` order.

    Enum order rather than declaration order, because the levels are the-loop's own
    vocabulary: a reader should meet them in the same sequence in every install.
    """
    declared = {
        entry.strip()
        for entry in _entries(config, EFFORT_KEY)
        if isinstance(entry, str) and entry.strip() in EFFORT_LEVELS
    }
    return [level for level in EFFORT_LEVELS if level in declared]


def declared_harnesses(config: Optional[Mapping[str, Any]]) -> List[str]:
    """The harness names this instance declares, in declaration order.

    An entry may be a bare name or a mapping carrying ``name`` (plus ``default`` and
    ``args``). Empty when the section is absent — callers fall back to the routing
    config's ``defaultHarness``, which is what every install written before issue-358 has.
    """
    names: List[str] = []
    for entry in _entries(config, HARNESSES_KEY):
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, Mapping):
            raw = entry.get("name")
            name = raw.strip() if isinstance(raw, str) else ""
        else:
            continue
        if name and name not in names:
            names.append(name)
    return names


def candidate_harnesses(config: Optional[Mapping[str, Any]], name: str) -> List[str]:
    """The harnesses ``name`` may be offered on, before the probe has its say.

    A bare declaration is a candidate for every declared harness; a ``harnesses:`` list
    narrows it to those. A narrowing that names an undeclared harness contributes nothing
    (R2.4) — the intersection only ever shrinks the set.

    This answers *which combinations are worth asking about*. Whether the harness can
    actually run the name is :mod:`the_loop.modelprobe`'s verdict, and a declaration can
    never stand in for it.
    """
    available = declared_harnesses(config)
    for entry in _entries(config, MODELS_KEY):
        if _model_name(entry) != name:
            continue
        if not isinstance(entry, Mapping):
            return list(available)
        declared = entry.get(HARNESSES_KEY)
        if not isinstance(declared, (list, tuple)):
            return list(available)
        narrowed = [
            h.strip() for h in declared if isinstance(h, str) and h.strip() in available
        ]
        return [h for i, h in enumerate(narrowed) if h not in narrowed[:i]]
    return []


def harness_args(
    config: Optional[Mapping[str, Any]], harness: str, fallback: Sequence[str] = ()
) -> List[str]:
    """This harness's launch arguments: ``harnesses[].args``, else ``fallback``.

    ``fallback`` is the deprecated ``routing.harnessArgs.<harness>``; the caller passes
    what it read there so this module needs no view of the routing config. Warn, never
    fail — an un-migrated config must not brick a daemon, which is how ``routing.runner``
    (issue-156) and the repository list (issue-348) were moved.
    """
    for entry in _entries(config, HARNESSES_KEY):
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("name")
        if not isinstance(raw, str) or raw.strip() != harness:
            continue
        args = entry.get("args")
        if isinstance(args, (list, tuple)):
            return [str(a) for a in args]
        break
    if fallback:
        logger.warning(
            "routing.harnessArgs.%s is deprecated: declare it as harnesses[].args for "
            "%r instead",
            harness,
            harness,
        )
    return [str(a) for a in fallback]


def model_args(name: str, adapter: Any) -> Tuple[str, ...]:
    """``(adapter.model_flag, name)`` — or ``()`` for a harness with no model flag.

    There is deliberately no operator-declared escape hatch here (R2.5): a harness that
    cannot be handed a model is offered no model section at all, rather than being given a
    hand-written flag that nothing validates.
    """
    flag = str(getattr(adapter, "model_flag", "") or "")
    if not flag or not name:
        return ()
    return (flag, name)


def effort_args(level: str, adapter: Any) -> Tuple[str, ...]:
    """The adapter's own translation of a normalised level, or ``()``.

    ``()`` means "this harness cannot express that level", which the gate reads as *do not
    offer it here* — never as "run without it".
    """
    if level not in EFFORT_LEVELS:
        return ()
    translate = getattr(adapter, "effort_args", None)
    if not callable(translate):
        return ()
    produced = translate(level)
    if not isinstance(produced, (list, tuple)):
        return ()
    return tuple(str(a) for a in produced)


def effective_args(
    base: Sequence[str], *resolved: Optional[Sequence[str]]
) -> List[str]:
    """``base``, then each resolved fragment, in order. Nothing else.

    The whole of R3.1–R3.2: the operator's own launch arguments are never removed,
    rewritten or reordered, and a choice contributes only what its resolution produced.
    Variadic so a call site reads ``effective_args(base, model, effort)`` and an absent
    choice contributes nothing.
    """
    args = [str(a) for a in base]
    for fragment in resolved:
        args.extend(str(a) for a in (fragment or ()))
    return args


@dataclass(frozen=True)
class Finding:
    """One thing wrong, or worth saying, about these three sections.

    Reported by ``the-loop models check`` and ``the-loop diagnose`` — at startup and on
    demand, never at spawn time. A spawn discovering a config mistake is the failure mode
    this whole feature exists to remove, so its own configuration must not be able to
    produce one.
    """

    level: str  # "error" | "warning"
    where: str  # the config path the finding is about
    message: str


def config_findings(
    config: Optional[Mapping[str, Any]],
    adapters: Optional[Mapping[str, Any]] = None,
    routing_args: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[Finding]:
    """Everything checkable about ``harnesses``/``models``/``effort`` without running one.

    ``adapters`` maps a harness name to its adapter, so the one structural fact that needs
    them — a harness with no model flag cannot be offered models — is checked here rather
    than found at a spawn. ``routing_args`` is the deprecated
    ``routing.harnessArgs``, passed in so this module still needs no view of the routing
    config.
    """
    findings: List[Finding] = []
    harnesses = declared_harnesses(config)
    models = declared_models(config)

    defaults = [
        entry.get("name")
        for entry in _entries(config, HARNESSES_KEY)
        if isinstance(entry, Mapping) and entry.get("default") is True
    ]
    if len(defaults) > 1:
        findings.append(
            Finding(
                "error",
                HARNESSES_KEY,
                "two harnesses claim `default: true` ("
                + ", ".join(str(d) for d in defaults)
                + "); a work item's harness decides which models it may be offered, so "
                "it cannot be ambiguous",
            )
        )

    for entry in _entries(config, MODELS_KEY):
        if not isinstance(entry, Mapping):
            continue
        name = _model_name(entry)
        declared = entry.get(HARNESSES_KEY)
        if not isinstance(declared, (list, tuple)):
            continue
        for harness in declared:
            if isinstance(harness, str) and harness.strip() not in harnesses:
                findings.append(
                    Finding(
                        "warning",
                        f"{MODELS_KEY}[{name}].{HARNESSES_KEY}",
                        f"{harness!r} is not a declared harness, so this narrowing "
                        "contributes nothing",
                    )
                )

    for harness in harnesses:
        adapter = (adapters or {}).get(harness)
        if adapter is None:
            findings.append(
                Finding(
                    "warning",
                    f"{HARNESSES_KEY}[{harness}]",
                    "the-loop has no adapter for this harness, so nothing can be "
                    "spawned on it",
                )
            )
            continue
        if models and not getattr(adapter, "model_flag", ""):
            findings.append(
                Finding(
                    "warning",
                    f"{HARNESSES_KEY}[{harness}]",
                    "this harness has no model flag, so no model choice is offered "
                    "for a work item on it",
                )
            )
        base = harness_args(config, harness, (routing_args or {}).get(harness) or ())
        flag = str(getattr(adapter, "model_flag", "") or "")
        if flag and flag in base:
            findings.append(
                Finding(
                    "warning",
                    f"{HARNESSES_KEY}[{harness}].args",
                    f"already carries {flag!r}; a work item's model is APPENDED after "
                    "it, and whether the appended one wins is this harness's own "
                    "argument-parsing rule, not the-loop's to assert",
                )
            )
    return findings
