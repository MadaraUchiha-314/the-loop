"""The coding harness's GitHub verbs — comment, ticket, pull request (issue-447).

After issue-442 no process of the-loop's spawned ``gh``, but the **agent** in its
session still did: to read its ticket, to post a spec-gate reply or the reviewer
briefing, to open, inspect and merge its pull request, to create a ticket. Every
session therefore needed a ``gh`` login or a token of its own. These operations
move those acts onto :class:`~the_loop.ghapi.GitHubClient`, behind the same
seams every other core verb has: the CLI, a control-plane route and an MCP tool
all call the functions here.

Three properties every function keeps:

* **Data out, words as data.** Each returns a dict carrying ``exitCode`` and
  ``messages`` beside its fields, and prints nothing — the same call serves the
  terminal, HTTP and MCP (the ``core.sessions`` convention).
* **A caller mistake is a** :class:`ValueError` (exit 2, HTTP 400), raised
  before any request. **GitHub's refusal is a result** — ``exitCode: 1`` and
  the client's message (the status plus GitHub's text, never the token).
* **The policy is the executing process's.** ``pr merge`` reads
  ``routing.mergeOnApproval`` from the config it is handed — the service's when
  the verb was routed there — so a session cannot bring a policy of its own.

Spec: docs/specs/issue-447/design.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .. import eventlog
from ..authz import mark_self_authored
from ..cli_config import merge_on_approval
from ..comments import create_issue, post_issue_comment_with_url, resolve_client
from ..ghapi import (
    CLOSE_REASONS,
    MERGE_METHODS,
    GitHubApiConfig,
    GitHubApiError,
    GitHubClient,
    is_branch_name,
)
from ..sessions import DEFAULT_GITHUB_HOST, is_github_host, is_github_name
from ..workitem import WorkItemRef
from . import sessions as core_sessions

logger = logging.getLogger("the-loop.github_ops")

__all__ = [
    "checks_rollup",
    "close_ticket",
    "comment",
    "create_pull_request",
    "create_ticket",
    "discover_pull_requests",
    "merge_pull_request",
    "pull_request_status",
    "pull_request_threads",
    "resolve_pull_request",
    "resolve_thread",
    "show_ticket",
]

#: A pull request's browser URL: ``https://<host>/<owner>/<repo>/pull/<n>``.
_PR_URL_RE = re.compile(
    r"^https?://(?P<host>[A-Za-z0-9.-]+(?::\d+)?)/(?P<owner>[A-Za-z0-9._-]+)/"
    r"(?P<repo>[A-Za-z0-9._-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$"
)

#: Check-run conclusions that fail a pull request's checks.
_FAILED_CONCLUSIONS = ("failure", "cancelled", "timed_out", "action_required")

#: Commit-status states that fail them.
_FAILED_STATES = ("failure", "error")


# ------------------------------------------------------------------ plumbing


def _api(config: Optional[Mapping[str, Any]]) -> GitHubApiConfig:
    return GitHubApiConfig.from_cli_config(dict(config or {}))


def _client(
    config: Optional[Mapping[str, Any]], client: Optional[GitHubClient]
) -> GitHubClient:
    return resolve_client(_api(config), client, 30.0)


def _host(ref: WorkItemRef) -> str:
    """The client's spelling of the ref's host: ``""`` for github.com."""
    return "" if ref.host in ("", DEFAULT_GITHUB_HOST) else ref.host


def _github_ref(ref: str) -> WorkItemRef:
    item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if item.provider != "github":
        raise ValueError(f"{item.ref} is not a GitHub work item")
    return item


def trusted_hosts(config: Optional[Mapping[str, Any]]) -> List[str]:
    """The GitHub hosts a verb may address: github.com and the operator's own.

    The operator's host is :func:`~the_loop.ghhost.github_host` — the configured
    ``integrations.github.host``, an enterprise ``baseUrl``'s host, ``$GH_HOST``.
    Nothing a caller names can add to it (issue-447 A3): a token sent to
    ``https://<any host>/api/v3`` would be a token handed to whoever runs it.
    """
    from ..ghhost import github_host

    hosts = [DEFAULT_GITHUB_HOST]
    own = github_host(dict(config or {}))
    if own and own not in hosts:
        hosts.append(own)
    return hosts


def _trusted(ref: WorkItemRef, config: Optional[Mapping[str, Any]]) -> WorkItemRef:
    """``ref``, if its host is one the operator trusts; else a caller mistake."""
    hosts = trusted_hosts(config)
    if ref.host.lower() not in [h.lower() for h in hosts]:
        raise ValueError(
            f"{ref.ref} is on {ref.host}, which is not a GitHub host this "
            f"instance is configured for ({', '.join(hosts)}); set "
            "integrations.github.host to use it"
        )
    return ref


def _registry(config: Optional[Mapping[str, Any]], registry_dir: str):
    from ..sessions.registry import SessionRegistry

    return SessionRegistry(
        core_sessions._registry_dir(dict(config or {}), registry_dir)
    )


def _is_adhoc(item: WorkItemRef, config: Optional[Mapping[str, Any]]) -> bool:
    """Whether ``item`` was armed as an ad-hoc task (`the-loop do`, issue-225)."""
    from ..graph.model import LOOP_FOR_CONTROL_COMMAND, PDLC_ADHOC_LOOP

    try:
        record = core_sessions._control_store(dict(config or {})).get(item)
    except Exception:  # noqa: BLE001 — an unreadable record grants nothing
        return False
    return bool(
        record and LOOP_FOR_CONTROL_COMMAND.get(record.command) == PDLC_ADHOC_LOOP
    )


def _accepted_here(item: WorkItemRef, config: Optional[Mapping[str, Any]]) -> bool:
    """Whether this instance accepted ``item`` and the item has not ended (issue-453).

    The second source of ownership beside the session registry. A work item
    `the-loop sessions start` accepts and parks at its first human gate has a
    control record and no session (issue-358); the record is what the instance
    wrote when it took the item, so it is what says the item is the instance's.
    Three conditions, each failing closed: the record exists and reads; its
    ``instance`` is this instance's name **as the config declares it** (an
    unnamed instance owns unnamed records only — a planted record cannot name
    itself in); and the portable record is not stamped ``ended``, because the
    daemon forgets an ended item's arming and so does this.
    """
    try:
        store = core_sessions._control_store(dict(config or {}))
        record = store.get(item)
        if record is None:
            return False
        if record.instance != core_sessions._instance(dict(config or {})).name:
            return False
        return store.ended(item) is None
    except Exception:  # noqa: BLE001 — an unreadable record grants nothing
        return False


def _authority(
    target: WorkItemRef,
    work_item: str,
    config: Optional[Mapping[str, Any]],
    registry_dir: str,
) -> str:
    """``""`` when this instance may act on ``target``; else why it may not.

    The owner's rule for every lifecycle act on a pull request or ticket
    (merge, close, resolve a thread, open a PR): it happens for a work item
    **registered on this instance** — ``target`` is one, or is a pull request
    recorded as delivering a live one. The one exception is an ad-hoc task
    (`the-loop do`): a registered work item armed with `do` may act on a pull
    request it names, because a tactical task is exactly "merge that PR". The
    registry is the executing process's, like the merge policy, so a routed
    verb answers to the daemon's records.

    Registered means **accepted**, not only session-backed (issue-453,
    decision-141): a work item this instance armed and parked at its first
    human gate has a control record and no session yet, and it is this
    instance's from the record on. That source reaches ``target`` itself only
    — a parked item has recorded no pull request.
    """
    registry = _registry(config, registry_dir)
    if registry.find_by_work_item(target) is not None:
        return ""
    for record in registry.list_sessions():
        if record.is_live and record.owns(target):
            return ""
    if _accepted_here(target, config):
        return ""
    if work_item:
        try:
            item = _github_ref(work_item)
        except ValueError:
            item = None
        if (
            item is not None
            and registry.find_by_work_item(item) is not None
            and _is_adhoc(item, config)
        ):
            return ""
    return (
        f"{target.ref} is not a work item registered on this instance, nor a pull "
        "request recorded against one — register the session (`the-loop sessions "
        "register`) and record the pull request (`the-loop sessions link-pr`), or "
        "act from an ad-hoc `the-loop do` work item named with --work-item"
    )


def _failed(data: Dict[str, Any], text: str) -> Dict[str, Any]:
    data.update(exitCode=1, messages=[{"stream": "err", "text": f"error: {text}"}])
    return data


def _done(data: Dict[str, Any], *lines: str) -> Dict[str, Any]:
    data.update(
        exitCode=0, messages=[{"stream": "out", "text": line} for line in lines if line]
    )
    return data


def _text(value: Any, what: str) -> str:
    text = str(value or "")
    if not text.strip():
        raise ValueError(f"the {what} is empty")
    return text


def _repository(value: str, default: WorkItemRef) -> WorkItemRef:
    """``[host/]owner/repo`` as a ref on ``default``'s number, or ``default``.

    ``""`` is the default's own repository. A host is accepted only in the shape
    a ref's host takes (A3), and a repository without one inherits the
    default's — a contributing repository lives on the work item's GitHub.
    """
    text = (value or "").strip()
    if not text:
        return default
    parts = text.split("/")
    if len(parts) == 3:
        host, owner, repo = parts
        if not is_github_host(host):
            raise ValueError(f"repository {text!r} does not name a host")
    elif len(parts) == 2:
        host, (owner, repo) = default.host, parts
    else:
        raise ValueError(f"repository {text!r} is not [host/]owner/repo")
    try:
        return WorkItemRef.parse(f"github:{host}/{owner}/{repo}#{default.number}")
    except ValueError:
        raise ValueError(f"repository {text!r} is not [host/]owner/repo") from None


def _slug(value: str) -> str:
    """``[host/]owner/repo``, validated before it reaches a request (A3)."""
    text = (value or "").strip()
    parts = text.split("/")
    if len(parts) not in (2, 3) or not all(parts):
        raise ValueError(f"repository {text!r} is not [host/]owner/repo")
    if len(parts) == 3 and not is_github_host(parts[0]):
        raise ValueError(f"repository {text!r} does not name a host")
    if not (is_github_name(parts[-2]) and is_github_name(parts[-1])):
        raise ValueError(f"repository {text!r} is not [host/]owner/repo")
    return text


def resolve_pull_request(pr: str, work_item: str = "") -> WorkItemRef:
    """A pull-request argument as a ref (R1.9).

    A ref, a pull-request URL, or a bare number resolved against ``work_item``'s
    repository — the grammar ``sessions link-pr`` already accepts, plus the URL a
    person pastes. Anything else is a :class:`ValueError`.
    """
    text = (pr or "").strip()
    if not text:
        raise ValueError("name the pull request: a ref, its URL, or a number")
    match = _PR_URL_RE.match(text)
    if match is not None:
        host = match.group("host")
        if host.lower() in ("github.com", "www.github.com"):
            host = ""
        if int(match.group("number")) <= 0:
            raise ValueError(f"a pull-request number must be positive, not {text}")
        return _github_ref(
            f"github:{host + '/' if host else ''}{match.group('owner')}/"
            f"{match.group('repo')}#{match.group('number')}"
        )
    if text.lstrip("#").isdigit():
        if int(text.lstrip("#")) <= 0:
            raise ValueError(f"a pull-request number must be positive, not {text}")
        if not work_item:
            raise ValueError(
                f"a bare pull-request number ({text}) needs --work-item to say "
                "which repository it is in"
            )
        return core_sessions.pull_request_ref(_github_ref(work_item), text)
    resolved = _github_ref(text)
    if resolved.number <= 0:
        raise ValueError(f"a pull-request number must be positive, not {text}")
    return resolved


# ------------------------------------------------------------------ comment


def comment(
    ref: str,
    body: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Post the agent's comment on its work item, marked and enveloped (R1.1).

    The comment is a ``comment.agent`` event published on the bus with
    ``record=True``: the GitHub ledger writes it (the self-authored marker and
    the envelope stamped centrally — A4, never agent memory), then every
    channel subscribed to the agent's comments gets it. The ingress drops an
    enveloped comment, so nothing re-publishes it. A bus fault falls back to
    posting the marked body directly: the ticket is the record either way.
    """
    item = _trusted(_github_ref(ref), config)
    text = _text(body, "comment")
    cli_config = dict(config or {})
    api = _api(cli_config)
    from ..channels.base import Event
    from ..channels.bus import publish as bus_publish
    from ..channels.github import GitHubLedger

    ledger = GitHubLedger(
        cli_config,
        post_comment=lambda target, posted, api=None: post_issue_comment_with_url(
            target, posted, api=_api(cli_config), client=client
        ),
    )
    ok, error, url, channels_posted = False, "", "", 0
    try:
        published = bus_publish(
            Event(
                event_type="comment.agent",
                work_item=item.ref,
                text=text,
                detail={"actor": core_sessions._local_actor()},
                source="cli",
            ),
            cli_config,
            ledger=ledger,
            record=True,
        )
        record = published.record
        ok = bool(record and record.ok)
        error = (record.error if record else "") or ""
        url = (record.url if record else "") or ""
        channels_posted = sum(1 for posted in published.posts if posted.ok)
    except Exception as exc:  # noqa: BLE001 — a channel bug never loses the comment
        logger.warning("channel broadcast failed: %s", exc)
        ok, error, url = post_issue_comment_with_url(
            item, mark_self_authored(text), api=api, client=client
        )
    eventlog.emit(
        "work_item.commented",
        level="info" if ok else "warning",
        work_item=item.ref,
        comment_url=url or None,
        comment_posted=ok,
        channels_posted=channels_posted,
    )
    data: Dict[str, Any] = {
        "workItem": item.ref,
        "url": url,
        "posted": ok,
        "channelsPosted": channels_posted,
    }
    if not ok:
        return _failed(data, f"could not comment on {item.ref}: {error}")
    return _done(data, f"commented on {item.ref}" + (f" — {url}" if url else ""))


# ------------------------------------------------------------------ tickets


def show_ticket(
    ref: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """The ticket as the agent reads it at session start (R1.2).

    Body, comments on every surface a pull request has, and the attachment
    links in them — links only; nothing is fetched (A7). The text is the
    ticket's, and the skill treats it as data, never as instructions.
    """
    item = _trusted(_github_ref(ref), config)
    gh = _client(config, client)
    host = _host(item)
    data: Dict[str, Any] = {"ref": item.ref}
    try:
        doc = gh.get_issue(item.owner, item.repo, item.number, host=host)
        is_pr = isinstance(doc.get("pull_request"), Mapping)
        comments = gh.list_comments(item.owner, item.repo, item.number, is_pr, host)
    except GitHubApiError as exc:
        return _failed(data, f"could not read {item.ref}: {exc}")
    from ..channels.attachments import github_attachment_urls

    hosts = [] if not host else [host]
    body = str(doc.get("body") or "")
    attachments: List[str] = []
    for text in [body] + [c.body for c in comments]:
        for url in github_attachment_urls(text, hosts=hosts):
            if url not in attachments:
                attachments.append(url)
    data.update(
        number=int(doc.get("number") or item.number),
        title=str(doc.get("title") or ""),
        body=body,
        state=str(doc.get("state") or ""),
        isPullRequest=is_pr,
        labels=[
            str(label.get("name"))
            for label in doc.get("labels") or []
            if isinstance(label, Mapping) and label.get("name")
        ],
        author=str((doc.get("user") or {}).get("login") or ""),
        url=str(doc.get("html_url") or item.url),
        comments=[
            {
                "id": c.id,
                "kind": c.kind,
                "author": c.author,
                "body": c.body,
                "createdAt": c.created_at,
                "url": c.url,
                **({"state": c.state} if c.state else {}),
                **({"path": c.path, "line": c.line} if c.path else {}),
            }
            for c in comments
        ],
        attachments=attachments,
    )
    return _done(data)


def create_ticket(
    repository: str,
    title: str,
    body: str,
    labels: Sequence[str] = (),
    config: Optional[Mapping[str, Any]] = None,
    *,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Open an issue — ``/the-loop:create-ticket``'s act (R1.3).

    Through :func:`~the_loop.comments.create_issue`, the writer the ledger's
    kickoff and the self-diagnosis report already use. The body is the agent's
    own and is posted as written: an issue body is the request itself, not a
    comment the ingress would read back.
    """
    title = _text(title, "title")
    target = _slug(repository)
    if target.count("/") == 2:
        _trusted(_github_ref(f"github:{target}#1"), config)
    ok, error, ref, url = create_issue(
        target,
        title,
        str(body or ""),
        [str(label) for label in labels],
        api=_api(config),
        client=client,
    )
    data: Dict[str, Any] = {"ref": ref, "url": url}
    if not ok:
        return _failed(data, f"could not open the ticket: {error}")
    return _done(data, f"opened {ref}" + (f" — {url}" if url else ""))


# ------------------------------------------------------------------ pull requests


def create_pull_request(
    ref: str,
    title: str,
    body: str,
    head: str,
    base: str = "",
    repository: str = "",
    draft: bool = False,
    config: Optional[Mapping[str, Any]] = None,
    *,
    registry_dir: str = "",
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Open the pull request and link it to the work item in one act (R1.4).

    ``head`` is resolved by the caller — the CLI reads the checkout's branch,
    because the service's working directory is not the checkout. ``base``
    defaults to the repository's default branch, ``repository`` to the work
    item's. The work item must be registered on this instance (R1.10): a pull
    request the-loop opens belongs to a work item it tracks. A link that still
    fails after the PR opened is a note, not a failure: the pull request exists,
    and saying otherwise would invite a second one (R1.5).
    """
    item = _trusted(_github_ref(ref), config)
    title = _text(title, "title")
    if not is_branch_name(str(head or "").rpartition(":")[2]):
        raise ValueError(f"unusable head branch {head!r}")
    if base and not is_branch_name(base):
        raise ValueError(f"unusable base branch {base!r}")
    target = _trusted(_repository(repository, item), config)
    data: Dict[str, Any] = {"workItem": item.ref, "linked": False}
    if _registry(config, registry_dir).find_by_work_item(item) is None:
        return _failed(
            data,
            f"not opening a pull request for {item.ref}: no session is registered "
            "for it on this instance — run `the-loop sessions register` first",
        )
    gh = _client(config, client)
    host = _host(target)
    try:
        if not base:
            base = str(
                gh.repository(target.owner, target.repo, host=host).get(
                    "default_branch"
                )
                or ""
            )
            if not base:
                return _failed(
                    data,
                    f"{target.path} has no default branch to target; pass --base",
                )
        number, url = gh.create_pull(
            target.owner,
            target.repo,
            title,
            str(body or ""),
            head,
            base,
            draft=draft,
            host=host,
        )
    except GitHubApiError as exc:
        return _failed(data, f"could not open the pull request: {exc}")
    # The repository's own spelling, as GitHub returned it: the ref keys the
    # registry, and a caller's lower-cased --repository must not become the key.
    pr = _pull_ref({"number": number, "html_url": url}, target)
    data.update(pullRequest=pr.ref, url=url, base=base, head=head)
    eventlog.emit(
        "work_item.pr_opened", work_item=item.ref, pull_request=pr.ref, url=url or None
    )
    lines = [f"opened {pr.ref}" + (f" — {url}" if url else "")]
    try:
        link = core_sessions.link_pull_request(
            item.ref, pr.ref, config=dict(config or {}), registry_dir=registry_dir
        )
    except Exception as exc:  # noqa: BLE001 — the PR exists; linking is bookkeeping
        link = {"exitCode": 1, "messages": [{"stream": "err", "text": str(exc)}]}
    data["linked"] = link.get("exitCode") == 0
    messages = [{"stream": "out", "text": line} for line in lines]
    for message in link.get("messages") or []:
        text = str(message.get("text") or "")
        if data["linked"]:
            messages.append({"stream": "out", "text": text})
        else:
            messages.append(
                {"stream": "err", "text": f"note: {pr.ref} is not linked: {text}"}
            )
    data.update(exitCode=0, messages=messages)
    return data


def checks_rollup(
    runs: Iterable[Mapping[str, Any]], statuses: Iterable[Mapping[str, Any]]
) -> Dict[str, Any]:
    """One verdict over a commit's check runs and commit statuses (R1.6).

    ``failure`` if anything failed, else ``pending`` if anything is still
    running, else ``success`` — and ``none`` when the commit carries no check
    at all, which is not the same as green.
    """
    failing: List[str] = []
    pending: List[str] = []
    total = 0
    for run in runs:
        total += 1
        name = str(run.get("name") or "")
        if str(run.get("status") or "") != "completed":
            pending.append(name)
        elif str(run.get("conclusion") or "") in _FAILED_CONCLUSIONS:
            failing.append(name)
    for status in statuses:
        total += 1
        name = str(status.get("context") or "")
        state = str(status.get("state") or "")
        if state in _FAILED_STATES:
            failing.append(name)
        elif state == "pending":
            pending.append(name)
    if failing:
        conclusion = "failure"
    elif pending:
        conclusion = "pending"
    elif total:
        conclusion = "success"
    else:
        conclusion = "none"
    return {
        "conclusion": conclusion,
        "total": total,
        "failing": failing,
        "pending": pending,
    }


def pull_request_status(
    pr: str,
    work_item: str = "",
    config: Optional[Mapping[str, Any]] = None,
    *,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """State, mergeability and one checks verdict — three requests (R1.6)."""
    target = _trusted(resolve_pull_request(pr, work_item), config)
    gh = _client(config, client)
    host = _host(target)
    data: Dict[str, Any] = {"pullRequest": target.ref}
    try:
        doc = gh.get_pull(target.owner, target.repo, target.number, host=host)
        sha = str((doc.get("head") or {}).get("sha") or "")
        runs, statuses = (
            gh.commit_checks(target.owner, target.repo, sha, host=host)
            if sha
            else ([], [])
        )
    except GitHubApiError as exc:
        return _failed(data, f"could not read {target.ref}: {exc}")
    mergeable = doc.get("mergeable")
    data.update(
        url=str(doc.get("html_url") or ""),
        state=str(doc.get("state") or ""),
        merged=bool(doc.get("merged")),
        mergeable=mergeable if isinstance(mergeable, bool) else None,
        mergeableState=str(doc.get("mergeable_state") or ""),
        draft=bool(doc.get("draft")),
        headSha=sha,
        checks=checks_rollup(runs, statuses),
    )
    return _done(data)


def pull_request_threads(
    pr: str,
    work_item: str = "",
    include_resolved: bool = False,
    config: Optional[Mapping[str, Any]] = None,
    *,
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """The review threads still open on a pull request (R1.7)."""
    target = _trusted(resolve_pull_request(pr, work_item), config)
    gh = _client(config, client)
    data: Dict[str, Any] = {"pullRequest": target.ref}
    try:
        threads = gh.review_threads(
            target.owner, target.repo, target.number, host=_host(target)
        )
    except GitHubApiError as exc:
        return _failed(data, f"could not read the threads of {target.ref}: {exc}")
    data["threads"] = [t for t in threads if include_resolved or not t["isResolved"]]
    return _done(data)


def merge_pull_request(
    pr: str,
    work_item: str = "",
    method: str = "merge",
    config: Optional[Mapping[str, Any]] = None,
    *,
    sha: str = "",
    registry_dir: str = "",
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Merge the pull request — only where the operator's policy says so (R1.8),
    and only for a registered work item (R1.10, :func:`_authority`).

    ``sha`` pins the head the caller reviewed: a commit pushed after the review
    makes GitHub refuse the merge rather than ship unreviewed code.

    ``routing.mergeOnApproval: false`` means a person merges; the verb then
    refuses and merges nothing (A2). The knob is read from ``config`` — the
    executing process's, never an argument — and GitHub itself still enforces
    branch protection and required reviews.
    """
    target = _trusted(resolve_pull_request(pr, work_item), config)
    if method not in MERGE_METHODS:
        raise ValueError(
            f"unknown merge method {method!r}; expected one of "
            + ", ".join(MERGE_METHODS)
        )
    if sha and not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
        raise ValueError(f"unusable head sha {sha!r}")
    data: Dict[str, Any] = {"pullRequest": target.ref, "merged": False}
    if not merge_on_approval(config):
        eventlog.emit(
            "work_item.merge_refused",
            level="warning",
            pull_request=target.ref,
            reason="routing.mergeOnApproval is false",
        )
        return _failed(
            data,
            f"not merging {target.ref}: routing.mergeOnApproval is false in the "
            "CLI config, so a person merges this pull request",
        )
    refusal = _authority(target, work_item, config, registry_dir)
    if refusal:
        eventlog.emit(
            "work_item.merge_refused",
            level="warning",
            pull_request=target.ref,
            reason="not a registered work item",
        )
        return _failed(data, f"not merging: {refusal}")
    gh = _client(config, client)
    try:
        result = gh.merge_pull(
            target.owner,
            target.repo,
            target.number,
            method,
            host=_host(target),
            sha=sha,
        )
    except GitHubApiError as exc:
        return _failed(data, f"could not merge {target.ref}: {exc}")
    merged = bool(result.get("merged", True))
    data.update(merged=merged, sha=str(result.get("sha") or ""))
    if not merged:
        return _failed(
            data,
            f"GitHub did not merge {target.ref}: "
            + str(result.get("message") or "no reason given"),
        )
    eventlog.emit("work_item.pr_merged", pull_request=target.ref, method=method)
    return _done(data, f"merged {target.ref} ({method})")


def _pull_ref(doc: Mapping[str, Any], target: WorkItemRef) -> WorkItemRef:
    """The ref of a listed pull request, in the repository's own spelling.

    GitHub is case-insensitive about owner and repo, but a ref keys the
    registry, so the PR's own ``html_url`` wins over the coordinates the caller
    happened to type (a checkout's origin reads lower-cased).
    """
    number = int(doc.get("number") or 0)
    match = _PR_URL_RE.match(str(doc.get("html_url") or ""))
    if match is not None and int(match.group("number")) == number:
        return replace(
            target, owner=match.group("owner"), repo=match.group("repo"), number=number
        )
    return replace(target, number=number)


def discover_pull_requests(
    ref: str,
    branch: str,
    repository: str = "",
    config: Optional[Mapping[str, Any]] = None,
    *,
    head_owner: str = "",
    registry_dir: str = "",
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Link every open pull request whose head is ``branch`` (R4.1).

    A fork (R4.5): the head lives in ``<head_owner>/…`` (default: the
    repository's owner) while the pull request lives in the repository it was
    opened against — so when ``repository`` is not the work item's own, the
    work item's repository is asked for ``<head_owner>:branch`` too.

    What the ``PostToolUse`` hook runs after a push or a PR-creating tool
    (issue-447 comment): no tool output is parsed, the pull requests are asked
    of GitHub. ``repository`` is the checkout's origin (the caller resolves it)
    or the work item's. Linking is idempotent, so running this after every push
    costs a request and writes nothing new.
    """
    item = _trusted(_github_ref(ref), config)
    if not is_branch_name(branch or ""):
        raise ValueError(f"unusable branch name {branch!r}")
    target = _trusted(_repository(repository, item), config)
    # The work item's own spelling when it is the same repository.
    if (target.host, target.owner.lower(), target.repo.lower()) == (
        item.host,
        item.owner.lower(),
        item.repo.lower(),
    ):
        target = item
    owner_of_head = head_owner or target.owner
    if not is_github_name(owner_of_head):
        raise ValueError(f"unusable head owner {head_owner!r}")
    gh = _client(config, client)
    data: Dict[str, Any] = {
        "workItem": item.ref,
        "branch": branch,
        "repository": target.path,
        "found": [],
        "linked": [],
    }
    # Where to look: the named repository, and the work item's own when they
    # differ (a fork's PR is opened upstream, into the work item's repository).
    places = [target] if target == item else [target, item]
    found: List[WorkItemRef] = []
    for place in places:
        try:
            pulls = gh.open_pulls_for_head(
                place.owner,
                place.repo,
                branch,
                host=_host(place),
                head_owner=owner_of_head if owner_of_head != place.owner else "",
            )
        except GitHubApiError as exc:
            return _failed(
                data, f"could not list the pull requests of {place.path}: {exc}"
            )
        for doc in pulls:
            if isinstance(doc.get("number"), int) and doc["number"] > 0:
                pr = _pull_ref(doc, place)
                if pr.ref != item.ref and pr.ref not in [f.ref for f in found]:
                    found.append(pr)
    data["found"] = [pr.ref for pr in found]
    if not found:
        return _done(data, f"no open pull request in {target.path} has head {branch!r}")
    messages: List[Dict[str, str]] = []
    exit_code = 0
    for pr in found:
        result = core_sessions.link_pull_request(
            item.ref, pr.ref, config=dict(config or {}), registry_dir=registry_dir
        )
        if result.get("exitCode") == 0:
            if result.get("linked"):
                data["linked"].append(pr.ref)
        else:
            exit_code = max(exit_code, int(result.get("exitCode") or 1))
        messages.extend(result.get("messages") or [])
    data.update(exitCode=exit_code, messages=messages)
    return data


# ------------------------------------------------------------------ closing


def close_ticket(
    ref: str,
    reason: str = "completed",
    work_item: str = "",
    config: Optional[Mapping[str, Any]] = None,
    *,
    registry_dir: str = "",
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Close a ticket — ``/the-loop:finish-tasks``'s cleanup step (R1.11).

    Only a work item registered on this instance (or one an ad-hoc work item
    names), like every lifecycle act (:func:`_authority`). ``reason`` is
    GitHub's ``state_reason``: ``completed`` or ``not_planned``. A ticket a merge's
    ``Closes #N`` already closed closes again as a no-op.

    Closing an item this instance accepted but never launched a session for
    (issue-453) also cancels its pending start — the ``stop`` an operator used
    to have to type after closing with ``gh`` — so the daemon's spawn gate
    cannot launch it later. ``startCancelled`` says whether that happened; a
    second close finds nothing to cancel and is exit 0 all the same.
    """
    target = _trusted(_github_ref(ref), config)
    if reason not in CLOSE_REASONS:
        raise ValueError(
            f"unknown close reason {reason!r}; expected one of "
            + ", ".join(CLOSE_REASONS)
        )
    data: Dict[str, Any] = {"ref": target.ref, "closed": False}
    refusal = _authority(target, work_item, config, registry_dir)
    if refusal:
        return _failed(data, f"not closing: {refusal}")
    gh = _client(config, client)
    try:
        gh.close_issue(
            target.owner, target.repo, target.number, reason, host=_host(target)
        )
    except GitHubApiError as exc:
        return _failed(data, f"could not close {target.ref}: {exc}")
    data["closed"] = True
    eventlog.emit("work_item.ticket_closed", work_item=target.ref, reason=reason)
    lines = [f"closed {target.ref} ({reason})"]
    cancelled, note = _cancel_pending_start(target, config, registry_dir)
    data["startCancelled"] = cancelled
    if cancelled:
        lines.append(f"cancelled the pending start for {target.ref}")
    result = _done(data, *lines)
    if note:
        result["messages"].append({"stream": "err", "text": note})
    return result


def _cancel_pending_start(
    target: WorkItemRef, config: Optional[Mapping[str, Any]], registry_dir: str
) -> Tuple[bool, str]:
    """Disarm a closed work item that has no session (issue-453 R2.2).

    ``(True, "")`` when a ``stop`` was recorded; ``(False, "")`` when there was
    nothing to cancel — a live session (its closure is the daemon's, on the
    ``closed`` event) or a record that no longer requests a start; ``(False,
    <warning>)`` when the record could not be written, since the ticket is
    closed either way and ``sessions stop`` is the remedy. The record is the
    same one ``sessions stop`` writes, so the spawn gate reads it the same way.
    """
    from ..control import STOP

    actor = ""
    try:
        if _registry(config, registry_dir).find_by_work_item(target) is not None:
            return False, ""
        store = core_sessions._control_store(dict(config or {}))
        if not store.start_requested(target):
            return False, ""
        actor = core_sessions._local_actor()
        instance = core_sessions._instance(dict(config or {})).name
        store.record(target, STOP, source="cli", actor=actor, instance=instance)
        store.clear_started(target)
    except Exception as exc:  # noqa: BLE001 — the close happened; say what did not
        return False, (
            f"warning: could not cancel the pending start for {target.ref} "
            f"({exc}); run `the-loop sessions stop {target.ref}` so it is not "
            "launched later"
        )
    eventlog.emit(
        "control.command",
        work_item=target.ref,
        command=STOP,
        source="cli",
        actor=actor or None,
        effect="start-cancelled",
    )
    return True, ""


def resolve_thread(
    pr: str,
    thread_id: str,
    work_item: str = "",
    config: Optional[Mapping[str, Any]] = None,
    *,
    registry_dir: str = "",
    client: Optional[GitHubClient] = None,
) -> Dict[str, Any]:
    """Resolve one review thread of a pull request — the reviewing procedure's
    "one finding, one commit, one resolved thread" (R1.12).

    The thread must be **one of this pull request's**: the id is checked against
    the PR's own threads before the mutation, so a node id from anywhere else is
    refused rather than resolved. The PR must belong to a registered work item
    (:func:`_authority`).
    """
    target = _trusted(resolve_pull_request(pr, work_item), config)
    thread = str(thread_id or "").strip()
    if not thread:
        raise ValueError("name the thread to resolve (its id, from `pr threads`)")
    data: Dict[str, Any] = {
        "pullRequest": target.ref,
        "thread": thread,
        "resolved": False,
    }
    refusal = _authority(target, work_item, config, registry_dir)
    if refusal:
        return _failed(data, f"not resolving: {refusal}")
    gh = _client(config, client)
    host = _host(target)
    try:
        threads = gh.review_threads(target.owner, target.repo, target.number, host=host)
        if thread not in [t.get("id") for t in threads]:
            return _failed(data, f"{thread} is not a review thread of {target.ref}")
        resolved = gh.resolve_review_thread(thread, host=host)
    except GitHubApiError as exc:
        return _failed(data, f"could not resolve {thread} on {target.ref}: {exc}")
    data["resolved"] = resolved
    if not resolved:
        return _failed(data, f"GitHub did not resolve {thread} on {target.ref}")
    eventlog.emit("work_item.thread_resolved", pull_request=target.ref, thread=thread)
    return _done(data, f"resolved {thread} on {target.ref}")
