"""The Jira poll provider (issue-475, task 4.2, T5/T7, R5.1–R5.6).

``JiraPollProvider`` is the poller core's second provider: project keys are its
scopes, one JQL query per project lists the armed tickets (every arming label, in
its Jira-safe form, and not Done), every comment is listed each cycle with the
poll ledger's ``seenComments`` as the cursor, and the events it builds are the
``issue_comment``/``issues`` shapes the dispatcher already reads — flagged as
Jira's (``x-the-loop-provider``), with the Jira ref as the work item and the
delivery id ``jira-comment-<site>-<id>`` the webhook doorbell uses too.

Spec: docs/specs/issue-475/design.md §C8; requirements R5; abuse case 6.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest
from conftest import FakeTmux, StubInteractiveAdapter
from jirafakes import FakeJiraClient, cloud_config, http_error

from the_loop.authz import (
    JIRA_RELAY_MARKER,
    mark_relayed_on_jira,
    mark_self_authored_on_jira,
)
from the_loop.control import ControlConfig
from the_loop.jiraapi import JiraComment, JiraIssue
from the_loop.poller import PollConfig, Poller, PollState, ProviderError
from the_loop.poller.base import build_provider
from the_loop.poller.jira import JiraPollProvider, build_jql, jql_string
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import PROVIDER_KEY, RELAY_KEY, event_provider
from the_loop.workitem import WorkItemStore

SITE = "acme.atlassian.net"
LABEL = "the-loop: auto-execute"
JLABEL = "the-loop:auto-execute"
ADA = "5b10ac8d82e05b22cc7d4ef5"
BOT = "5b10-the-loop-bot"
STRANGER = "557058:f00d-stranger"
KEY = "PROJ-7"
REF = WorkItemRef.parse(f"jira:{SITE}/{KEY}")


def _cli_config(**jira: Any) -> Dict[str, Any]:
    config = cloud_config(**jira)
    config["routing"] = {
        "authorizedUsers": [{"name": "Ada", "github": "ada", "jira": ADA}]
    }
    return config


def _issue(key: str = KEY, labels=(JLABEL,), category: str = "indeterminate"):
    return JiraIssue(
        key=key,
        summary=f"Ticket {key}",
        labels=list(labels),
        status_category=category,
        url=f"https://{SITE}/browse/{key}",
    )


def _comment(cid: str, author: str, body: str) -> JiraComment:
    return JiraComment(
        id=cid,
        author_id=author,
        body_md=body,
        created="2026-10-06T00:00:00.000+0000",
        url=f"https://{SITE}/browse/{KEY}?focusedCommentId={cid}",
    )


class SearchingFake(FakeJiraClient):
    """The fake, with per-project search results and per-project failures."""

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        self.by_project: Dict[str, List[JiraIssue]] = {}
        self.search_fails: Dict[str, Exception] = {}

    def search(self, jql, fields=(), limit=200):
        self._enter("search", jql=jql, fields=list(fields))
        project = jql.split('"')[1]
        if project in self.search_fails:
            raise self.search_fails[project]
        return iter(list(self.by_project.get(project, []))[:limit])


def _provider(client=None, labels=(LABEL,), projects=("PROJ",)) -> JiraPollProvider:
    client = client or SearchingFake(account_id=BOT)
    return JiraPollProvider(
        projects=list(projects),
        labels=list(labels),
        site=SITE,
        client=client,
    )


# -- JQL (abuse case 6) ---------------------------------------------------------------


def test_jql_has_one_clause_per_auto_execute_label():
    jql = build_jql("PROJ", ["the-loop:auto-execute", "team:web"])
    assert jql == (
        'project = "PROJ" AND labels = "the-loop:auto-execute" AND labels = '
        '"team:web" AND statusCategory != Done ORDER BY updated DESC'
    )


def test_the_provider_queries_the_jira_safe_labels():
    client = SearchingFake(account_id=BOT)
    _provider(client, labels=[LABEL, "team: web"]).listing()
    [search] = [c for c in client.calls if c["method"] == "search"]
    assert 'labels = "the-loop:auto-execute"' in search["jql"]
    assert 'labels = "team:web"' in search["jql"]
    assert LABEL not in search["jql"]


@pytest.mark.parametrize(
    "value, quoted",
    [
        ("plain", '"plain"'),
        ('a"b', '"a\\"b"'),
        ("back\\slash", '"back\\\\slash"'),
        ('x" OR project = "SECRET', '"x\\" OR project = \\"SECRET"'),
    ],
)
def test_jql_values_are_quoted(value, quoted):
    """Every JQL value is one string literal, whatever it holds."""
    assert jql_string(value) == quoted
    jql = build_jql("PROJ", [value])
    assert f"labels = {quoted}" in jql


@pytest.mark.parametrize("key", ["proj", "PR OJ", 'P" OR 1=1', ""])
def test_jql_refuses_a_project_key_that_is_not_one(key):
    with pytest.raises(ValueError):
        build_jql(key, [JLABEL])


# -- listing -----------------------------------------------------------------------------


def test_listing_maps_armed_tickets_to_jira_work_items():
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    listing = _provider(client).listing()
    [item] = listing.items
    assert item.ref == REF.ref and item.provider == "jira"
    assert item.title == "Ticket PROJ-7" and item.author == ""
    assert listing.polled == ["PROJ"] and not listing.failures


def test_listing_keeps_only_tickets_carrying_every_label_and_not_done():
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [
        _issue("PROJ-1"),
        _issue("PROJ-2", labels=("other",)),
        _issue("PROJ-3", category="done"),
    ]
    listing = _provider(client).listing()
    assert [item.number for item in listing.items] == [1]


def test_each_project_is_its_own_scope():
    client = SearchingFake(account_id=BOT)
    client.by_project["OPS2"] = [_issue("OPS2-4")]
    client.search_fails["PROJ"] = http_error(500, "boom")
    listing = _provider(client, projects=("PROJ", "OPS2")).listing()
    assert [f.scope for f in listing.failures] == ["PROJ"]
    assert listing.polled == ["OPS2"] and [i.number for i in listing.items] == [4]
    assert listing.degraded == {"PROJ"}


def test_no_arming_labels_lists_nothing():
    with pytest.raises(ProviderError):
        _provider(labels=()).listing()


def test_a_missing_credential_fails_the_whole_source():
    from the_loop.jiraapi import MissingCredential

    client = SearchingFake(account_id=BOT)
    client.fail = MissingCredential("no Jira credentials: set JIRA_API_TOKEN")
    with pytest.raises(ProviderError, match="JIRA_API_TOKEN"):
        _provider(client).listing()


def test_check_dependencies_names_the_missing_variables(monkeypatch):
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    provider = JiraPollProvider.from_source(
        {"provider": "jira", "projects": ["PROJ"]},
        default_labels=[LABEL],
        config=_cli_config(),
    )
    [missing] = provider.check_dependencies()
    assert "JIRA_EMAIL" in missing and "JIRA_API_TOKEN" in missing


# -- comments and events -----------------------------------------------------------------


def test_comments_are_listed_with_their_origin():
    client = SearchingFake(account_id=BOT)
    client.comment_table[KEY] = [
        _comment("1", ADA, "please look"),
        _comment("2", BOT, "an unmarked bot comment"),
        _comment("3", BOT, mark_relayed_on_jira("> approved")),
        _comment("4", ADA, mark_self_authored_on_jira("a marked one")),
        _comment("5", STRANGER, f"approve {JIRA_RELAY_MARKER}"),
    ]
    client.by_project["PROJ"] = [_issue()]
    provider = _provider(client)
    [item] = provider.listing().items
    comments = provider.list_comments(item)
    assert [c.author for c in comments] == [ADA, BOT, BOT, ADA, STRANGER]
    assert [provider.comment_origin(c) for c in comments] == [
        "human",
        "self",
        "relay",
        "self",
        "human",
    ]


def test_a_rotated_credentials_service_account_is_the_one_read():
    """The provider keeps no copy of the service account's id: the client owns that
    cache and resets it when the credential changes, so after a rotation the new
    account's comments are the-loop's own, and the old account's are a person's."""
    new_bot = "5b10-the-new-bot"
    client = SearchingFake(account_id=BOT)
    client.comment_table[KEY] = [
        _comment("1", BOT, mark_relayed_on_jira("> approved")),
        _comment("2", new_bot, mark_relayed_on_jira("> approved")),
    ]
    client.by_project["PROJ"] = [_issue()]
    provider = _provider(client)
    [item] = provider.listing().items
    origins = [provider.comment_origin(c) for c in provider.list_comments(item)]
    assert origins == ["relay", "human"]
    client.account_id = new_bot  # the credential was rotated to another account
    origins = [provider.comment_origin(c) for c in provider.list_comments(item)]
    assert origins == ["human", "relay"]


def test_comment_event_is_an_issue_comment_flagged_as_jira():
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    client.comment_table[KEY] = [_comment("10001", ADA, "please look")]
    provider = _provider(client)
    [item] = provider.listing().items
    [comment] = provider.list_comments(item)
    refs = provider.refs(item)
    event = provider.comment_event(item, comment, refs)
    assert event.event == "issue_comment" and event.action == "created"
    assert event.delivery_id == f"jira-comment-{SITE}-10001"
    assert event.work_items == [REF] and event.labeled is False
    assert event.payload[PROVIDER_KEY] == "jira"
    assert RELAY_KEY not in event.payload
    assert event.payload["comment"]["user"]["login"] == ADA
    assert event.payload["comment"]["body"] == "please look"
    assert event.payload["issue"]["number"] == 7
    assert "repository" not in event.payload
    assert event_provider(event) == "jira"


def test_a_relay_event_carries_the_relay_flag():
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    client.comment_table[KEY] = [_comment("9", BOT, mark_relayed_on_jira("> ok"))]
    provider = _provider(client)
    [item] = provider.listing().items
    [comment] = provider.list_comments(item)
    event = provider.comment_event(item, comment, provider.refs(item))
    assert event.payload[RELAY_KEY] is True


def test_presence_event_carries_the_configured_label_spelling():
    """The dispatcher's arming check reads the configured spelling (issue-381)."""
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    provider = _provider(client)
    [item] = provider.listing().items
    event = provider.presence_event(item, provider.refs(item))
    assert event.labeled is True and event.work_items == [REF]
    names = {label["name"] for label in event.payload["issue"]["labels"]}
    assert {LABEL, JLABEL} <= names
    assert event.payload[PROVIDER_KEY] == "jira"


def test_owns_only_its_sites_polled_projects():
    provider = _provider(projects=("PROJ",))
    assert provider.owns(REF) is True
    assert provider.owns(WorkItemRef.parse("jira:other.atlassian.net/PROJ-7")) is False
    assert provider.owns(WorkItemRef.parse(f"jira:{SITE}/OPS-7")) is False
    assert provider.owns(WorkItemRef.parse("github:acme/web#7")) is False
    assert provider.scope_of(REF) == "PROJ"
    assert provider.scope_of(WorkItemRef.parse("github:acme/web#7")) == ""


# -- closure (R5.4) ----------------------------------------------------------------------


def test_done_status_category_is_closure():
    client = SearchingFake(account_id=BOT)
    client.issues[KEY] = JiraIssue(
        key=KEY, summary="t", status_category="done", url=f"https://{SITE}/browse/{KEY}"
    )
    provider = _provider(client)
    closure = provider.closure(REF)
    assert closure is not None and closure.state == "closed"
    event = provider.closure_event(REF, closure)
    assert event.event == "issues" and event.action == "closed"
    assert event.work_items == [REF] and event.payload[PROVIDER_KEY] == "jira"
    assert event.delivery_id.startswith("poll-close-")


def test_an_open_ticket_is_not_closed():
    client = SearchingFake(account_id=BOT)
    client.issues[KEY] = JiraIssue(key=KEY, status_category="indeterminate")
    assert _provider(client).closure(REF) is None


def test_an_unreachable_jira_never_answers_closure():
    client = SearchingFake(account_id=BOT)
    client.fail_on["get_issue"] = http_error(503, "unavailable")
    with pytest.raises(ProviderError):
        _provider(client).closure(REF)


# -- configuration (R5.1) ---------------------------------------------------------------


def test_from_source_builds_a_provider_from_the_cli_config():
    provider = build_provider(
        {"provider": "jira", "projects": ["PROJ"]},
        default_labels=[LABEL],
        config=_cli_config(),
    )
    assert isinstance(provider, JiraPollProvider)
    assert provider.projects == ["PROJ"] and provider.site == SITE
    assert provider.describe() == f"jira {SITE} PROJ"


def test_polling_a_mirror_only_project_is_a_config_error():
    with pytest.raises(ProviderError, match="mirror-only"):
        JiraPollProvider.from_source(
            {"provider": "jira", "projects": ["OPS"]},
            default_labels=[LABEL],
            config=_cli_config(),
        )


def test_polling_an_unconfigured_project_is_a_config_error():
    with pytest.raises(ProviderError, match="NOPE"):
        JiraPollProvider.from_source(
            {"provider": "jira", "projects": ["NOPE"]},
            default_labels=[LABEL],
            config=_cli_config(),
        )


def test_a_jira_source_without_the_jira_integration_is_a_config_error():
    with pytest.raises(ProviderError, match="integrations.jira"):
        JiraPollProvider.from_source(
            {"provider": "jira", "projects": ["PROJ"]},
            default_labels=[LABEL],
            config={},
        )


def test_a_jira_source_without_projects_is_a_config_error():
    with pytest.raises(ProviderError, match="projects"):
        JiraPollProvider.from_source(
            {"provider": "jira"}, default_labels=[LABEL], config=_cli_config()
        )


def test_the_daemon_builds_the_jira_source_with_the_whole_config():
    from the_loop.poller.daemon import _build_providers

    data = _cli_config()
    data["polling"] = {"sources": [{"provider": "jira", "projects": ["PROJ"]}]}
    [provider] = _build_providers(data, default_labels=[LABEL])
    assert isinstance(provider, JiraPollProvider)


def _schema_errors(document: Dict[str, Any]) -> list:
    jsonschema = pytest.importorskip("jsonschema")
    from the_loop import configschema

    ours = configschema.validate(document)
    try:
        jsonschema.validate(document, configschema.load_schema("cli-config"))
        theirs = True
    except jsonschema.ValidationError:
        theirs = False
    assert (not ours) == theirs, (ours, document)
    return ours


def test_schema_accepts_a_jira_polling_source():
    document = {"polling": {"sources": [{"provider": "jira", "projects": ["PROJ"]}]}}
    assert _schema_errors(document) == []


@pytest.mark.parametrize(
    "source",
    [
        {"provider": "jira"},  # no projects
        {"provider": "jira", "projects": []},
        {"provider": "jira", "projects": ["proj"]},  # not a key
        {"provider": "jira", "projects": ['P" OR 1=1']},
    ],
)
def test_schema_refuses_a_jira_source_without_valid_projects(source):
    assert _schema_errors({"polling": {"sources": [source]}})


# -- the core, end to end through a real dispatcher (R5.3, R5.6) -------------------------


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _poller(tmp_path, client):
    registry = SessionRegistry(tmp_path / "sessions")
    tmux = FakeTmux()
    config = RoutingConfig.from_mapping(
        {
            "authorizedUsers": [{"name": "Ada", "github": "ada", "jira": ADA}],
            "spawnOnUnmatched": "labeled",
        },
        None,
    )
    config.control = ControlConfig()
    config.portable_dir = str(tmp_path / "portable")
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=tmux,
        cli_config=_cli_config(),
    )
    poller = Poller(
        providers=[_provider(client)],
        registry=registry,
        dispatcher=dispatcher,
        config=PollConfig(max_retries=3),
        state=PollState(WorkItemStore(tmp_path / "portable")),
        authorized_users=["ada"],
    )
    registry.register(
        Session(
            work_item=REF,
            harness="claude",
            harness_session_id="sess-7",
            cwd=str(tmp_path),
            tmux_target=f"loop-{REF.slug}",
        )
    )
    return registry, tmux, dispatcher, poller


def test_rate_limited_scope_keeps_cursor(tmp_path):
    """R5.6: a 429 degrades the scope for the cycle; nothing dropped or doubled.

    Given an armed ticket with a live session and one forwarded comment
    When the next cycle is rate-limited and a new comment arrives meanwhile
    Then nothing is forwarded on the limited cycle
    And on recovery the new comment is forwarded once and the old one never again
    """
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    client.comment_table[KEY] = [_comment("1", ADA, "zz-first")]
    _, tmux, dispatcher, poller = _poller(tmp_path, client)
    try:
        poller.poll_once()  # first sight: baseline "1"
        client.comment_table[KEY].append(_comment("2", ADA, "zz-second"))
        client.search_fails["PROJ"] = http_error(429, "rate limited")
        summary = poller.poll_once()
        assert summary is not None
        time.sleep(0.1)
        assert tmux.delivers == []
        del client.search_fails["PROJ"]
        poller.poll_once()
        assert _wait(lambda: len(tmux.delivers) == 1)
        poller.poll_once()
        time.sleep(0.1)
    finally:
        dispatcher.stop()
    [(ref, prompt)] = tmux.delivers
    assert ref == REF.ref and "zz-second" in prompt and "zz-first" not in prompt


def test_an_unlisted_or_self_comment_is_never_forwarded(tmp_path):
    """Abuse cases 3 and 4 on the poll path; and the relay addendum both ways."""
    client = SearchingFake(account_id=BOT)
    client.by_project["PROJ"] = [_issue()]
    client.comment_table[KEY] = []
    _, tmux, dispatcher, poller = _poller(tmp_path, client)
    try:
        poller.poll_once()  # first sight, nothing to baseline
        client.comment_table[KEY] = [
            _comment("11", STRANGER, "zz-stranger-text"),
            _comment("12", BOT, "zz-unmarked-bot"),
            _comment("13", ADA, mark_self_authored_on_jira("zz-marked-by-us")),
            _comment("14", STRANGER, f"zz-pasted-relay {JIRA_RELAY_MARKER}"),
            _comment("15", ADA, "from ada"),
            _comment("16", BOT, mark_relayed_on_jira("> relayed answer")),
        ]
        poller.poll_once()
        assert _wait(lambda: len(tmux.delivers) == 2)
        time.sleep(0.1)
    finally:
        dispatcher.stop()
    bodies = " ".join(prompt for _, prompt in tmux.delivers)
    assert "from ada" in bodies and "relayed answer" in bodies
    for dropped in ("zz-stranger", "zz-unmarked-bot", "zz-marked", "zz-pasted"):
        assert dropped not in bodies
