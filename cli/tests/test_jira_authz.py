"""Jira identities on the allow-list (issue-475, task 4.1, T5/T7, R7.1–R7.3).

A Jira comment is authorized exactly as a GitHub one is — by an exact id on the
one allow-list, ``routing.authorizedUsers`` — but on the **Jira** id: the Cloud
``accountId`` or the Data Center user ``key``, never a display name, an email or a
GitHub login. Two rules differ from GitHub on purpose:

* a **missing** actor is unauthorized on Jira (GitHub's "no actor means CI"
  exemption carries no meaning there — every Jira event the-loop acts on is a
  person's comment or a fetched issue state);
* the ingress decides, per comment, whether it is the-loop's own, a **relay** of
  an authorized person's words from another channel, or a human's — the design
  addendum to PR 3's ledger (the relay marker), so a Slack-relayed gate answer is
  read as the operator's words on Jira as it is on GitHub.

Spec: docs/specs/issue-475/design.md §C8 (allow-list), §Security design boundary 2,
abuse case 3; requirements R7.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List

import pytest

from the_loop.authz import (
    JIRA_RELAY_MARKER,
    JIRA_SELF_MARKER,
    is_authorized,
    is_authorized_on,
    is_self_authored,
    jira_comment_origin,
    mark_relayed_on_jira,
    mark_self_authored_on_jira,
)
from the_loop.identity import parse_authorized_users
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import (
    PROVIDER_KEY,
    RELAY_KEY,
    Router,
    RoutedEvent,
    event_provider,
    event_relayed,
)

SITE = "acme.atlassian.net"
ADA = "5b10ac8d82e05b22cc7d4ef5"  # a Cloud accountId
BOT = "5b10-the-loop-bot"  # the service account
DC_KEY = "JIRAUSER10100"  # a Data Center user key
REF = WorkItemRef.parse(f"jira:{SITE}/PROJ-7")
GH_REF = WorkItemRef.parse("github:acme/web#7")

PRINCIPALS = parse_authorized_users(
    [
        {"name": "Ada", "github": "ada", "jira": ADA},
        {"name": "Dee", "jira": DC_KEY},
        "octocat",
    ]
)


# -- is_authorized_on --------------------------------------------------------------


def test_exact_account_id_is_authorized_on_jira():
    assert is_authorized_on("jira", ADA, PRINCIPALS) is True


@pytest.mark.parametrize(
    "actor",
    [
        ADA.upper(),  # ids are matched exactly, never case-folded
        ADA[:-1],  # nor by prefix
        f" {ADA}",
        "Ada",  # a display name is not an identity (R7.3)
        "ada@acme.example",  # nor is an email
    ],
)
def test_jira_id_is_matched_exactly(actor):
    assert is_authorized_on("jira", actor, PRINCIPALS) is False


def test_unlisted_author_is_unauthorized_on_jira():
    assert is_authorized_on("jira", "557058:f00d-stranger", PRINCIPALS) is False


@pytest.mark.parametrize("actor", [None, ""])
def test_missing_actor_is_unauthorized_on_jira(actor):
    """R7.2: no actor is not an exemption on Jira — unlike GitHub's CI rule."""
    assert is_authorized_on("jira", actor, PRINCIPALS) is False
    # The GitHub rule is unchanged: an actor-less (CI) event is allowed there.
    assert is_authorized(actor, ["octocat"]) is True


def test_data_center_user_key_is_authorized_on_jira():
    assert is_authorized_on("jira", DC_KEY, PRINCIPALS) is True
    assert is_authorized_on("jira", DC_KEY.lower(), PRINCIPALS) is False


def test_a_github_login_never_authorizes_on_jira_and_back():
    """One person, one id per channel: neither id stands in for the other."""
    assert is_authorized_on("jira", "ada", PRINCIPALS) is False
    assert is_authorized_on("jira", "octocat", PRINCIPALS) is False
    assert is_authorized_on("github", ADA, PRINCIPALS) is False
    assert is_authorized_on("github", "ada", PRINCIPALS) is True


def test_an_empty_allow_list_authorizes_nobody_on_jira():
    assert is_authorized_on("jira", ADA, []) is False


# -- the schema: authorizedUsers[].jira ----------------------------------------------


def _verdict(document: Dict[str, Any]) -> list:
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


def test_schema_accepts_a_jira_id_on_an_authorized_user():
    document = {
        "routing": {"authorizedUsers": [{"name": "Ada", "github": "ada", "jira": ADA}]}
    }
    assert _verdict(document) == []


@pytest.mark.parametrize("value", [["a", "b"], {"id": ADA}, 7, ""])
def test_schema_refuses_a_jira_id_that_is_not_one_string(value):
    document = {"routing": {"authorizedUsers": [{"name": "Ada", "jira": value}]}}
    assert _verdict(document)


def test_the_jira_id_is_documented_on_the_schema():
    from the_loop import configschema

    schema = configschema.load_schema("cli-config")
    entry = schema["properties"]["routing"]["properties"]["authorizedUsers"]["items"]
    assert "jira" in entry["properties"]
    assert "accountId" in entry["properties"]["jira"]["description"]


# -- whose comment is it? (the relay addendum) -----------------------------------------


def test_a_marked_comment_is_the_loops_own_whoever_posted_it():
    body = mark_self_authored_on_jira("Approved.")
    assert jira_comment_origin(body, ADA, BOT) == "self"
    assert jira_comment_origin(body, BOT, BOT) == "self"


def test_an_unmarked_service_account_comment_is_the_loops_own():
    """The author test, independent of the text (abuse case 4, author variant)."""
    assert jira_comment_origin("Approved.", BOT, BOT) == "self"


def test_a_service_account_relay_is_a_relay():
    body = mark_relayed_on_jira("> approved")
    assert JIRA_RELAY_MARKER in body and JIRA_SELF_MARKER not in body
    assert not is_self_authored(body)
    assert jira_comment_origin(body, BOT, BOT) == "relay"


def test_a_relay_that_also_carries_the_agent_marker_is_the_loops_own():
    body = mark_self_authored_on_jira(mark_relayed_on_jira("> approved"))
    assert jira_comment_origin(body, BOT, BOT) == "self"


def test_relay_marker_from_other_user_grants_nothing():
    """A person who types the relay marker is still just that person.

    The marker means something only on a comment the service account wrote; on
    anyone else's it is text, and the comment is judged by its own author.
    """
    body = f"approved, ship it\n\n{JIRA_RELAY_MARKER}"
    assert jira_comment_origin(body, "557058:f00d-stranger", BOT) == "human"
    assert is_authorized_on("jira", "557058:f00d-stranger", PRINCIPALS) is False
    # An authorized person who pastes it gains nothing either: still "human".
    assert jira_comment_origin(body, ADA, BOT) == "human"


def test_without_the_service_account_id_nothing_is_a_relay():
    """`myself` unreadable: the relay test cannot be made, so it fails closed."""
    body = mark_relayed_on_jira("> approved")
    assert jira_comment_origin(body, BOT, "") == "human"
    assert is_authorized_on("jira", BOT, PRINCIPALS) is False


def test_mark_relayed_on_jira_is_idempotent():
    once = mark_relayed_on_jira("> the-loop execute")
    assert mark_relayed_on_jira(once) == once
    assert "the-loop execute" in once  # keywords kept: ingress acts on them


# -- the router: jira events are judged on jira ids ---------------------------------------


def _jira_payload(author: str, body: str = "please look", relayed: bool = False):
    payload: Dict[str, Any] = {
        PROVIDER_KEY: "jira",
        "action": "created",
        "issue": {
            "number": 7,
            "key": "PROJ-7",
            "title": "t",
            "html_url": f"https://{SITE}/browse/PROJ-7",
            "labels": [],
        },
        "comment": {
            "id": "10001",
            "body": body,
            "html_url": f"https://{SITE}/browse/PROJ-7?focusedCommentId=10001",
            "user": {"login": author},
        },
    }
    if relayed:
        payload[RELAY_KEY] = True
    return payload


def _router(**kw: Any) -> Router:
    return Router(
        authorized_users=["octocat", "ada"],
        principals=PRINCIPALS,
        repositories={"github.com/acme/web"},
        **kw,
    )


def test_jira_comment_from_unlisted_author_is_ignored():
    """Abuse case 3: an unlisted Jira author's comment is dropped at ingress."""
    routed = _router().route(
        "issue_comment",
        _jira_payload("557058:f00d-stranger"),
        f"jira-comment-{SITE}-10001",
        work_items=[REF],
    )
    assert routed is None


def test_jira_comment_from_listed_author_is_routed():
    routed = _router().route(
        "issue_comment", _jira_payload(ADA), f"jira-comment-{SITE}-10001", [REF]
    )
    assert routed is not None and routed.work_items == [REF]
    assert event_provider(routed) == "jira"


def test_jira_comment_without_an_author_is_ignored():
    assert (
        _router().route("issue_comment", _jira_payload(""), "jira-comment-x-1", [REF])
        is None
    )


def test_a_github_login_on_a_jira_comment_is_not_authorized():
    """`ada` is Ada's GitHub login: on a Jira comment it names nobody."""
    assert (
        _router().route(
            "issue_comment", _jira_payload("ada"), "jira-comment-x-2", [REF]
        )
        is None
    )


def test_jira_events_are_not_bounded_by_the_github_repositories():
    """The GitHub repository bound has nothing to say about a Jira ticket."""
    router = _router()
    router.repositories = set()  # nothing declared on GitHub at all
    routed = router.route(
        "issue_comment", _jira_payload(ADA), "jira-comment-x-3", work_items=[REF]
    )
    assert routed is not None


def test_a_relay_flag_is_authorized_on_jira():
    routed = _router().route(
        "issue_comment",
        _jira_payload(BOT, mark_relayed_on_jira("> approved"), relayed=True),
        "jira-comment-x-4",
        [REF],
    )
    assert routed is not None and event_relayed(routed) is True


def test_a_github_delivery_claiming_to_be_jira_is_refused():
    """Only the in-process Jira ingress names a provider; a pushed body cannot."""
    payload = _jira_payload(ADA)
    payload["repository"] = {"full_name": "acme/web"}
    assert _router().route("issue_comment", payload, "gh-delivery-1") is None


def test_the_provider_and_relay_flags_need_jira_refs():
    """A payload flag alone never makes a GitHub work item's event a Jira one."""
    payload = _jira_payload(ADA, relayed=True)
    routed = RoutedEvent("issue_comment", "created", "d", [GH_REF], payload)
    assert event_provider(routed) == "github" and event_relayed(routed) is False


def test_github_routing_is_unchanged_for_a_github_event():
    payload = {
        "action": "created",
        "repository": {
            "full_name": "acme/web",
            "html_url": "https://github.com/acme/web",
        },
        "issue": {"number": 7, "labels": []},
        "comment": {"id": 1, "body": "hi", "user": {"login": "octocat"}},
    }
    routed = _router().route("issue_comment", copy.deepcopy(payload), "gh-2")
    assert routed is not None and routed.work_items == [GH_REF]
    assert event_provider(routed) == "github"
    stranger = copy.deepcopy(payload)
    stranger["comment"]["user"]["login"] = ADA  # a Jira id is not a GitHub login
    assert _router().route("issue_comment", stranger, "gh-3") is None


# -- the dispatcher's named-actor re-check ---------------------------------------------


def _dispatcher(tmp_path):
    from conftest import FakeTmux, StubInteractiveAdapter

    from the_loop.control import ControlConfig
    from the_loop.sessions import SessionRegistry
    from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig

    config = RoutingConfig.from_mapping(
        {
            "authorizedUsers": [
                {"name": "Ada", "github": "ada", "jira": ADA},
                "octocat",
            ],
            "spawnOnUnmatched": "labeled",
        },
        None,
    )
    config.control = ControlConfig()
    config.portable_dir = str(tmp_path / "portable")
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": StubInteractiveAdapter()},
        config=config,
        tmux_runner=FakeTmux(),
    )


def _command(author: str, relayed: bool = False, body: str = "the-loop pause"):
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=f"jira-comment-{SITE}-{author}-{time.monotonic_ns()}",
        work_items=[REF],
        payload=_jira_payload(author, body, relayed=relayed),
    )


@pytest.mark.parametrize(
    "author, relayed, recorded",
    [
        (ADA, False, True),  # a listed Jira id
        ("ada", False, False),  # Ada's GitHub login is not her Jira id
        ("557058:f00d-stranger", False, False),
        (BOT, True, True),  # the service account's relay: the operator's words
    ],
)
def test_a_control_command_on_jira_needs_a_named_jira_actor(
    tmp_path, author, relayed, recorded
):
    dispatcher = _dispatcher(tmp_path)
    try:
        dispatcher.handle(_command(author, relayed=relayed))
        records: List[Any] = [dispatcher.control_store.get(REF.ref)]
    finally:
        dispatcher.stop()
    assert (records[0] is not None) is recorded


# -- the human gates: a Jira author in the gate's Jira namespace (task 4.4) --------------


def test_a_github_only_gate_list_is_unchanged():
    from the_loop.authz import gate_authorized_users

    principals = parse_authorized_users(["octocat", {"github": "ada", "slack": "U1"}])
    assert gate_authorized_users(["octocat", "ada"], principals) == ["octocat", "ada"]


def test_a_jira_deployments_gate_list_names_jira_ids_in_their_namespace():
    from the_loop.authz import JIRA_RELAY_GATE_AUTHOR, gate_authorized_users

    allowed = gate_authorized_users(["octocat", "ada"], PRINCIPALS, jira=True)
    assert allowed == [
        "octocat",
        "ada",
        f"jira:{ADA}",
        f"jira:{DC_KEY}",
        JIRA_RELAY_GATE_AUTHOR,
    ]
    assert ADA not in allowed, "a bare Jira id is a GitHub login's namespace"


def test_comments_from_names_a_jira_author_in_the_jira_namespace():
    from the_loop.authz import JIRA_RELAY_GATE_AUTHOR
    from the_loop.graphlink import comments_from

    human = RoutedEvent(
        "issue_comment", "created", "d", [REF], _jira_payload(ADA, "ok")
    )
    assert comments_from(human) == [{"author": f"jira:{ADA}", "body": "ok"}]
    relay = RoutedEvent(
        "issue_comment", "created", "d", [REF], _jira_payload(BOT, "ok", relayed=True)
    )
    assert comments_from(relay) == [{"author": JIRA_RELAY_GATE_AUTHOR, "body": "ok"}]


def test_a_github_account_named_like_a_jira_id_never_passes_as_that_person():
    """A GitHub login equal to a listed accountId reaches a gate as itself."""
    from the_loop.authz import gate_authorized_users
    from the_loop.graphlink import comments_from

    payload = {
        "action": "created",
        "comment": {"id": 1, "body": "approved", "user": {"login": ADA}},
    }
    routed = RoutedEvent("issue_comment", "created", "d", [GH_REF], payload)
    [comment] = comments_from(routed)
    allowed = gate_authorized_users(["octocat"], PRINCIPALS, jira=True)
    assert comment["author"] == ADA and comment["author"] not in allowed
