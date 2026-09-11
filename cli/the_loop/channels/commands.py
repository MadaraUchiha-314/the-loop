"""The ``/the-loop`` slash command — the channel's third inbound shape (issue-334).

A thread reply reaches the work item its thread is bound to; a top-level message
can become one (``work-item.create``). Neither can address the things that have
**no thread**: this instance itself (*restart yourself*), a work item that has not
started, a standing session that is not running. A slash command can, because it
is delivered on the same Socket Mode connection ``the-loop channels listen`` holds
and carries the invoking member's id — so the same allow-list judges it.

The discipline is the thread pipeline's, restated for a message with arguments
instead of prose (decision-116):

* **authorize first** — the member id against the ``slack`` ids of
  ``routing.authorizedUsers``; an unlisted member is dropped and answered with
  nothing, the silence a dropped reply gets;
* **parse a fixed vocabulary** — whole tokens against the configured control
  keywords, three instance verbs and four standing verbs; a name, a login and an
  address each against its own grammar; anything else is refused whole and
  nothing is ever interpolated from the text;
* **grant** — each verb family is a catalog event type in
  ``channels.slack.publish``: ``control.command`` (work-item verbs, reused),
  ``instance.command`` and ``standing.command`` (new, off by default);
* **act** — a work-item verb publishes ``control.command`` and **stops at the
  ledger record**, exactly as a keyword typed in a thread does (decision-103 D1:
  through the ledger, never around it), so the ledger's ingress executes it with
  every guard a typed comment meets; an instance or standing verb calls the core
  facade the CLI and the API already route to;
* **answer** — ephemerally, through the command's ``response_url``, and only to
  Slack's own host.

The work item a command names is bounded (decision-116 D4): its repository must be
``kickoff.repo`` or a poll source, or the work item must already be managed or
have a bound thread — the operator's credential never writes onto a repository the
operator never configured.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from importlib import resources
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence, Set

from .. import eventlog
from ..collaborators import parse_logins
from ..control import COLLABORATOR_COMMANDS, COMMANDS, ControlConfig
from ..ghhost import github_host
from ..identity import principal_for
from ..instance import NAME_RE as INSTANCE_NAME_RE
from ..sessions import WorkItemRef
from ..sessions.registry import is_github_host, is_github_name
from ..standing import NAME_RE as STANDING_NAME_RE
from .base import Event
from .github import GitHubLedger
from .repos import parse_repo_path, repository_keys
from .slack import SlackChannelConfig, slack_state_path
from .state import ChannelState, canonical

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "FAMILY_GRANTS",
    "INSTANCE_VERBS",
    "SLACK_HOOKS_PREFIX",
    "STANDING_VERBS",
    "Invocation",
    "handle_slash_command",
    "manifest_text",
    "may_target",
    "parse_invocation",
    "render_status",
    "reset_seen",
    "resolve_work_item",
    "usage",
    "webhook_responder",
]

#: The verbs that address this instance (R2.2).
INSTANCE_VERBS = ("status", "restart", "upgrade")
#: The standing-session verbs — the control plane's, minus create/delete.
STANDING_VERBS = ("list", "start", "stop", "restart")
#: Each verb family's grant — a catalog event type in `channels.slack.publish`.
FAMILY_GRANTS: Dict[str, str] = {
    "work-item": "control.command",
    "instance": "instance.command",
    "standing": "standing.command",
}
#: The only host an answer is ever posted to (A5).
SLACK_HOOKS_PREFIX = "https://hooks.slack.com/"
#: The packaged app manifest — Slack's importable definition of the app.
_MANIFEST = "slack-app-manifest.yaml"

_URL_RE = re.compile(
    r"^https?://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"/(?:issues|pull)/(?P<number>\d+)/?$"
)
_PATH_RE = re.compile(r"^(?P<path>[^#\s]+)#(?P<number>\d+)$")
_NUMBER_RE = re.compile(r"^#?(?P<number>\d+)$")
_ADDRESS_PREFIX = "instance:"


@dataclass(frozen=True)
class Invocation:
    """What a command's text asked for — one family and verb, validated tokens, or
    a refusal (``error`` set, ``family`` empty)."""

    family: str = ""  # help | work-item | instance | standing
    verb: str = ""  # a control COMMAND constant, an instance verb, a standing verb
    target: str = ""  # the raw work-item token, or the standing name
    subject: str = ""  # @login for the collaborator commands
    address: str = ""  # instance:<name>
    error: str = ""


def _refused(why: str) -> Invocation:
    return Invocation(error=why)


def usage() -> str:
    """The vocabulary, as the usage line and the `help` answer print it."""
    return (
        "`/the-loop help` — this text\n"
        "`/the-loop <keyword> <work-item> [@login] [instance:<name>]` — a control "
        "keyword on a work item (`start`, `stop`, `pause`, `resume`, `execute`, "
        "`contribute`, `do`, `review`, `cleanup`, `add-collaborator @login`, "
        "`remove-collaborator @login`); the work item is `github:owner/repo#N`, "
        "`owner/repo#N`, `#N` (against kickoff.repo) or its GitHub URL\n"
        "`/the-loop status` · `/the-loop restart` · `/the-loop upgrade` — this "
        "instance\n"
        "`/the-loop standing list` · `/the-loop standing start|stop|restart <name>` "
        "— standing sessions"
    )


def _command_for(verb: str, control: ControlConfig) -> Optional[str]:
    """The control command ``verb`` names: the last word of its configured keyword
    (`the-loop start` → `start`; an operator's `loop go` → `go`) or the command's
    own name. A disabled keyword (``""``) names nothing; two matches name nothing."""
    matches: List[str] = []
    for command in COMMANDS:
        keyword = control.keyword(command)
        if not keyword:
            continue
        if verb == command or verb == keyword.split()[-1].lower():
            matches.append(command)
    return matches[0] if len(matches) == 1 else None


def parse_invocation(text: Optional[str], control: ControlConfig) -> Invocation:
    """The one invocation ``text`` is (R2.2), or a refusal. Pure."""
    tokens = (text or "").split()
    if not tokens or tokens[0].lower() == "help":
        return Invocation(family="help", verb="help")
    verb, rest = tokens[0].lower(), tokens[1:]
    if verb in INSTANCE_VERBS:
        if rest:
            return _refused(f"`{verb}` takes no argument")
        return Invocation(family="instance", verb=verb)
    if verb == "standing":
        if not rest:
            return _refused("`standing` needs a verb: list, start, stop or restart")
        sub, args = rest[0].lower(), rest[1:]
        if sub not in STANDING_VERBS:
            return _refused(f"unknown standing verb `{sub}`")
        if sub == "list":
            if args:
                return _refused("`standing list` takes no argument")
            return Invocation(family="standing", verb=sub)
        if len(args) != 1:
            return _refused(f"`standing {sub}` needs exactly one session name")
        if not STANDING_NAME_RE.fullmatch(args[0]):
            return _refused(
                f"`{args[0]}` is not a standing-session name "
                "(lowercase letters, digits and hyphens, up to 40)"
            )
        return Invocation(family="standing", verb=sub, target=args[0])
    command = _command_for(verb, control)
    if command is None:
        return _refused(f"unknown verb `{verb}`")
    target = ""
    logins: List[str] = []
    addresses: List[str] = []
    for token in rest:
        if token.lower().startswith(_ADDRESS_PREFIX):
            name = token[len(_ADDRESS_PREFIX) :]
            if not INSTANCE_NAME_RE.fullmatch(name):
                return _refused(f"`{token}` is not an instance address")
            addresses.append(name)
        elif token.startswith("@"):
            parsed = parse_logins(token)
            if len(parsed) != 1:
                return _refused(f"`{token}` is not a GitHub login")
            logins.append(parsed[0])
        elif not target:
            target = token
        else:
            return _refused(
                f"one work item per command — `{token}` is a second argument"
            )
    if not target:
        return _refused(f"`{verb}` needs a work item (`#N`, `owner/repo#N` or a URL)")
    if len(addresses) > 1:
        return _refused("two instance addresses — name one")
    subject = ""
    if command in COLLABORATOR_COMMANDS:
        if len(logins) != 1:
            return _refused(f"`{verb}` takes exactly one @login")
        subject = logins[0]
    elif logins:
        return _refused(f"`{verb}` takes no @login")
    return Invocation(
        family="work-item",
        verb=command,
        target=target,
        subject=subject,
        address=addresses[0] if addresses else "",
    )


# -- the target (R2.3, R2.4) --------------------------------------------------------


def _ref(host: str, owner: str, repo: str, number: int, cli_config) -> WorkItemRef:
    host = host or github_host(cli_config)
    if not (is_github_host(host) and is_github_name(owner) and is_github_name(repo)):
        raise ValueError(f"{host}/{owner}/{repo} is not a GitHub repository path")
    return WorkItemRef(
        provider="github", owner=owner, repo=repo, number=number, host=host
    )


def _ref_from_path(path: str, number: int, cli_config) -> WorkItemRef:
    """``[host/]owner/repo`` + a number → a ref, through the one repository-path
    parse this instance has (:mod:`.repos`, issue-341)."""
    entry = parse_repo_path(path, cli_config)
    return _ref(entry.host, entry.owner, entry.repo, number, cli_config)


def resolve_work_item(token: str, cli_config: Optional[Mapping]) -> WorkItemRef:
    """The work item ``token`` names (R2.3) — ``ValueError`` for anything else.

    Four shapes: ``github:[host/]owner/repo#N``; ``[host/]owner/repo#N``; ``#N`` or
    ``N`` against ``channels.slack.kickoff.repo``; a GitHub issue / pull-request
    URL on this instance's own GitHub host. A bare ``owner/repo`` — from the token
    or from ``kickoff.repo`` — carries the resolved host (the issue-331 rule).
    """
    token = (token or "").strip()
    if not token:
        raise ValueError("a work item is required")
    if token.startswith("github:"):
        return WorkItemRef.parse(token)
    match = _URL_RE.match(token)
    if match:
        own = github_host(cli_config)
        if match["host"].lower() != own.lower():
            raise ValueError(
                f"{match['host']} is not this instance's GitHub host ({own})"
            )
        return _ref(
            match["host"],
            match["owner"],
            match["repo"],
            int(match["number"]),
            cli_config,
        )
    match = _NUMBER_RE.match(token)
    if match:
        repo = SlackChannelConfig.from_mapping(cli_config).kickoff_repo
        if not repo:
            raise ValueError(
                "`#N` needs channels.slack.kickoff.repo to resolve against — "
                "name the repository: `owner/repo#N`"
            )
        return _ref_from_path(repo, int(match["number"]), cli_config)
    match = _PATH_RE.match(token)
    if match:
        return _ref_from_path(match["path"], int(match["number"]), cli_config)
    if ":" in token:
        raise ValueError(f"{token!r}: only GitHub work items can be named here")
    raise ValueError(
        f"{token!r} is not a work item (`#N`, `owner/repo#N`, `github:owner/repo#N` "
        "or a GitHub issue / pull-request URL)"
    )


def _repo_key(ref: WorkItemRef) -> str:
    return f"{ref.host}/{ref.owner}/{ref.repo}".lower()


def may_target(ref: WorkItemRef, cli_config: Optional[Mapping]) -> bool:
    """Whether this instance may act on ``ref`` from a slash command (R2.4, A3):
    a configured repository, an already managed work item, or a bound thread.
    Every read is best-effort and a failing one contributes nothing — the
    fail-closed direction."""
    if _repo_key(ref) in repository_keys(cli_config):
        return True
    wanted = canonical(ref.ref)
    try:
        from ..core import instance as core_instance

        managed = core_instance.describe_instance(dict(cli_config or {}))["managed"]
        if any(canonical(str(row.get("ref") or "")) == wanted for row in managed):
            return True
    except Exception as exc:  # noqa: BLE001 — an unreadable registry widens nothing
        logger.debug("managed set unreadable: %s", exc)
    try:
        state = ChannelState.load(slack_state_path(cli_config))
        if wanted in state.conversations:
            return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("channel state unreadable: %s", exc)
    return False


# -- the answer (R2.1, A5) ----------------------------------------------------------


def _send_webhook(url: str, text: str) -> bool:
    from slack_sdk.webhook import WebhookClient  # type: ignore[import-not-found]

    response = WebhookClient(url).send(text=text, response_type="ephemeral")
    return int(getattr(response, "status_code", 0) or 0) == 200


def webhook_responder(url: str, text: str) -> bool:
    """Post ``text`` ephemerally through a slash command's ``response_url`` —
    Slack's own host only (A5); anything else is refused and logged."""
    if not url or not url.startswith(SLACK_HOOKS_PREFIX):
        logger.warning(
            "slack: refusing to answer a slash command through %r — not a %s URL",
            url or "(no response_url)",
            SLACK_HOOKS_PREFIX,
        )
        return False
    return _send_webhook(url, text)


# -- duplicates (A9) ----------------------------------------------------------------

_SEEN: Deque[str] = deque()
_SEEN_SET: Set[str] = set()
_SEEN_MAX = 256


def _first_sight(trigger: str) -> bool:
    """Whether ``trigger`` is new to this process; remembers it in a bounded ring."""
    if not trigger:
        return True
    if trigger in _SEEN_SET:
        return False
    _SEEN.append(trigger)
    _SEEN_SET.add(trigger)
    while len(_SEEN) > _SEEN_MAX:
        _SEEN_SET.discard(_SEEN.popleft())
    return True


def reset_seen() -> None:
    """Forget every trigger (tests)."""
    _SEEN.clear()
    _SEEN_SET.clear()


# -- rendering ----------------------------------------------------------------------


def render_status(doc: Mapping[str, Any]) -> str:
    """`status_all`'s document as the lines `the-loop status` prints."""
    instance = doc.get("instance") or {}
    name = str(instance.get("name") or "unnamed")
    mode = str((instance.get("scope") or {}).get("mode") or "open")
    lines = [
        f"the-loop status — instance `{name}` (mode: {mode}) · "
        f"{'ok' if doc.get('ok') else 'not ok'}"
    ]
    for row in doc.get("services") or []:
        if not row.get("enabled"):
            state = "disabled"
        elif row.get("running"):
            state = "running"
            if row.get("pid"):
                state += f" (pid {row['pid']})"
            if row.get("hosted"):
                state += ", hosted by the service"
            if row.get("url"):
                state += f" — {row['url']}"
        else:
            state = "stopped (enabled)"
        lines.append(f"• {row.get('service', '?')}: {state}")
    for rival in doc.get("conflictingRoots") or []:
        # Never silently picked between (issue-339, R4.2).
        lines.append(
            f"• conflict: `{rival}` also holds a poller heartbeat — reporting on "
            f"`{doc.get('stateRoot')}`"
        )
    standing = doc.get("standingSessions") or []
    lines.append(
        "• standing: "
        + (
            " · ".join(
                f"{s.get('name', '?')} {'running' if s.get('running') else 'stopped'}"
                for s in standing
            )
            if standing
            else "none"
        )
    )
    return "\n".join(lines)


def _render_standing_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "no standing sessions — none declared, none recorded"
    lines = []
    for row in rows:
        if "outcome" in row:
            detail = f" — {row['detail']}" if row.get("detail") else ""
            lines.append(f"• {row.get('name', '?')}: {row['outcome']}{detail}")
        else:
            kind = "declared" if row.get("declared") else "created"
            state = "running" if row.get("running") else "stopped"
            lines.append(f"• {row.get('name', '?')}: {state} ({kind})")
    return "\n".join(lines)


def manifest_text() -> str:
    """The packaged Slack app manifest, verbatim (R4.1)."""
    return (
        resources.files(__package__ or "the_loop.channels")
        .joinpath(_MANIFEST)
        .read_text("utf-8")
    )


# -- the handler (R2.1, R3) ---------------------------------------------------------


def _control_config(cli_config: Optional[Mapping]) -> ControlConfig:
    routing = (dict(cli_config or {}).get("routing") or {}) if cli_config else {}
    control = routing.get("control") if isinstance(routing, Mapping) else None
    return ControlConfig.from_mapping(
        dict(control) if isinstance(control, Mapping) else {}
    )


def _drop(reason: str, actor: str, level: str = "info", **fields) -> Dict[str, Any]:
    eventlog.emit(
        "channel.dropped",
        level=level,
        channel="slack",
        reason=reason,
        actor=actor,
        **fields,
    )
    return {"outcome": reason}


def handle_slash_command(
    payload: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    respond: Optional[Callable[[str, str], bool]] = None,
    post_comment: Optional[Callable] = None,
    lifecycle: Any = None,
    standing: Any = None,
) -> Dict[str, Any]:
    """One slash command through authorize → parse → grant → act → answer.

    Returns the outcome; **never raises**. ``respond`` is ``(response_url,
    text) -> bool``; ``lifecycle`` and ``standing`` default to the core modules
    and are the tests' seams, as ``post_comment`` is the ledger writer's.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    member = str(payload.get("user_id") or "")
    text = str(payload.get("text") or "")
    url = str(payload.get("response_url") or "")
    answer = respond or webhook_responder

    if not config.enabled:
        # The listener never runs for a disabled channel; an embedder calling this
        # directly gets the same fail-closed answer the transports give.
        return _drop("channel-disabled", member)
    # 1. Authorize before anything is read from the text (R3.1, A1).
    if not config.authorized_users or member not in set(config.authorized_users):
        return _drop("unauthorized-actor", member, level="warning")
    # 2. A trigger acts once (A9).
    if not _first_sight(str(payload.get("trigger_id") or "")):
        return _drop("duplicate", member)

    def reply(message: str) -> bool:
        try:
            ok = bool(answer(url, message))
        except Exception as exc:  # noqa: BLE001 — the answer is a receipt, never the act
            logger.warning("slack: could not answer a slash command: %s", exc)
            ok = False
        if not ok:
            eventlog.emit(
                "channel.command_answer_failed",
                level="warning",
                channel="slack",
                actor=member,
            )
        return ok

    # 3. Parse the fixed vocabulary (R2.2, A4).
    invocation = parse_invocation(text, _control_config(cli_config))
    if not invocation.family:
        reply(f"{invocation.error}.\n{usage()}")
        return _drop("unknown-command", member)
    if invocation.family == "help":
        grants = "\n".join(
            f"• {family} verbs — `{grant}`: "
            f"{'granted' if grant in config.publish else 'not granted'}"
            for family, grant in FAMILY_GRANTS.items()
        )
        answered = reply(f"{usage()}\n\nWhat this channel may do here:\n{grants}")
        return {"outcome": "help", "answered": answered}
    # 5. The family's grant (R3.2, A2).
    grant = FAMILY_GRANTS[invocation.family]
    if grant not in config.publish:
        reply(
            f"This channel does not hold `{grant}` — add it to "
            f"`channels.slack.publish` to allow `{invocation.verb}` from Slack."
        )
        return _drop("unpublishable-event", member, level="warning", kind=grant)

    result: Dict[str, Any] = {
        "family": invocation.family,
        "verb": invocation.verb,
    }
    if invocation.family == "work-item":
        outcome, message = _work_item_verb(
            invocation, config, cli_config, member, post_comment, result
        )
    elif invocation.family == "instance":
        outcome, message = _instance_verb(invocation, cli_config, member, lifecycle)
    else:
        outcome, message = _standing_verb(
            invocation, cli_config, member, standing, result
        )
    if outcome in ("unknown-target",):
        reply(message)
        return _drop(outcome, member, target=result.get("workItem") or None)
    eventlog.emit(
        "channel.command_completed",
        channel="slack",
        actor=member,
        family=invocation.family,
        verb=invocation.verb,
        work_item=result.get("workItem") or None,
        standing=result.get("standing") or None,
        outcome=outcome,
    )
    result["answered"] = reply(message)
    return {"outcome": outcome, **result}


def _received(member: str, invocation: Invocation, target: str) -> None:
    eventlog.emit(
        "channel.command_received",
        channel="slack",
        actor=member,
        family=invocation.family,
        verb=invocation.verb,
        target=target,
    )


def _work_item_verb(invocation, config, cli_config, member, post_comment, result):
    """A control keyword on a work item — through the ledger, never around it
    (R3.3, decision-116 D2). Returns ``(outcome, answer)``."""
    try:
        ref = resolve_work_item(invocation.target, cli_config)
    except ValueError as exc:
        return "unknown-target", f"`{invocation.target}` — {exc}."
    result["workItem"] = ref.ref
    if not may_target(ref, cli_config):
        return (
            "unknown-target",
            f"`{ref.ref}` — this instance is not configured for `{ref.path}` "
            "(channels.slack.kickoff.repo, polling.sources, or a work item it "
            "already manages).",
        )
    _received(member, invocation, ref.ref)
    control = _control_config(cli_config)
    # Composed from the configured keyword and validated tokens — never from the
    # payload's text (A4). The same line a member would type in the thread.
    line = control.keyword(invocation.verb)
    if invocation.subject:
        line = f"{line} @{invocation.subject}"
    if invocation.address:
        line = f"{line} instance:{invocation.address}"
    event = Event(
        event_type="control.command",
        work_item=ref.ref,
        text=line,
        source="slack",
        actor=principal_for(config.principals, "slack", member),
        detail={"invocation": "slash", "command": invocation.verb},
    )
    from .bus import publish

    ledger = GitHubLedger(cli_config, post_comment=post_comment)
    record = publish(event, cli_config, channels=[], ledger=ledger).record
    if record and record.ok:
        link = f" — {record.url}" if record.url else ""
        return (
            "recorded",
            f"Recorded `{line}` on `{ref.ref}`{link}. The loop executes it on its "
            "next ingress (a webhook delivery or a poll cycle); a start opens the "
            "work item's thread here.",
        )
    error = (record.error if record else "") or "the ledger did not record it"
    return "record-failed", f"Could not record `{line}` on `{ref.ref}`: {error}"


def _instance_verb(invocation, cli_config, member, lifecycle):
    """`status`, `restart`, `upgrade` — the core facade the API exposes (R3.5)."""
    if lifecycle is None:
        from ..core import lifecycle as core_lifecycle

        lifecycle = core_lifecycle
    _received(member, invocation, "instance")
    config = dict(cli_config or {})
    try:
        from .. import cli_config as cli_config_module

        if invocation.verb == "status":
            return "ok", render_status(
                lifecycle.status_all(
                    config, config_path=cli_config_module.default_cli_config_path()
                )
            )

        upgrade = invocation.verb == "upgrade"
        scheduled = lifecycle.schedule_restart(
            config,
            with_upgrade=upgrade,
            config_path=cli_config_module.default_cli_config_path(),
        )
        what = "the-loop restart --with-upgrade" if upgrade else "the-loop restart"
        return (
            "ok",
            f"Scheduled `{what}` (pid {scheduled.get('pid')}); its output goes to "
            f"`{scheduled.get('logfile')}`. `/the-loop status` says when it is back.",
        )
    except Exception as exc:  # noqa: BLE001 — the answer carries the failure (R3.6)
        logger.warning("slack: /the-loop %s failed: %s", invocation.verb, exc)
        return "failed", f"`{invocation.verb}` failed: {exc}"


def _standing_verb(invocation, cli_config, member, standing, result):
    """`standing list|start|stop|restart` — the core facade (R3.5)."""
    if standing is None:
        from ..core import standing as core_standing

        standing = core_standing
    _received(member, invocation, invocation.target or "list")
    config = dict(cli_config or {})
    try:
        if invocation.verb == "list":
            return "ok", _render_standing_rows(standing.list_standing(config))
        result["standing"] = invocation.target
        outcome = standing.control_standing(invocation.target, invocation.verb, config)
        return "ok", _render_standing_rows(outcome.get("sessions") or [])
    except Exception as exc:  # noqa: BLE001 — the answer carries the failure (R3.6)
        logger.warning("slack: /the-loop standing %s failed: %s", invocation.verb, exc)
        return "failed", f"`standing {invocation.verb}` failed: {exc}"
