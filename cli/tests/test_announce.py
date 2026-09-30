"""Unit tests for the session announcement comment (issue-86, issue-442).

Pure pieces only: config parsing, the markdown body, the no-op ladder and the
call the announcer makes on the daemon's GitHub client (driven by the in-memory
double — no network). Dispatcher-level scenarios live in
``test_tmux_runner_integration.py``.
"""

from ghfakes import FakeGitHubClient, http_error

from the_loop.announce import AnnounceConfig, SessionAnnouncer, announcement_body
from the_loop.authz import SELF_COMMENT_ATTRIBUTION, is_self_authored
from the_loop.ghapi import GitHubApiConfig
from the_loop.sessions import Session, WorkItemRef

REF = "github:octo/repo#15"
TARGET = "loop-github-octo-repo-15"


def make_session(**overrides) -> Session:
    session = Session(
        work_item=WorkItemRef.parse(REF),
        harness="claude",
        harness_session_id="9f1c-secret-session-id",
        cwd="/home/operator/work/checkouts/repo",
        tmux_target=TARGET,
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


# -- AnnounceConfig -------------------------------------------------------------


def test_announce_config_defaults_are_on():
    config = AnnounceConfig.from_mapping({})
    assert config.enabled is True  # the point of issue-86 is that it reaches you
    assert config.github == GitHubApiConfig()


def test_announce_config_reads_camel_case_keys():
    config = AnnounceConfig.from_mapping({"enabled": False})
    assert config.enabled is False


def test_the_token_config_comes_from_the_integrations_block():
    """issue-109 declared GitHub once under `integrations`; issue-442 fans the
    `api` block (where the token is) in under `_github`."""
    from the_loop.cli_config import apply_integrations

    data = apply_integrations(
        {
            "integrations": {
                "github": {
                    "api": {"tokenEnv": ["LOOP_TOKEN"], "baseUrl": "https://ghe/api/v3"}
                }
            },
            "routing": {"announce": {"enabled": True}},
        }
    )
    section = data["routing"]["announce"]
    assert AnnounceConfig.from_mapping(section).github == GitHubApiConfig(
        token_envs=("LOOP_TOKEN",), base_url="https://ghe/api/v3"
    )


# -- announcement_body ----------------------------------------------------------


def test_body_carries_the_attach_commands():
    body = announcement_body(make_session())
    assert f"tmux attach -t {TARGET}" in body
    assert f"the-loop sessions attach --work-item {REF} --read-only" in body
    assert "`claude`" in body


def test_body_leaks_no_paths_or_session_ids():
    # AC3.6: the comment is public — it must carry nothing about the operator's
    # machine beyond the session name the work-item ref already implies.
    body = announcement_body(make_session())
    assert "/home/operator" not in body
    assert "9f1c-secret-session-id" not in body


def test_body_is_marked_as_the_loops_own():
    # issue-104: the daemon posts under the operator's own credentials, so an
    # unmarked announcement is re-ingested on the next poll cycle and pasted
    # into the very session it announces.
    body = announcement_body(make_session())
    assert is_self_authored(body) is True
    assert SELF_COMMENT_ATTRIBUTION in body
    # …and the human-readable content is unchanged by the marking.
    assert f"tmux attach -t {TARGET}" in body
    assert "`claude`" in body
    assert "respawn" in body


def test_body_names_the_real_tmux_session():
    # AC4 (issue-154): the attach command posted on the ticket is the visible
    # symptom of the bug — it named `loop-github-octo-foo.js-15` while tmux had
    # created `loop-github-octo-foo_js-15`, so the human's copy-paste answered
    # "can't find pane: js-15".
    session = Session(
        work_item=WorkItemRef.parse("github:octo/foo.js#15"),
        harness="claude",
        harness_session_id="9f1c-secret-session-id",
        cwd="/home/operator/work/checkouts/repo",
        tmux_target="loop-github-octo-foo.js-15",
    )
    body = announcement_body(session)
    assert "tmux attach -t loop-github-octo-foo_js-15" in body
    assert "loop-github-octo-foo.js-15" not in body


def test_body_explains_the_commands_survive_a_respawn():
    # A respawn reuses the same loop-<slug> name and posts no second comment
    # (owner decision, PR #87), so the body says the commands keep working.
    assert "respawn" in announcement_body(make_session())


# -- the no-op ladder -----------------------------------------------------------


def test_disabled_is_a_noop():
    gh = FakeGitHubClient()
    announcer = SessionAnnouncer(AnnounceConfig(enabled=False), client=gh)
    assert announcer.announce(make_session()) is False
    assert gh.calls == []


def test_sessions_without_a_tmux_target_are_not_announced():
    # Nothing spawned yet (a self-registered record) — nothing to attach to.
    gh = FakeGitHubClient()
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    session = make_session(tmux_target="")
    assert announcer.announce(session) is False
    assert gh.calls == []


def test_non_github_work_items_are_a_noop():
    gh = FakeGitHubClient()
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    session = make_session(work_item=WorkItemRef.parse("jira:acme/proj#4"))
    assert announcer.announce(session) is False
    assert gh.calls == []


def test_malformed_repo_coordinates_are_a_noop():
    gh = FakeGitHubClient()
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    session = make_session(
        work_item=WorkItemRef(provider="github", owner="octo", repo="re po", number=1)
    )
    assert announcer.announce(session) is False
    assert gh.calls == []


def test_missing_token_warns_once(caplog):
    gh = FakeGitHubClient(token=False)
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    with caplog.at_level("WARNING", logger="the-loop.announce"):
        assert announcer.announce(make_session()) is False
        assert announcer.announce(make_session()) is False
    assert gh.posted == []
    assert len([r for r in caplog.records if "no GitHub token" in r.message]) == 1


# -- the write ------------------------------------------------------------------


def test_posts_a_comment_on_the_work_item():
    gh = FakeGitHubClient()
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    assert announcer.announce(make_session()) is True
    ((owner, repo, number, body, host),) = gh.posted
    # The issues endpoint serves PR conversations too.
    assert (owner, repo, number, host) == ("octo", "repo", 15, "")
    assert f"tmux attach -t {TARGET}" in body


def test_github_failure_is_a_logged_noop():
    gh = FakeGitHubClient(fail=http_error(500, "boom"))
    announcer = SessionAnnouncer(AnnounceConfig(), client=gh)
    assert announcer.announce(make_session()) is False


def test_a_client_exception_never_raises():
    class Exploding(FakeGitHubClient):
        def post_comment(self, *a, **k):
            raise OSError("x")

    announcer = SessionAnnouncer(AnnounceConfig(), client=Exploding())
    assert announcer.announce(make_session()) is False


# -- the 404 is evidence, not decoration (issue-269) ----------------------------


def test_a_404_on_the_work_item_is_reported_as_a_missing_work_item(caplog):
    """The daemon has direct evidence the work item does not exist — R3.1/R3.2."""
    seen = []
    announcer = SessionAnnouncer(
        AnnounceConfig(),
        client=FakeGitHubClient(missing={("octo", "repo", 15)}),
        on_work_item_missing=seen.append,
    )
    with caplog.at_level("ERROR"):
        assert announcer.announce(make_session()) is False
    assert [item.ref for item in seen] == [REF]
    assert any("does not exist" in r.message for r in caplog.records)


def test_any_other_announcement_failure_says_nothing_about_existence():
    seen = []
    announcer = SessionAnnouncer(
        AnnounceConfig(),
        client=FakeGitHubClient(fail=http_error(401, "Bad credentials")),
        on_work_item_missing=seen.append,
    )
    assert announcer.announce(make_session()) is False
    assert seen == []


def test_a_missing_work_item_still_never_fails_the_dispatch():
    """Best-effort stays best-effort: it reports, it does not raise or kill."""
    announcer = SessionAnnouncer(
        AnnounceConfig(), client=FakeGitHubClient(missing={("octo", "repo", 15)})
    )
    assert announcer.announce(make_session()) is False
