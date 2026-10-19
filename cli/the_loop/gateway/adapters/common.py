"""What every adapter shares: the reference a payload names, and its dedup key
(issue-496, R2.3, R5.1, R5.2, R5.8, R5.10, R7.3).

**Only the direct reference.** :func:`resolve_ref` reads the issue or pull-request
number, the Jira key or the Slack thread the payload itself names, then the bindings
instances have published and the rooms and repositories declared in
``gateway-config.yaml`` — and nothing else (R5.2). The closing-keyword and branch-name
linkage that ties a pull request to its ticket stays the instance's router's: the
instance that receives the PR event publishes the binding (R5.8), and the gateway only
follows it from then on.

**Bytes in, fields out.** The adapter hands a parsed JSON object; this module reads a
handful of fields with ``.get()`` chains and type checks and never renders payload text
(§Security design).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from ...sessions import WorkItemRef
from ..config import GatewayConfig
from ..envelope import UNASSIGNED, subject_for_slug
from ..store import Store

__all__ = [
    "Resolved",
    "Unbound",
    "actor_of",
    "dedup_key",
    "resolve_ref",
    "slack_thread_key",
    "slug_of",
]


class Unbound(ValueError):
    """The event concerns an object bound to no work item that cannot start one
    (R5.10): the gateway drops it and records ``gateway.dropped: unbound``.
    ``reason`` is ``unbound`` or ``undeclared-repository``."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


@dataclass(frozen=True)
class Resolved:
    """Where an event goes: its subject, the work item when known, the other subjects
    it also concerns (a PR's linked ticket), and — when it has no work item yet — the
    key a later binding will match (``held_key``)."""

    subject: str
    work_item: Optional[str]
    linked: Tuple[str, ...] = ()
    held_key: str = ""

    @property
    def startable(self) -> bool:
        return self.work_item is not None or bool(self.held_key)


def slug_of(ref: str) -> str:
    return WorkItemRef.parse(ref).slug


def _subject(ref: str) -> str:
    return subject_for_slug(slug_of(ref))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


# -- GitHub -----------------------------------------------------------------------------------

_ISSUE_EVENTS = ("issues", "issue_comment")
_PR_EVENTS = (
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "pull_request_target",
)
_CI_EVENTS = ("check_run", "check_suite", "workflow_run", "status")


def _github_repo(payload: Mapping[str, Any]) -> str:
    return _text(_mapping(payload.get("repository")).get("full_name"))


def _declared(repo: str, config: GatewayConfig) -> bool:
    return repo.lower() in {r.lower() for r in config.repositories}


def _github_ref(repo: str, number: int) -> str:
    return f"github:{repo}#{number}"


def _pr_numbers(payload: Mapping[str, Any], kind: str) -> List[int]:
    obj = _mapping(payload.get(kind))
    numbers: List[int] = []
    for pr in obj.get("pull_requests") or []:
        number = _int(_mapping(pr).get("number"))
        if number is not None:
            numbers.append(number)
    return numbers


def _resolve_github(
    kind: str, payload: Mapping[str, Any], store: Store, config: GatewayConfig
) -> Resolved:
    repo = _github_repo(payload)
    if not repo:
        raise Unbound("unbound", "no repository in the payload")
    if not _declared(repo, config):
        raise Unbound("undeclared-repository", repo)
    if kind in _ISSUE_EVENTS:
        issue = _mapping(payload.get("issue"))
        number = _int(issue.get("number"))
        if number is None:
            raise Unbound("unbound", f"{kind} names no issue number")
        ref = _github_ref(repo, number)
        resolved = Resolved(subject=_subject(ref), work_item=ref)
        # a comment on a pull request arrives as issue_comment with a `pull_request` key:
        # the PR's own subject plus the ticket it is bound to, when known
        if "pull_request" in issue:
            return _with_linked_ticket(resolved, repo, number, store)
        return resolved
    if kind in _PR_EVENTS:
        number = _int(_mapping(payload.get("pull_request")).get("number"))
        if number is None:
            raise Unbound("unbound", f"{kind} names no pull request number")
        ref = _github_ref(repo, number)
        return _with_linked_ticket(
            Resolved(subject=_subject(ref), work_item=ref), repo, number, store
        )
    if kind in _CI_EVENTS:
        numbers = _pr_numbers(payload, kind)
        if kind == "workflow_run":
            numbers = _pr_numbers(payload, "workflow_run")
        if numbers:
            ref = _github_ref(repo, numbers[0])
            return _with_linked_ticket(
                Resolved(subject=_subject(ref), work_item=ref), repo, numbers[0], store
            )
        sha = (
            _text(payload.get("sha"))
            or _text(_mapping(_mapping(payload.get(kind)).get("head_commit")).get("id"))
            or _text(_mapping(payload.get(kind)).get("head_sha"))
        )
        if sha:
            bound = store.resolve_slug("github", f"{repo}@{sha}")
            if bound:
                ref, slug = bound
                return Resolved(subject=subject_for_slug(slug), work_item=ref)
        raise Unbound("unbound", f"{kind} names no pull request")
    raise Unbound("unbound", f"unhandled GitHub event {kind}")


def _with_linked_ticket(
    resolved: Resolved, repo: str, number: int, store: Store
) -> Resolved:
    """A PR's subject plus the ticket subject its binding names (R5.4)."""
    bound = store.resolve_slug("github", f"{repo}#{number}")
    if bound is None:
        return resolved
    _ref, slug = bound
    linked = subject_for_slug(slug)
    if linked == resolved.subject:
        return resolved
    return Resolved(
        subject=resolved.subject,
        work_item=resolved.work_item,
        linked=(linked,),
        held_key=resolved.held_key,
    )


# -- Jira -------------------------------------------------------------------------------------


def _jira_site(payload: Mapping[str, Any], config: GatewayConfig) -> str:
    if config.jira is not None and config.jira.poll.site:
        return config.jira.poll.site
    self_url = _text(_mapping(payload.get("issue")).get("self"))
    if "://" in self_url:
        return self_url.split("://", 1)[1].split("/", 1)[0]
    return ""


def _resolve_jira(
    kind: str, payload: Mapping[str, Any], store: Store, config: GatewayConfig
) -> Resolved:
    key = _text(_mapping(payload.get("issue")).get("key"))
    if not key or "-" not in key:
        raise Unbound("unbound", f"{kind} names no issue key")
    project = key.rsplit("-", 1)[0]
    declared = {p.upper() for p in (config.jira.projects if config.jira else ())}
    if project.upper() not in declared:
        raise Unbound("unbound", f"project {project} is not mapped")
    site = _jira_site(payload, config)
    if not site:
        raise Unbound("unbound", "no Jira site for the key")
    ref = f"jira:{site}/{key}"
    return Resolved(subject=_subject(ref), work_item=ref)


# -- Slack ------------------------------------------------------------------------------------


def slack_thread_key(channel: str, thread_ts: str) -> str:
    return f"{channel}:{thread_ts}"


def _slack_location(kind: str, payload: Mapping[str, Any]) -> Tuple[str, str]:
    """``(channel, thread_ts)`` of a Socket Mode / HTTP payload, by envelope type."""
    if kind == "events_api":
        event = _mapping(payload.get("event"))
        channel = _text(event.get("channel")) or _text(event.get("channel_id"))
        thread = _text(event.get("thread_ts")) or _text(event.get("ts"))
        return channel, thread
    if kind == "interactive":
        container = _mapping(payload.get("container"))
        channel = _text(container.get("channel_id")) or _text(
            _mapping(payload.get("channel")).get("id")
        )
        thread = _text(container.get("thread_ts")) or _text(container.get("message_ts"))
        return channel, thread
    if kind == "slash_commands":
        return _text(payload.get("channel_id")), ""
    return "", ""


def _resolve_slack(
    kind: str, payload: Mapping[str, Any], store: Store, config: GatewayConfig
) -> Resolved:
    channel, thread = _slack_location(kind, payload)
    if channel and thread:
        bound = store.resolve_slug("slack", slack_thread_key(channel, thread))
        if bound:
            ref, slug = bound
            return Resolved(subject=subject_for_slug(slug), work_item=ref)
    rooms = {
        r.channel: r.work_item for r in (config.slack.rooms if config.slack else ())
    }
    if channel in rooms:
        ref = rooms[channel]
        return Resolved(subject=_subject(ref), work_item=ref)
    if channel and thread:
        # a thread nobody bound yet in a channel the instance may still know: hold it
        # under the thread key, so the instance's binding routes it (R5.7)
        return Resolved(
            subject=UNASSIGNED,
            work_item=None,
            held_key=slack_thread_key(channel, thread),
        )
    raise Unbound("unbound", "no thread, no room")


# -- the public pair -----------------------------------------------------------------------------


def resolve_ref(
    provider: str,
    kind: str,
    payload: Any,
    store: Store,
    config: GatewayConfig,
) -> Resolved:
    """The subject (and work item, linked subjects, held key) a delivery concerns.

    Raises :class:`Unbound` when the object can start no work item (R5.10). A GitHub
    pull request the gateway has no binding for resolves to the PR's **own** subject —
    the instance that receives it recognises the linkage and publishes the binding
    (R5.8) — and a Slack thread nobody bound yet is held under its thread key.
    """
    if not isinstance(payload, Mapping):
        raise Unbound("invalid-payload", "the payload is not a JSON object")
    if provider == "github":
        return _resolve_github(kind, payload, store, config)
    if provider == "jira":
        return _resolve_jira(kind, payload, store, config)
    if provider == "slack":
        return _resolve_slack(kind, payload, store, config)
    raise Unbound("unbound", f"unknown provider {provider}")


def actor_of(provider: str, kind: str, payload: Any) -> Optional[str]:
    """Who caused the event, for actor routing (R5.5): the GitHub login, the Slack user
    id, the Jira account id. ``None`` when the payload names nobody."""
    if not isinstance(payload, Mapping):
        return None
    if provider == "github":
        for path in (
            ("comment", "user", "login"),
            ("review", "user", "login"),
            ("sender", "login"),
            ("issue", "user", "login"),
            ("pull_request", "user", "login"),
        ):
            node: Any = payload
            for step in path:
                node = _mapping(node).get(step)
            if isinstance(node, str) and node:
                return node
        return None
    if provider == "jira":
        for path in (("comment", "author", "accountId"), ("user", "accountId")):
            node = payload
            for step in path:
                node = _mapping(node).get(step)
            if isinstance(node, str) and node:
                return node
        return None
    if provider == "slack":
        if kind == "events_api":
            return _text(_mapping(payload.get("event")).get("user")) or None
        user = _mapping(payload.get("user"))
        return _text(user.get("id")) or _text(payload.get("user_id")) or None
    return None


def dedup_key(provider: str, kind: str, payload: Any, delivery_id: str) -> str:
    """The key that makes two transports' copies of one event one row (R7.3).

    GitHub: a comment by its id, an issue/PR action by object and ``updated_at``, CI by
    ref, name and conclusion, a closure by ref and state — the same whether it came by
    webhook or by poll. Jira: ``jira-comment-<site>-<id>``, already shared by both Jira
    paths. Slack: ``slack-<event_id>`` from the HTTP body and the same id from the
    Socket Mode envelope. Anything else: the provider's delivery id.
    """
    body = payload if isinstance(payload, Mapping) else {}
    if delivery_id.startswith("poll-presence-"):
        # a presence offer is re-made on purpose (a fresh uuid each cycle) until an
        # instance judges it; it never collides with a webhook's one-off `labeled`
        return f"{provider}:{delivery_id}"
    if provider == "github":
        repo = _github_repo(body)
        action = _text(body.get("action"))
        if kind in ("issue_comment", "pull_request_review_comment"):
            comment = _mapping(body.get("comment"))
            comment_id = _int(comment.get("id"))
            if comment_id is not None:
                if action in ("", "created"):
                    # the one key a webhook and a poll of the same comment share
                    return f"gh-comment-{comment_id}"
                # an edit (the attestation tick) or a deletion is its own event
                # (critic C2); keyed on the action and the edit time
                return f"gh-comment-{comment_id}-{action}-{_text(comment.get('updated_at'))}"
        if kind == "pull_request_review":
            review = _mapping(body.get("review"))
            review_id = _int(review.get("id"))
            if review_id is not None:
                if action in ("", "submitted"):
                    return f"gh-review-{review_id}"
                return f"gh-review-{review_id}-{action}-{_text(review.get('submitted_at'))}"
        if kind in ("issues", "pull_request"):
            obj = _mapping(body.get("issue" if kind == "issues" else "pull_request"))
            number = _int(obj.get("number"))
            action = _text(body.get("action"))
            if number is not None:
                if action == "closed":
                    # a closure keys on its time: close → reopen → close is two events
                    when = _text(obj.get("closed_at")) or _text(obj.get("updated_at"))
                    return f"gh-close-{repo}#{number}-{when or 'closed'}"
                # the object named by the action joins the key: two labels added in one
                # UI action share `updated_at` and are two events (self-review R2)
                qualifier = ""
                if action in ("labeled", "unlabeled"):
                    qualifier = _text(_mapping(body.get("label")).get("name"))
                elif action in ("assigned", "unassigned"):
                    qualifier = _text(_mapping(body.get("assignee")).get("login"))
                elif action in ("review_requested", "review_request_removed"):
                    qualifier = _text(
                        _mapping(body.get("requested_reviewer")).get("login")
                    ) or _text(_mapping(body.get("requested_team")).get("slug"))
                tail = f"{qualifier}-" if qualifier else ""
                return (
                    f"gh-{kind}-{action}-{repo}#{number}-{tail}"
                    f"{_text(obj.get('updated_at'))}"
                )
        if kind in _CI_EVENTS:
            obj = _mapping(body.get(kind))
            name = _text(obj.get("name")) or _text(body.get("context"))
            conclusion = _text(obj.get("conclusion")) or _text(body.get("state"))
            sha = _text(obj.get("head_sha")) or _text(body.get("sha"))
            if sha and (name or conclusion):
                return f"gh-ci-{repo}@{sha}-{name}-{conclusion}"
        return f"github:{delivery_id}"
    if provider == "jira":
        comment_id = _text(_mapping(body.get("comment")).get("id")) or str(
            _int(_mapping(body.get("comment")).get("id")) or ""
        )
        if comment_id:
            site = (
                _text(_mapping(body.get("issue")).get("self"))
                .split("://")[-1]
                .split("/")[0]
            )
            return f"jira-comment-{site}-{comment_id}"
        return f"jira:{delivery_id}"
    if provider == "slack":
        event_id = _text(body.get("event_id"))
        if event_id:
            return f"slack-{event_id}"
        trigger = _text(body.get("trigger_id"))
        if trigger:
            return f"slack-trigger-{trigger}"
        return f"slack:{delivery_id}"
    return f"{provider}:{delivery_id}"
