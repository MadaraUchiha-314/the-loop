"""Chain execution — run a node's hooks in order and decide what happens.

The rule (issue-109, R3): hooks run in declared order and the **first non-pass
short-circuits**. Aggregating many findings is the *hook's* job, not the
chain's — ``validate-artifacts`` returns every unmet requirement in one result
so the agent repairs in one round rather than discovering failures one at a
time.

A hook that raises or times out becomes ``block``, never ``pass`` (R2.6): the
only safe reading of "the check itself is broken" is "the gate is not
satisfied".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Sequence

from .contract import PASS, HookContext, HookResult, Message
from .registry import get_hook

logger = logging.getLogger("the-loop.graph")

__all__ = ["ChainOutcome", "run_chain"]


@dataclass
class ChainOutcome:
    """What a whole chain decided."""

    status: str
    results: List[HookResult] = field(default_factory=list)
    blocking: HookResult | None = None

    @property
    def satisfied(self) -> bool:
        return self.status == PASS

    @property
    def outcome(self) -> str:
        """The value edges route on — the deciding hook's outcome, else ``pass``.

        A hook that *blocks* is the deciding one. Otherwise the decision can
        still have been made by a hook that **passed**: ``classify-feedback``
        returns ``pass`` carrying ``data["outcome"] = "approved"``, because a
        classified review is a satisfied gate, not a blocked one. Reading only
        the blocking result discarded that verdict, so every human-approval node
        in ``pdlc.yaml`` — whose edges are declared ``on: approved`` /
        ``on: changes-requested`` — parked with ``no_edge`` however the reviewer
        replied (issue-113).

        The *last* explicit declaration wins: hooks run in declared order, so a
        later one has seen the earlier results and is the better-informed
        verdict. Only an explicit ``data["outcome"]`` counts — a plain
        ``HookResult.ok`` reports its status as its outcome, and treating that
        as a declaration would make every passing chain claim the last hook's
        name for a verdict.
        """
        if self.blocking is not None:
            return self.blocking.outcome
        for result in reversed(self.results):
            declared = result.data.get("outcome")
            if declared:
                return str(declared)
        return PASS

    @property
    def messages(self) -> List[Message]:
        return list(self.blocking.messages) if self.blocking is not None else []

    def render(self) -> str:
        """Feedback for the harness: the-loop's own text only (R3.6)."""
        if self.blocking is None:
            return ""
        head = f"`{self.blocking.hook}` did not pass:"
        return head + "\n" + self.blocking.render()

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "outcome": self.outcome,
            "results": [r.as_dict() for r in self.results],
        }


def _normalise_spec(spec: Any) -> tuple[str, Mapping[str, Any]]:
    """A chain entry is either a bare hook name or ``{hook: name, with: {...}}``."""
    if isinstance(spec, str):
        return spec, {}
    if isinstance(spec, Mapping) and "hook" in spec:
        return str(spec["hook"]), dict(spec.get("with") or {})
    raise ValueError(f"malformed hook entry: {spec!r}")


def run_chain(specs: Sequence[Any], ctx: HookContext) -> ChainOutcome:
    """Run ``specs`` in order against ``ctx``; stop at the first non-``pass``."""
    results: List[HookResult] = []
    for spec in specs:
        name, params = _normalise_spec(spec)
        fn = get_hook(name)
        ctx.results = results
        ctx.params = params
        try:
            result = fn(ctx)
        except Exception as exc:  # noqa: BLE001 — a broken check is never a pass
            logger.exception("hook %s raised", name)
            result = HookResult.blocked(
                name,
                [Message(text=f"the {name} hook failed to run: {exc}")],
                retriable=False,
            )
        results.append(result)
        if result.status != PASS:
            return ChainOutcome(status=result.status, results=results, blocking=result)
    return ChainOutcome(status=PASS, results=results)
