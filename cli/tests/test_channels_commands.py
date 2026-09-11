"""The `/the-loop` slash command (issue-334): the parser, the target boundary,
the handler per family, and every abuse case of the requirements.

Everything past the process boundary is faked at its injection point: the
ledger writer (``post_comment``), the core facade (``lifecycle`` / ``standing``)
and the responder (``respond``). No Slack, no ``gh``, no tmux.
"""

from __future__ import annotations

import json

import pytest

from the_loop import eventlog
from the_loop.authz import is_self_authored
from the_loop.channels import commands
from the_loop.channels.envelope import parse as parse_envelope
from the_loop.channels.events import EVENTS, PUBLISHABLE_EVENTS, is_recorded
from the_loop.channels.slack import slack_state_path
from the_loop.channels.state import ChannelState
from the_loop.control import ControlConfig, parse_command
from the_loop.sessions import WorkItemRef

ALL_GRANTS = [
    "work-item.reply",
    "control.command",
    "instance.command",
    "standing.command",
]


def cli_config(tmp_path, authorized=("UHUMAN",), publish=None, **extra):
    section = {
        "enabled": True,
        "channel": "C123",
        "read": {"mode": "socket"},
        "kickoff": {"repo": "o/r"},
        "publish": list(ALL_GRANTS if publish is None else publish),
    }
    config = {
        "state": {"root": str(tmp_path / "state")},
        "routing": {
            "authorizedUsers": [
                {"github": f"gh-{member}", "slack": member, "name": member.lower()}
                for member in authorized
            ]
        },
        "channels": {"slack": section},
    }
    config.update(extra)
    return config


def payload(text, user="UHUMAN", trigger="trig-1", url="https://hooks.slack.com/x"):
    return {
        "command": "/the-loop",
        "text": text,
        "user_id": user,
        "user_name": "someone",
        "channel_id": "C123",
        "trigger_id": trigger,
        "response_url": url,
    }


class FakeLifecycle:
    def __init__(self, doc=None, raises=None):
        self.calls = []
        self.doc = doc or {
            "instance": {"name": "laptop-b", "scope": {"mode": "open"}},
            "services": [
                {
                    "service": "service",
                    "enabled": True,
                    "running": True,
                    "pid": 4242,
                    "url": "http://127.0.0.1:8787",
                },
                {
                    "service": "gh-webhook",
                    "enabled": True,
                    "running": True,
                    "pid": 4242,
                    "hosted": True,
                },
                {"service": "poller", "enabled": False, "running": False, "pid": 0},
            ],
            "standingSessions": [
                {"name": "supervisor", "running": True},
                {"name": "watcher", "running": False},
            ],
            "ok": True,
        }
        self.raises = raises

    def status_all(self, config=None, config_path=None):
        self.calls.append(("status_all",))
        if self.raises:
            raise self.raises
        return self.doc

    def schedule_restart(self, config=None, with_upgrade=False, config_path=None):
        self.calls.append(("schedule_restart", with_upgrade, config_path))
        if self.raises:
            raise self.raises
        return {
            "scheduled": True,
            "pid": 77,
            "withUpgrade": with_upgrade,
            "logfile": "/tmp/state/logs/restart.out",
        }


class FakeStanding:
    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def list_standing(self, config=None, registry_dir=""):
        self.calls.append(("list",))
        if self.raises:
            raise self.raises
        return [
            {"name": "supervisor", "running": True, "declared": True},
            {"name": "scratch", "running": False, "declared": False},
        ]

    def control_standing(self, name, verb, config=None, registry_dir=""):
        self.calls.append((verb, name))
        if self.raises:
            raise self.raises
        return {
            "sessions": [
                {"name": name, "outcome": "started", "detail": "loop-standing-" + name}
            ],
            "ok": True,
        }


def run(tmp_path, text, *, config=None, post_ok=True, post_url="https://x/c1", **kw):
    """The handler with every boundary faked. Returns (outcome, posts, answers, fakes)."""
    posts, answers = [], []
    config = config or cli_config(tmp_path)
    lifecycle = kw.pop("lifecycle", FakeLifecycle())
    standing = kw.pop("standing", FakeStanding())

    def post_comment(item, body, gh_binary="gh"):
        posts.append((item.ref, body))
        return (True, "", post_url) if post_ok else (False, "gh exited 1", "")

    def respond(url, message):
        answers.append((url, message))
        return True

    outcome = commands.handle_slash_command(
        payload(text, **kw),
        config,
        respond=respond,
        post_comment=post_comment,
        lifecycle=lifecycle,
        standing=standing,
    )
    return outcome, posts, answers, (lifecycle, standing)


@pytest.fixture(autouse=True)
def fresh_ring():
    commands.reset_seen()
    yield
    commands.reset_seen()


# -- the catalog (task 1) ---------------------------------------------------------


def test_the_catalog_carries_the_two_command_grants():
    """R3.2, R3.4: publishable, not subscribable, not recorded."""
    for name in ("instance.command", "standing.command"):
        assert name in PUBLISHABLE_EVENTS
        assert EVENTS[name].subscribable is False
        assert EVENTS[name].origin == "channel"
        assert is_recorded(name) is False
    assert is_recorded("control.command") is True


def test_the_family_grants_are_catalog_rows():
    assert set(commands.FAMILY_GRANTS.values()) <= set(PUBLISHABLE_EVENTS)


# -- the parser (task 2) ----------------------------------------------------------


def parse(text, **keywords):
    control = ControlConfig.from_mapping({"keywords": keywords} if keywords else {})
    return commands.parse_invocation(text, control)


def test_parse_help():
    for text in ("", "   ", "help", "HELP"):
        assert parse(text).family == "help"


def test_parse_instance_verbs():
    for verb in commands.INSTANCE_VERBS:
        invocation = parse(verb)
        assert (invocation.family, invocation.verb) == ("instance", verb)
    assert parse("status now").error
    assert parse("Upgrade").verb == "upgrade"


def test_parse_standing_verbs():
    assert parse("standing list").family == "standing"
    assert parse("standing list").verb == "list"
    for verb in ("start", "stop", "restart"):
        invocation = parse(f"standing {verb} supervisor")
        assert invocation.family == "standing"
        assert (invocation.verb, invocation.target) == (verb, "supervisor")
    assert parse("standing").error
    assert parse("standing start").error
    assert parse("standing list extra").error
    assert parse("standing delete supervisor").error
    assert parse("standing start supervisor extra").error


def test_parse_work_item_verbs_from_the_configured_keywords():
    """R2.2: the verb is the last word of the configured keyword — or the
    command's own name — never a substring search."""
    for verb in (
        "start",
        "stop",
        "pause",
        "resume",
        "execute",
        "contribute",
        "do",
        "review",
        "cleanup",
    ):
        invocation = parse(f"{verb} #7")
        assert invocation.family == "work-item", verb
        assert (invocation.verb, invocation.target) == (verb, "#7")
    renamed = parse("go o/r#7", start="loop go")
    assert (renamed.family, renamed.verb, renamed.target) == (
        "work-item",
        "start",
        "o/r#7",
    )
    by_name = parse("start o/r#7", start="loop go")
    assert (by_name.family, by_name.verb) == ("work-item", "start")


def test_parse_collaborator_commands_take_one_login():
    invocation = parse("add-collaborator #7 @octocat")
    assert invocation.verb == "add-collaborator"
    assert (invocation.target, invocation.subject) == ("#7", "octocat")
    assert parse("remove-collaborator @octocat #7").subject == "octocat"
    assert parse("add-collaborator #7").error  # no login
    assert parse("add-collaborator #7 @a @b").error  # two logins
    assert parse("start #7 @octocat").error  # a login on a verb that takes none


def test_parse_reads_one_instance_address():
    invocation = parse("start #7 instance:laptop-b")
    assert invocation.address == "laptop-b"
    assert parse("start instance:laptop-b #7").target == "#7"
    assert parse("start #7 instance:a instance:b").error  # two addresses
    assert parse("start #7 instance:Not_Valid").error  # outside the grammar


def test_parse_refuses_a_malformed_standing_name():
    for name in ("Supervisor", "a b", "-x", "x" * 41, "sup;rm"):
        assert parse(f"standing start {name}").error, name


def test_parse_refuses_a_malformed_login():
    assert parse("add-collaborator #7 @not-a$login").error


def test_parse_refuses_a_disabled_keyword():
    assert parse("start #7", start="").error


def test_parse_refuses_unknown_and_extra_tokens():
    """A4: anything beyond the vocabulary is refused whole."""
    for text in (
        "launch #7",
        "start",
        "start #7 now",
        "start #7 #8",
        "start #7; rm -rf /",
        "start stop #7",
        "the-loop start #7",
    ):
        invocation = parse(text)
        assert invocation.error and not invocation.family, text


def test_usage_names_every_family():
    text = commands.usage()
    for word in ("help", "status", "restart", "upgrade", "standing", "start"):
        assert word in text


# -- the target (task 2) ----------------------------------------------------------


def test_resolve_work_item_shapes(tmp_path):
    config = cli_config(tmp_path)
    for token in (
        "github:o/r#7",
        "o/r#7",
        "#7",
        "7",
        "https://github.com/o/r/issues/7",
        "https://github.com/o/r/pull/7",
    ):
        assert commands.resolve_work_item(token, config).ref == "github:o/r#7", token


def test_resolve_refuses_what_is_not_a_work_item(tmp_path):
    config = cli_config(tmp_path)
    for token in (
        "",
        "o/r",
        "o/r#",
        "#x",
        "jira:ABC-1",
        "https://example.com/o/r/issues/7",
        "o/r/x#7",
        "o/r#7#8",
    ):
        with pytest.raises(ValueError):
            commands.resolve_work_item(token, config)


def test_resolve_bare_numbers_need_kickoff_repo(tmp_path):
    config = cli_config(tmp_path)
    config["channels"]["slack"]["kickoff"] = {}
    with pytest.raises(ValueError, match="kickoff.repo"):
        commands.resolve_work_item("#7", config)


def test_resolve_applies_the_resolved_host(tmp_path):
    """The issue-331 rule: a bare owner/repo is on the resolved GitHub host."""
    config = cli_config(tmp_path, integrations={"github": {"host": "ghe.corp.example"}})
    assert (
        commands.resolve_work_item("o/r#7", config).ref
        == "github:ghe.corp.example/o/r#7"
    )
    assert commands.resolve_work_item("#7", config).host == "ghe.corp.example"
    assert (
        commands.resolve_work_item("https://ghe.corp.example/o/r/pull/9", config).ref
        == "github:ghe.corp.example/o/r#9"
    )


def test_may_target_kickoff_repo_and_poll_sources(tmp_path):
    config = cli_config(
        tmp_path, polling={"sources": [{"provider": "github", "repos": ["Other/Repo"]}]}
    )
    assert commands.may_target(WorkItemRef.parse("github:o/r#7"), config)
    assert commands.may_target(WorkItemRef.parse("github:other/repo#1"), config)
    assert not commands.may_target(WorkItemRef.parse("github:stranger/repo#1"), config)


def test_may_target_a_bound_conversation_and_a_managed_item(tmp_path):
    config = cli_config(tmp_path)
    config["channels"]["slack"]["kickoff"] = {}
    ref = WorkItemRef.parse("github:elsewhere/repo#3")
    assert not commands.may_target(ref, config)
    with ChannelState.locked(slack_state_path(config)) as state:
        state.bind("1700.1", ref.ref, "C123")
        state.save(slack_state_path(config))
    assert commands.may_target(ref, config)
    declared = WorkItemRef.parse("github:declared/repo#4")
    config["instance"] = {"name": "laptop-b", "scope": {"workItems": [declared.ref]}}
    assert commands.may_target(declared, config)


def test_a_failing_read_contributes_nothing(tmp_path, monkeypatch):
    """A3: a source that cannot be read never widens the target set."""
    config = cli_config(tmp_path, polling={"sources": "not-a-list"})
    config["channels"]["slack"]["kickoff"] = {}
    monkeypatch.setattr(
        "the_loop.core.instance.describe_instance",
        lambda cfg=None: (_ for _ in ()).throw(RuntimeError("registry unreadable")),
    )
    assert not commands.may_target(WorkItemRef.parse("github:o/r#7"), config)


# -- the handler: refusals (task 3) ------------------------------------------------


def test_an_unlisted_member_is_dropped_before_parsing(tmp_path, monkeypatch):
    """R3.1, A1: nothing parsed, nothing recorded, nothing answered."""
    events = []
    monkeypatch.setattr(
        commands.eventlog,
        "emit",
        lambda name, level="info", **f: events.append((name, f)),
    )
    outcome, posts, answers, (lifecycle, standing) = run(
        tmp_path, "restart", user="UEVIL"
    )
    assert outcome["outcome"] == "unauthorized-actor"
    assert posts == [] and answers == []
    assert lifecycle.calls == [] and standing.calls == []
    assert [e for e in events if e[0] == "channel.dropped"][0][1]["reason"] == (
        "unauthorized-actor"
    )


def test_a_disabled_channel_acts_on_nothing(tmp_path):
    config = cli_config(tmp_path)
    config["channels"]["slack"]["enabled"] = False
    outcome, posts, answers, (lifecycle, _) = run(tmp_path, "restart", config=config)
    assert outcome["outcome"] == "channel-disabled"
    assert posts == [] and answers == [] and lifecycle.calls == []


def test_an_empty_allowlist_denies_everyone(tmp_path):
    outcome, posts, answers, _ = run(tmp_path, "help", config=cli_config(tmp_path, ()))
    assert outcome["outcome"] == "unauthorized-actor" and answers == []


def test_a_duplicate_trigger_is_dropped(tmp_path):
    """A9: the same trigger_id acts once."""
    first, posts, answers, _ = run(tmp_path, "start #7", trigger="t-9")
    second, posts2, answers2, _ = run(tmp_path, "start #7", trigger="t-9")
    assert first["outcome"] == "recorded" and len(posts) == 1
    assert second["outcome"] == "duplicate" and posts2 == [] and answers2 == []


def test_an_unknown_command_is_answered_with_usage(tmp_path):
    outcome, posts, answers, _ = run(tmp_path, "launch #7")
    assert outcome["outcome"] == "unknown-command"
    assert posts == []
    assert len(answers) == 1 and "/the-loop help" in answers[0][1]


def test_help_names_the_grants_this_channel_holds(tmp_path):
    config = cli_config(tmp_path, publish=["work-item.reply", "control.command"])
    outcome, posts, answers, _ = run(tmp_path, "help", config=config)
    assert outcome["outcome"] == "help" and posts == []
    text = answers[0][1]
    assert "control.command" in text and "granted" in text
    assert "instance.command" in text and "not granted" in text


def test_a_verb_without_its_grant_is_refused_and_named(tmp_path):
    """R3.2, A2."""
    config = cli_config(tmp_path, publish=["work-item.reply"])
    for text, grant in (
        ("start #7", "control.command"),
        ("restart", "instance.command"),
        ("standing start supervisor", "standing.command"),
    ):
        outcome, posts, answers, (lifecycle, standing) = run(
            tmp_path, text, config=config, trigger=text
        )
        assert outcome["outcome"] == "unpublishable-event", text
        assert posts == [] and lifecycle.calls == [] and standing.calls == []
        assert grant in answers[0][1]


def test_a_foreign_repository_is_refused_and_nothing_is_recorded(tmp_path):
    """A3."""
    outcome, posts, answers, _ = run(tmp_path, "start stranger/repo#1")
    assert outcome["outcome"] == "unknown-target" and posts == []
    assert "stranger/repo" in answers[0][1]


def test_an_unparsable_target_is_refused(tmp_path):
    outcome, posts, answers, _ = run(tmp_path, "start o/r")
    assert outcome["outcome"] == "unknown-target" and posts == []


# -- the handler: work-item verbs (task 3) ----------------------------------------


def test_a_work_item_verb_records_the_composed_line_unmarked(tmp_path):
    """R3.3: the same record the thread path makes — unmarked, keyword intact,
    the envelope naming the person — and nothing delivered by the handler."""
    outcome, posts, answers, (lifecycle, standing) = run(tmp_path, "start #7")
    assert outcome == {
        "outcome": "recorded",
        "family": "work-item",
        "verb": "start",
        "workItem": "github:o/r#7",
        "answered": True,
    }
    assert lifecycle.calls == [] and standing.calls == []
    ref, body = posts[0]
    assert ref == "github:o/r#7"
    assert not is_self_authored(body)
    assert parse_command(body, ControlConfig()).command == "start"
    envelope = parse_envelope(body)
    assert envelope is not None
    assert envelope.type == "control.command" and envelope.source == "slack"
    assert envelope.actor == {"github": "gh-UHUMAN", "slack": "UHUMAN"}
    assert "https://x/c1" in answers[0][1] and "the-loop start" in answers[0][1]


def test_the_recorded_line_is_built_from_the_keyword_not_the_text(tmp_path):
    """A4: an operator's renamed keyword is what lands; the tokens are validated."""
    config = cli_config(tmp_path)
    config["routing"]["control"] = {"keywords": {"start": "loop go"}}
    outcome, posts, _, _ = run(tmp_path, "go #7 instance:laptop-b", config=config)
    assert outcome["outcome"] == "recorded"
    body = posts[0][1]
    assert "loop go instance:laptop-b" in body
    assert (
        parse_command(
            body, ControlConfig.from_mapping(config["routing"]["control"])
        ).command
        == "start"
    )


def test_collaborator_and_execute_verbs_relay_like_any_other(tmp_path):
    outcome, posts, _, _ = run(tmp_path, "add-collaborator #7 @octocat", trigger="a")
    assert outcome["outcome"] == "recorded"
    result = parse_command(posts[0][1], ControlConfig())
    assert (result.command, result.subjects) == ("add-collaborator", ["octocat"])
    outcome, posts, _, _ = run(tmp_path, "execute github:o/r#7", trigger="b")
    assert outcome["outcome"] == "recorded"
    assert parse_command(posts[0][1], ControlConfig()).command == "execute"


def test_a_failing_ledger_is_a_recorded_outcome(tmp_path):
    """R3.6."""
    outcome, posts, answers, _ = run(tmp_path, "start #7", post_ok=False)
    assert outcome["outcome"] == "record-failed"
    assert "gh exited 1" in answers[0][1]


# -- the handler: instance verbs (task 3) -----------------------------------------


def test_status_renders_the_facade_document(tmp_path):
    outcome, posts, answers, (lifecycle, _) = run(tmp_path, "status")
    assert outcome["outcome"] == "ok" and posts == []
    assert lifecycle.calls == [("status_all",)]
    text = answers[0][1]
    assert "laptop-b" in text and "service: running" in text and "4242" in text
    assert "gh-webhook: running" in text and "hosted" in text
    assert "poller: disabled" in text
    assert "supervisor running" in text and "watcher stopped" in text


def test_render_status_without_standing_sessions():
    doc = FakeLifecycle().doc
    doc = {**doc, "standingSessions": [], "ok": False}
    text = commands.render_status(doc)
    assert "standing: none" in text and "not ok" in text


def test_restart_and_upgrade_schedule_through_the_facade(tmp_path, monkeypatch):
    """R3.5, A7: one boolean and the path this process read; nothing else."""
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    outcome, _, answers, (lifecycle, _) = run(tmp_path, "restart", trigger="r")
    assert outcome["outcome"] == "ok"
    outcome, _, answers2, (lifecycle2, _) = run(tmp_path, "upgrade", trigger="u")
    assert outcome["outcome"] == "ok"
    assert lifecycle.calls == [
        ("schedule_restart", False, tmp_path / "cli-config.yaml")
    ]
    assert lifecycle2.calls == [
        ("schedule_restart", True, tmp_path / "cli-config.yaml")
    ]
    assert "77" in answers[0][1] and "upgrade" in answers2[0][1]


def test_a_raising_facade_is_answered_not_raised(tmp_path):
    outcome, _, answers, _ = run(
        tmp_path, "status", lifecycle=FakeLifecycle(raises=RuntimeError("boom"))
    )
    assert outcome["outcome"] == "failed" and "boom" in answers[0][1]


# -- the handler: standing verbs (task 3) -----------------------------------------


def test_standing_verbs_call_the_facade(tmp_path):
    outcome, posts, answers, (_, standing) = run(tmp_path, "standing list", trigger="l")
    assert outcome["outcome"] == "ok" and posts == []
    assert standing.calls == [("list",)]
    assert "supervisor" in answers[0][1] and "running" in answers[0][1]
    outcome, _, answers, (_, standing) = run(
        tmp_path, "standing start supervisor", trigger="s"
    )
    assert outcome == {
        "outcome": "ok",
        "family": "standing",
        "verb": "start",
        "standing": "supervisor",
        "answered": True,
    }
    assert standing.calls == [("start", "supervisor")]
    assert "started" in answers[0][1]


def test_a_standing_refusal_is_the_answer(tmp_path):
    outcome, _, answers, _ = run(
        tmp_path,
        "standing stop ghost",
        standing=FakeStanding(raises=LookupError("no standing session 'ghost'")),
    )
    assert outcome["outcome"] == "failed" and "ghost" in answers[0][1]


# -- the answer (task 3) ----------------------------------------------------------


def test_an_off_host_response_url_is_never_posted_to(tmp_path, monkeypatch, caplog):
    """A5."""
    sent = []
    monkeypatch.setattr(
        commands, "_send_webhook", lambda url, text: sent.append(url) or True
    )
    with caplog.at_level("WARNING", logger="the-loop.channels"):
        assert commands.webhook_responder("https://evil.example/hook", "hi") is False
        assert commands.webhook_responder("", "hi") is False
        assert commands.webhook_responder(
            "https://hooks.slack.com/commands/T/1/x", "hi"
        )
    assert sent == ["https://hooks.slack.com/commands/T/1/x"]
    assert "evil.example" in caplog.text


def test_a_failed_answer_keeps_the_outcome(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(
        commands.eventlog,
        "emit",
        lambda name, level="info", **f: events.append((name, f)),
    )
    posts = []

    def post_comment(item, body, gh_binary="gh"):
        posts.append(body)
        return True, "", ""

    outcome = commands.handle_slash_command(
        payload("start #7"),
        cli_config(tmp_path),
        respond=lambda url, text: False,
        post_comment=post_comment,
        lifecycle=FakeLifecycle(),
        standing=FakeStanding(),
    )
    assert outcome["outcome"] == "recorded" and outcome["answered"] is False
    assert len(posts) == 1
    assert "channel.command_answer_failed" in [e[0] for e in events]


def test_a_raising_responder_never_escapes(tmp_path):
    def respond(url, text):
        raise RuntimeError("network down")

    outcome = commands.handle_slash_command(
        payload("status"),
        cli_config(tmp_path),
        respond=respond,
        lifecycle=FakeLifecycle(),
        standing=FakeStanding(),
    )
    assert outcome["outcome"] == "ok" and outcome["answered"] is False


def test_command_events_carry_ids_never_text(tmp_path, monkeypatch):
    """R3.4, A8."""
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-supersecret")
    log = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log, enabled=True)
    try:
        run(tmp_path, "start #7 instance:laptop-b", trigger="1")
        run(tmp_path, "status", trigger="2")
        run(tmp_path, "standing start supervisor", trigger="3")
        run(tmp_path, "launch the-secret-thing #7", trigger="4")
    finally:
        eventlog.reset()
    raw = log.read_text()
    kinds = [json.loads(line)["event"] for line in raw.splitlines()]
    assert kinds.count("channel.command_received") == 3
    assert kinds.count("channel.command_completed") == 3
    assert "channel.dropped" in kinds
    assert "xoxb-supersecret" not in raw
    assert "the-secret-thing" not in raw
    assert "hooks.slack.com" not in raw


# -- the manifest (task 4) --------------------------------------------------------


def test_the_manifest_is_packaged_and_printed(tmp_path, monkeypatch, capsys):
    """R4.1."""
    text = commands.manifest_text()
    assert "/the-loop" in text and "socket_mode_enabled: true" in text
    for scope in (
        "chat:write",
        "channels:history",
        "groups:history",
        "reactions:write",
        "commands",
    ):
        assert scope in text
    import argparse

    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(cli_config(tmp_path)), encoding="utf-8"
    )
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["manifest"])) == 0
    assert capsys.readouterr().out.strip() == text.strip()


def test_channels_status_says_which_command_families_are_granted(
    tmp_path, monkeypatch, capsys
):
    import argparse

    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    config = cli_config(tmp_path, publish=["work-item.reply", "control.command"])
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    ChannelsCommand().run(parser.parse_args(["status"]))
    out = capsys.readouterr().out
    assert "commands:     /the-loop over Socket Mode" in out
    assert "work-item: granted" in out and "instance: not granted" in out
    config["channels"]["slack"]["read"] = {"mode": "poll"}
    (tmp_path / "cli-config.yaml").write_text(json.dumps(config), encoding="utf-8")
    ChannelsCommand().run(parser.parse_args(["status"]))
    assert "slash commands need read.mode: socket" in capsys.readouterr().out


# -- docs pins (task 5) -----------------------------------------------------------

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    not (REPO_ROOT / "docs").is_dir(), reason="documentation site not present"
)
def test_the_guide_reproduces_the_packaged_manifest():
    """R4.1: the guide's fenced manifest is the file the package ships."""
    guide = (REPO_ROOT / "docs" / "guide" / "slack.md").read_text(encoding="utf-8")
    text = commands.manifest_text()
    start = guide.index("```yaml\n" + text.splitlines()[0])
    end = guide.index("```", start + 8)
    assert guide[start + 8 : end].strip() == text.strip()


@pytest.mark.skipif(
    not (REPO_ROOT / "docs").is_dir(), reason="documentation site not present"
)
def test_the_docs_list_every_publishable_event():
    """R4.3: the `publish` table names every grant the catalog marks publishable."""
    page = (REPO_ROOT / "docs" / "config" / "cli" / "channels-options.md").read_text(
        encoding="utf-8"
    )
    for name in PUBLISHABLE_EVENTS:
        assert f"| `{name}` |" in page, name
