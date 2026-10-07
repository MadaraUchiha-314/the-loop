"""Per-provider work-item ref grammar (issue-475, design § C1).

A :class:`~the_loop.sessions.registry.WorkItemRef` keeps its five fields for
every provider. What a ref *looks like* — how it parses, renders, slugs, links
and names its spec folder — is its provider's :class:`RefScheme`, looked up in
:data:`SCHEMES`. The GitHub scheme is the code ``WorkItemRef`` carried before
issue-475, moved; the Jira scheme sits beside it. A provider with no scheme of
its own keeps the provider-neutral ``<provider>:[<host>/]<owner>/<repo>#<n>``
grammar every ref had before, with no URL and no spec id.

:func:`origin_repository` answers the one question the two providers answer
differently: which GitHub repository a work item's spec chain, worktree and pull
requests live in (design § C2).

Stdlib only, and nothing here imports the registry at module level: the
registry imports this module.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from .registry import WorkItemRef

__all__ = [
    "DEFAULT_GITHUB_HOST",
    "SCHEMES",
    "GitHubScheme",
    "JiraScheme",
    "RefScheme",
    "UnknownJiraProject",
    "is_github_host",
    "is_github_name",
    "jira_section",
    "origin_ref",
    "origin_repository",
    "scheme_for",
]

_REF_RE = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*):(?P<path>[^#]+)#(?P<number>\d+)$")

# GitHub's own owner/repo name shape, used to validate the names a browser URL is
# built from (issue-130). A name that is not this shape gets no URL at all: a
# link to the wrong repository is worse than no link.
_GITHUB_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


def is_github_name(value: str) -> bool:
    """Whether ``value`` is a shape GitHub accepts as an owner or repository name.

    Public because a second caller needs the same answer (issue-194): deriving a
    ref from the harness config's ``ticketing.github`` validates owner and repo
    before building anything, and "what GitHub accepts" must have **one**
    definition — two copies of this expression is how one of them ends up
    accepting a `/` and pointing a comment at the wrong repository.
    """
    return bool(_GITHUB_NAME_RE.fullmatch(value))


# A host in a ref (issue-130 review). Deliberately narrow — no scheme, no
# credentials, no path — because this value is interpolated into a URL. It must
# also be *recognisable* as a host, because it is what distinguishes a
# three-segment path (`host/owner/repo`) from a malformed two-segment one: a
# dotted name, or a name with an explicit port. `github:octo/repo/sub#15` is
# therefore rejected rather than quietly read as a work item on a host called
# "octo" — a silent second identity for something that was probably a typo.
_HOST_PATTERN = (
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::\d+)?"  # dotted, optional port
    r"|[A-Za-z0-9-]+:\d+"  # or a bare name with an explicit port
)
_HOST_RE = re.compile(_HOST_PATTERN)


def is_github_host(value: str) -> bool:
    """Whether ``value`` is the shape of a GitHub host — the one grammar for a host.

    Public since issue-311: the host resolver (``ghhost``), ``ref_for``, a poll
    source's ``[HOST/]OWNER/REPO`` and a kickoff slug all refuse through this one
    expression **before** a value is interpolated into a URL or a ``--hostname``
    argument. Two copies of it is how one of them comes to accept a scheme.
    """
    return bool(_HOST_RE.fullmatch(value or ""))


#: The host a ``github:`` ref means when it does not say (github.com). A ref
#: names its host only when it is somewhere else, so every ref written before
#: issue-130 keeps its exact form — and its file name.
DEFAULT_GITHUB_HOST = "github.com"

_UNSAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _ref_type() -> Any:
    from .registry import WorkItemRef

    return WorkItemRef


class RefScheme(Protocol):
    """How one provider's refs are shaped (design § C1)."""

    provider: str

    def parse(self, text: str) -> "WorkItemRef":
        """``text`` as a ref; :class:`ValueError` naming the form when it is not one."""
        ...

    def render(self, ref: "WorkItemRef") -> str:
        """The inverse of :meth:`parse`."""
        ...

    def path(self, ref: "WorkItemRef") -> str:
        """The part between the provider prefix and the number."""
        ...

    def url(self, ref: "WorkItemRef") -> str:
        """The browser URL, or ``""`` when none can be derived honestly."""
        ...

    def slug(self, ref: "WorkItemRef") -> str:
        """The filesystem-safe name — the registry file, the worktree directory."""
        ...

    def spec_id(self, ref: "WorkItemRef") -> Optional[str]:
        """The spec folder id, or ``None`` when the provider has no convention."""
        ...

    def default_host(self) -> str:
        """The host a ref means when it names none; ``""`` when there is none."""
        ...


class _PathScheme:
    """``<provider>:[<host>/]<owner>/<repo>#<n>`` — the grammar every ref had
    before issue-475, kept for a provider with no scheme of its own: no URL, no
    spec id, and its host never written."""

    def __init__(self, provider: str = "") -> None:
        self.provider = provider

    def default_host(self) -> str:
        return ""

    def _host_unwritten(self, ref: "WorkItemRef") -> bool:
        default = self.default_host()
        return not default or ref.host == default

    def path(self, ref: "WorkItemRef") -> str:
        """``[<host>/]<owner>/<repo>`` — the host only when it is not the default."""
        prefix = "" if self._host_unwritten(ref) else f"{ref.host}/"
        return f"{prefix}{ref.owner}/{ref.repo}"

    def render(self, ref: "WorkItemRef") -> str:
        return f"{ref.provider}:{self.path(ref)}#{ref.number}"

    def url(self, ref: "WorkItemRef") -> str:
        return ""

    def slug(self, ref: "WorkItemRef") -> str:
        """Built from :meth:`path`, so a github.com work item's file name is exactly
        what it was before refs learned about hosts, and two work items with the
        same owner/repo/number on different hosts get different files."""
        raw = f"{ref.provider}-{self.path(ref).replace('/', '-')}-{ref.number}"
        return _UNSAFE_SLUG_RE.sub("-", raw)

    def spec_id(self, ref: "WorkItemRef") -> Optional[str]:
        return None

    def parse(self, text: str) -> "WorkItemRef":
        match = _REF_RE.match(text.strip())
        if not match:
            raise ValueError(
                f"invalid work-item ref {text!r}; expected "
                "<provider>:[<host>/]<owner>/<repo>#<number> "
                "(e.g. github:octo/repo#15, github:ghe.corp.example/octo/repo#15)"
            )
        parts = match.group("path").split("/")
        if len(parts) == 2:
            host, (owner, repo) = "", parts
        elif len(parts) == 3:
            host, owner, repo = parts
        else:
            raise ValueError(
                f"invalid work-item ref {text!r}; expected <owner>/<repo>, "
                "optionally preceded by a host, before '#'"
            )
        if not owner or not repo or (host and not _HOST_RE.fullmatch(host)):
            raise ValueError(
                f"invalid work-item ref {text!r}; expected <owner>/<repo>, "
                "optionally preceded by a host, before '#'"
            )
        return _ref_type()(
            provider=match.group("provider"),
            owner=owner,
            repo=repo,
            number=int(match.group("number")),
            host=host,
        )


class GitHubScheme(_PathScheme):
    """``github:[<host>/]<owner>/<repo>#<n>`` — the GitHub ref, unchanged.

    The path is ``[<host>/]<owner>/<repo>``: a work item on GitHub Enterprise
    names its host (``github:ghe.corp.example/owner/repo#15``), and one on
    github.com does not (issue-130 review). Keeping the default host *unwritten*
    is what makes this backwards compatible in the only two places that matter —
    every ref string already on disk still parses to the same work item, and the
    slug still resolves to the same file name.
    """

    def __init__(self) -> None:
        super().__init__("github")

    def default_host(self) -> str:
        return DEFAULT_GITHUB_HOST

    def url(self, ref: "WorkItemRef") -> str:
        """Derived, never guessed. The host is the ref's own (github.com unless it
        says otherwise), and GitHub redirects ``/issues/<n>`` to ``/pull/<n>``
        when the number is a pull request, so one form serves both. A host, owner
        or repo that is not the shape GitHub accepts yields ``""``: a link to the
        wrong place is worse than no link."""
        if not (
            _HOST_RE.fullmatch(ref.host)
            and is_github_name(ref.owner)
            and is_github_name(ref.repo)
        ):
            return ""
        return f"https://{ref.host}/{ref.owner}/{ref.repo}/issues/{ref.number}"

    def spec_id(self, ref: "WorkItemRef") -> Optional[str]:
        """``issue-<n>``. ``ref.number`` is an ``int``, so the id cannot contain a
        path separator however the ref arrived (issue-113 A5)."""
        return f"issue-{int(ref.number)}"


#: A Jira project key: Jira's own default rule, capped at its default ten
#: characters. Also the only part of a Jira spec id that is not a number.
JIRA_KEY_PATTERN = r"[A-Z][A-Z0-9_]{1,9}"
_JIRA_NUMBER_PATTERN = r"[1-9][0-9]{0,9}"
_JIRA_REF_RE = re.compile(
    rf"^jira:(?P<site>{_HOST_PATTERN})/"
    rf"(?P<key>{JIRA_KEY_PATTERN})-(?P<number>{_JIRA_NUMBER_PATTERN})$"
)
_JIRA_KEY_RE = re.compile(JIRA_KEY_PATTERN)
#: ``jira-<key lower>-<n>``: the spec id :meth:`JiraScheme.spec_id` writes.
JIRA_SPEC_ID_RE = re.compile(
    rf"^jira-(?P<key>{JIRA_KEY_PATTERN.replace('A-Z', 'a-z')})"
    rf"-(?P<number>{_JIRA_NUMBER_PATTERN})$"
)


class JiraScheme:
    """``jira:<site>/<KEY>-<n>`` — a Jira ticket (issue-475).

    The site is the ref's ``host`` (lower-cased), the project key its ``owner``,
    and ``repo`` is empty: a Jira ticket has no repository of its own, which is
    what :func:`origin_repository` supplies. The spec id is
    ``jira-<key lower>-<n>``, disjoint by prefix from GitHub's ``issue-<n>`` —
    even for a project whose key is ``ISSUE`` (R2.2).
    """

    provider = "jira"

    def default_host(self) -> str:
        return ""

    def parse(self, text: str) -> "WorkItemRef":
        match = _JIRA_REF_RE.match(text.strip())
        if not match:
            raise ValueError(
                f"invalid Jira work-item ref {text!r}; expected "
                "jira:<site>/<KEY>-<number> (e.g. jira:acme.atlassian.net/PROJ-123): "
                "the site a bare hostname, the key [A-Z][A-Z0-9_]{1,9}, the number "
                "positive"
            )
        return _ref_type()(
            provider=self.provider,
            owner=match.group("key"),
            repo="",
            number=int(match.group("number")),
            host=match.group("site").lower(),
        )

    def path(self, ref: "WorkItemRef") -> str:
        return f"{ref.host}/{ref.owner}"

    def render(self, ref: "WorkItemRef") -> str:
        return f"jira:{ref.host}/{ref.owner}-{ref.number}"

    def url(self, ref: "WorkItemRef") -> str:
        """``https://<site>/browse/<KEY>-<n>``; ``""`` for a site or key that is
        not the grammar's (a ref built by hand rather than parsed)."""
        if not (_HOST_RE.fullmatch(ref.host) and _JIRA_KEY_RE.fullmatch(ref.owner)):
            return ""
        return f"https://{ref.host}/browse/{ref.owner}-{ref.number}"

    def slug(self, ref: "WorkItemRef") -> str:
        """``jira-<site>-<KEY>-<n>`` — ends in ``-<digits>`` like every slug, so
        the registry's file filter and the workspace's name check accept it."""
        raw = f"jira-{ref.host}-{ref.owner}-{ref.number}"
        return _UNSAFE_SLUG_RE.sub("-", raw)

    def spec_id(self, ref: "WorkItemRef") -> Optional[str]:
        return f"jira-{ref.owner.lower()}-{int(ref.number)}"


SCHEMES: Dict[str, RefScheme] = {"github": GitHubScheme(), "jira": JiraScheme()}


def scheme_for(provider: str) -> RefScheme:
    """The scheme for ``provider`` — the provider-neutral grammar when it has none."""
    return SCHEMES.get(provider) or _PathScheme(provider)


# -- origin repository (design § C2) ------------------------------------------------


class UnknownJiraProject(ValueError):
    """A Jira ref this deployment cannot place: another site, a project that is not
    configured, or a mirror-only project with no ``repository``. Raised before
    anything is resolved or sent — the fail-closed path for abuse cases 7 and 8."""


def jira_section(config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """``integrations.jira`` of a CLI config (or a graph runtime's config), or ``{}``."""
    integrations = config.get("integrations") if isinstance(config, Mapping) else None
    jira = integrations.get("jira") if isinstance(integrations, Mapping) else None
    return jira if isinstance(jira, Mapping) else {}


def jira_site(config: Optional[Mapping[str, Any]]) -> str:
    """The one Jira site this deployment is configured for, lower-cased; ``""``."""
    return str(jira_section(config).get("site") or "").strip().lower()


def _jira_repository(ref: "WorkItemRef", config: Optional[Mapping[str, Any]]) -> str:
    site = jira_site(config)
    if not site or ref.host.lower() != site:
        raise UnknownJiraProject(
            f"{ref.ref} is on {ref.host}, which is not the configured Jira site "
            f"({site or 'none'}); set integrations.jira.site to use it"
        )
    projects = jira_section(config).get("projects")
    project = projects.get(ref.owner) if isinstance(projects, Mapping) else None
    if not isinstance(project, Mapping):
        raise UnknownJiraProject(
            f"{ref.ref}: Jira project {ref.owner} is not configured under "
            "integrations.jira.projects"
        )
    repository = str(project.get("repository") or "").strip()
    owner, sep, repo = repository.partition("/")
    if not repository:
        raise UnknownJiraProject(
            f"{ref.ref}: Jira project {ref.owner} is mirror-only (no repository "
            "under integrations.jira.projects), so it is not a work-item source"
        )
    if not (sep and is_github_name(owner) and is_github_name(repo)):
        raise UnknownJiraProject(
            f"{ref.ref}: integrations.jira.projects.{ref.owner}.repository "
            f"{repository!r} is not <owner>/<repo>"
        )
    return repository


def origin_repository(ref: "WorkItemRef", config: Optional[Mapping[str, Any]]) -> str:
    """``<owner>/<repo>`` of the GitHub repository ``ref``'s work lives in.

    A GitHub ref's own repository; a Jira ref's
    ``integrations.jira.projects.<KEY>.repository``. A Jira ref on another site,
    in an unconfigured project or in a mirror-only one raises
    :class:`UnknownJiraProject`. Pure: reads ``config`` and nothing else.
    """
    if ref.provider == "jira":
        return _jira_repository(ref, config)
    return f"{ref.owner}/{ref.repo}"


def origin_ref(
    ref: "WorkItemRef",
    config: Optional[Mapping[str, Any]],
    number: Optional[int] = None,
) -> "WorkItemRef":
    """A GitHub ref in ``ref``'s origin repository, numbered ``number``.

    ``ref`` itself (renumbered when asked) for a GitHub ref — exactly what the
    callers built by hand before issue-475. For a Jira ref, the mapped repository
    on the operator's GitHub host (:func:`the_loop.ghhost.github_host`). A Jira
    ref this deployment cannot place raises :class:`UnknownJiraProject` before
    anything else is read.
    """
    WorkItemRef = _ref_type()
    n = ref.number if number is None else number
    if ref.provider != "jira":
        return WorkItemRef(
            provider=ref.provider,
            owner=ref.owner,
            repo=ref.repo,
            number=n,
            host=ref.host,
        )
    owner, _, repo = _jira_repository(ref, config).partition("/")
    from ..ghhost import github_host

    host = github_host(config)
    return WorkItemRef(
        provider="github",
        owner=owner,
        repo=repo,
        number=n,
        host="" if host == DEFAULT_GITHUB_HOST else host,
    )
