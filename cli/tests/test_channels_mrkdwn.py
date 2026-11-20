"""GitHub markdown drawn as Slack mrkdwn, and what replaced the digest.

The drawing (issue-338 D3) moved to :mod:`the_loop.channels.mrkdwn` in issue-549
and is kept; the digest that condensed long text is retired (issue-549 R1.2,
decision-154). These tests cover the drawing, the deprecated keys that used to
steer the digest, and that the phone's fallback text is the short form.
No Slack, no network: the SDK boundary is the injected client factory.
"""

from __future__ import annotations

import argparse
import importlib.util
import json

import pytest

from the_loop import configschema
from the_loop.channels.base import Event
from the_loop.channels.mrkdwn import strip_comments, to_mrkdwn
from the_loop.channels.slack import (
    PHASE_SELECTION_MARKER,
    SlackBotChannel,
    SlackChannelConfig,
)

# -- fixtures -----------------------------------------------------------------

#: Shaped like `graph/hooks/selection.py`'s checklist: the question first, the
#: instruction, the boxes, the marker at the end.
CHECKLIST = f"""🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. **Untick anything this work item does not need — right here on this comment — then reply `the-loop execute`.** The tick state at that moment is frozen and becomes the graph this item walks.

- [x] brainstorming
- [x] requirements-definition
- [x] design
- [x] test-planning
- [x] tasks-breakdown
- [x] implementation
- [x] verification

**Every phase of this loop is selectable — including the reviews, the security review and the approval gate.** Nothing but this question is mandatory, so each box you untick is an omission recorded against your name: in the work item's graph state, in a confirmation comment here, and in every `the-loop check` from now on.

**Where should the outer loop happen?** This is not a phase — it is where the requirements, design, testing plan and task list are iterated with you:

- [ ] `outer-loop-on-pull-request` — on a pull request in this repository.

Leave it unticked (the default) and they happen **on this work item**, here. Tick it and they happen on a pull request instead.

A doc fix usually needs little more than implementation and verification; a feature usually needs every phase. Reply `the-loop execute` with the boxes untouched to run the full process.

{PHASE_SELECTION_MARKER}
<!-- the-loop:agent-comment -->
_— the-loop_
"""


# -- to_mrkdwn (issue-338 R3.3, R3.4) ----------------------------------------------


def test_to_mrkdwn_draws_markdown_as_slack_does():
    text = (
        "## Heading\n"
        "Some **bold** and __also bold__ and ~~gone~~ text.\n"
        "- [x] done\n"
        "- [ ] todo\n"
        "- plain\n"
        "* star\n"
        "See [the doc](https://x/y) and ![shot](https://x/s.png).\n"
        "<!-- the-loop:agent-comment -->\n"
    )
    out = to_mrkdwn(text)
    assert "*Heading*" in out and "## " not in out
    assert "*bold*" in out and "**" not in out and "__" not in out
    assert "~gone~" in out and "~~" not in out
    assert "☑ done" in out and "☐ todo" in out and "• plain" in out and "• star" in out
    assert "<https://x/y|the doc>" in out and "<https://x/s.png|shot>" in out
    assert "<!--" not in out and "agent-comment" not in out


def test_to_mrkdwn_is_idempotent_and_leaves_prose_alone():
    prose = "Should I use approach A or B? The cap is 1500 chars — see the link."
    assert to_mrkdwn(prose) == prose
    once = to_mrkdwn(CHECKLIST)
    assert to_mrkdwn(once) == once


def test_collapsed_blocks_unfold_for_slack():
    """issue-472 R3.4 — Slack has no collapsible block and reads `<…>` as link
    syntax, so `<details>` goes and a `<summary>` becomes a bold line."""
    text = (
        "Pick one:\n\n- [ ] `model-a`\n\n<details>\n"
        "<summary>ℹ️ What this means</summary>\n\n"
        "Leave it alone and the default stands.\n\n</details>\n\n"
        "Keep `<details>` here.\n\n```html\n<details>\n```\n"
    )
    out = to_mrkdwn(text)
    assert "*ℹ️ What this means*" in out
    assert "<summary>" not in out and "</details>" not in out
    assert "Leave it alone and the default stands." in out
    # code is drawn as written, HTML included
    assert "Keep `<details>` here." in out and "```html\n<details>\n```" in out
    assert to_mrkdwn(out) == out


def test_html_comments_never_reach_slack():
    assert strip_comments("a <!-- x --> b") == "a  b"
    assert strip_comments("a <!-- x\ny --> b <!-- z -->") == "a  b "
    # an unterminated opener is text, never an infinite scan
    assert strip_comments("a <!-- open") == "a <!-- open"
    assert PHASE_SELECTION_MARKER not in to_mrkdwn(CHECKLIST)


def test_code_is_drawn_as_written():
    """A `# comment` in a shell snippet is not a heading; `**` in a code span is
    two asterisks; a bullet inside a fence stays a dash."""
    text = (
        "Run this:\n\n```sh\n# the cap\n- not a bullet\n**literal**\n```\n\n"
        "Then `**keep**` and `- [x] raw` inline, and **bold** outside."
    )
    out = to_mrkdwn(text)
    assert "# the cap\n- not a bullet\n**literal**" in out
    assert "`**keep**`" in out and "`- [x] raw`" in out and " *bold* " in out


def test_a_foreign_html_comment_is_removed_too():
    """A5: the scan is not marker-aware — every comment goes, whoever wrote it."""
    assert to_mrkdwn("x <!-- not the-loop's --> y") == "x  y"


def test_a_slack_broadcast_in_a_comment_is_neutralised():
    """A2: a comment on a ticket can never page a workspace."""
    text = "hey <!channel> and <!here> and <!everyone> and <!subteam^S1|eng>"
    out = to_mrkdwn(text)
    assert "<!" not in out and "&lt;!channel>" in out and "&lt;!subteam^S1|eng>" in out


# -- the digest is retired (issue-549 R1.1, R1.2) ----------------------------------


def test_the_digest_module_is_gone():
    """R1.2: nothing condenses or truncates a message any more, so the module
    that did is not importable and no channel module names it."""
    from pathlib import Path

    from the_loop import channels

    assert importlib.util.find_spec("the_loop.channels.digest") is None
    package = Path(str(channels.__file__)).parent
    assert not [
        path.name
        for path in package.glob("*.py")
        if "from .digest" in path.read_text() or "channels.digest" in path.read_text()
    ]


def _config(tmp_path, **slack):
    section = {"enabled": True, "channel": "C123", **slack}
    return {"state": {"root": str(tmp_path / "state")}, "channels": {"slack": section}}


@pytest.mark.parametrize("value", ["truncate", "llm"])
def test_long_messages_is_ignored_since_issue_549(tmp_path, caplog, monkeypatch, value):
    """issue-549 R1.2, R1.3 (was issue-338 R1.4): the key is deprecated, the
    config still loads whatever it says, and loading it warns by name."""
    monkeypatch.setattr("the_loop.channels.slack._DEPRECATED_WARNED", set())
    with caplog.at_level("WARNING", logger="the-loop.channels"):
        config = SlackChannelConfig.from_mapping(_config(tmp_path, longMessages=value))
    assert config.enabled
    assert not hasattr(config, "long_messages") and not hasattr(config, "max_chars")
    assert "longMessages" in caplog.text
    schema = configschema.load_schema("cli-config")
    key = schema["properties"]["channels"]["properties"]["slack"]["properties"][
        "longMessages"
    ]
    assert key["deprecated"] is True


# -- the fallback text (issue-549 R2.7) ---------------------------------------------


def _event(text, **kw):
    return Event(
        event_type=kw.pop("event_type", "comment.agent"),
        work_item="github:o/r#338",
        text=text,
        url=kw.pop("url", "https://gh/o/r/issues/338#c1"),
        detail=kw.pop("detail", {"author": "the-loop"}),
        source="github",
    )


class _Client:
    def __init__(self):
        self.posted = []

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None, **unfurl):
        self.posted.append({"text": text, "blocks": blocks, "thread_ts": thread_ts})
        return {"ok": True, "ts": f"1700.{len(self.posted):06d}"}

    def chat_getPermalink(self, **kw):
        return {"permalink": ""}


def test_the_fallback_text_is_the_short_form(tmp_path, monkeypatch):
    """issue-549 R2.7 (replaces issue-338 R1.5, the digest in the fallback): the
    phone's notification preview is the short form, exactly as the message
    draws it, and leads with the ask."""
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    client = _Client()
    config = SlackChannelConfig.from_mapping(_config(tmp_path))
    channel = SlackBotChannel(
        config, tmp_path / "state" / "slack.json", client_factory=lambda t: client
    )
    channel.post(_event(CHECKLIST))
    reply = client.posted[-1]
    section = reply["blocks"][0]["text"]["text"]
    assert reply["text"] == section
    assert "which phases does this work item need?" in reply["text"]
    assert PHASE_SELECTION_MARKER not in reply["text"]
    channel.post(_event("A or B?"))
    assert client.posted[-1]["text"].startswith("A or B?")
    assert client.posted[-1]["text"] == client.posted[-1]["blocks"][0]["text"]["text"]


# -- channels status (issue-549 R1.4) ----------------------------------------------


@pytest.mark.parametrize("value", ["digest", "truncate"])
def test_status_prints_neither_deprecated_key(tmp_path, monkeypatch, capsys, value):
    """issue-549 R1.4 (was issue-338 R4.3): `channels status` prints no
    `maxChars` or `longMessages` line, whatever the config still sets."""
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(_config(tmp_path, longMessages=value, maxChars=700)),
        encoding="utf-8",
    )
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    out = capsys.readouterr().out
    assert "slack" in out
    assert "maxChars" not in out and "longMessages" not in out
