"""Load and validate ``gateway-config.yaml`` (issue-496, R8).

The gateway's own file, separate from any instance's ``cli-config.yaml`` so a process on
another box carries none of an instance's keys. Resolved the way
:func:`the_loop.cli_config.default_cli_config_path` resolves the CLI config: an explicit
path, then ``$THE_LOOP_GATEWAY_CONFIG``, then ``./.the-loop/gateway-config.yaml``, then
``~/.the-loop/gateway-config.yaml``.

Validation is the shipped ``gateway-config`` schema through
:func:`the_loop.configschema.validate`; a violation raises :class:`ConfigError` naming
every offending path at once (R8.1), so ``the-loop gateway start`` refuses to start with
one message rather than one per restart. Every secret in the file is an environment
variable **name** — the schema's ``pattern`` on each ``*Env`` key rejects a pasted value
(abuse case 7) — and the file's own ``env.file`` is loaded first, through
:func:`the_loop.envfile.load`, under the CLI config's rules (issue-318): relative to the
config file, never overwriting a set variable, a missing file a warning naming the path.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

import yaml

from .. import configschema, envfile

__all__ = [
    "GATEWAY_CONFIG_ENV",
    "GATEWAY_CONFIG_FILENAME",
    "DEFAULT_PORT",
    "ConfigError",
    "GatewayConfig",
    "Listen",
    "StoreConfig",
    "Consume",
    "GitHubIngress",
    "GitHubWebhook",
    "GitHubPoll",
    "PollSource",
    "JiraIngress",
    "JiraWebhook",
    "JiraPoll",
    "SlackIngress",
    "SlackSocket",
    "SlackHttp",
    "Room",
    "default_gateway_config_path",
    "load_gateway_config",
    "load_gateway_env_file",
    "resolve_gateway_env_file",
]

logger = logging.getLogger("the-loop.gateway.config")

GATEWAY_CONFIG_ENV = "THE_LOOP_GATEWAY_CONFIG"
GATEWAY_CONFIG_FILENAME = "gateway-config.yaml"
#: ≠ the service (4114) and the stdlib receiver (8787): all three start on one laptop
#: with no configuration (R14.2).
DEFAULT_PORT = 8790
DEFAULT_STATE_ROOT = "~/.the-loop/gateway"

_override: Optional[Path] = None


class ConfigError(ValueError):
    """``gateway-config.yaml`` is missing, unparseable or violates its schema.

    ``errors`` carries every violation as ``"<key path>: <what is wrong>"``; ``str()``
    joins them, naming the file first.
    """

    def __init__(self, path: Path, errors: Sequence[str]) -> None:
        self.path = Path(path)
        self.errors = list(errors)
        lines = [f"{self.path}: invalid gateway configuration"]
        lines.extend(f"  - {error}" for error in self.errors)
        super().__init__("\n".join(lines))


# -- the typed configuration ------------------------------------------------------------


@dataclass(frozen=True)
class Listen:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    exposed: bool = False


@dataclass(frozen=True)
class StoreConfig:
    path: Path
    retention_days: int = 7
    max_attempts: int = 3
    dedup_window: int = 10_000


@dataclass(frozen=True)
class Consume:
    max_batch: int = 256
    max_wait_s: int = 30
    lease_s: Tuple[int, int] = (10, 300)


@dataclass(frozen=True)
class GitHubWebhook:
    enabled: bool = False
    path: str = "/gh-webhook"
    secret_env: str = "THE_LOOP_GH_WEBHOOK_SECRET"


@dataclass(frozen=True)
class PollSource:
    repository: str
    labels: Tuple[str, ...] = ()
    issues: bool = True
    pull_requests: bool = True


@dataclass(frozen=True)
class GitHubPoll:
    enabled: bool = False
    interval_seconds: int = 60
    token_env: str = "GITHUB_TOKEN"
    sources: Tuple[PollSource, ...] = ()


@dataclass(frozen=True)
class GitHubIngress:
    webhook: GitHubWebhook = GitHubWebhook()
    poll: GitHubPoll = GitHubPoll()


@dataclass(frozen=True)
class JiraWebhook:
    enabled: bool = False
    secret_env: str = "THE_LOOP_JIRA_WEBHOOK_SECRET"


@dataclass(frozen=True)
class JiraPoll:
    enabled: bool = False
    interval_seconds: int = 60
    site: str = ""
    email_env: str = "THE_LOOP_JIRA_EMAIL"
    token_env: str = "THE_LOOP_JIRA_TOKEN"
    labels: Tuple[str, ...] = ()


@dataclass(frozen=True)
class JiraIngress:
    webhook: JiraWebhook = JiraWebhook()
    poll: JiraPoll = JiraPoll()
    projects: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SlackSocket:
    enabled: bool = True
    app_token_env: str = "THE_LOOP_SLACK_APP_TOKEN"
    bot_token_env: str = "THE_LOOP_SLACK_BOT_TOKEN"
    split_check_beats: int = 3


@dataclass(frozen=True)
class SlackHttp:
    enabled: bool = False
    signing_secret_env: str = "SLACK_SIGNING_SECRET"


@dataclass(frozen=True)
class Room:
    channel: str
    work_item: str


@dataclass(frozen=True)
class SlackIngress:
    socket: SlackSocket = SlackSocket()
    http: SlackHttp = SlackHttp()
    rooms: Tuple[Room, ...] = ()


@dataclass(frozen=True)
class GatewayConfig:
    """``gateway-config.yaml``, validated and resolved: every path absolute, every
    block present with its defaults, every secret a variable name."""

    path: Path
    state_root: Path
    listen: Listen = Listen()
    store: StoreConfig = field(default=None)  # type: ignore[assignment]  # set in __post_init__
    consume: Consume = Consume()
    repositories: Tuple[str, ...] = ()
    github: Optional[GitHubIngress] = None
    jira: Optional[JiraIngress] = None
    slack: Optional[SlackIngress] = None
    instances: Optional[Tuple[str, ...]] = None
    event_log: Optional[Path] = None
    event_log_enabled: bool = True
    env_file: Optional[Path] = None
    version: str = ""

    def __post_init__(self) -> None:
        if self.store is None:
            object.__setattr__(
                self, "store", StoreConfig(path=self.state_root / "gateway.db")
            )
        if self.event_log is None:
            object.__setattr__(
                self, "event_log", self.state_root / "logs" / "events.jsonl"
            )

    @property
    def pidfile(self) -> Path:
        return self.state_root / "gateway.pid"

    @property
    def logfile(self) -> Path:
        return self.state_root / "logs" / "gateway.out"

    @property
    def listen_file(self) -> Path:
        """Where the running process records the address it bound (R8.6): the file
        may already say another port while the process still listens on this one."""
        return self.state_root / "gateway.listen"

    @property
    def base_url(self) -> str:
        return f"http://{self.listen.host}:{self.listen.port}"

    def secret_names(self) -> List[str]:
        """Every environment-variable name the file declares — what the event log's
        redaction list gains, so a value never reaches a line (§Security design)."""
        names: List[str] = []
        if self.github is not None:
            names += [self.github.webhook.secret_env, self.github.poll.token_env]
        if self.jira is not None:
            names += [
                self.jira.webhook.secret_env,
                self.jira.poll.email_env,
                self.jira.poll.token_env,
            ]
        if self.slack is not None:
            names += [
                self.slack.socket.app_token_env,
                self.slack.socket.bot_token_env,
                self.slack.http.signing_secret_env,
            ]
        return sorted(set(names))


# -- resolution -------------------------------------------------------------------------


def set_override(path: Optional[Union[str, Path]]) -> None:
    """``--config`` for the gateway verbs; ``None`` clears it."""
    global _override
    _override = Path(path) if path is not None else None


def default_gateway_config_path() -> Path:
    """The gateway config path — see the module docstring for priority."""
    if _override is not None:
        return _override
    env = os.environ.get(GATEWAY_CONFIG_ENV)
    if env:
        return Path(env)
    cwd_candidate = Path(".the-loop") / GATEWAY_CONFIG_FILENAME
    if cwd_candidate.is_file():
        return cwd_candidate
    return Path.home() / ".the-loop" / GATEWAY_CONFIG_FILENAME


def _read_raw(path: Path) -> Any:
    if not path.is_file():
        raise ConfigError(path, [f"(root): {path} not found"])
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(path, [f"(root): not valid YAML ({exc})"]) from exc
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ConfigError(path, ["(root): the document must be a mapping"])
    return dict(data)


def _resolve_path(raw: str, base: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return Path(os.path.abspath(candidate))


def resolve_gateway_env_file(
    data: Mapping[str, Any], config_path: Path
) -> Optional[Path]:
    """``env.file`` resolved against the config file's directory; ``None`` when unset."""
    block = data.get("env")
    if not isinstance(block, Mapping):
        return None
    value = block.get("file")
    if not isinstance(value, str) or not value.strip():
        return None
    return _resolve_path(value, Path(config_path).parent)


def load_gateway_env_file(
    config_path: Optional[Union[str, Path]] = None,
) -> Optional[envfile.LoadResult]:
    """Load the env file the gateway config names into ``os.environ``, never raising.

    Called first by ``gateway/serve.py`` and the ``gateway`` verbs, as
    :func:`the_loop.cli_config.load_env_file` is by the instance's entry points: the
    variables are in place before any adapter reads them. Lenient on purpose — a file
    that fails to parse here is reported once, by :func:`load_gateway_config`.
    """
    try:
        path = (
            Path(config_path)
            if config_path is not None
            else default_gateway_config_path()
        )
        try:
            data = _read_raw(path)
        except ConfigError:
            return None
        env_path = resolve_gateway_env_file(data, path)
        if env_path is None:
            return None
        return envfile.load(env_path, os.environ)
    except Exception as exc:  # noqa: BLE001 — never block a start over the env file
        logger.warning("gateway env file not loaded (%s)", type(exc).__name__)
        return None


# -- typing the validated document --------------------------------------------------------


def _get(block: Mapping[str, Any], key: str, default: Any) -> Any:
    value = block.get(key)
    return default if value is None else value


def _github(block: Mapping[str, Any]) -> GitHubIngress:
    wh = block.get("webhook") or {}
    poll = block.get("poll") or {}
    sources = []
    for entry in poll.get("sources") or []:
        monitor = entry.get("monitor") or {}
        sources.append(
            PollSource(
                repository=entry["repository"],
                labels=tuple(entry.get("labels") or ()),
                issues=bool(_get(monitor, "issues", True)),
                pull_requests=bool(_get(monitor, "pullRequests", True)),
            )
        )
    return GitHubIngress(
        webhook=GitHubWebhook(
            enabled=bool(_get(wh, "enabled", False)),
            path=str(_get(wh, "path", "/gh-webhook")),
            secret_env=str(_get(wh, "secretEnv", "THE_LOOP_GH_WEBHOOK_SECRET")),
        ),
        poll=GitHubPoll(
            enabled=bool(_get(poll, "enabled", False)),
            interval_seconds=int(_get(poll, "intervalSeconds", 60)),
            token_env=str(_get(poll, "tokenEnv", "GITHUB_TOKEN")),
            sources=tuple(sources),
        ),
    )


def _jira(block: Mapping[str, Any]) -> JiraIngress:
    wh = block.get("webhook") or {}
    poll = block.get("poll") or {}
    return JiraIngress(
        webhook=JiraWebhook(
            enabled=bool(_get(wh, "enabled", False)),
            secret_env=str(_get(wh, "secretEnv", "THE_LOOP_JIRA_WEBHOOK_SECRET")),
        ),
        poll=JiraPoll(
            enabled=bool(_get(poll, "enabled", False)),
            interval_seconds=int(_get(poll, "intervalSeconds", 60)),
            site=str(_get(poll, "site", "")),
            email_env=str(_get(poll, "emailEnv", "THE_LOOP_JIRA_EMAIL")),
            token_env=str(_get(poll, "tokenEnv", "THE_LOOP_JIRA_TOKEN")),
            labels=tuple(poll.get("labels") or ()),
        ),
        projects=tuple(block.get("projects") or ()),
    )


def _slack(block: Mapping[str, Any]) -> SlackIngress:
    socket = block.get("socket") or {}
    http = block.get("http") or {}
    return SlackIngress(
        socket=SlackSocket(
            enabled=bool(_get(socket, "enabled", True)),
            app_token_env=str(_get(socket, "appTokenEnv", "THE_LOOP_SLACK_APP_TOKEN")),
            bot_token_env=str(_get(socket, "botTokenEnv", "THE_LOOP_SLACK_BOT_TOKEN")),
            split_check_beats=int(_get(socket, "splitCheckBeats", 3)),
        ),
        http=SlackHttp(
            enabled=bool(_get(http, "enabled", False)),
            signing_secret_env=str(
                _get(http, "signingSecretEnv", "SLACK_SIGNING_SECRET")
            ),
        ),
        rooms=tuple(
            Room(channel=str(room["channel"]), work_item=str(room["workItem"]))
            for room in block.get("rooms") or []
        ),
    )


def load_gateway_config(path: Optional[Union[str, Path]] = None) -> GatewayConfig:
    """Read, validate and type ``gateway-config.yaml``.

    Raises :class:`ConfigError` — naming the file and every violating path — when the
    file is missing, is not YAML, or fails the shipped schema. ``path`` defaults to
    :func:`default_gateway_config_path`.
    """
    config_path = Path(path) if path is not None else default_gateway_config_path()
    config_path = Path(os.path.abspath(config_path.expanduser()))
    data = _read_raw(config_path)
    errors = configschema.validate(data, configschema.load_schema("gateway-config"))
    if errors:
        raise ConfigError(config_path, errors)

    base = config_path.parent
    state = data.get("state") or {}
    state_root = _resolve_path(str(_get(state, "root", DEFAULT_STATE_ROOT)), base)

    listen_block = data.get("listen") or {}
    listen = Listen(
        host=str(_get(listen_block, "host", "127.0.0.1")),
        port=int(_get(listen_block, "port", DEFAULT_PORT)),
        exposed=bool(_get(listen_block, "exposed", False)),
    )

    store_block = data.get("store") or {}
    store_path_raw = str(_get(store_block, "path", "")).strip()
    store = StoreConfig(
        path=_resolve_path(store_path_raw, base)
        if store_path_raw
        else state_root / "gateway.db",
        retention_days=int(_get(store_block, "retentionDays", 7)),
        max_attempts=int(_get(store_block, "maxAttempts", 3)),
        dedup_window=int(_get(store_block, "dedupWindow", 10_000)),
    )

    consume_block = data.get("consume") or {}
    lease = consume_block.get("leaseSeconds") or {}
    consume = Consume(
        max_batch=int(_get(consume_block, "maxBatch", 256)),
        max_wait_s=int(_get(consume_block, "maxWaitSeconds", 30)),
        lease_s=(int(_get(lease, "min", 10)), int(_get(lease, "max", 300))),
    )

    obs = (data.get("observability") or {}).get("eventLog") or {}
    log_raw = str(_get(obs, "path", "")).strip()
    event_log = (
        _resolve_path(log_raw, base)
        if log_raw
        else state_root / "logs" / "events.jsonl"
    )

    instances = data.get("instances")
    # The gateway writes only under its state root (design §Security design): the
    # store and the event log are resolved with realpath and must sit under it.
    root_real = Path(os.path.realpath(state_root))
    confined: List[str] = []
    for key, candidate in (
        ("store.path", store.path),
        ("observability.eventLog.path", event_log),
    ):
        real = Path(os.path.realpath(candidate))
        if root_real != real and root_real not in real.parents:
            confined.append(
                f"{key}: {candidate} is not under state.root ({state_root})"
            )
    if confined:
        raise ConfigError(config_path, confined)
    return GatewayConfig(
        path=config_path,
        state_root=state_root,
        listen=listen,
        store=store,
        consume=consume,
        repositories=tuple(data.get("repositories") or ()),
        github=_github(data["github"])
        if isinstance(data.get("github"), Mapping)
        else None,
        jira=_jira(data["jira"]) if isinstance(data.get("jira"), Mapping) else None,
        slack=_slack(data["slack"]) if isinstance(data.get("slack"), Mapping) else None,
        instances=tuple(instances) if instances else None,
        event_log=event_log,
        event_log_enabled=bool(_get(obs, "enabled", True)),
        env_file=resolve_gateway_env_file(data, config_path),
        version=str(data.get("version") or ""),
    )
