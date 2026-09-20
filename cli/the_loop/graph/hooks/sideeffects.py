"""Side-effecting hooks — labels, review requests, notifications, publishing.

All ordinary hooks, so what the-loop ships and what could later be added are the
same kind of thing. Each is best-effort by contract: a Slack outage or a GitHub
hiccup records and continues rather than wedging the graph (R6.12) — except
where the hook *is* the transition.
"""

from __future__ import annotations

import logging
from typing import List

from ...authz import mark_self_authored
from ..contract import HookContext, HookResult
from ..integrations import IntegrationError
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

#: The namespace of the phase labels the loop writes on a ticket. A constant since
#: issue-352: it was the harness config's ``workflow.phaseLabelPrefix``, a key the
#: CLI no longer reads — and one label vocabulary across every repository is what
#: lets a dashboard built on ``loop:<phase>`` work everywhere (issue-73).
PHASE_LABEL_PREFIX = "loop:"

__all__ = [
    "PHASE_LABEL_PREFIX",
    "notify",
    "publish_artifact",
    "request_review",
    "set_phase_label",
]


def _integration(ctx: HookContext, target: str):
    """The provider, resolved at call time.

    Imported inside the function for the reason ``selection.py`` spells out: a
    module-level ``from ..integrations import resolve`` binds the name *here*, so
    the seam every other caller and every test patches
    (``the_loop.graph.integrations.resolve``) silently did not apply to this
    module — which is how a test of ``set-phase-label`` reached the real GitHub
    API instead of its fake (issue-194).
    """
    from ..integrations import resolve

    return resolve(target, ctx.config)


@hook("set-phase-label")
def set_phase_label(ctx: HookContext) -> HookResult:
    """Keep the ticket's phase label in sync (R5.5, R9.2).

    A node without a `phase` declares no label, and creates none — labels stay
    coarse while work-item state carries the fine detail.
    """
    name = "set-phase-label"
    phase = str(ctx.node.get("phase") or "")
    if not phase:
        return HookResult.skipped(name, "node declares no phase label")
    label = f"{PHASE_LABEL_PREFIX}{phase}"
    github = _integration(ctx, "github")
    # issue-393 B10: the phase label is documented as THE position marker, and
    # every dashboard query assumes one `loop:*` label per item — but the add was
    # add-only, so the labels piled up and a board showed the item in every
    # column. Remove any other `loop:*` label first (best-effort: a failure to
    # tidy an old label must never block setting the new one, which is the fact
    # a reader actually needs).
    removed = _remove_stale_phase_labels(github, ctx.work_item.ref, label)
    try:
        github.call("set-labels", ref=ctx.work_item.ref, labels=[label])
    except IntegrationError as exc:
        # issue-393 F3/R13.2: a repository the daemon works may never have been
        # `/the-loop:init`-ed, so the `loop:*` label does not exist and the edit
        # fails ("not found"). Rather than degrade silently — the phase label is
        # the one thing a ticket reader and the dashboards use — create the label
        # and retry once. Any other failure (permissions, outage) still degrades.
        if not _is_missing_label(exc):
            logger.warning("could not sync %s: %s", label, exc)
            return HookResult.ok(
                name, label=label, applied=False, error=str(exc), removed=removed
            )
        try:
            github.call("create-label", ref=ctx.work_item.ref, name=label)
            github.call("set-labels", ref=ctx.work_item.ref, labels=[label])
        except IntegrationError as retry_exc:
            logger.warning("could not create/sync %s: %s", label, retry_exc)
            return HookResult.ok(
                name,
                label=label,
                applied=False,
                error=str(retry_exc),
                created=False,
                removed=removed,
            )
        return HookResult.ok(
            name, label=label, applied=True, created=True, removed=removed
        )
    return HookResult.ok(name, label=label, applied=True, removed=removed)


def _remove_stale_phase_labels(github, ref: str, keep: str) -> List[str]:
    """Remove every ``loop:*`` label on ``ref`` except ``keep`` — the B10 fix.

    Best-effort and never raises: reading the current labels or removing a stale
    one can fail (permissions, outage, an API that cannot list), and none of that
    should stop the new label being set — the position marker a reader needs is
    the new one being present, not the old ones being gone. Returns the labels it
    removed, for the hook's result. When the labels cannot even be read, it does
    nothing rather than guess.
    """
    try:
        current = github.call("get-labels", ref=ref).get("labels") or []
    except Exception as exc:  # noqa: BLE001 — an unreadable label set tidies nothing
        logger.debug("could not read labels on %s to tidy stale ones: %s", ref, exc)
        return []
    stale = [
        str(name_)
        for name_ in current
        if str(name_).startswith(PHASE_LABEL_PREFIX) and str(name_) != keep
    ]
    removed: List[str] = []
    for name_ in stale:
        try:
            github.call("remove-label", ref=ref, label=name_)
            removed.append(name_)
        except Exception as exc:  # noqa: BLE001 — one stale label left is not fatal
            logger.debug(
                "could not remove the stale label %s on %s: %s", name_, ref, exc
            )
    return removed


def _is_missing_label(exc: Exception) -> bool:
    """Whether an integration error is a 'label does not exist' (issue-393 R13.2).

    Both transports surface it differently — the API as a 422/'not found' on the
    label name, `gh` as its own 'not found' text — so match on the shared words
    rather than a status. Conservative: an unrecognised error is NOT treated as a
    missing label, so a permissions failure degrades rather than looping on
    create.
    """
    text = str(exc).lower()
    return (
        "not found" in text
        or "does not exist" in text
        or "label" in text
        and "422" in text
    )


@hook("request-review")
def request_review(ctx: HookContext) -> HookResult:
    """Ask for the review that this gate is waiting on.

    Posted with the-loop's self-authored marker, so the poller never reads its
    own request back as new input.
    """
    name = "request-review"
    body = mark_self_authored(
        f"🤖 _the-loop_ — **{ctx.node_id}** is ready for review.\n\n"
        f"Work item `{ctx.work_item.id}` has reached a human gate. Reply with an "
        "approval, an approval with comments, or the changes you want."
    )
    try:
        _integration(ctx, "github").call(
            "add-comment", ref=ctx.work_item.ref, body=body
        )
    except IntegrationError as exc:
        logger.warning("could not request review: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


@hook("publish-artifact")
def publish_artifact(ctx: HookContext) -> HookResult:
    """Post an artifact's content to the work item's thread — the review surface
    of a GUEST loop (issue-185, PR #187 review; re-based on the loop in issue-352).

    In the work item's own loops the artifact is checked in and reviewable in
    the repository, so this hook does nothing — the gate comment
    (``request-review``) already points at it. In a **guest** loop (a
    contribution, a review) the spec tree is excluded from git
    (``Runtime.start``), so the file exists only in the working checkout and no
    human can see it: the thread is where the plan and its verification results
    must land. Re-posting on each entry is deliberate — a gate looped back
    through ``changes-requested`` shows the *revised* artifact, and each post is
    one comment the requester asked for, not bloat.

    Best-effort by contract: an outage or a missing file (planning declared
    away) records and continues — ``validate-artifacts`` remains the gate.
    """
    name = "publish-artifact"
    if ctx.config.get("guestLoop") is not True:
        return HookResult.skipped(
            name, "the repository carries the artifact; it is reviewable there"
        )
    artifact = str(ctx.params.get("artifact") or "")
    if not artifact:
        return HookResult.skipped(name, "no artifact named")
    path = ctx.work_item.spec_dir / artifact
    if not path.is_file():
        return HookResult.skipped(name, f"no {artifact} for this work item")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("could not read %s: %s", path, exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    body = mark_self_authored(
        f"🤖 _the-loop_ — **`{artifact}`** for `{ctx.work_item.id}`.\n\n"
        "the-loop is a guest in this repository, so the artifact is working "
        "state — kept out of git — and this comment is its review "
        "surface.\n\n---\n\n" + content
    )
    # Deliberately bound at call time, not import time (the goal/selection
    # hooks' rule): the test seam and any embedder patch
    # ``graph.integrations.resolve``, and a module-level binding would slip
    # past them.
    from ..integrations import resolve

    try:
        resolve("github", ctx.config).call(
            "add-comment", ref=ctx.work_item.ref, body=body
        )
    except IntegrationError as exc:
        logger.warning("could not publish %s: %s", artifact, exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True, artifact=artifact)


def _recipients(ctx: HookContext, event: str) -> List[str]:
    """Roles for ``event`` — only what the node's own ``with:`` names.

    Until issue-352 the harness config's ``notifications.events`` supplied them;
    the CLI reads that file no more, and nothing ever resolved a role to a person
    (issue-304), so the roles are detail the graph may carry and nothing gates on.
    """
    return [str(r) for r in (ctx.params.get("roles") or [])]


#: How much of an artifact a notification carries (issue-309 R4.4). The channel
#: caps it again at its own `maxChars`; this keeps the event itself bounded.
EXCERPT_MAX_CHARS = 4_000


def _excerpt(ctx: HookContext) -> str:
    """The named artifact's body after its front matter, capped — or empty.

    A missing artifact is an empty excerpt, never a failure: the node that names
    one may have declared its authoring phase away.
    """
    artifact = str(ctx.params.get("artifact") or "")
    if not artifact:
        return ""
    from ..model import resolve_produces

    try:
        slots = resolve_produces([artifact], ctx.work_item.spec_dir)
        present = [p for slot in slots for p in slot.present]
    except Exception:  # noqa: BLE001 — a slot the model cannot resolve is no excerpt
        present = []
    path = present[0] if present else ctx.work_item.spec_dir / artifact
    if not path.is_file():
        return ""
    try:
        from ..frontmatter import split_front_matter

        _, body = split_front_matter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return ""
    body = str(body or "").strip()
    if len(body) > EXCERPT_MAX_CHARS:
        body = body[:EXCERPT_MAX_CHARS].rstrip() + "\n… (truncated)"
    return body


def _work_item_url(ref: str) -> str:
    from ...sessions import WorkItemRef

    try:
        return WorkItemRef.parse(ref).url
    except ValueError:
        return ""


def _linked_pr(ctx: HookContext):
    """The work item's newest open pull request, from its state — or ``None``
    (issue-393 B7/O8). Read best-effort: a state that will not load just means
    the PR-review message falls back to the work item, exactly as before.
    """
    try:
        from ..state import WorkItemState

        state = WorkItemState.load(ctx.work_item.spec_dir, ctx.work_item.id)
    except Exception:  # noqa: BLE001 — a missing/corrupt state names no PR
        return None
    prs = [pr for pr in getattr(state, "pull_requests", []) if pr.state == "open"]
    if not prs:
        prs = list(getattr(state, "pull_requests", []))
    return prs[-1] if prs else None


@hook("notify")
def notify(ctx: HookContext) -> HookResult:
    """Publish the node's notification event. Never wedges the graph if a
    channel is down.

    One event on the **bus** (issue-309, decision-103): the graph's notification
    is one more event, and whether it goes anywhere is each channel's
    ``subscribe`` list — so an operator subscribes their Slack channel to
    ``phase-approval-pending`` and friends, and the reply path those channels
    carry works for notifications too. The event carries the work item's URL
    and, when the node names an ``artifact``, an excerpt of it (R4.4), so a
    ``quiet`` channel finally gets the link its contract promised and a
    ``normal`` one sees what it is approving.

    Roles a node names in its ``with:`` ride along as detail; they never gate
    the hook — nothing ever resolved a role to a person (issue-304), and the
    subscription is the channel's decision now.
    """
    name = "notify"
    event = str(ctx.params.get("event") or "phase-approval-pending")
    roles = _recipients(ctx, event)
    detail = {"node": ctx.node_id}
    url = _work_item_url(ctx.work_item.ref)
    # issue-393 B7/O8: the PR-review gate names the pull request — number, link —
    # and points at IT, not the issue. Before this the message read "…is at
    # *human-approval*" with an Open button that went to the issue, and a
    # reviewer on a phone had to find the PR themselves.
    pr = _linked_pr(ctx) if event == "pr-review-pending" else None
    if pr is not None:
        text = (
            f"👀 PR #{pr.number} is ready for review. "
            f"Start there, then approve or request changes."
        )
        if pr.url:
            url = pr.url
        detail["pullRequest"] = str(pr.number)
    else:
        text = f"the-loop: {ctx.work_item.id} is at *{ctx.node_id}* ({event})."
    if roles:
        text += f" Roles: {', '.join(roles)}"
    if roles:
        detail["roles"] = ", ".join(roles)
    excerpt = _excerpt(ctx)
    if excerpt:
        detail["excerpt"] = excerpt
        detail["artifact"] = str(ctx.params.get("artifact") or "")
    # Call-time import, the `_integration` rule: the test seam and any embedder
    # patch the channels module, and a module-level binding would slip past them.
    from ...channels.base import Event
    from ...channels.bus import publish

    result = publish(
        Event(
            event_type=event,
            work_item=ctx.work_item.ref,
            text=text,
            url=url,
            detail=detail,
            source="loop",
        ),
        cli_config=ctx.config,
    )
    if not result.posts:
        return HookResult.skipped(
            name,
            f"no channel subscribed to {event} — add it to the channel's "
            "`subscribe` list (channels.<name>.subscribe)",
        )
    errors = "; ".join(post.error for post in result.posts if not post.ok)
    if not result.delivered:
        logger.warning("notification not delivered: %s", errors)
        return HookResult.ok(name, delivered=False, roles=roles, error=errors)
    return HookResult.ok(name, delivered=True, roles=roles)
