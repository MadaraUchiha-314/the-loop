"""The chain runner (issue-344, R2.3, R6): executors in order, decisions carried,
failures recorded, and a promise — :meth:`Runner.run` never raises.

The one rule a caller relies on: the context handed in is the context handed back, with
its decisions as the last executor left them. A hook that raises, times out or answers
badly is a ``hooks.failed`` record and a skipped turn, not a stopped dispatch — unless
the operator marked it ``required`` and the point carries ``proceed``, in which case the
refusal is the answer (decision-137 D4).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Sequence, Tuple, TypeVar

from .. import eventlog
from .contract import Context
from .executors import Executor

logger = logging.getLogger("the-loop.lifecycle")

__all__ = ["Runner"]

C = TypeVar("C", bound=Context)


class Runner:
    def __init__(self, executors: Sequence[Executor] = ()):
        self.executors: Tuple[Executor, ...] = tuple(executors)

    @property
    def empty(self) -> bool:
        return not self.executors

    def describe(self) -> List[Dict[str, Any]]:
        return [e.describe() for e in self.executors]

    def run(self, ctx: C) -> C:
        """Run every executor that handles ``ctx``'s point, in order. Never raises."""
        try:
            self._run(ctx)
        except Exception:  # noqa: BLE001 — R6.2: no hook failure reaches a caller
            logger.exception(
                "the lifecycle hook chain for %s failed unexpectedly", ctx.POINT
            )
        return ctx

    def _run(self, ctx: Context) -> None:
        point = ctx.POINT
        for executor in self.executors:
            try:
                if not executor.handles(point):
                    continue
                changed = self._apply(executor.call(point, ctx), ctx)
            except Exception as exc:  # noqa: BLE001 — the hook's error is recorded
                self._failed(executor, ctx, exc)
                continue
            if changed:
                eventlog.emit(
                    "hooks.decided",
                    point=point,
                    hook=executor.name,
                    changed=list(changed),
                    work_item=ctx.work_item.ref or None,
                )

    @staticmethod
    def _apply(returned: Any, ctx: Context) -> Tuple[str, ...]:
        if returned is None:
            return ()
        if isinstance(returned, Context):
            return ctx.copy_decisions_from(returned)
        if isinstance(returned, Mapping):
            return ctx.apply(returned)
        raise TypeError(
            f"a hook returned a {type(returned).__name__}; return the context, a mapping "
            "of decisions, or None"
        )

    @staticmethod
    def _failed(executor: Executor, ctx: Context, exc: BaseException) -> None:
        error = (
            f"{exc.__class__.__name__}: {exc}"
            if not str(exc).startswith(exc.__class__.__name__)
            else str(exc)
        )
        logger.warning(
            "lifecycle hook %s failed at %s (%s); continuing %s",
            executor.name,
            ctx.POINT,
            error,
            "and refusing — the hook is required"
            if executor.required and "proceed" in ctx.decisions()
            else "unchanged by it",
        )
        eventlog.emit(
            "hooks.failed",
            level="warning",
            point=ctx.POINT,
            hook=executor.name,
            error=error,
            required=executor.required,
            work_item=ctx.work_item.ref or None,
        )
        if executor.required and "proceed" in ctx.decisions():
            changed = ctx.apply(
                {
                    "proceed": False,
                    "reason": f"required hook {executor.name} failed: {error}",
                }
            )
            if changed:
                eventlog.emit(
                    "hooks.decided",
                    point=ctx.POINT,
                    hook=executor.name,
                    changed=list(changed),
                    work_item=ctx.work_item.ref or None,
                )
