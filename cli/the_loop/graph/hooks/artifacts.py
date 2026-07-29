"""``validate-artifacts`` — does this node's output actually exist and hold up?

The load-bearing behaviour is **aggregation**: every unmet requirement comes
back in ONE result with one message each, so the agent repairs them in a single
round instead of discovering them one at a time across three turns (R3.5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping

from ..contract import HookContext, HookResult, Message
from ..frontmatter import sections, split_front_matter
from ..registry import hook

NAME = "validate-artifacts"


def _artifact_paths(ctx: HookContext) -> List[Path]:
    produces = ctx.node.get("produces") or []
    if isinstance(produces, (str, Path)):
        produces = [produces]
    return [ctx.work_item.spec_dir / str(p) for p in produces]


@hook(NAME)
def validate_artifacts(ctx: HookContext) -> HookResult:
    params: Mapping[str, Any] = ctx.params or {}
    findings: List[Message] = []

    paths = _artifact_paths(ctx)
    if not paths:
        return HookResult.skipped(NAME, "this node declares no artifacts")

    # An *optional* node that produced nothing was simply not entered. The
    # workflow reference is explicit that brainstorming is optional — "a work
    # item whose scope is already clear starts directly at
    # requirements-definition" — so a missing artifact there is a skip, not a
    # finding. Once the artifact exists, every gate applies normally.
    if ctx.node.get("optional") and not any(p.is_file() for p in paths):
        return HookResult.skipped(NAME, "optional node; no artifact was produced")

    for path in paths:
        rel = (
            str(path.relative_to(ctx.repo))
            if path.is_relative_to(ctx.repo)
            else str(path)
        )
        if not path.is_file():
            findings.append(Message(text="required artifact is missing", path=rel))
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Message(text=f"artifact could not be read: {exc}", path=rel)
            )
            continue

        front, body = split_front_matter(text)

        if params.get("locked"):
            status = str(front.get("status", "")).strip()
            if status != "approved":
                findings.append(
                    Message(
                        text=(
                            "artifact is not locked — front-matter says "
                            f"status: {status or '(unset)'}, expected status: approved"
                        ),
                        path=rel,
                    )
                )

        for key, expected in (params.get("frontMatter") or {}).items():
            actual = front.get(key)
            if str(actual) != str(expected):
                findings.append(
                    Message(
                        text=(
                            f"front-matter {key}: expected {expected!r}, "
                            f"found {actual!r}"
                        ),
                        path=rel,
                    )
                )

        found = sections(body)
        for wanted in params.get("sections") or []:
            match = next((h for h in found if h.strip() == str(wanted).strip()), None)
            if match is None:
                findings.append(
                    Message(text=f"required section is missing: {wanted}", path=rel)
                )
            elif not found[match].strip():
                findings.append(
                    Message(text=f"required section is empty: {wanted}", path=rel)
                )

        if params.get("checkmarks") == "complete" and "- [ ]" in body:
            outstanding = body.count("- [ ]")
            findings.append(
                Message(
                    text=f"{outstanding} task(s) still unticked",
                    path=rel,
                )
            )

    if findings:
        return HookResult.blocked(NAME, findings)
    return HookResult.ok(NAME, artifacts=[str(p) for p in paths])


@hook("enforces-boundaries-from")
def enforces_boundaries_from(ctx: HookContext) -> HookResult:
    """Every trust boundary named upstream must be answered downstream.

    A cheap structural check with real value: it is exactly the "design.md
    silently drops a boundary requirements.md raised" failure that the-loop's
    own security gate is meant to catch, and which prose alone never caught.
    """
    name = "enforces-boundaries-from"
    upstream = ctx.params.get("upstream")
    if not upstream:
        return HookResult.skipped(name, "no upstream artifact declared")
    up = ctx.work_item.spec_dir / str(upstream)
    downs = _artifact_paths(ctx)
    if not up.is_file() or not downs:
        return HookResult.skipped(name, "upstream or downstream artifact absent")

    up_body = split_front_matter(up.read_text(encoding="utf-8"))[1].lower()
    down_body = "\n".join(
        split_front_matter(d.read_text(encoding="utf-8"))[1]
        for d in downs
        if d.is_file()
    ).lower()

    missing = [
        marker
        for marker in (ctx.params.get("markers") or [])
        if str(marker).lower() in up_body and str(marker).lower() not in down_body
    ]
    if missing:
        return HookResult.blocked(
            name,
            [
                Message(text=f"boundary named upstream is unanswered here: {m}")
                for m in missing
            ],
        )
    return HookResult.ok(name)
