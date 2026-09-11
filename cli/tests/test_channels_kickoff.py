"""Unit tests for issue-341: a Slack kickoff names its own repository with a
first-line ``<repo>:`` prefix, resolved against the repositories the operator
already declared. Spec: docs/specs/issue-341/{requirements,design,testing-plan}.md."""

from __future__ import annotations

import pytest

from the_loop import repos
from the_loop.channels import kickoff
from the_loop.channels.slack import SlackChannelConfig

POLLED = [
    "expertise-help/slim-gym",
    "expertise-help/agent-sims",
    "jchou2/devbox",
    "other-org/slim-gym",
]


def config_map(
    kickoff_repo="octocat/hello-world", polled=POLLED, publish=None, declared=None
):
    """A CLI config with a kickoff target and a declared set — the reporter's shape.

    Since issue-348 the set is the top-level ``repositories`` and ``kickoff.repo``
    points at one of them, so the default declaration carries both. ``declared``
    overrides the list outright, for the cases that need a fallback outside it.
    """
    if declared is None:
        declared = ([kickoff_repo] if kickoff_repo else []) + list(polled)
    return {
        "routing": {"authorizedUsers": [{"github": "gh-UHUMAN", "slack": "UHUMAN"}]},
        "repositories": list(declared),
        "channels": {
            "slack": {
                "enabled": True,
                "channel": "C123",
                "publish": publish
                if publish is not None
                else ["work-item.reply", "work-item.create"],
                "kickoff": {"repo": kickoff_repo, "labels": ["the-loop: auto-execute"]},
            }
        },
        "polling": {"sources": [{"provider": "github"}]},
    }


def resolve(text, **kwargs):
    cfg = config_map(**kwargs)
    return kickoff.resolve_target(text, SlackChannelConfig.from_mapping(cfg), cfg)


# -- the declared set (R2.1; issue-348 moved the builder to `the_loop.repos`) -------


def test_the_declared_set_is_the_top_level_declaration():
    declared = repos.declared_repositories(config_map())
    assert [d.declared for d in declared] == ["octocat/hello-world"] + POLLED
    assert {d.source for d in declared} == {"repositories"}


def test_a_declared_entry_keeps_the_operators_own_slug():
    """What reaches ``gh --repo`` is the operator's string, not a normalisation."""
    declared = repos.declared_repositories(
        config_map(kickoff_repo="github.com/octocat/hello-world")
    )
    assert declared[0].declared == "github.com/octocat/hello-world"
    assert declared[0].key == "github.com/octocat/hello-world"


def test_repository_keys_is_the_same_set():
    cfg = config_map()
    assert repos.repository_keys(cfg) == {
        d.key for d in repos.declared_repositories(cfg)
    }


# -- the grammar (R1.2, R1.4) -------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    ["agent-sims", "expertise-help/agent-sims", "github.com/expertise-help/agent-sims"],
)
def test_the_prefix_grammar_accepts_three_shapes(prefix):
    target = resolve(f"{prefix}: flaky teardown")
    assert target.outcome == "resolved"
    assert target.repo == "expertise-help/agent-sims"
    assert target.text == "flaky teardown"


def test_the_prefix_is_case_insensitive():
    target = resolve("Expertise-Help/Agent-Sims: flaky teardown")
    assert target.outcome == "resolved" and target.repo == "expertise-help/agent-sims"


@pytest.mark.parametrize(
    "text",
    [
        "fix: flaky teardown",  # prose that happens to carry a colon
        "https://github.com/o/r is broken",
        "no colon at all",
        "a/b/c/d: too many segments",
        "  : empty prefix",
        "flaky teardown\nagent-sims: on line two",
    ],
)
def test_prose_is_not_a_prefix(text):
    """R2.4/R1.4: the fallback takes it, and the text is untouched."""
    target = resolve(text)
    assert target.outcome == "fallback"
    assert target.repo == "octocat/hello-world"
    assert target.text == text


@pytest.mark.parametrize(
    "prefix", ["../etc/passwd", "$(id)", "a;b", "o/r --repo evil/x", "-flag"]
)
def test_metacharacters_never_parse_as_a_prefix(prefix):
    """A3: the grammar cannot express one, so nothing of the sort is ever read."""
    target = resolve(f"{prefix}: do a thing")
    assert target.outcome == "fallback" and target.repo == "octocat/hello-world"


def test_only_a_declared_slug_reaches_the_writer():
    """A3: the repo handed on is a config string, never the member's text."""
    target = resolve("agent-sims: x")
    assert target.repo in {
        d.declared for d in repos.declared_repositories(config_map())
    }


# -- resolution (R1.1, R1.3, R2.2, R2.3, R2.4) --------------------------------------


def test_a_bare_prefix_resolves_and_is_stripped():
    target = resolve("agent-sims: flaky teardown in the batch runner")
    assert target.outcome == "resolved"
    assert target.repo == "expertise-help/agent-sims"
    assert target.text == "flaky teardown in the batch runner"
    assert target.prefix == "agent-sims"


def test_a_qualified_prefix_resolves():
    target = resolve("other-org/slim-gym: teardown")
    assert target.outcome == "resolved" and target.repo == "other-org/slim-gym"


def test_stripping_keeps_the_following_lines():
    target = resolve("devbox: title here\n\nthe body\nand more")
    assert target.text == "title here\n\nthe body\nand more"


def test_a_prefix_on_its_own_line_drops_that_line():
    target = resolve("devbox:\n\nflaky teardown")
    assert target.outcome == "resolved"
    assert target.text.lstrip("\n").startswith("flaky teardown")


def test_a_prefix_alone_is_refused_as_an_empty_message():
    """R1.3: a resolved prefix with nothing after it is not a work item."""
    target = resolve("devbox:")
    assert target.outcome == "empty-message" and target.ok is False
    assert "put the title after the prefix" in kickoff.refusal_text(target)


def test_an_undeclared_qualified_prefix_is_refused():
    target = resolve("stranger/repo: do a thing")
    assert target.outcome == "unknown-repo" and target.repo == ""
    assert target.prefix == "stranger/repo"


def test_an_undeclared_qualified_prefix_never_falls_back():
    """A2: the fallback must not silently absorb a repository that was named."""
    assert resolve("stranger/repo: x", kickoff_repo="octocat/hello-world").repo == ""


def test_a_foreign_host_matches_nothing():
    """A4: keys are built from declared entries and this instance's own host."""
    target = resolve("evil.example/expertise-help/slim-gym: x")
    assert target.outcome == "unknown-repo"


def test_an_ambiguous_bare_prefix_is_refused():
    target = resolve("slim-gym: flaky teardown")
    assert target.outcome == "ambiguous-repo" and target.repo == ""
    assert target.candidates == ("expertise-help/slim-gym", "other-org/slim-gym")


def test_an_unmatched_bare_prefix_falls_back():
    """decision-120 D3: a bare word that matches nothing is not a prefix."""
    target = resolve("slim-gim: flaky teardown")
    assert target.outcome == "fallback"
    assert target.repo == "octocat/hello-world"
    assert target.text == "slim-gim: flaky teardown"


# -- the fallback and the refusals (R3.1, R3.2) -------------------------------------


def test_no_prefix_uses_the_fallback():
    target = resolve("just a plain sentence")
    assert target.outcome == "fallback" and target.repo == "octocat/hello-world"
    assert target.ok is True


def test_no_prefix_and_no_fallback_is_no_target():
    target = resolve("just a plain sentence", kickoff_repo="")
    assert target.outcome == "no-target" and target.ok is False


def test_an_unmatched_bare_prefix_without_a_fallback_is_no_target():
    target = resolve("slim-gim: teardown", kickoff_repo="")
    assert target.outcome == "no-target"


# -- the refusal's words (R2.5) -----------------------------------------------------


def test_refusal_text_names_the_candidates():
    text = kickoff.refusal_text(resolve("slim-gym: x"))
    assert "`slim-gym`" in text
    assert "`expertise-help/slim-gym`" in text and "`other-org/slim-gym`" in text


def test_the_unknown_repo_refusal_asks_for_a_declared_one():
    text = kickoff.refusal_text(resolve("stranger/repo: x"))
    assert "`stranger/repo`" in text and "`jchou2/devbox`" in text


def test_the_no_target_refusal_asks_for_a_prefix():
    text = kickoff.refusal_text(resolve("plain sentence", kickoff_repo=""))
    assert "<repo>:" in text and "`jchou2/devbox`" in text


def test_the_candidate_list_is_capped():
    polled = [f"org{n}/repo{n}" for n in range(20)]
    text = kickoff.refusal_text(
        resolve("stranger/repo: x", kickoff_repo="", polled=polled)
    )
    assert text.count("`org") == kickoff.CANDIDATE_LIMIT
    assert "and 8 more" in text


def test_refusal_text_with_no_declared_repositories():
    text = kickoff.refusal_text(resolve("plain", kickoff_repo="", polled=[]))
    assert "`repositories`" in text and "polling.sources" not in text


def test_the_refusal_carries_no_token_or_other_config(monkeypatch):
    """A5: the prefix, fixed words and declared names — nothing else."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-secret")
    text = kickoff.refusal_text(resolve("stranger/repo: my secret plan"))
    assert "xoxb" not in text and "my secret plan" not in text
    assert "UHUMAN" not in text and "C123" not in text


# -- the precondition (R3.3, A7) ----------------------------------------------------


def test_kickoff_is_enabled_without_a_repo():
    config = SlackChannelConfig.from_mapping(config_map(kickoff_repo=""))
    assert config.kickoff_repo == "" and config.kickoff_enabled is True


def test_without_the_grant_nothing_is_read_or_answered():
    """A7: the grant is the gate it always was."""
    config = SlackChannelConfig.from_mapping(config_map(publish=["work-item.reply"]))
    assert config.kickoff_enabled is False


# -- `channels status` says where a kickoff goes (R5.1) -----------------------------


def _status_output(tmp_path, monkeypatch, capsys, **kwargs):
    import argparse
    import json

    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    cfg = config_map(**kwargs)
    cfg["state"] = {"root": str(tmp_path / "state")}
    (tmp_path / "cli-config.yaml").write_text(json.dumps(cfg), encoding="utf-8")
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    return capsys.readouterr().out


def test_status_names_the_fallback_and_how_many_a_prefix_may_pick(
    tmp_path, monkeypatch, capsys
):
    out = _status_output(tmp_path, monkeypatch, capsys)
    assert "kickoff:      octocat/hello-world" in out
    assert "5 declared repositories" in out


def test_status_says_when_there_is_no_fallback(tmp_path, monkeypatch, capsys):
    out = _status_output(tmp_path, monkeypatch, capsys, kickoff_repo="")
    assert "no fallback — every message must name one" in out
    assert "4 declared repositories" in out


def test_status_says_kickoff_is_off_without_the_grant(tmp_path, monkeypatch, capsys):
    out = _status_output(tmp_path, monkeypatch, capsys, publish=["work-item.reply"])
    assert "kickoff:      off — channels.slack.publish does not grant" in out
