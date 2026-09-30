"""The daemon's GitHub client, proved against PyGithub itself (issue-442, T1/T7/T8).

Every test here runs the real :class:`the_loop.ghapi.GitHubClient` over the real
PyGithub, with HTTP replaced by PyGithub's own connection-injection hook
(``ghreplay``): what is asserted is the verb, path, body and headers PyGithub
sent, not a fake of them. No network.
"""

from __future__ import annotations

import logging

import pytest

from the_loop.ghapi import (
    LIST_LIMIT,
    PAGE_SIZE,
    GhComment,
    GhItem,
    GitHubApiConfig,
    GitHubApiError,
    GitHubClient,
)

OWNER, REPO = "octo", "repo"
GHE = "ghe.corp.example"
LABEL = "the-loop: auto-execute"


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_test_token_1234567890")
    return "ghp_test_token_1234567890"


@pytest.fixture
def client(token):
    return GitHubClient(GitHubApiConfig(), timeout=7)


def _page_info(has_next=False, cursor=None):
    return {"hasNextPage": has_next, "endCursor": cursor}


# -- the credential and the base ------------------------------------------------


def test_the_config_reads_the_api_block_and_defaults_the_variables():
    api = GitHubApiConfig.from_cli_config(
        {
            "integrations": {
                "github": {
                    "api": {"tokenEnv": ["A", "B"], "baseUrl": "https://ghe/api/v3/"}
                }
            }
        }
    )
    assert api == GitHubApiConfig(token_envs=("A", "B"), base_url="https://ghe/api/v3")
    assert GitHubApiConfig.from_cli_config({}) == GitHubApiConfig()
    assert GitHubApiConfig.from_mapping({"tokenEnv": "ONE"}).token_envs == ("ONE",)
    assert GitHubApiConfig.from_mapping(None) == GitHubApiConfig()


def test_the_token_is_the_first_set_variable_read_at_call_time(monkeypatch):
    api = GitHubApiConfig(token_envs=("FIRST", "SECOND"))
    monkeypatch.delenv("FIRST", raising=False)
    monkeypatch.setenv("SECOND", " second ")
    assert api.token() == "second"
    monkeypatch.setenv("FIRST", "first")
    assert api.token() == "first"
    assert api.token({}) == ""
    assert api.missing_token_reason == "no GitHub token: set FIRST or SECOND"


def test_a_missing_token_is_the_one_error_a_variable_fixes(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    client = GitHubClient(GitHubApiConfig())
    assert client.has_token() is False
    with pytest.raises(GitHubApiError) as exc:
        client.post_comment(OWNER, REPO, 1, "hi")
    assert exc.value.missing_token and exc.value.status is None
    assert str(exc.value) == "no GitHub token: set GH_TOKEN or GITHUB_TOKEN"


def test_every_request_carries_the_bearer_token_and_the_loops_agent(
    client, github_replay, token
):
    github_replay.on("GET", "/user", 200, {"login": "the-loop-bot"})
    assert client.viewer_login() == "the-loop-bot"
    (exchange,) = github_replay.exchanges
    assert exchange.authorization == f"token {token}"
    assert exchange.headers["User-Agent"] == "the-loop"
    assert exchange.host == "api.github.com"


def test_the_github_is_built_without_a_rate_limit_sleep(client):
    """A5 — connection-level retries and the caller's timeout, never `GithubRetry`."""
    from github.GithubRetry import GithubRetry

    gh = client.github()
    requester = gh.requester
    assert not isinstance(requester._Requester__retry, GithubRetry)
    assert requester._Requester__retry == 2
    assert requester._Requester__timeout == 7
    assert requester._Requester__seconds_between_requests is None
    assert requester._Requester__seconds_between_writes is None
    assert requester.per_page == PAGE_SIZE


def test_one_github_per_host_and_token(client, monkeypatch):
    first = client.github()
    assert client.github() is first
    assert client.github("github.com") is first
    ghe = client.github(GHE)
    assert ghe is not first and ghe.requester.base_url == f"https://{GHE}/api/v3"
    monkeypatch.setenv("GH_TOKEN", "rotated-token-0987654321")
    assert client.github() is not first  # a rotated token builds a new one


def test_an_explicit_enterprise_base_is_honoured_for_every_host(token):
    client = GitHubClient(GitHubApiConfig(base_url="https://explicit.example/api/v3"))
    assert client.github().requester.base_url == "https://explicit.example/api/v3"
    assert client.github(GHE).requester.base_url == "https://explicit.example/api/v3"


def test_a_value_that_is_not_a_host_never_builds_a_base(client, github_replay):
    """A3 — a hostile third segment cannot point the token at another API."""
    for bad in ("https://evil.example/api", "evil.example/x", "ghe"):
        with pytest.raises(GitHubApiError, match="not a GitHub host"):
            client.get_issue(OWNER, REPO, 1, host=bad)
    assert github_replay.exchanges == []


def test_shared_clients_are_one_per_config_and_timeout():
    a = GitHubClient.shared(GitHubApiConfig(), timeout=30)
    assert GitHubClient.shared(GitHubApiConfig(), timeout=30) is a
    assert GitHubClient.shared(GitHubApiConfig(), timeout=10) is not a
    assert GitHubClient.shared(GitHubApiConfig(token_envs=("X",))) is not a


# -- O1 comments ---------------------------------------------------------------


def test_post_comment_is_one_post_on_the_issues_endpoint(client, github_replay):
    github_replay.on(
        "POST",
        "/repos/octo/repo/issues/15/comments",
        201,
        {"id": 1, "html_url": "https://github.com/octo/repo/issues/15#issuecomment-9"},
    )
    url = client.post_comment(OWNER, REPO, 15, "hello")
    assert url == "https://github.com/octo/repo/issues/15#issuecomment-9"
    (exchange,) = github_replay.exchanges  # no GET to "complete" the lazy issue
    assert (exchange.verb, exchange.path) == (
        "POST",
        "/repos/octo/repo/issues/15/comments",
    )
    assert exchange.json == {"body": "hello"}


def test_a_hosted_comment_goes_to_that_hosts_api(client, github_replay):
    github_replay.on(
        "POST", "/api/v3/repos/octo/repo/issues/15/comments", 201, {"html_url": "u"}
    )
    assert client.post_comment(OWNER, REPO, 15, "hi", host=GHE) == "u"
    (exchange,) = github_replay.exchanges
    assert (
        exchange.host == GHE
        and exchange.path == "/api/v3/repos/octo/repo/issues/15/comments"
    )


def test_a_response_without_a_url_is_still_a_posted_comment(client, github_replay):
    github_replay.on("POST", "/repos/octo/repo/issues/15/comments", 201, {"id": 1})
    assert client.post_comment(OWNER, REPO, 15, "hello") == ""


# -- O2 issues -----------------------------------------------------------------


def test_create_issue_sends_labels_on_the_same_request(client, github_replay):
    github_replay.on(
        "POST",
        "/repos/octo/repo/issues",
        201,
        {"number": 42, "html_url": "https://github.com/octo/repo/issues/42"},
    )
    assert client.create_issue(OWNER, REPO, "T", "B", ["a", " ", "b"]) == (
        42,
        "https://github.com/octo/repo/issues/42",
    )
    (exchange,) = github_replay.exchanges
    assert exchange.json == {"title": "T", "body": "B", "labels": ["a", "b"]}
    github_replay.exchanges.clear()
    client.create_issue(OWNER, REPO, "T", "B")
    assert github_replay.exchanges[0].json == {"title": "T", "body": "B"}


def test_create_issue_without_a_number_is_an_error(client, github_replay):
    github_replay.on("POST", "/repos/octo/repo/issues", 201, {"html_url": "u"})
    with pytest.raises(GitHubApiError, match="no issue number"):
        client.create_issue(OWNER, REPO, "T", "B")


# -- O3 / O10 the issues document -------------------------------------------------


def test_get_issue_reads_the_one_endpoint_that_answers_for_both_kinds(
    client, github_replay
):
    github_replay.on(
        "GET", "/repos/octo/repo/issues/15", 200, {"number": 15, "state": "open"}
    )
    assert client.get_issue(OWNER, REPO, 15) == {"number": 15, "state": "open"}
    assert github_replay.exchanges[0].path == "/repos/octo/repo/issues/15"


def test_a_404_is_not_found_and_every_other_status_is_not(client, github_replay):
    with pytest.raises(GitHubApiError) as exc:
        client.get_issue(OWNER, REPO, 99)
    assert exc.value.not_found and exc.value.status == 404
    assert str(exc.value) == "GitHub 404: Not Found"
    github_replay.on(
        "GET", "/repos/octo/repo/issues/98", 401, {"message": "Bad credentials"}
    )
    with pytest.raises(GitHubApiError) as exc:
        client.get_issue(OWNER, REPO, 98)
    assert (exc.value.status, exc.value.not_found) == (401, False)
    assert str(exc.value) == "GitHub 401: Bad credentials"


def test_item_state_reads_closure_kind_merge_and_closer(client, github_replay):
    github_replay.on(
        "GET",
        "/repos/octo/repo/issues/16",
        200,
        {
            "number": 16,
            "state": "closed",
            "title": "t",
            "html_url": "u",
            "pull_request": {"merged_at": "2026"},
            "closed_by": {"login": "octocat"},
        },
    )
    state = client.item_state(OWNER, REPO, 16)
    assert (state.is_pr, state.merged, state.closed_by, state.open) == (
        True,
        True,
        "octocat",
        False,
    )
    github_replay.on(
        "GET", "/repos/octo/repo/issues/17", 200, {"number": 17, "state": "open"}
    )
    assert client.item_state(OWNER, REPO, 17).open is True


def test_an_empty_document_is_an_error_not_an_open_item(client, github_replay):
    github_replay.on("GET", "/repos/octo/repo/issues/15", 200, {})
    with pytest.raises(GitHubApiError, match="returned no object"):
        client.get_issue(OWNER, REPO, 15)


# -- O4 reactions ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,path",
    [
        ("issue", "/repos/octo/repo/issues/15/reactions"),
        ("issue-comment", "/repos/octo/repo/issues/comments/15/reactions"),
        ("review-comment", "/repos/octo/repo/pulls/comments/15/reactions"),
    ],
)
def test_a_rest_reaction_posts_to_the_endpoint_of_its_kind(
    client, github_replay, kind, path
):
    github_replay.on("POST", path, 201, {"id": 1})
    client.add_reaction(OWNER, REPO, kind, 15, "eyes")
    (exchange,) = github_replay.exchanges
    assert (exchange.verb, exchange.path, exchange.json) == (
        "POST",
        path,
        {"content": "eyes"},
    )


def test_a_node_reaction_is_the_graphql_mutation_with_variables(client, github_replay):
    github_replay.graphql("addReaction", {"addReaction": {"clientMutationId": None}})
    client.add_reaction_by_node("IC_kwDOabc", "hooray")
    (exchange,) = github_replay.exchanges
    assert exchange.path == "/graphql"
    assert exchange.json["variables"] == {
        "subjectId": "IC_kwDOabc",
        "content": "HOORAY",
    }
    assert "IC_kwDOabc" not in exchange.json["query"]  # A6: values travel as variables


def test_reactions_refuse_an_unknown_content_or_a_bad_target_before_any_request(
    client, github_replay
):
    with pytest.raises(GitHubApiError, match="unknown reaction"):
        client.add_reaction(OWNER, REPO, "issue", 15, "sparkles")
    with pytest.raises(GitHubApiError, match="unknown reaction target"):
        client.add_reaction(OWNER, REPO, "gist", 15, "eyes")
    with pytest.raises(GitHubApiError, match="unusable node id"):
        client.add_reaction_by_node("IC_k;rm -rf /", "eyes")
    with pytest.raises(GitHubApiError, match="unusable id"):
        client.add_reaction(OWNER, REPO, "issue", "15;x", "eyes")
    assert github_replay.exchanges == []


# -- O11 labels -----------------------------------------------------------------


def test_add_labels_posts_and_never_replaces(client, github_replay):
    github_replay.on("POST", "/repos/octo/repo/issues/15/labels", 200, [])
    client.add_labels(OWNER, REPO, 15, ["loop:design", ""])
    (exchange,) = github_replay.exchanges
    assert exchange.verb == "POST" and exchange.json == ["loop:design"]
    client.add_labels(OWNER, REPO, 15, [])
    assert len(github_replay.exchanges) == 1  # nothing to add, nothing sent


def test_ensure_label_treats_an_existing_label_as_success(client, github_replay):
    github_replay.on("POST", "/repos/octo/repo/labels", 201, {"name": "loop:design"})
    assert client.ensure_label(OWNER, REPO, "loop:design") is True
    assert github_replay.exchanges[0].json == {"name": "loop:design", "color": "ededed"}
    github_replay.on(
        "POST",
        "/repos/octo/repo/labels",
        422,
        {"message": "Validation Failed", "errors": [{"code": "already_exists"}]},
    )
    github_replay.routes.insert(0, github_replay.routes.pop())
    assert client.ensure_label(OWNER, REPO, "loop:design") is False


def test_remove_label_treats_an_absent_label_as_success_and_quotes_the_name(
    client, github_replay
):
    github_replay.on(
        "DELETE", "/repos/octo/repo/issues/15/labels/loop%3Adesign", 200, []
    )
    assert client.remove_label(OWNER, REPO, 15, "loop:design") is True
    assert client.remove_label(OWNER, REPO, 15, "never-there") is False  # 404
    assert (
        github_replay.exchanges[-1].path
        == "/repos/octo/repo/issues/15/labels/never-there"
    )


def test_labels_of_reads_every_page(client, github_replay):
    github_replay.on(
        "GET", "/repos/octo/repo/issues/15/labels", 200, [{"name": "a"}, {"name": None}]
    )
    assert client.labels_of(OWNER, REPO, 15) == ["a"]


# -- O5 viewer ------------------------------------------------------------------


def test_viewer_login_is_empty_when_unreadable(client, github_replay, monkeypatch):
    github_replay.on("GET", "/user", 401, {"message": "Bad credentials"})
    assert client.viewer_login() == ""
    monkeypatch.delenv("GH_TOKEN")
    assert GitHubClient().viewer_login() == ""


# -- O6 / O7 listings -------------------------------------------------------------


def _issue_node(number, labels=(LABEL,)):
    return {
        "number": number,
        "title": f"t{number}",
        "updatedAt": "2026-01-01T00:00:00Z",
        "url": f"https://github.com/octo/repo/issues/{number}",
        "author": {"login": "octocat"},
        "labels": {"nodes": [{"name": name} for name in labels]},
    }


def test_list_labeled_issues_is_the_graphql_query_gh_ran(client, github_replay):
    github_replay.graphql(
        "issues(states",
        {
            "repository": {
                "hasIssuesEnabled": True,
                "issues": {"pageInfo": _page_info(), "nodes": [_issue_node(1)]},
            }
        },
    )
    items = client.list_labeled_issues(OWNER, REPO, [LABEL])
    assert items == [
        GhItem(
            1,
            "t1",
            [LABEL],
            "2026-01-01T00:00:00Z",
            "https://github.com/octo/repo/issues/1",
            False,
            "octocat",
        )
    ]
    (exchange,) = github_replay.exchanges
    assert exchange.json["variables"] == {
        "owner": OWNER,
        "name": REPO,
        "first": PAGE_SIZE,
        "after": None,
        "labels": [LABEL],
    }


def test_a_repository_with_issues_disabled_is_a_410(client, github_replay):
    github_replay.graphql(
        "issues(states",
        {
            "repository": {
                "hasIssuesEnabled": False,
                "issues": {"pageInfo": _page_info(), "nodes": []},
            }
        },
    )
    with pytest.raises(GitHubApiError) as exc:
        client.list_labeled_issues(OWNER, REPO, [LABEL])
    assert exc.value.status == 410 and "Issues are disabled" in str(exc.value)


def test_an_unknown_repository_is_a_404(client, github_replay):
    github_replay.graphql("issues(states", {"repository": None})
    with pytest.raises(GitHubApiError) as exc:
        client.list_labeled_issues(OWNER, REPO, [LABEL])
    assert exc.value.not_found


def test_list_labeled_prs_walks_the_cursor_and_stops_at_the_cap(client, github_replay):
    def page(exchange):
        after = exchange.json["variables"]["after"]
        start = 0 if after is None else int(after)
        nodes = [
            {
                **_issue_node(n),
                "headRefName": f"issue-{n}",
                "body": "b",
                "closingIssuesReferences": {
                    "nodes": [{"number": n + 1000}, {"number": "x"}]
                },
            }
            for n in range(start, start + PAGE_SIZE)
        ]
        return {
            "repository": {
                "pullRequests": {
                    "pageInfo": _page_info(True, str(start + PAGE_SIZE)),
                    "nodes": nodes,
                }
            }
        }

    github_replay.graphql("pullRequests(states", page)
    items = client.list_labeled_prs(OWNER, REPO, [LABEL])
    assert len(items) == LIST_LIMIT
    assert (
        items[0].is_pr
        and items[0].head_ref == "issue-0"
        and items[0].linked_issues == [1000]
    )
    assert len(github_replay.exchanges) == LIST_LIMIT // PAGE_SIZE
    assert github_replay.exchanges[1].json["variables"]["after"] == str(PAGE_SIZE)


# -- O8 / O9 comments -------------------------------------------------------------


def _comment_node(node_id, created):
    return {
        "id": node_id,
        "body": "b",
        "createdAt": created,
        "url": "u",
        "author": {"login": "octocat"},
    }


def test_conversation_comments_keep_graphql_node_ids_across_pages(
    client, github_replay
):
    def page(exchange):
        after = exchange.json["variables"]["after"]
        if after is None:
            return {
                "repository": {
                    "issueOrPullRequest": {
                        "comments": {
                            "pageInfo": _page_info(True, "c1"),
                            "nodes": [_comment_node("IC_1", "2026-01-01T00:00:00Z")],
                        }
                    }
                }
            }
        return {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {
                        "pageInfo": _page_info(),
                        "nodes": [_comment_node("IC_2", "2026-01-02T00:00:00Z")],
                    }
                }
            }
        }

    github_replay.graphql("issueOrPullRequest", page)
    comments = client.list_issue_comments(OWNER, REPO, 15)
    assert [c.id for c in comments] == ["IC_1", "IC_2"]
    assert comments[0] == GhComment("IC_1", "b", "octocat", "2026-01-01T00:00:00Z", "u")
    assert github_replay.exchanges[0].json["variables"]["number"] == 15


def test_a_thread_that_is_not_an_issue_or_pull_request_is_a_404(client, github_replay):
    github_replay.graphql(
        "issueOrPullRequest", {"repository": {"issueOrPullRequest": None}}
    )
    with pytest.raises(GitHubApiError) as exc:
        client.list_issue_comments(OWNER, REPO, 15)
    assert exc.value.not_found


def _review_row(
    node_id,
    body,
    state="COMMENTED",
    submitted="2026-08-16T03:00:00Z",
    user: "str | None" = "octocat",
):
    return {
        "node_id": node_id,
        "body": body,
        "state": state,
        "submitted_at": submitted,
        "html_url": "r",
        "user": {"login": user} if user else None,
    }


def test_a_pull_requests_three_surfaces_are_read_and_merged_chronologically(
    client, github_replay
):
    github_replay.graphql(
        "issueOrPullRequest",
        {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {
                        "pageInfo": _page_info(),
                        "nodes": [_comment_node("IC_1", "2026-08-16T01:00:00Z")],
                    }
                }
            }
        },
    )
    github_replay.on(
        "GET",
        "/repos/octo/repo/pulls/42/reviews",
        200,
        [
            _review_row("PRR_1", "please rename it"),
            _review_row("PRR_empty", "", state="APPROVED"),
            _review_row("PRR_draft", "not yet", state="PENDING"),
            _review_row("PRR_ghost", "do the thing", user=None),
        ],
    )
    github_replay.on(
        "GET",
        "/repos/octo/repo/pulls/42/comments",
        200,
        [
            {
                "node_id": "PRRC_1",
                "body": "this line",
                "created_at": "2026-08-16T02:00:00Z",
                "html_url": "c",
                "user": {"login": "octocat"},
                "path": "cli/x.py",
                "line": None,
                "original_line": 17,
            },
        ],
    )
    comments = client.list_comments(OWNER, REPO, 42, is_pr=True)
    assert [c.id for c in comments] == ["IC_1", "PRRC_1", "PRR_1", "PRR_ghost"]
    assert [c.kind for c in comments] == [
        "conversation",
        "review-thread",
        "review",
        "review",
    ]
    assert (comments[1].path, comments[1].line) == ("cli/x.py", 17)
    assert comments[3].author == ""  # a review GitHub attributes to nobody
    assert [e.path for e in github_replay.rest_calls()] == [
        "/repos/octo/repo/pulls/42/reviews",
        "/repos/octo/repo/pulls/42/comments",
    ]
    assert all("per_page=100" in e.query for e in github_replay.rest_calls())


def test_an_issue_is_one_read_and_no_pull_request_endpoint(client, github_replay):
    github_replay.graphql(
        "issueOrPullRequest",
        {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {"pageInfo": _page_info(), "nodes": []}
                }
            }
        },
    )
    assert client.list_comments(OWNER, REPO, 15, is_pr=False) == []
    assert len(github_replay.exchanges) == 1 and github_replay.rest_calls() == []


def test_rest_pages_follow_the_link_header(client, github_replay):
    next_url = (
        "https://api.github.com/repos/octo/repo/pulls/7/reviews?per_page=100&page=2"
    )
    github_replay.reply(
        "GET",
        lambda e: e.path == "/repos/octo/repo/pulls/7/reviews" and "page=2" in e.query,
        lambda e: (200, [_review_row("PRR_2", "y")]),
    )
    github_replay.on(
        "GET",
        "/repos/octo/repo/pulls/7/reviews",
        200,
        [_review_row("PRR_1", "x")],
        {"link": f'<{next_url}>; rel="next"'},
    )
    assert [r.id for r in client.list_reviews(OWNER, REPO, 7)] == ["PRR_1", "PRR_2"]
    assert [e.url for e in github_replay.exchanges] == [
        "/repos/octo/repo/pulls/7/reviews?per_page=100",
        "/repos/octo/repo/pulls/7/reviews?page=2&per_page=100",
    ]


def test_a_review_fetch_failure_is_not_swallowed_into_no_comments(
    client, github_replay
):
    github_replay.graphql(
        "issueOrPullRequest",
        {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {"pageInfo": _page_info(), "nodes": []}
                }
            }
        },
    )
    github_replay.on(
        "GET", "/repos/octo/repo/pulls/42/reviews", 502, {"message": "upstream"}
    )
    with pytest.raises(GitHubApiError) as exc:
        client.list_comments(OWNER, REPO, 42, is_pr=True)
    assert exc.value.status == 502


# -- the boundary (A1, A2, T7) and the error classes ------------------------------


@pytest.mark.parametrize(
    "owner,repo",
    [
        ("octo;rm -rf /", "repo"),
        ("octo", "repo && curl evil"),
        ("../..", "repo"),
        ("", "repo"),
    ],
)
def test_hostile_coordinates_never_reach_a_request(client, github_replay, owner, repo):
    for call in (
        lambda: client.post_comment(owner, repo, 1, "x"),
        lambda: client.get_issue(owner, repo, 1),
        lambda: client.list_labeled_issues(owner, repo, [LABEL]),
        lambda: client.add_labels(owner, repo, 1, ["a"]),
    ):
        with pytest.raises(GitHubApiError, match="unusable repo coordinates"):
            call()
    assert github_replay.exchanges == []


def test_a_bad_number_never_reaches_a_request(client, github_replay):
    for bad in ("15;x", 0, -1, True, "abc"):
        with pytest.raises(GitHubApiError, match="unusable"):
            client.get_issue(OWNER, REPO, bad)
    assert github_replay.exchanges == []


def test_the_token_never_appears_in_a_reason_or_a_log_line(
    client, github_replay, token, caplog
):
    github_replay.on(
        "GET",
        "/repos/octo/repo/issues/1",
        401,
        {
            "message": "Bad credentials",
            "documentation_url": "https://docs.github.com/rest",
        },
    )
    with caplog.at_level(logging.DEBUG, logger="the-loop.ghapi"):
        with pytest.raises(GitHubApiError) as exc:
            client.get_issue(OWNER, REPO, 1)
    assert token not in str(exc.value) and token not in repr(exc.value)
    assert token not in caplog.text


def test_a_graphql_error_document_is_an_error(client, github_replay):
    github_replay.graphql(
        "issueOrPullRequest",
        errors=[{"message": "Something went wrong", "type": "SERVICE_UNAVAILABLE"}],
    )
    with pytest.raises(GitHubApiError) as exc:
        client.list_issue_comments(OWNER, REPO, 15)
    assert "Something went wrong" in str(exc.value)


def test_a_graphql_answer_without_data_is_an_error(client, github_replay):
    github_replay.on("POST", "/graphql", 200, {"nonsense": True})
    with pytest.raises(GitHubApiError, match="no data object"):
        client.list_issue_comments(OWNER, REPO, 15)


def test_a_transport_failure_has_no_status(client, github_replay):
    def boom(exchange):
        raise ConnectionError("connection reset by peer")

    github_replay.reply("GET", "/repos/octo/repo/issues/1", boom)
    with pytest.raises(GitHubApiError) as exc:
        client.get_issue(OWNER, REPO, 1)
    assert exc.value.status is None and "connection reset" in str(exc.value)


# -- T8: the request count of a poll cycle ------------------------------------------


def test_one_poll_cycle_over_one_issue_and_one_pull_request_costs_six_requests(
    client, github_replay
):
    """R5.2 — two listings, one comment read for the issue, three for the PR."""
    github_replay.graphql(
        "issues(states",
        {
            "repository": {
                "hasIssuesEnabled": True,
                "issues": {"pageInfo": _page_info(), "nodes": [_issue_node(15)]},
            }
        },
    )
    github_replay.graphql(
        "pullRequests(states",
        {
            "repository": {
                "pullRequests": {
                    "pageInfo": _page_info(),
                    "nodes": [
                        {
                            **_issue_node(42),
                            "headRefName": "x",
                            "body": "",
                            "closingIssuesReferences": {"nodes": []},
                        }
                    ],
                }
            }
        },
    )
    github_replay.graphql(
        "issueOrPullRequest",
        {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {"pageInfo": _page_info(), "nodes": []}
                }
            }
        },
    )
    github_replay.on("GET", "/repos/octo/repo/pulls/42/reviews", 200, [])
    github_replay.on("GET", "/repos/octo/repo/pulls/42/comments", 200, [])
    client.list_labeled_issues(OWNER, REPO, [LABEL])
    client.list_labeled_prs(OWNER, REPO, [LABEL])
    client.list_comments(OWNER, REPO, 15, is_pr=False)
    client.list_comments(OWNER, REPO, 42, is_pr=True)
    assert len(github_replay.exchanges) == 2 + 1 + 3


def test_the_shared_client_reuses_one_github_per_host_across_writers(
    client, github_replay
):
    github_replay.on(
        "POST", "/repos/octo/repo/issues/15/comments", 201, {"html_url": "u"}
    )
    client.post_comment(OWNER, REPO, 15, "one")
    client.post_comment(OWNER, REPO, 15, "two")
    assert client.github() is client.github()
    assert len(github_replay.exchanges) == 2


# -- issue-447: the harness's pull-request verbs ------------------------------------


def test_repository_is_one_get(client, github_replay):
    github_replay.on("GET", "/repos/octo/repo", 200, {"default_branch": "trunk"})
    assert client.repository(OWNER, REPO)["default_branch"] == "trunk"
    assert [e.path for e in github_replay.exchanges] == ["/repos/octo/repo"]


def test_create_pull_is_one_post_with_the_whole_request(client, github_replay):
    github_replay.on(
        "POST",
        "/repos/octo/repo/pulls",
        201,
        {"number": 12, "html_url": "https://github.com/octo/repo/pull/12"},
    )
    assert client.create_pull(OWNER, REPO, "T", "B", "feat/x", "main", draft=True) == (
        12,
        "https://github.com/octo/repo/pull/12",
    )
    (exchange,) = github_replay.exchanges
    assert exchange.json == {
        "title": "T",
        "body": "B",
        "head": "feat/x",
        "base": "main",
        "draft": True,
    }


def test_a_duplicate_pull_request_is_githubs_refusal(client, github_replay):
    github_replay.on(
        "POST",
        "/repos/octo/repo/pulls",
        422,
        {
            "message": "Validation Failed",
            "errors": [{"message": "A pull request already exists"}],
        },
    )
    with pytest.raises(GitHubApiError) as exc:
        client.create_pull(OWNER, REPO, "T", "B", "feat/x", "main")
    assert exc.value.status == 422


@pytest.mark.parametrize(
    "head, base",
    [
        ("feat x", "main"),
        ("-x", "main"),
        ("a..b", "main"),
        ("feat/x", "main;rm"),
        ("x@{1}", "main"),
        ("evil owner:feat", "main"),
        ("", "main"),
    ],
)
def test_abuse_447_a3_hostile_branches_are_refused_before_a_request(
    client, github_replay, head, base
):
    with pytest.raises(GitHubApiError, match="unusable"):
        client.create_pull(OWNER, REPO, "T", "B", head, base)
    assert github_replay.exchanges == []


def test_a_fork_head_is_owner_colon_branch(client, github_replay):
    github_replay.on("POST", "/repos/octo/repo/pulls", 201, {"number": 3})
    client.create_pull(OWNER, REPO, "T", "B", "someone:feat/x", "main")
    assert github_replay.exchanges[0].json["head"] == "someone:feat/x"


def test_pr_status_reads_are_bounded_at_three_exchanges(client, github_replay):
    github_replay.on(
        "GET", "/repos/octo/repo/pulls/12", 200, {"head": {"sha": "a" * 40}}
    )
    github_replay.on(
        "GET",
        f"/repos/octo/repo/commits/{'a' * 40}/check-runs",
        200,
        {"total_count": 1, "check_runs": [{"name": "test", "status": "completed"}]},
    )
    github_replay.on(
        "GET",
        f"/repos/octo/repo/commits/{'a' * 40}/status",
        200,
        {"state": "success", "statuses": [{"context": "ci", "state": "success"}]},
    )
    pull = client.get_pull(OWNER, REPO, 12)
    runs, statuses = client.commit_checks(OWNER, REPO, pull["head"]["sha"])
    assert runs == [{"name": "test", "status": "completed"}]
    assert statuses == [{"context": "ci", "state": "success"}]
    assert len(github_replay.exchanges) == 3
    assert github_replay.exchanges[1].query == "per_page=100"


def test_abuse_447_a3_a_hostile_sha_is_refused(client, github_replay):
    with pytest.raises(GitHubApiError, match="unusable commit sha"):
        client.commit_checks(OWNER, REPO, "../../etc")
    assert github_replay.exchanges == []


def test_merge_pull_is_one_put_with_the_method(client, github_replay):
    github_replay.on(
        "PUT", "/repos/octo/repo/pulls/12/merge", 200, {"merged": True, "sha": "abc"}
    )
    assert client.merge_pull(OWNER, REPO, 12, "squash") == {
        "merged": True,
        "sha": "abc",
    }
    assert github_replay.exchanges[0].json == {"merge_method": "squash"}


def test_a_pull_request_github_will_not_merge_is_a_405(client, github_replay):
    github_replay.on(
        "PUT",
        "/repos/octo/repo/pulls/12/merge",
        405,
        {"message": "Pull Request is not mergeable"},
    )
    with pytest.raises(GitHubApiError) as exc:
        client.merge_pull(OWNER, REPO, 12, "merge")
    assert exc.value.status == 405
    assert "not mergeable" in str(exc.value)


def test_abuse_447_a3_an_unknown_merge_method_is_refused(client, github_replay):
    with pytest.raises(GitHubApiError, match="merge method"):
        client.merge_pull(OWNER, REPO, 12, "octopus")
    assert github_replay.exchanges == []


def _thread(n, resolved=False):
    return {
        "id": f"PRRT_{n}",
        "isResolved": resolved,
        "isOutdated": False,
        "path": "cli/x.py",
        "line": n,
        "comments": {
            "nodes": [
                {
                    "id": f"PRRC_{n}",
                    "body": "fix this",
                    "createdAt": "2026-09-30T10:00:00Z",
                    "url": f"https://github.com/octo/repo/pull/12#r{n}",
                    "author": {"login": "alice"},
                }
            ]
        },
    }


def test_review_threads_walk_the_cursor_with_values_as_variables(client, github_replay):
    def page(exchange):
        after = exchange.json["variables"]["after"]
        nodes = [_thread(1)] if after is None else [_thread(2, resolved=True)]
        return {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": _page_info(after is None, "c1"),
                        "nodes": nodes,
                    }
                }
            }
        }

    github_replay.graphql("reviewThreads", page)
    threads = client.review_threads(OWNER, REPO, 12)
    assert [t["id"] for t in threads] == ["PRRT_1", "PRRT_2"]
    assert threads[1]["isResolved"] is True
    assert threads[0]["comments"][0]["author"] == "alice"
    calls = github_replay.graphql_calls()
    assert len(calls) == 2
    assert calls[0].json["variables"] == {
        "owner": OWNER,
        "name": REPO,
        "number": 12,
        "first": PAGE_SIZE,
        "after": None,
    }
    assert "octo" not in calls[0].json["query"]  # A6 of issue-442, kept


def test_review_threads_of_a_missing_pull_request_are_a_404(client, github_replay):
    github_replay.graphql("reviewThreads", {"repository": {"pullRequest": None}})
    with pytest.raises(GitHubApiError) as exc:
        client.review_threads(OWNER, REPO, 12)
    assert exc.value.not_found


def test_open_pulls_for_head_filters_by_owner_and_branch(client, github_replay):
    github_replay.on(
        "GET", "/repos/octo/repo/pulls", 200, [{"number": 7, "html_url": "u"}]
    )
    assert client.open_pulls_for_head(OWNER, REPO, "claude/x") == [
        {"number": 7, "html_url": "u"}
    ]
    query = github_replay.exchanges[0].query
    assert "state=open" in query and "head=octo%3Aclaude%2Fx" in query


def test_abuse_447_a1_the_token_never_reaches_a_verb_error(
    client, github_replay, token
):
    github_replay.on(
        "PUT", "/repos/octo/repo/pulls/12/merge", 401, {"message": "Bad credentials"}
    )
    with pytest.raises(GitHubApiError) as exc:
        client.merge_pull(OWNER, REPO, 12, "merge")
    assert token not in str(exc.value)


def test_merge_pull_sends_the_reviewed_head(client, github_replay):
    github_replay.on("PUT", "/repos/octo/repo/pulls/12/merge", 200, {"merged": True})
    client.merge_pull(OWNER, REPO, 12, "merge", sha="a" * 40)
    assert github_replay.exchanges[0].json == {"merge_method": "merge", "sha": "a" * 40}
