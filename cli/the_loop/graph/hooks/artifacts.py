"""``validate-artifacts`` — does this node's output actually exist and hold up?

The load-bearing behaviour is **aggregation**: every unmet requirement comes
back in ONE result with one message each, so the agent repairs them in a single
round instead of discovering them one at a time across three turns (R3.5).

A node's ``produces`` names an **artifact**, not a file: one entry may accept
several names (``requirements.md|bugfix.md``), because a bug's phase-1 spec is
called ``bugfix.md`` and always has been (issue-124, decision-045). Resolution
lives in :mod:`the_loop.graph.model`; what lives here is the *policy* — what to
do when none of the accepted names is present, and what to do when more than one
is.

Some nodes gate an artifact they did **not** author. The six nodes between
``implementation`` and ``complete`` each own one section of the *shared*
``execution-log.md``, so ``produces`` — which means "this node wrote it" — has
nothing to say about them. They declare ``validates:`` instead (issue-167,
decision-063), and a gate that declares content checks but resolves no artifact
at all now **blocks**: those six nodes previously reported ``skipped`` on every
run, and since a skip is not a decision (decision-060) the chain passed straight
through them — including the ``required: true`` security review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping

from ..contract import HookContext, HookResult, Message
from ..frontmatter import sections, split_front_matter
from ..model import ArtifactSlot, artifact_names, resolve_produces
from ..registry import hook

NAME = "validate-artifacts"

#: The params that make this hook an assertion rather than a no-op. If any of
#: them is declared, the hook has something to check and therefore needs
#: something to check it against.
_CHECKS = ("locked", "frontMatter", "sections", "checkmarks")


def _slots(ctx: HookContext) -> List[ArtifactSlot]:
    return resolve_produces(ctx.node.get("produces"), ctx.work_item.spec_dir)


def _validated(ctx: HookContext) -> List[ArtifactSlot]:
    """Artifacts this hook *asserts against*, which the node did not author.

    Same resolver as ``produces``, deliberately: alternation, presence and the
    ambiguity policy are then identical for both, and cannot drift apart the way
    two private copies of the resolver did before issue-124.
    """
    return resolve_produces((ctx.params or {}).get("validates"), ctx.work_item.spec_dir)


def _rel(ctx: HookContext, path: Path) -> str:
    return (
        str(path.relative_to(ctx.repo)) if path.is_relative_to(ctx.repo) else str(path)
    )


@hook(NAME)
def validate_artifacts(ctx: HookContext) -> HookResult:
    params: Mapping[str, Any] = ctx.params or {}
    findings: List[Message] = []

    produced = _slots(ctx)
    slots = produced + _validated(ctx)
    if not slots:
        # Fail closed. A gate that declares sections and resolves no file to
        # look for them in reports success without ever running — the shape
        # decision-045 named, and the shape six of this graph's own nodes shipped
        # in (issue-167). Not retriable: re-running the node cannot repair a
        # graph-authoring fault, and pretending it might would burn maxAttempts
        # before anyone was told.
        if any(params.get(check) for check in _CHECKS):
            return HookResult.blocked(
                NAME,
                [
                    Message(
                        text=(
                            "this node gates on artifact content but names no "
                            "artifact to read it from — the graph must declare "
                            "`produces:` on the node or `validates:` on this hook "
                            "entry"
                        ),
                        path=_rel(ctx, ctx.work_item.spec_dir),
                    )
                ],
                retriable=False,
            )
        return HookResult.skipped(NAME, "this node declares no artifacts")

    # An *optional* node that produced nothing was simply not entered. The
    # workflow reference is explicit that brainstorming is optional — "a work
    # item whose scope is already clear starts directly at
    # requirements-definition" — so a missing artifact there is a skip, not a
    # finding. Once the artifact exists, every gate applies normally.
    #
    # Judged on what the node *authored* when it declares any: a shared artifact
    # it merely validates says nothing about whether this node ran, and the
    # execution log exists for every work item.
    entered = produced or slots
    if ctx.node.get("optional") and not any(slot.present for slot in entered):
        return HookResult.skipped(NAME, "optional node; no artifact was produced")

    paths: List[Path] = []
    covered_absent = 0
    for slot in slots:
        present = list(slot.present)
        if not present:
            # A planned absence is not a finding (issue-177): when EVERY name
            # this slot accepts is authored by a node the work item's declared
            # skips removed, the artifact was never going to exist — e.g.
            # `implementation` re-gating `tasks.md` after `tasks-breakdown`
            # was declared skipped. Only absence is tolerated: a present
            # artifact is gated normally a few lines down, declarations or not.
            if slot.names and all(name in ctx.skipped_artifacts for name in slot.names):
                covered_absent += 1
                continue
            # Name every accepted name: an agent cannot write the right file if
            # the block does not say what the right file may be called.
            if slot.alternatives:
                findings.append(
                    Message(
                        text=f"required artifact is missing — write one of: {slot.label()}",
                        path=_rel(ctx, ctx.work_item.spec_dir),
                    )
                )
            else:
                findings.append(
                    Message(
                        text="required artifact is missing",
                        path=_rel(ctx, slot.candidates[0]),
                    )
                )
            continue

        if len(present) > 1:
            # Fail closed. Two artifacts filling one slot have no defined source
            # of truth, and a resolver that quietly preferred the first-declared
            # name would approve the gate against whichever the graph happened to
            # list first — which could be the stale one.
            findings.append(
                Message(
                    text=(
                        f"{len(present)} artifacts present where one is expected "
                        f"— keep one of: {slot.label()}"
                    ),
                    path=_rel(ctx, ctx.work_item.spec_dir),
                )
            )
            continue

        paths.append(present[0])

    for path in paths:
        rel = _rel(ctx, path)

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
    if covered_absent and not paths:
        # Everything this gate would read was authored by declared-skipped
        # nodes and none of it exists — the hook has nothing to assert against,
        # and says so rather than minting a pass (a skip is not a decision).
        return HookResult.skipped(
            NAME, "artifact(s) authored by a declared-skipped node; absence is planned"
        )
    return HookResult.ok(NAME, artifacts=[str(p) for p in paths])


@hook("enforces-boundaries-from")
def enforces_boundaries_from(ctx: HookContext) -> HookResult:
    """Every trust boundary named upstream must be answered downstream.

    A cheap structural check with real value: it is exactly the "design.md
    silently drops a boundary requirements.md raised" failure that the-loop's
    own security gate is meant to catch, and which prose alone never caught.

    ``upstream`` accepts the same alternation as ``produces``, and it must: it
    named ``requirements.md`` literally until issue-124, so for every *bug* work
    item the upstream resolved to nothing, the hook took its "absent" branch, and
    a skip passed the chain. The gate reported success without ever running —
    which is worse than the missing-artifact block that made the same mismatch
    visible one node earlier.

    When several accepted names are present their bodies are **joined** rather
    than one being chosen: a boundary raised in either file still has to be
    answered downstream, and this hook never has to make the choice
    ``validate-artifacts`` deliberately refuses to make.
    """
    name = "enforces-boundaries-from"
    upstream = ctx.params.get("upstream")
    if not upstream:
        return HookResult.skipped(name, "no upstream artifact declared")
    ups = [
        p
        for p in (ctx.work_item.spec_dir / n for n in artifact_names(upstream))
        if p.is_file()
    ]
    # Gate on what the node *declares*, and read what is *present*. A declared but
    # missing downstream artifact leaves `down_body` empty, so every upstream
    # marker reads as unanswered and blocks — which is what this hook did before
    # alternation, and the direction to keep. (In the shipped graph the earlier
    # `validate-artifacts` in the same chain blocks first, so this branch is a
    # floor rather than a path anything reaches.)
    slots = _slots(ctx)
    downs = [p for slot in slots for p in slot.present]
    if not ups or not slots:
        return HookResult.skipped(name, "upstream or downstream artifact absent")

    up_body = "\n".join(
        split_front_matter(u.read_text(encoding="utf-8"))[1] for u in ups
    ).lower()
    down_body = "\n".join(
        split_front_matter(d.read_text(encoding="utf-8"))[1] for d in downs
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
