"""The daemon's one Jira client — the pycontribs ``jira`` SDK behind one seam (issue-475).

This module mirrors :mod:`the_loop.ghapi` (decision-139) for Jira
(decision-142). Every Jira read and write a process of the-loop's makes goes
through :class:`JiraClient`, and no other module imports the SDK.

Three properties every caller relies on:

* **The credential is the one the configuration names.** :class:`JiraApiConfig`
  reads ``integrations.jira``: the site, the deployment, and the environment
  variables holding the account email (Cloud) and the token. The values are read
  from the process environment **at call time**, so a rotated token takes effect
  without a restart. A missing one is :class:`MissingCredential`, naming the
  variables and never a value.
* **One exception type.** The SDK's ``JIRAError``, a transport error from
  ``requests``, anything else: all become :class:`JiraApiError` here, carrying
  the HTTP status (``None`` for a transport failure) and the server's own text.
  The message is scrubbed of the ``Authorization`` header, the email and the
  token. ``JIRAError.__str__`` prints the request headers, so it is never used.
* **Plain types out.** :class:`JiraIssue`, :class:`JiraComment` and
  :class:`JiraTransition`, never an SDK resource.

Where requests go, and how they authenticate, is decided by ``deployment``:

==============  ==============================================  ==================  ====
deployment      server                                          auth                REST
==============  ==============================================  ==================  ====
cloud           ``https://<site>``                              email + API token   3
cloud-scoped    ``https://api.atlassian.com/ex/jira/<cloudId>`` email + scoped tok  3
data-center     ``https://<site>``                              PAT (Bearer)        2
==============  ==============================================  ==================  ====

Bodies: a Cloud comment is ADF, a Data Center one wiki markup. The conversion
from the-loop's Markdown, and back, is :mod:`the_loop.jiraformat`'s, through
:meth:`JiraClient._body` and :meth:`JiraClient._markdown` — every body this
client sends or returns passes through them.

The SDK logs through the ``jira`` and ``jira.resilientsession`` loggers. A
redaction filter is installed on both, so neither a development log nor a
daemon log ever carries a credential.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import threading
from dataclasses import dataclass, field, replace
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from .authz import is_self_authored

logger = logging.getLogger("the-loop.jiraapi")

__all__ = [
    "DEPLOYMENTS",
    "GATEWAY",
    "JiraApiConfig",
    "JiraApiError",
    "JiraAuth",
    "JiraClient",
    "JiraComment",
    "JiraIssue",
    "JiraTransition",
    "MissingCredential",
    "is_issue_key",
    "issue_key_for",
]

#: The three deployments a config can name.
DEPLOYMENTS: Tuple[str, ...] = ("cloud", "cloud-scoped", "data-center")

#: Where a scoped Cloud token's calls go.
GATEWAY = "https://api.atlassian.com/ex/jira"

#: Page size for a search, and the cap on what one search returns.
PAGE_SIZE = 100
SEARCH_LIMIT = 200
#: The most comments one listing reads (critic C2). A ticket past it keeps its
#: NEWEST ones — what a poller's cursor and a gate's "latest" need — with a warning.
COMMENTS_LIMIT = 5000


def _number_or(value: Any, default: int) -> int:
    """``value`` as an int, or ``default`` when it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


#: The SDK's loggers. ``jira.resilientsession`` is a child, and a logger's
#: filters do not see a child's records, so each gets its own filter.
SDK_LOGGERS: Tuple[str, ...] = ("jira", "jira.resilientsession")

#: An issue key, the only thing of a ref's that reaches a URL path.
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-[1-9][0-9]{0,9}$")
_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")

#: The header and keyword shapes a credential travels in, whatever its value.
_AUTH_HEADER_RE = re.compile(
    r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)(?:basic|bearer)?\s*[^\s'\",}]+"
)
_BASIC_AUTH_RE = re.compile(r"(?i)(basic_auth\s*=\s*)\([^)]*\)")
_TOKEN_AUTH_RE = re.compile(r"(?i)(token_auth\s*=\s*)['\"]?[^\s'\",)]+")
_REDACTED = "[redacted]"


def is_issue_key(value: str) -> bool:
    """Whether ``value`` is a Jira issue key (``PROJ-123``) — checked before a URL."""
    return bool(_ISSUE_KEY_RE.match(value or ""))


def issue_key_for(ref: str, config: "JiraApiConfig") -> str:
    """``jira:<site>/<KEY>-<n>`` → ``KEY-n``, or :class:`JiraApiError` before any
    request: the ref must be a Jira ref, on the configured site, in a project
    listed under ``integrations.jira.projects`` (mirror-only included). A ref
    naming another site never carries this deployment's credential there
    (abuse case 8)."""
    from .sessions import WorkItemRef

    try:
        parsed = WorkItemRef.parse(str(ref))
    except ValueError as exc:
        raise JiraApiError(f"malformed work item ref {ref!r}: {exc}") from None
    if parsed.provider != "jira":
        raise JiraApiError(
            f"{ref!r} is not a Jira ref — expected 'jira:<site>/<KEY>-<n>'"
        )
    site = config.site
    if not site or parsed.host.lower() != site:
        raise JiraApiError(
            f"{parsed.ref} is on {parsed.host}, not the configured Jira "
            f"site ({site or 'none'}); nothing was sent"
        )
    if parsed.owner not in config.projects:
        raise JiraApiError(
            f"project {parsed.owner} is not configured under "
            "integrations.jira.projects; nothing was sent"
        )
    return f"{parsed.owner}-{parsed.number}"


# ------------------------------------------------------------------ redaction

_secrets: Set[str] = set()
_secrets_lock = threading.Lock()
_filter_installed = False


def _remember(*values: str) -> None:
    """Register credential values the scrubber must remove wherever they appear."""
    with _secrets_lock:
        for value in values:
            if value and len(value) >= 4:
                _secrets.add(value)


def scrub(text: str) -> str:
    """``text`` with every known credential, and every credential-shaped header, gone."""
    out = _AUTH_HEADER_RE.sub(lambda m: m.group(1) + _REDACTED, str(text))
    out = _BASIC_AUTH_RE.sub(lambda m: m.group(1) + _REDACTED, out)
    out = _TOKEN_AUTH_RE.sub(lambda m: m.group(1) + _REDACTED, out)
    with _secrets_lock:
        known = sorted(_secrets, key=len, reverse=True)
    for value in known:
        out = out.replace(value, _REDACTED)
    return out


class _RedactingFilter(logging.Filter):
    """Rewrites an SDK log record's message with :func:`scrub` before any handler
    sees it. It never drops a record: a scrubbed line is still evidence."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — a malformed record is left to logging
            return True
        clean = scrub(message)
        if clean != message:
            record.msg, record.args = clean, None
        return True


def install_log_redaction() -> None:
    """Put the redaction filter on the SDK's loggers, once per process."""
    global _filter_installed
    with _secrets_lock:
        if _filter_installed:
            return
        _filter_installed = True
    for name in SDK_LOGGERS:
        logging.getLogger(name).addFilter(_RedactingFilter())


# ---------------------------------------------------------------- the config


@dataclass(frozen=True)
class JiraAuth:
    """A credential read from the environment. ``repr`` never shows the token."""

    kind: str  # "basic" | "bearer"
    token: str = field(repr=False)
    email: str = field(default="", repr=False)


@dataclass(frozen=True)
class JiraApiConfig:
    """Mirror of ``integrations.jira`` — where the site is and where the credential is.

    ``email_env``/``token_env`` are variable **names**; a value is never a config
    value (the schema refuses one). Frozen and hashable: it keys the process-wide
    client cache. An absent block is a config with ``configured`` false.
    """

    site: str = ""
    deployment: str = ""
    email_env: Tuple[str, ...] = ()
    token_env: Tuple[str, ...] = ()
    cloud_id: str = ""
    close_transition: str = ""
    projects: Tuple[str, ...] = ()

    @classmethod
    def from_cli_config(cls, config: Optional[Mapping[str, Any]]) -> "JiraApiConfig":
        """``integrations.jira`` of a CLI config document (absent = unconfigured)."""
        integrations = (dict(config or {}).get("integrations")) or {}
        jira = integrations.get("jira") if isinstance(integrations, Mapping) else None
        if not isinstance(jira, Mapping):
            return cls()
        raw_api = jira.get("api")
        api: Mapping[str, Any] = raw_api if isinstance(raw_api, Mapping) else {}
        projects = jira.get("projects")
        return cls(
            site=str(jira.get("site") or "").strip().lower(),
            deployment=str(jira.get("deployment") or "").strip(),
            email_env=_names(api.get("emailEnv")),
            token_env=_names(api.get("tokenEnv")),
            cloud_id=str(jira.get("cloudId") or "").strip(),
            close_transition=str(jira.get("closeTransition") or "").strip(),
            projects=tuple(
                sorted(
                    str(key)
                    for key in (projects if isinstance(projects, Mapping) else {})
                    if _PROJECT_KEY_RE.match(str(key))
                )
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.site) and self.deployment in DEPLOYMENTS

    @property
    def cloud(self) -> bool:
        return self.deployment in ("cloud", "cloud-scoped")

    @property
    def rest_version(self) -> str:
        """``"3"`` on Cloud (ADF bodies), ``"2"`` on Data Center (wiki markup)."""
        return "3" if self.cloud else "2"

    def server(self) -> str:
        """Where requests go. Raises when the block is absent or incomplete."""
        if not self.configured:
            raise JiraApiError("integrations.jira is not configured")
        if self.deployment == "cloud-scoped":
            if not self.cloud_id:
                raise JiraApiError(
                    "integrations.jira.cloudId is required for deployment cloud-scoped"
                )
            return f"{GATEWAY}/{self.cloud_id}"
        return f"https://{self.site}"

    def browse_url(self, key: str) -> str:
        """The link a person opens — always on the site, even through the gateway."""
        return f"https://{self.site}/browse/{key}"

    def comment_url(self, key: str, comment_id: str) -> str:
        return f"{self.browse_url(key)}?focusedCommentId={comment_id}"

    def _required(self) -> List[Tuple[str, Tuple[str, ...]]]:
        needed = [("token", self.token_env)]
        if self.cloud:
            needed.insert(0, ("email", self.email_env))
        return needed

    def missing_credentials(self, env: Optional[Mapping[str, str]] = None) -> List[str]:
        """The variable names of each credential that no variable supplies.

        One entry per missing credential: its variables joined by `` or ``. Empty
        when every credential this deployment needs is set.
        """
        environ: Mapping[str, str] = os.environ if env is None else env
        missing = []
        for what, names in self._required():
            if not _first(names, environ):
                missing.append(" or ".join(names) if names else f"(no {what} variable)")
        return missing

    def credentials(self, env: Optional[Mapping[str, str]] = None) -> JiraAuth:
        """The credential, read from the environment now. Raises
        :class:`MissingCredential` naming the variables — never a value."""
        environ: Mapping[str, str] = os.environ if env is None else env
        missing = self.missing_credentials(environ)
        if missing:
            raise MissingCredential(
                "no Jira credentials: set " + " and ".join(missing),
                missing_credential=True,
            )
        token = _first(self.token_env, environ)
        if self.cloud:
            return JiraAuth("basic", token=token, email=_first(self.email_env, environ))
        return JiraAuth("bearer", token=token)


def _names(raw: Any) -> Tuple[str, ...]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(n).strip() for n in raw if str(n).strip())


def _first(names: Sequence[str], environ: Mapping[str, str]) -> str:
    for name in names:
        value = (environ.get(name) or "").strip()
        if value:
            return value
    return ""


# ----------------------------------------------------------------- the error


class JiraApiError(Exception):
    """A Jira call could not be made or was refused.

    ``status`` is the HTTP status Jira answered (``None`` for a transport failure
    or a missing credential); ``message`` is the server's text, scrubbed. The
    text never carries a credential.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        missing_credential: bool = False,
    ):
        message = scrub(message)
        super().__init__(message)
        self.message = message
        self.status = status
        self.missing_credential = missing_credential

    @property
    def not_found(self) -> bool:
        return self.status == 404

    def __str__(self) -> str:
        if self.status is not None:
            return f"Jira {self.status}: {self.message}"
        return self.message


class MissingCredential(JiraApiError):
    """The configured credential variables are not set."""


# --------------------------------------------------------------- plain types


@dataclass(frozen=True)
class JiraIssue:
    key: str
    summary: str = ""
    labels: List[str] = field(default_factory=list)
    status_category: str = ""  # "new" | "indeterminate" | "done"
    description_md: str = ""
    #: Set when Jira answered for a different key than asked: the issue moved.
    moved_to: str = ""
    url: str = ""


@dataclass(frozen=True)
class JiraComment:
    id: str
    author_id: str  # Cloud accountId; Data Center user key
    body_md: str
    created: str = ""
    url: str = ""
    #: Whether the-loop wrote it: a self-marker in the body, or the author is the
    #: service account (:meth:`JiraClient.comments`).
    is_self: bool = False


@dataclass(frozen=True)
class JiraTransition:
    id: str
    name: str
    to_status: str = ""
    to_category: str = ""  # the target status category key: "done" closes


# ---------------------------------------------------------------- the client


class JiraClient:
    """The operations the-loop uses, over one ``jira.JIRA`` per credential.

    ``factory(config, auth)`` builds the SDK object; tests inject one. The SDK is
    imported lazily, so a GitHub-only process never loads it.
    """

    _shared: Dict[Tuple[JiraApiConfig, float], "JiraClient"] = {}
    _shared_lock = threading.Lock()

    def __init__(
        self,
        config: Optional[JiraApiConfig] = None,
        *,
        timeout: float = 30.0,
        factory: Optional[Callable[[JiraApiConfig, JiraAuth], Any]] = None,
    ):
        self.config = config or JiraApiConfig()
        self.timeout = timeout
        self._factory = factory or self._build
        self._sdk: Optional[Any] = None
        self._sdk_key: Optional[Tuple[str, str, str]] = None
        self._me: str = ""
        self._lock = threading.Lock()
        install_log_redaction()

    @classmethod
    def shared(
        cls, config: Optional[JiraApiConfig] = None, *, timeout: float = 30.0
    ) -> "JiraClient":
        """One client per ``(config, timeout)`` for the process."""
        key = (config or JiraApiConfig(), float(timeout))
        with cls._shared_lock:
            client = cls._shared.get(key)
            if client is None:
                client = cls(key[0], timeout=key[1])
                cls._shared[key] = client
            return client

    # -- construction ------------------------------------------------------------

    def _build(self, config: JiraApiConfig, auth: JiraAuth) -> Any:
        import jira

        kwargs: Dict[str, Any] = {
            "server": config.server(),
            "options": {
                "rest_api_version": config.rest_version,
                # No PyPI version check from inside a daemon.
                "check_update": False,
            },
            # One request per operation: no server-info probe at construction.
            "get_server_info": False,
            "max_retries": 2,
            "timeout": max(1, int(self.timeout)),
        }
        if auth.kind == "basic":
            kwargs["basic_auth"] = (auth.email, auth.token)
        else:
            kwargs["token_auth"] = auth.token
        sdk = jira.JIRA(**kwargs)
        # Without the server-info probe the SDK does not know it is on Cloud, and
        # its Cloud-only calls (the /search/jql pager) would return None. The
        # configuration knows.
        sdk.deploymentType = "Cloud" if config.cloud else "Server"
        return sdk

    def has_credentials(self) -> bool:
        return self.config.configured and not self.config.missing_credentials()

    def sdk(self) -> Any:
        """The ``jira.JIRA`` for the current credential, or raise.

        Rebuilt when the credential changes, so a rotated token is used at once.
        """
        self.config.server()  # unconfigured or incomplete: refused before reading env
        auth = self.config.credentials()
        _remember(auth.token, auth.email)
        if auth.email:
            _remember(base64.b64encode(f"{auth.email}:{auth.token}".encode()).decode())
        key = (auth.kind, auth.email, auth.token)
        with self._lock:
            if self._sdk is None or self._sdk_key != key:
                self._sdk = self._factory(self.config, auth)
                self._sdk_key = key
                self._me = ""
            return self._sdk

    # -- the boundary ------------------------------------------------------------

    def _call(self, what: str, fn: Callable[[Any], Any]) -> Any:
        """Run one SDK call, translating every failure to :class:`JiraApiError`."""
        sdk = self.sdk()
        try:
            return fn(sdk)
        except JiraApiError:
            raise
        except Exception as exc:  # noqa: BLE001 — the one translation boundary
            raise self._translate(what, exc) from None

    @staticmethod
    def _translate(what: str, exc: BaseException) -> JiraApiError:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and status:
            # The server's own text only: JIRAError.__str__ prints request headers.
            text = str(getattr(exc, "text", "") or "").strip()
            message = text or exc.__class__.__name__
            logger.debug("%s failed: %s %s", what, status, scrub(message))
            return JiraApiError(message, status=status)
        text = str(exc).strip() or exc.__class__.__name__
        logger.debug("%s failed without a status: %s", what, scrub(text))
        return JiraApiError(f"{what}: {text}")

    @staticmethod
    def _key(value: str) -> str:
        key = str(value or "")
        if not is_issue_key(key):
            raise JiraApiError(f"unusable Jira issue key {key!r}")
        return key

    # -- bodies -------------------------------------------------------------------

    def _body(self, markdown: str) -> Any:
        """``markdown`` in this deployment's format, through ``jiraformat``:
        an ADF document on REST v3 (Cloud), wiki markup on v2 (Data Center)."""
        from .jiraformat import to_jira

        return to_jira(markdown, self.config.rest_version)

    @classmethod
    def _markdown(cls, body: Any, markers: bool = True) -> str:
        """A body Jira returned, as Markdown: ADF (a mapping) or wiki (a string).

        ``markers=False`` keeps its the-loop markers visible text — for a body
        the service account did not write (:func:`~the_loop.jiraformat.from_jira`).
        """
        from .jiraformat import from_jira

        return from_jira(body, markers=markers)

    # -- reading SDK documents -----------------------------------------------------

    def _issue_of(self, raw: Mapping[str, Any], asked: str = "") -> JiraIssue:
        fields = raw.get("fields") or {}
        status = fields.get("status") or {}
        category = (status.get("statusCategory") or {}).get("key") or ""
        key = str(raw.get("key") or asked)
        return JiraIssue(
            key=key,
            summary=str(fields.get("summary") or ""),
            labels=[str(label) for label in fields.get("labels") or []],
            status_category=str(category),
            description_md=self._markdown(fields.get("description")),
            moved_to=key if asked and key != asked else "",
            url=self.config.browse_url(key),
        )

    def _comment_of(
        self, key: str, raw: Mapping[str, Any], markers: bool = True
    ) -> JiraComment:
        author = raw.get("author") or {}
        author_id = str(author.get("accountId") or author.get("key") or "")
        comment_id = str(raw.get("id") or "")
        return JiraComment(
            id=comment_id,
            author_id=author_id,
            body_md=self._markdown(raw.get("body"), markers=markers),
            created=str(raw.get("created") or ""),
            url=self.config.comment_url(key, comment_id),
        )

    # -- the operations ------------------------------------------------------------

    def get_issue(self, key: str) -> JiraIssue:
        key = self._key(key)
        found = self._call(
            "get issue",
            lambda j: j.issue(key, fields="summary,labels,status,description"),
        )
        return self._issue_of(getattr(found, "raw", {}) or {}, asked=key)

    def labels(self, key: str) -> List[str]:
        key = self._key(key)
        found = self._call("read labels", lambda j: j.issue(key, fields="labels"))
        raw = getattr(found, "raw", {}) or {}
        return [str(label) for label in (raw.get("fields") or {}).get("labels") or []]

    def add_labels(self, key: str, labels: Sequence[str]) -> None:
        """Add ``labels``, leaving every other label in place (one update)."""
        key = self._key(key)
        ops = [{"add": str(label)} for label in labels]
        if not ops:
            return
        self._call(
            "add labels",
            lambda j: j.issue(key, fields="labels").update(update={"labels": ops}),
        )

    def remove_label(self, key: str, label: str) -> bool:
        """Take one label off. ``False`` when the issue does not carry it."""
        key = self._key(key)

        def run(j: Any) -> bool:
            found = j.issue(key, fields="labels")
            current = ((getattr(found, "raw", {}) or {}).get("fields") or {}).get(
                "labels"
            ) or []
            if label not in current:
                return False
            found.update(update={"labels": [{"remove": label}]})
            return True

        return bool(self._call("remove label", run))

    def comments(self, key: str) -> List[JiraComment]:
        """The issue's comments, each with ``is_self`` decided (R4.6).

        A comment is the-loop's own when its body carries a self-marker **or**
        its author is this client's account (:meth:`myself`) — two independent
        tests, either one enough (design §C6, trade-off 6). ``myself`` is asked
        only when some comment is unmarked or carries a gate marker, and an
        answer that cannot be had leaves the marker as the only test.

        A visible gate marker (``[the-loop:phase-selection]``, …) becomes the
        hidden one a gate matches ONLY on a comment by the service account —
        never on the strength of a self-marker, which anyone can type. Anyone
        else's reads as literal text, so a Jira user cannot plant a checklist
        an authorized ``execute`` then freezes (self-review R2-4). Unreadable
        ``myself``: no comment's markers are converted (fail closed).

        Every page is read (``startAt``/``maxResults`` on Cloud's v3 and Data
        Center's v2 ``issue/{key}/comment`` alike), oldest first. A page that
        fails raises — never a truncated list, so a poller keeps its cursor. Past
        :data:`COMMENTS_LIMIT` the newest are kept, with a warning (critic C2).
        """
        key = self._key(key)
        return self._read_comments(key, self._comment_pages(key))

    def _comment_pages(self, key: str) -> List[Mapping[str, Any]]:
        path = f"issue/{key}/comment"
        raws: List[Mapping[str, Any]] = []
        start = 0
        skipped = False
        while True:
            page = (
                self._call(
                    "list comments",
                    lambda j, s=start: j._get_json(
                        path, params={"startAt": s, "maxResults": PAGE_SIZE}
                    ),
                )
                or {}
            )
            found = [c for c in page.get("comments") or [] if isinstance(c, Mapping)]
            total = _number_or(page.get("total"), -1)
            if not skipped and total > COMMENTS_LIMIT:
                skipped = True
                logger.warning(
                    "Jira %s has %d comments; reading only the newest %d",
                    key,
                    total,
                    COMMENTS_LIMIT,
                )
                start = total - COMMENTS_LIMIT
                continue
            raws.extend(found)
            start += len(found)
            if not found or (total >= 0 and start >= total):
                break
            if len(raws) >= COMMENTS_LIMIT:
                logger.warning(
                    "Jira %s: stopped listing comments at %d", key, COMMENTS_LIMIT
                )
                break
        return raws[-COMMENTS_LIMIT:]

    def comment(self, key: str, comment_id: str) -> Optional[JiraComment]:
        """One comment by id (``issue/{key}/comment/{id}``), read as
        :meth:`comments` reads each; ``None`` when Jira has no such comment.

        The webhook doorbell's read: the delivered comment, wherever it sits in
        the thread, never a scan of the first page (critic C2).
        """
        key = self._key(key)
        if not str(comment_id).isdigit():
            raise JiraApiError(f"unusable Jira comment id {comment_id!r}")
        try:
            raw = self._call(
                "read comment",
                lambda j: j._get_json(f"issue/{key}/comment/{comment_id}"),
            )
        except JiraApiError as exc:
            if exc.status == 404:
                return None
            raise
        if not isinstance(raw, Mapping):
            return None
        [found] = self._read_comments(key, [raw])
        return found

    def _read_comments(
        self, key: str, raws: Sequence[Mapping[str, Any]]
    ) -> List[JiraComment]:
        """``raws`` as comments, each with ``is_self`` decided and its gate
        markers promoted only on the service account's (self-review R2-4)."""
        read = [self._comment_of(key, raw, markers=False) for raw in raws]
        marked = [self._markdown(raw.get("body")) for raw in raws]
        unmarked = [c for c in read if not is_self_authored(c.body_md, "jira")]
        gated = any(md != c.body_md for md, c in zip(marked, read))
        me = self._self_id() if unmarked or gated else ""
        return [
            replace(
                c,
                body_md=md if me and c.author_id == me else c.body_md,
                is_self=(
                    is_self_authored(c.body_md, "jira")
                    or bool(me and c.author_id == me)
                ),
            )
            for md, c in zip(marked, read)
        ]

    def _self_id(self) -> str:
        try:
            return self.myself()
        except JiraApiError as exc:
            logger.debug("could not read the Jira account's own id: %s", exc)
            return ""

    def add_comment(self, key: str, markdown: str) -> JiraComment:
        key = self._key(key)
        body = self._body(markdown)
        made = self._call("add comment", lambda j: j.add_comment(key, body))
        return replace(
            self._comment_of(key, getattr(made, "raw", {}) or {}), is_self=True
        )

    def transitions(self, key: str) -> List[JiraTransition]:
        key = self._key(key)
        found = self._call("list transitions", lambda j: j.transitions(key))
        out = []
        for raw in found or []:
            target = raw.get("to") or {}
            out.append(
                JiraTransition(
                    id=str(raw.get("id") or ""),
                    name=str(raw.get("name") or ""),
                    to_status=str(target.get("name") or ""),
                    to_category=str(
                        (target.get("statusCategory") or {}).get("key") or ""
                    ),
                )
            )
        return out

    def transition(self, key: str, transition_id: str) -> None:
        key = self._key(key)
        if not str(transition_id).isdigit():
            raise JiraApiError(f"unusable Jira transition id {transition_id!r}")
        self._call(
            "transition issue", lambda j: j.transition_issue(key, str(transition_id))
        )

    def search(
        self, jql: str, fields: Sequence[str] = (), limit: int = SEARCH_LIMIT
    ) -> Iterator[JiraIssue]:
        """Issues matching ``jql``, paged; at most ``limit``.

        Cloud: ``/rest/api/3/search/jql`` by ``nextPageToken``. Data Center:
        ``/search`` by ``startAt``. The caller builds ``jql`` from validated
        values only (design §Security boundary 4).
        """
        wanted = list(fields) or ["summary", "labels", "status"]
        seen = 0
        if self.config.cloud:
            token: Optional[str] = None
            while seen < limit:
                page = (
                    self._call(
                        "search",
                        lambda j, t=token: j.enhanced_search_issues(
                            jql,
                            nextPageToken=t,
                            maxResults=min(PAGE_SIZE, limit - seen),
                            fields=list(wanted),
                            json_result=True,
                        ),
                    )
                    or {}
                )
                for raw in page.get("issues") or []:
                    seen += 1
                    yield self._issue_of(raw)
                    if seen >= limit:
                        return
                token = page.get("nextPageToken")
                if not token or page.get("isLast"):
                    return
            return
        start = 0
        while seen < limit:
            page = (
                self._call(
                    "search",
                    lambda j, s=start: j.search_issues(
                        jql,
                        startAt=s,
                        maxResults=min(PAGE_SIZE, limit - seen),
                        fields=list(wanted),
                        json_result=True,
                    ),
                )
                or {}
            )
            issues = page.get("issues") or []
            for raw in issues:
                seen += 1
                yield self._issue_of(raw)
                if seen >= limit:
                    return
            start += len(issues)
            if not issues or start >= int(page.get("total") or 0):
                return

    def create_issue(
        self,
        project: str,
        summary: str,
        description_md: str = "",
        labels: Sequence[str] = (),
        issue_type: str = "Task",
    ) -> JiraIssue:
        if not _PROJECT_KEY_RE.match(project or ""):
            raise JiraApiError(f"unusable Jira project key {project!r}")
        fields: Dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "labels": [str(label) for label in labels],
        }
        if description_md:
            fields["description"] = self._body(description_md)
        made = self._call("create issue", lambda j: j.create_issue(fields=fields))
        raw = getattr(made, "raw", {}) or {}
        return JiraIssue(
            key=str(raw.get("key") or getattr(made, "key", "")),
            summary=summary,
            labels=list(fields["labels"]),
            description_md=description_md,
            url=self.config.browse_url(str(raw.get("key") or "")),
        )

    def myself(self) -> str:
        """The bot's own account id (Cloud ``accountId``, Data Center ``key``). Cached."""
        sdk = self.sdk()
        with self._lock:
            if self._me:
                return self._me
        me = self._call("read myself", lambda j: j.myself()) or {}
        ident = str(me.get("accountId") or me.get("key") or "")
        with self._lock:
            if self._sdk is sdk:
                self._me = ident
        return ident
