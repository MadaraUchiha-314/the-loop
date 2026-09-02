"""The brief gate — the review loop's own first phase (issue-279).

**No brief, no review.** When the-loop is asked to review a pull request,
"the-loop review" alone never cuts it: a review that does not know what the
reviewer cares about answers nothing. The `review-brief` node is
`required: true` in `pdlc-review-loop` — the structural mirror of the
contribution loop's `goal-definition` (issue-185): the loop cannot begin
without a named, authorized human stating the brief.

The expected shape, anywhere in one comment (the arming `the-loop review`
comment itself qualifies) — at least one content section with at least one
bullet, drop the sections you don't need::

    Questions:
    - does the retry change alter the public client API?
    Angles:
    - concurrency around the session registry
    Validations:
    - run the poller integration suite against this branch
    Pull requests:
    - github:o/r#12

`Pull requests:` is the **work-item** review's scope section (the owner's
ruling on PR #280): armed on a work item rather than a pull request, one
review conversation spans every pull request delivering the item, the
template asks which those are, and the-loop pre-fills the ones it can detect
— its own ``pr-loops/`` state first, then the provider's linked pull
requests. Stated entries are normalized to ``github:owner/repo#n`` refs and
anything unparseable is dropped: the frozen list is composed by the-loop,
never free text.

Two rules, inherited from `feedback.py` and load-bearing here exactly as they
are at every other human gate:

* **Only authorized authors' text is read at all** — and the-loop's own
  self-marked comments are dropped before authorization is even considered, so
  the harness cannot brief its own review. Fail closed: an empty
  ``authorizedUsers`` accepts no brief, ever.
* **The reply produces a fact, never a destination.** The parsed brief is
  frozen into graph state as a decision with provenance (the same mechanism
  that freezes the contribution goal) and echoed in a confirmation comment;
  the routing stays with the graph's one declared ``briefed`` edge. An
  injected "brief" cannot choose phases, name paths, or reach an argv — the
  session runs its ``Validations:`` under its ordinary untrusted-content
  rules, exactly as it reads the diff itself.

The gate reads the event's comments **and** re-reads the whole thread, for the
same reason ``classify-goal`` does: the comment most likely to carry the brief
— the arming comment — is consumed by the control path and never forwarded as
an event, so thread state is the only place it can be found.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...authz import is_self_authored, mark_self_authored
from ..contract import HookContext, HookResult
from ..registry import hook
from .feedback import _authorized_comments
from .goal import _resolve, _thread_comments

logger = logging.getLogger("the-loop.graph")

#: The marker the entry hook leaves in its own template comment, so the posting
#: is idempotent across redelivered spawns.
BRIEF_REQUEST_MARKER = "<!-- the-loop:review-brief-request -->"

#: Where the answered-ness of this gate is recorded in ``GraphState.decisions``.
DECISION_KEY = "review-brief"

#: The three content sections a brief may carry, in the order the issue names
#: them: the questions the reviewer has, the angles they are interested in,
#: the validations they want run.
SECTIONS = ("questions", "angles", "validations")

#: The scope section a **work-item** review adds (the owner's ruling on
#: PR #280): which pull requests the review spans. Scope, not content — a PR
#: list alone is not a brief.
PULLS_SECTION = "pullRequests"

#: A section marker line — `Questions:` / `Angles:` / `Validations:` /
#: `Pull requests:` (`PRs:` accepted), with the same bold/heading decoration
#: tolerance the goal gate's markers have.
_SECTION_LINE = re.compile(
    r"^\s*(?:[#>*_\s]*)(?P<section>questions|angles|validations"
    r"|pull\s+requests|prs)"
    r"(?:\*\*|__)?\s*:?\s*(?:\*\*|__)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _section_key(marker: str) -> str:
    """The dict key a matched section marker selects."""
    name = re.sub(r"\s+", " ", marker.lower())
    return PULLS_SECTION if name in ("pull requests", "prs") else name


#: One brief bullet — plain or checkboxed, checkbox state ignored.
_BULLET_LINE = re.compile(r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?(?P<text>\S.*?)\s*$")

#: A template placeholder bullet (`- <what you want answered …>`), so the
#: posted template itself — quoted back, or filled only partially — never
#: parses as a brief through its own examples.
_PLACEHOLDER = re.compile(r"^<.*>$")


def _bullets(body: str, start: int) -> List[str]:
    """The bullet list following ``start``, stopping at the first non-bullet."""
    items: List[str] = []
    for line in body[start:].splitlines():
        if not line.strip():
            if items:
                break  # the list ended; a later paragraph is not a bullet
            continue
        item = _BULLET_LINE.match(line)
        if item is None:
            break
        text = item.group("text")
        if not _PLACEHOLDER.match(text):
            items.append(text)
    return items


def parse_brief(body: str) -> Optional[Dict[str, List[str]]]:
    """The brief's sections out of one comment — or ``None``.

    ``{"questions": […], "angles": […], "validations": […],
    "pullRequests": […]}``. At least one of the three **content** sections
    must carry at least one bullet; a reviewer states only what they need and
    the empty sections come back as empty lists. ``pullRequests`` is scope,
    not content (a PR list alone is not a brief), and its bullets are raw
    here — :func:`_normalize_pulls` turns them into refs where the work
    item's own repository is known. Pure and side-effect free, so the
    accepted shape is testable without a thread.
    """
    text = str(body or "")
    found: Dict[str, List[str]] = {s: [] for s in (*SECTIONS, PULLS_SECTION)}
    matched = False
    for marker in _SECTION_LINE.finditer(text):
        matched = True
        section = _section_key(marker.group("section"))
        found[section] = _bullets(text, marker.end()) or found[section]
    if not matched or not any(found[section] for section in SECTIONS):
        return None
    return found


#: The shapes a stated pull request may take: a full URL, an owner/repo#n
#: slug, or a bare number (the work item's own repository). Anything else is
#: dropped — the frozen list is a fact rendered back into comments and
#: prompts, so it holds refs the-loop composed, never free text.
#: A pull request stated by URL keeps the URL's host (issue-311, R3.1): a
#: reviewer on GitHub Enterprise pastes an enterprise link, and the ref frozen
#: from it must name that GitHub, not github.com.
_PULL_URL = re.compile(
    r"https?://(?P<host>[^/\s]+)/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pull/(?P<n>\d+)"
)
#: A slug may carry a host the way a ref does (`github:ghe.corp/o/r#7`), which
#: is what the-loop's own detected refs look like on GitHub Enterprise; a bare
#: `o/r#7` is on the work item's host.
_PULL_SLUG = re.compile(
    r"^(?:github:)?(?:(?P<host>[^/\s#]+)/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)"
    r"#(?P<n>\d+)$"
)
_PULL_BARE = re.compile(r"^#?(?P<n>\d+)$")


def _own_coords(ref: str) -> tuple[str, str, str]:
    """``github:[host/]owner/repo#9`` → ``(host, owner, repo)`` — or three ``""``.

    The host is ``""`` for github.com, so a ref spelled from it leaves the
    default unwritten (issue-311).
    """
    from ...sessions import DEFAULT_GITHUB_HOST, WorkItemRef

    try:
        parsed = WorkItemRef.parse(ref)
    except ValueError:
        return "", "", ""
    host = "" if parsed.host == DEFAULT_GITHUB_HOST else parsed.host
    return host, parsed.owner, parsed.repo


def _pull_ref(host: str, owner: str, repo: str, number: str) -> str:
    """One spelling for every ref this module composes — or ``""``.

    Through ``WorkItemRef`` so the host is written exactly when it is not the
    default and a host that is not a host (a pasted URL on some other service)
    yields nothing rather than a ref pointing somewhere else.
    """
    from ...sessions import DEFAULT_GITHUB_HOST, WorkItemRef, is_github_host

    if host and host != DEFAULT_GITHUB_HOST and not is_github_host(host):
        return ""
    try:
        return WorkItemRef(
            provider="github", owner=owner, repo=repo, number=int(number), host=host
        ).ref
    except ValueError:
        return ""


def _normalize_pulls(items: List[str], work_item_ref: str) -> List[str]:
    """Stated/detected pull requests as ``github:[host/]owner/repo#n`` refs, deduped.

    A URL keeps its own host; a slug or a bare number is on the **work item's**
    host — the ticket's GitHub is the default for everything named beside it
    (issue-311, R3.2).
    """
    own_host, owner, repo = _own_coords(work_item_ref)
    refs: List[str] = []
    for item in items:
        text = str(item or "").strip().rstrip(".,;")
        url = _PULL_URL.search(text)
        slug = _PULL_SLUG.match(text)
        bare = _PULL_BARE.match(text)
        if url:
            ref = _pull_ref(
                url.group("host"), url.group("owner"), url.group("repo"), url.group("n")
            )
        elif slug:
            ref = _pull_ref(
                slug.group("host") or own_host,
                slug.group("owner"),
                slug.group("repo"),
                slug.group("n"),
            )
        elif bare and owner:
            ref = _pull_ref(own_host, owner, repo, bare.group("n"))
        else:
            continue
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _latest_brief(ctx: HookContext) -> Optional[Dict[str, Any]]:
    """The most recent authorized brief — event comments included.

    Thread order first, then the event's own comments (which are newer than
    any fetched snapshot); the last parseable statement wins, so a reviewer
    can restate the brief and the restatement is what freezes. The stated
    pull requests are normalized to refs here, where the work item is known.
    """
    found: Optional[Dict[str, Any]] = None
    for comment in _thread_comments(ctx) + _authorized_comments(ctx):
        parsed = parse_brief(comment["body"])
        if parsed is not None:
            found = {**parsed, "by": f"@{str(comment['author']).lstrip('@')}"}
    if found is not None:
        found[PULLS_SECTION] = _normalize_pulls(
            found.get(PULLS_SECTION) or [], ctx.work_item.ref
        )
    return found


def _thread_kind(ctx: HookContext) -> str:
    """``"pull-request"`` / ``"issue"`` — or ``""`` when GitHub cannot say.

    Unknown falls back to the pull-request wording (the issue's primary
    case): a review that asks one section too few is a smaller failure than a
    gate that cannot post its template at all.
    """
    try:
        data = _resolve(ctx).call("get-thread", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001 — best-effort, wording only
        logger.debug("could not resolve the thread kind: %s", exc)
        return ""
    kind = str((data or {}).get("kind") or "")
    return kind if kind in ("pull-request", "issue") else ""


def _state_pulls(ctx: HookContext) -> List[str]:
    """The pull requests the-loop's own state links to this work item.

    The ``pr-loops/`` tree beside the outer graph state (issue-172/183) — the
    JSON the loop generates for every PR that walked an inner loop, and the
    owner's "piggyback on that" (PR #280). Two layouts: ``pr-<n>/`` for the
    work item's own repository, ``<owner>__<repo>/pr-<n>/`` for a
    contributing one.
    """
    own_host, own_owner, own_repo = _own_coords(ctx.work_item.ref)
    root = Path(ctx.work_item.spec_dir) / "pr-loops"
    refs: List[str] = []
    try:
        entries = sorted(root.iterdir()) if root.is_dir() else []
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        if name.startswith("pr-") and name[3:].isdigit() and own_owner:
            refs.append(_pull_ref(own_host, own_owner, own_repo, name[3:]))
            continue
        if "__" not in name or not entry.is_dir():
            continue
        owner, _, repo = name.partition("__")
        try:
            inner = sorted(entry.iterdir())
        except OSError:
            continue
        for pr_dir in inner:
            pr_name = pr_dir.name
            if pr_name.startswith("pr-") and pr_name[3:].isdigit():
                # A contributing repository inherits the work item's host: the
                # state directory names owner and repo, never a host.
                refs.append(_pull_ref(own_host, owner, repo, pr_name[3:]))
    return [ref for ref in refs if ref]


def _detected_pulls(ctx: HookContext) -> List[str]:
    """Best-effort suggestions for a work-item review's PR scope.

    the-loop's own state first (authoritative for an item the loop
    delivered), then the work item's linked pull requests from the provider
    (`linked-pulls` — the "Development" panel's links), deduped in that
    order. Empty on any failure: a suggestion is never worth wedging the
    template post.
    """
    refs = _state_pulls(ctx)
    try:
        data = _resolve(ctx).call("linked-pulls", ref=ctx.work_item.ref)
        linked = [str(p) for p in (data or {}).get("pulls") or []]
    except Exception as exc:  # noqa: BLE001 — best-effort, suggestions only
        logger.debug("could not list linked pull requests: %s", exc)
        linked = []
    return _normalize_pulls(refs + linked, ctx.work_item.ref)


def _request_body(ctx: HookContext) -> str:
    """The fill-in template — worded for what is being reviewed.

    A **work item** review (the owner's ruling on PR #280) differs from a
    pull-request review in exactly one asked-for way: the template also asks
    which pull requests the review spans — pre-filled with the ones the-loop
    could detect (its own ``pr-loops/`` state, then the provider's links), so
    the reviewer edits a list rather than reconstructing one. One review, one
    session, however many pull requests deliver the item.
    """
    work_item_review = _thread_kind(ctx) == "issue"
    detected = _detected_pulls(ctx) if work_item_review else []
    subject = "work item" if work_item_review else "thread"
    lines = [
        "🤖 _the-loop_ — **what should this review look at?**",
        "",
        f"the-loop was asked to review this {subject}. It will not start "
        "until an authorized user states the review's brief — in one comment, "
        "in this shape (keep the sections you need, drop the rest; at least "
        "one bullet in at least one of Questions/Angles/Validations):",
        "",
        "```",
        "Questions:",
        "- <what you want answered about this change>",
        "Angles:",
        "- <the perspectives to review from — correctness, security, "
        "performance, API shape, …>",
        "Validations:",
        "- <what to run or prove — commands, scenarios, invariants>",
    ]
    if work_item_review:
        lines.append("Pull requests:")
        if detected:
            lines += [f"- {ref}" for ref in detected]
        else:
            lines.append("- <the pull requests delivering this work item>")
    lines += [
        "```",
        "",
        "The brief becomes the review's contract: it is frozen with your name "
        "on it, every question gets an answer, every angle gets examined, and "
        "every validation gets run (or a stated reason it could not be). "
        "Follow-ups are welcome after each round; the review ends when you say "
        "it is done. If your `the-loop review` comment already contained this "
        "block, nothing more is needed.",
    ]
    if work_item_review:
        detected_line = (
            "the-loop pre-filled `Pull requests:` with the ones it detected — "
            "from its own state and the work item's linked pull requests — "
            "edit that list if it is wrong. "
        )
        lines += [
            "",
            "This is a **work-item** review: one review conversation across "
            "every pull request delivering the item. "
            + (
                detected_line
                if detected
                else "the-loop could not detect any linked pull requests, so "
                "please list them under `Pull requests:` (a `#number`, an "
                "`owner/repo#number`, or a URL per bullet). "
            )
            + "A review with no pull requests reviews the work item itself.",
        ]
    lines += ["", BRIEF_REQUEST_MARKER]
    return mark_self_authored("\n".join(lines))


def _already_requested(ctx: HookContext) -> bool:
    """Whether the-loop's own template comment is already on the thread.

    Only a **self-authored** comment counts (security review, issue-279): the
    idempotence marker is public text, so without the check any commenter —
    authorized or not — could paste it and suppress the template ever being
    posted. Cosmetic, since the gate never proceeds without an authorized
    brief, but a gate that can be quietly muted is a gate that confuses its
    humans.
    """
    try:
        data = _resolve(ctx).call("list-comments", ref=ctx.work_item.ref)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not list comments for %s: %s", ctx.work_item.ref, exc)
        return False
    return any(
        isinstance(c, dict)
        and BRIEF_REQUEST_MARKER in str(c.get("body") or "")
        and is_self_authored(str(c.get("body") or ""))
        for c in (data.get("comments") or [])
    )


@hook("post-review-brief")
def post_review_brief(ctx: HookContext) -> HookResult:
    """Ask the thread for a brief (entry hook) — unless one is already there.

    Best-effort like every outbound hook: a GitHub outage must not wedge the
    review at its first node with no way to answer. The gate stays waiting
    either way, and a later entry re-posts.
    """
    name = "post-review-brief"
    if _latest_brief(ctx) is not None:
        # The fast path: the brief rode in with the arming comment, so asking
        # again would be noise on the thread under review.
        return HookResult.ok(name, posted=False, reason="brief already stated")
    if _already_requested(ctx):
        return HookResult.ok(name, posted=False, reason="already asked")
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_request_body(ctx)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the review-brief request: %s", exc)
        return HookResult.ok(name, posted=False, error=str(exc))
    return HookResult.ok(name, posted=True)


def _confirmation(brief: Dict[str, Any]) -> str:
    lines = [
        "🤖 _the-loop_ — **review brief recorded**",
        "",
        f"Reviewing against, as stated by {brief['by']}:",
        "",
    ]
    titles = {
        "questions": "Questions",
        "angles": "Angles",
        "validations": "Validations",
        PULLS_SECTION: "Pull requests in scope",
    }
    for section in (*SECTIONS, PULLS_SECTION):
        items = brief.get(section) or []
        if not items:
            continue
        lines.append(f"> **{titles[section]}:**")
        lines += [f"> - {item}" for item in items]
        lines.append(">")
    if lines[-1] == ">":
        lines.pop()
    lines += [
        "",
        "This brief is now the review's contract. the-loop reviews the change "
        "against it and posts its findings here; reply with follow-ups for "
        "another round, or say the review is done to end it.",
    ]
    return mark_self_authored("\n".join(lines))


@hook("classify-review-brief")
def classify_review_brief(ctx: HookContext) -> HookResult:
    """Read the authorized brief; freeze it and release the gate — or wait.

    The returned brief is a *fact* the runtime records with provenance under
    ``decisions["review-brief"]``; the outcome (``briefed``) is what the
    graph's one declared edge routes on.
    """
    name = "classify-review-brief"
    if (ctx.decisions or {}).get(DECISION_KEY):
        # Already answered. Re-asking would make `the-loop check` report every
        # review item as stuck at its first node forever.
        return HookResult(
            status="pass",
            hook=name,
            data={"outcome": "briefed", "decision": DECISION_KEY},
        )
    brief = _latest_brief(ctx)
    if brief is None:
        return HookResult.waiting(
            name,
            "waiting for an authorized user to state the review brief "
            "(`Questions:` / `Angles:` / `Validations:` bullet lists — at "
            "least one section, in one comment)",
        )
    try:
        _resolve(ctx).call(
            "add-comment", ref=ctx.work_item.ref, body=_confirmation(brief)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not post the brief confirmation: %s", exc)
    return HookResult(
        status="pass",
        hook=name,
        data={"outcome": "briefed", "decision": DECISION_KEY, "brief": brief},
    )
