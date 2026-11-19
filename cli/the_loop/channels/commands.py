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
from dataclasses import dataclass
from importlib import resources
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .. import eventlog, strings
from ..collaborators import parse_logins
from ..control import COLLABORATOR_COMMANDS, COMMANDS, ControlConfig
from ..ghhost import github_host
from ..identity import principal_for
from ..instance import NAME_RE as INSTANCE_NAME_RE
from ..sessions import WorkItemRef
from ..sessions.registry import is_github_host, is_github_name
from ..standing import NAME_RE as STANDING_NAME_RE
from . import once
from .base import Event
from .github import GitHubLedger
from .jira import ledger_for_ref
from ..repos import parse_repo_path, repository_keys
from .slack import SlackChannelConfig, slack_state_path
from .state import ChannelState, ChannelStores, canonical

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "CREATE_VERBS",
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
#: The verbs that open a work item (issue-378): `new`, and `create` as its alias.
CREATE_VERBS = ("new", "create")
#: Each verb family's grant — a catalog event type in `channels.slack.publish`.
#: `create` reuses the kickoff's grant: a slash command that files an issue is
#: the top-level message's gesture with the text in the command instead.
FAMILY_GRANTS: Dict[str, str] = {
    "work-item": "control.command",
    "create": "work-item.create",
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

    family: str = ""  # help | work-item | create | instance | standing
    verb: str = ""  # a control COMMAND constant, an instance verb, a standing verb
    target: str = ""  # the raw work-item token, the standing name, or `new`'s text
    subject: str = ""  # @login for the collaborator commands
    address: str = ""  # instance:<name>
    error: str = ""


def _refused(why: str) -> Invocation:
    return Invocation(error=why)


def usage() -> str:
    """The vocabulary, as the usage line and the `help` answer print it."""
    return strings.t("channels.commands.usage")


def _command_for(verb: str, control: ControlConfig) -> Optional[str]:
    """The control command ``verb`` names: the last word of its configured keyword
    (`the-loop start` → `start`; an operator's `loop go` → `go`) or the command's
    own name. A disabled keyword (``""``) names nothing; two matches name nothing."""
    matches: List[str] = []
    # The operator's own words too (issue-343): the line posted is the word's
    # keyword, which the dispatcher parses as `start` onto the bound loop.
    for command in (*COMMANDS, *control.custom_commands):
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
    if verb in CREATE_VERBS:
        # The one family whose argument is prose: everything after the verb,
        # newlines kept, because the kickoff reads a first line and a body.
        prose = (text or "").strip()[len(tokens[0]) :].strip()
        if not prose:
            return _refused(
                strings.t("channels.commands.refusal.needs-title", verb=verb)
            )
        return Invocation(family="create", verb="new", target=prose)
    if verb in INSTANCE_VERBS:
        if rest:
            return _refused(
                strings.t("channels.commands.refusal.no-argument", verb=verb)
            )
        return Invocation(family="instance", verb=verb)
    if verb == "standing":
        if not rest:
            return _refused(strings.t("channels.commands.refusal.standing-needs-verb"))
        sub, args = rest[0].lower(), rest[1:]
        if sub not in STANDING_VERBS:
            return _refused(
                strings.t("channels.commands.refusal.unknown-standing-verb", sub=sub)
            )
        if sub == "list":
            if args:
                return _refused(
                    strings.t("channels.commands.refusal.standing-list-no-argument")
                )
            return Invocation(family="standing", verb=sub)
        if len(args) != 1:
            return _refused(
                strings.t("channels.commands.refusal.standing-needs-name", sub=sub)
            )
        if not STANDING_NAME_RE.fullmatch(args[0]):
            return _refused(
                strings.t("channels.commands.refusal.bad-standing-name", name=args[0])
            )
        return Invocation(family="standing", verb=sub, target=args[0])
    command = _command_for(verb, control)
    if command is None:
        return _refused(strings.t("channels.commands.refusal.unknown-verb", verb=verb))
    target = ""
    logins: List[str] = []
    addresses: List[str] = []
    for token in rest:
        if token.lower().startswith(_ADDRESS_PREFIX):
            name = token[len(_ADDRESS_PREFIX) :]
            if not INSTANCE_NAME_RE.fullmatch(name):
                return _refused(
                    strings.t("channels.commands.refusal.bad-address", token=token)
                )
            addresses.append(name)
        elif token.startswith("@"):
            parsed = parse_logins(token)
            if len(parsed) != 1:
                return _refused(
                    strings.t("channels.commands.refusal.bad-login", token=token)
                )
            logins.append(parsed[0])
        elif not target:
            target = token
        else:
            return _refused(
                strings.t("channels.commands.refusal.second-argument", token=token)
            )
    if not target:
        return _refused(
            strings.t("channels.commands.refusal.needs-work-item", verb=verb)
        )
    if len(addresses) > 1:
        return _refused(strings.t("channels.commands.refusal.two-addresses"))
    subject = ""
    if command in COLLABORATOR_COMMANDS:
        if len(logins) != 1:
            return _refused(strings.t("channels.commands.refusal.one-login", verb=verb))
        subject = logins[0]
    elif logins:
        return _refused(strings.t("channels.commands.refusal.no-login", verb=verb))
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
        path = slack_state_path(cli_config)
        state = ChannelState.load(path, ChannelStores.beside(path))
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


def _first_sight(trigger: str) -> bool:
    """Whether ``trigger`` is new to this process — the ring every interactive
    surface shares since issue-389 (:mod:`.once`)."""
    return once.first_sight(trigger)


def reset_seen() -> None:
    """Forget every trigger (tests)."""
    once.reset()


# -- rendering ----------------------------------------------------------------------


def render_status(doc: Mapping[str, Any]) -> str:
    """`status_all`'s document as the lines `the-loop status` prints."""
    from ..core.lifecycle import environment_line, split_lines

    instance = doc.get("instance") or {}
    name = str(instance.get("name") or strings.t("channels.commands.status.unnamed"))
    mode = str((instance.get("scope") or {}).get("mode") or "open")
    lines = [
        strings.t(
            "channels.commands.status.header",
            name=name,
            mode=mode,
            health=(
                strings.t("channels.commands.status.ok")
                if doc.get("ok")
                else strings.t("channels.commands.status.not-ok")
            ),
        )
    ]
    for row in doc.get("services") or []:
        if not row.get("enabled"):
            state = strings.t("channels.commands.status.disabled")
        elif row.get("running"):
            state = strings.t("channels.commands.status.running")
            if row.get("pid"):
                state += strings.t("channels.commands.status.pid", pid=row["pid"])
            if row.get("hosted"):
                state += strings.t("channels.commands.status.hosted")
            if row.get("url"):
                state += f" — {row['url']}"
        else:
            state = strings.t("channels.commands.status.stopped-enabled")
        lines.append(f"• {row.get('service', '?')}: {state}")
    for rival in doc.get("conflictingRoots") or []:
        # Never silently picked between (issue-339, R4.2).
        lines.append(
            strings.t(
                "channels.commands.status.conflict",
                rival=rival,
                state_root=doc.get("stateRoot"),
            )
        )
    drift = environment_line(doc)
    if drift:
        lines.append(strings.t("channels.commands.status.sessions", drift=drift))
    split = split_lines(doc)
    if split:
        # The same sentences `the-loop status` prints (issue-413) — the operator
        # reading this in Slack is the one whose room is losing envelopes. One
        # bullet, because it is one finding; the caveat and the remedy are its
        # continuation, not two more items in the list.
        lines.append(strings.t("channels.commands.status.slack", line=split[0]))
        lines.extend(f"  {line}" for line in split[1:])
    standing = doc.get("standingSessions") or []
    running = strings.t("channels.commands.standing.running")
    stopped = strings.t("channels.commands.standing.stopped")
    lines.append(
        strings.t(
            "channels.commands.status.standing",
            sessions=(
                " · ".join(
                    f"{s.get('name', '?')} {running if s.get('running') else stopped}"
                    for s in standing
                )
                if standing
                else strings.t("channels.commands.status.standing-none")
            ),
        )
    )
    return "\n".join(lines)


def _render_standing_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return strings.t("channels.commands.standing.none")
    lines = []
    for row in rows:
        if "outcome" in row:
            detail = f" — {row['detail']}" if row.get("detail") else ""
            lines.append(f"• {row.get('name', '?')}: {row['outcome']}{detail}")
        else:
            kind = (
                strings.t("channels.commands.standing.declared")
                if row.get("declared")
                else strings.t("channels.commands.standing.created")
            )
            state = (
                strings.t("channels.commands.standing.running")
                if row.get("running")
                else strings.t("channels.commands.standing.stopped")
            )
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
    # The declared graphs too (issue-343): the operator's own command words are
    # control commands on every surface, or a Slack reply would forward one the
    # dispatcher executes.
    return ControlConfig.from_mapping(
        dict(control) if isinstance(control, Mapping) else {},
        graphs=_declared_graphs(cli_config),
    )


def _declared_graphs(cli_config: Optional[Mapping]) -> Any:
    """The top-level ``graphs`` list, or the ``routing._graphs`` copy the loader
    fans it into (issue-343) — whichever this config object carries."""
    if not cli_config:
        return None
    raw = dict(cli_config).get("graphs")
    if raw is None:
        routing = dict(cli_config).get("routing")
        raw = routing.get("_graphs") if isinstance(routing, Mapping) else None
    return raw


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
    create_issue: Optional[Callable] = None,
    client_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One slash command through authorize → parse → grant → act → answer.

    Returns the outcome; **never raises**. ``respond`` is ``(response_url,
    text) -> bool``; ``lifecycle`` and ``standing`` default to the core modules
    and are the tests' seams, as ``post_comment`` is the ledger writer's,
    ``create_issue`` the issue writer's and ``client_factory`` the Slack
    client's (both for `/the-loop new`, issue-378).
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
    # 1. Authorize before anything is read from the text (R3.1, A1). The same
    #    check the thread pipeline makes, through the same function, so an
    #    allow-list entry naming a handle rather than a member id works on every
    #    inbound surface or on none (PR #376 review).
    from .inbound import _authorized

    if not _authorized(member, config, cli_config):
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
        reply(
            strings.t(
                "channels.commands.answer.refused",
                error=invocation.error,
                usage=usage(),
            )
        )
        return _drop("unknown-command", member)
    if invocation.family == "help":
        granted = strings.t("channels.commands.answer.granted")
        not_granted = strings.t("channels.commands.answer.not-granted")
        grants = "\n".join(
            strings.t(
                "channels.commands.answer.help-grant",
                family=family,
                grant=grant,
                state=granted if grant in config.publish else not_granted,
            )
            for family, grant in FAMILY_GRANTS.items()
        )
        answered = reply(
            strings.t("channels.commands.answer.help", usage=usage(), grants=grants)
        )
        return {"outcome": "help", "answered": answered}
    # 5. The family's grant (R3.2, A2).
    grant = FAMILY_GRANTS[invocation.family]
    if grant not in config.publish:
        reply(
            strings.t(
                "channels.commands.answer.missing-grant",
                grant=grant,
                verb=invocation.verb,
            )
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
    elif invocation.family == "create":
        outcome, message = _create_verb(
            invocation,
            config,
            cli_config,
            member,
            post_comment,
            create_issue,
            client_factory,
            result,
        )
    elif invocation.family == "instance":
        outcome, message = _instance_verb(invocation, cli_config, member, lifecycle)
    else:
        outcome, message = _standing_verb(
            invocation, cli_config, member, standing, result
        )
    if outcome == "unknown-target" or outcome.startswith("kickoff-"):
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
        return "unknown-target", strings.t(
            "channels.commands.answer.unknown-target",
            target=invocation.target,
            error=exc,
        )
    result["workItem"] = ref.ref
    if not may_target(ref, cli_config):
        return (
            "unknown-target",
            strings.t(
                "channels.commands.answer.not-configured", ref=ref.ref, path=ref.path
            ),
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

    ledger = ledger_for_ref(
        ref.ref, cli_config, lambda: GitHubLedger(cli_config, post_comment=post_comment)
    )
    record = publish(event, cli_config, channels=[], ledger=ledger).record
    if record and record.ok:
        link = f" — {record.url}" if record.url else ""
        return (
            "recorded",
            strings.t(
                "channels.commands.answer.recorded", line=line, ref=ref.ref, link=link
            ),
        )
    error = (record.error if record else "") or strings.t(
        "channels.commands.answer.record-error"
    )
    return "record-failed", strings.t(
        "channels.commands.answer.record-failed", line=line, ref=ref.ref, error=error
    )


def _create_verb(
    invocation, config, cli_config, member, post_comment, create_issue, factory, result
):
    """`/the-loop new [<repo>:] <title>` — the kickoff's tail with the thread step
    swapped (issue-378 R4). Returns ``(outcome, answer)``.

    The text goes through the kickoff's own grammar (:func:`resolve_target`),
    so what reaches the ledger is a **declared** slug and never the member's
    words (A1); an unresolved target is refused with the kickoff's own text,
    because a slash command has no message to hold and no thread to ask in
    (R4.3). The issue is opened through the same ``work-item.create`` event a
    top-level message publishes; the conversation is then opened the way a
    start opens it (R4.2), and a thread that cannot be opened never fails the
    creation (R4.6).
    """
    from .kickoff import refusal_text, resolve_target

    target = resolve_target(invocation.target, config, cli_config)
    if not target.ok:
        return f"kickoff-{target.outcome}", refusal_text(target)
    _received(member, invocation, target.repo)
    event = Event(
        event_type="work-item.create",
        work_item="",
        text=target.text,
        source="slack",
        actor=principal_for(config.principals, "slack", member),
        detail={
            "repo": target.repo,
            "labels": ",".join(config.kickoff_labels),
            "thread": "",
            "invocation": "slash",
        },
    )
    from .bus import publish

    ledger = GitHubLedger(
        cli_config, post_comment=post_comment, create_issue=create_issue
    )
    record = publish(event, cli_config, channels=[], ledger=ledger).record
    if not (record and record.ok and record.ref):
        error = (record.error if record else "") or strings.t(
            "channels.commands.answer.create-error"
        )
        return "create-failed", strings.t(
            "channels.commands.answer.create-failed", error=error
        )
    result["workItem"] = record.ref
    result["url"] = record.url
    link = f" — {record.url}" if record.url else ""
    # The conversation, opened as a start opens it (issue-317) with the
    # kickoff's origin, then told the link with the Do / Start buttons where a
    # press can be received (issue-337, issue-529). Best-effort: the issue
    # exists either way.
    from .slack import KICKOFF_COMMANDS, SlackBotChannel, render_reply_blocks

    bot = SlackBotChannel(
        config,
        slack_state_path(cli_config),
        client_factory=factory,
        cli_config=cli_config,
    )
    where = ""
    try:
        bot.open(record.ref, origin="kickoff")
        state = ChannelState.load(bot.state_path, bot.stores)
        conversation = state.conversation_for(record.ref) or ("", "")
    except Exception as exc:  # noqa: BLE001 — a thread is a nicety; the issue is the act
        eventlog.emit(
            "channel.open_failed",
            level="warning",
            channel="slack",
            work_item=record.ref,
            error=str(exc),
        )
        where = strings.t("channels.commands.answer.open-failed", error=exc)
    else:
        channel_id, thread = conversation
        said = (
            strings.t(
                "channels.commands.answer.opened-thread", ref=record.ref, link=link
            )
            if thread
            else strings.t(
                "channels.commands.answer.opened-channel", ref=record.ref, link=link
            )
        )
        bot.say(
            thread,
            said,
            channel_id,
            blocks=render_reply_blocks(
                said, config.command_buttons_for(*KICKOFF_COMMANDS)
            ),
        )
        eventlog.emit(
            "channel.created",
            channel="slack",
            work_item=record.ref,
            actor=member,
            thread=thread or None,
            channel_id=channel_id or None,
        )
        if channel_id:
            keyword = config.keyword("start")
            typed = (
                strings.t("channels.commands.answer.typed", keyword=keyword)
                if keyword
                else ""
            )
            where = (
                strings.t(
                    "channels.commands.answer.where-thread",
                    channel_id=channel_id,
                    typed=typed,
                    ref=record.ref,
                )
                if thread
                else strings.t(
                    "channels.commands.answer.where-channel",
                    channel_id=channel_id,
                    typed=typed,
                    ref=record.ref,
                )
            )
    return "created", strings.t(
        "channels.commands.answer.created", ref=record.ref, link=link, where=where
    )


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
            strings.t(
                "channels.commands.answer.scheduled",
                what=what,
                pid=scheduled.get("pid"),
                logfile=scheduled.get("logfile"),
            ),
        )
    except Exception as exc:  # noqa: BLE001 — the answer carries the failure (R3.6)
        logger.warning("slack: /the-loop %s failed: %s", invocation.verb, exc)
        return "failed", strings.t(
            "channels.commands.answer.failed", verb=invocation.verb, error=exc
        )


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
        return "failed", strings.t(
            "channels.commands.answer.standing-failed", verb=invocation.verb, error=exc
        )
