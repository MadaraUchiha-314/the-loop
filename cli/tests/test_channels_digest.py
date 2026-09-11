"""The Slack digest (issue-338): long text condensed by structure — the ask
first, choices numbered, code / tables / traces as pointers, paths shortened,
cut at a sentence — and GitHub markdown drawn as Slack mrkdwn on every message.

Pure functions over strings, plus the renderer's and the config's use of them.
No Slack, no network: the SDK boundary is the injected client factory.
"""

from __future__ import annotations

import argparse
import json
import re
import time

import pytest

from the_loop import configschema
from the_loop.channels.base import Event
from the_loop.channels.digest import (
    DEFAULT_DIGEST_MODE,
    DIGEST_MODES,
    condense,
    fit,
    shorten_paths,
    strip_comments,
    to_mrkdwn,
    truncate,
)
from the_loop.channels.slack import (
    PHASE_SELECTION_MARKER,
    SlackBotChannel,
    SlackChannelConfig,
    render_blocks,
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

#: A progress comment with everything Slack cannot use, and the question last.
REPORT = """## Verification failed on task 3

I ran the suite from `/home/user/the-loop/cli/tests/test_channels.py` and one case is red.

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels.py
F.......
```

The failure:

Traceback (most recent call last):
  File "/home/user/the-loop/cli/the_loop/channels/slack.py", line 480, in _cap
    return text[:max_chars].rstrip()
TypeError: slice indices must be integers

| case | expected | got |
|------|----------|-----|
| cap  | 400      | 401 |
| link | kept     | kept |

The cause is a string `maxChars` in the fixture. Two ways out: coerce in the renderer, or refuse at parse time (see [decision-094](https://github.com/o/r/blob/main/docs/decisions/decision-094.md)).

1. Coerce in the renderer — one line, hides a config error.
2. Refuse at parse time — the fail-closed direction, one more warning.

Which one should I take?
"""


def _lines(text):
    return [line for line in text.split("\n") if line.strip()]


def _strip_dressing(line):
    """A digest line without what the digest added — the number, the box, the
    bold of an ask or heading, the ellipsis."""
    core = re.sub(r"^\d+\. ", "", line.strip())
    core = re.sub(r"^[☑☐] ", "", core)
    if core.startswith("*") and core.endswith("*") and len(core) > 2:
        core = core[1:-1]
    return core.rstrip("…").strip()


# -- to_mrkdwn (R3.3, R3.4) --------------------------------------------------------


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


def test_html_comments_never_reach_slack():
    assert strip_comments("a <!-- x --> b") == "a  b"
    assert strip_comments("a <!-- x\ny --> b <!-- z -->") == "a  b "
    # an unterminated opener is text, never an infinite scan
    assert strip_comments("a <!-- open") == "a <!-- open"
    assert PHASE_SELECTION_MARKER not in to_mrkdwn(CHECKLIST)
    assert PHASE_SELECTION_MARKER not in condense(CHECKLIST, 600)


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
    digested = condense(text + " " + "Filler sentence here. " * 100, 300)
    assert "`**keep**`" in digested and "⟨code: 3 lines⟩" in digested


def test_a_text_that_grows_past_the_cap_when_drawn_is_digested():
    """Only the broadcast rewrite grows a text; it never posts over the cap."""
    text = "Q? " + "<!here> " * 40  # 323 raw characters, 443 once drawn
    out = fit(text, 400)
    assert len(out) <= 400 and "<!here>" not in out and out.startswith("*Q?*")


def test_a_question_in_a_heading_leads_and_leaves_no_empty_heading():
    text = "## Which one?\n\n" + "Detail sentence here. " * 100
    out = condense(text, 200)
    assert out.startswith("*Which one?*") and "**" not in out


def test_a_foreign_html_comment_is_removed_too():
    """A5: the scan is not marker-aware — every comment goes, whoever wrote it."""
    assert to_mrkdwn("x <!-- not the-loop's --> y") == "x  y"


def test_a_slack_broadcast_in_a_comment_is_neutralised():
    """A2: a comment on a ticket can never page a workspace."""
    text = "hey <!channel> and <!here> and <!everyone> and <!subteam^S1|eng>"
    out = to_mrkdwn(text)
    assert "<!" not in out and "&lt;!channel>" in out and "&lt;!subteam^S1|eng>" in out
    # digested or not
    long_text = text + " " + ("word " * 400)
    assert "<!channel>" not in condense(long_text, 300)
    assert "<!channel>" not in fit(long_text, 300, "truncate")


# -- condense: the ask, the choices, the order (R2) ----------------------------------


def test_the_first_question_leads():
    out = condense(CHECKLIST, 700, url="https://gh/o/r/issues/338#c1")
    first = _lines(out)[0]
    assert first == "*🤖 _the-loop_ — which phases does this work item need?*"
    # the instruction sentence stays where it was, in the author's paragraph
    assert "then reply `the-loop execute`" in out


def test_a_reply_instruction_leads_when_nothing_asks():
    text = (
        "The plan is written. Nothing else is pending on my side.\n\n"
        "Tick the boxes and then reply `the-loop execute` to run it.\n\n" + "x. " * 600
    )
    out = condense(text, 300)
    assert (
        _lines(out)[0]
        == "*Tick the boxes and then reply `the-loop execute` to run it.*"
    )


def test_without_an_ask_the_first_sentence_leads():
    text = "The suite is green. " + "More detail follows here. " * 100
    out = condense(text, 200)
    assert out.startswith("The suite is green.")
    assert "*" not in _lines(out)[0]  # nothing is dressed up as an ask


def test_a_list_becomes_numbered_lines_with_its_boxes():
    out = condense(CHECKLIST, 2900)  # room for every list; the budget is T1's own test
    assert "1. ☑ brainstorming" in out
    assert "7. ☑ verification" in out
    assert (
        "1. ☐ `outer-loop-on-pull-request` — on a pull request in this repository."
        in out
    )
    report = condense(REPORT, 1200)
    assert "1. Coerce in the renderer — one line, hides a config error." in report
    assert (
        "2. Refuse at parse time — the fail-closed direction, one more warning."
        in report
    )


def test_the_authors_order_is_kept_after_the_ask():
    out = condense(REPORT, 1500, url="https://gh/c")
    lines = _lines(out)
    assert lines[0] == "*Which one should I take?*"
    order = [
        lines.index(next(line for line in lines if needle in line))
        for needle in (
            "*Verification failed on task 3*",
            "one case is red",
            "⟨code: 2 lines⟩",
            "⟨stack trace: 4 lines⟩",
            "⟨table: 2 rows⟩",
            "1. Coerce",
            "2. Refuse",
        )
    ]
    assert order == sorted(order)


# -- condense: pointers and paths (R3) ------------------------------------------------


def test_fences_tables_and_traces_become_pointers():
    out = condense(REPORT, 1500, url="https://gh/c")
    assert "_⟨code: 2 lines⟩_" in out
    assert "_⟨stack trace: 4 lines⟩_" in out
    assert "_⟨table: 2 rows⟩_" in out
    assert "```" not in out and "Traceback" not in out and "| case |" not in out
    assert "TypeError" not in out
    assert out.rstrip().endswith("_… full text: <https://gh/c|GitHub>_")


def test_absolute_paths_are_shortened_and_urls_untouched():
    text = (
        "Edit `/home/user/the-loop/cli/the_loop/channels/slack.py` at "
        "/home/user/the-loop/cli/tests/test_channels.py:480 and see "
        "https://github.com/o/r/blob/main/docs/decisions/decision-094.md — /tmp/x stays."
    )
    out = shorten_paths(text)
    assert "`…/channels/slack.py`" in out
    assert " …/tests/test_channels.py:480" in out
    assert "https://github.com/o/r/blob/main/docs/decisions/decision-094.md" in out
    assert "/tmp/x stays" in out
    assert "/home/user" not in out
    assert "/home/user" not in condense(REPORT, 1500)


# -- condense: the budget and the cut (R1) --------------------------------------------


@pytest.mark.parametrize("limit", [200, 400, 700, 1200, 2900])
def test_a_long_text_is_digested_within_the_limit(limit):
    for text in (CHECKLIST, REPORT):
        out = condense(text, limit, url="https://gh/c")
        assert 0 < len(out) <= limit, (limit, len(out))


def test_the_cut_falls_on_a_sentence_boundary():
    text = "Q? " + " ".join(f"Sentence number {n} is here." for n in range(1, 200))
    out = condense(text, 300, url="https://gh/c")
    body = out.split("\n\n")[1]
    assert body.endswith("is here.")
    assert "…" not in body  # a sentence cut needs no ellipsis of its own
    assert out.rstrip().endswith("_… full text: <https://gh/c|GitHub>_")


def test_a_sentence_too_long_for_the_room_is_cut_at_a_clause_then_a_space():
    one_sentence = ", ".join(f"clause {n}" for n in range(1, 200)) + "."
    out = condense(one_sentence, 120, url="")
    body = _lines(out)[0]
    assert len(out) <= 120
    assert re.fullmatch(r"clause 1(, clause \d+)+…", body), body  # whole clauses only
    no_clauses = " ".join(f"word{n}" for n in range(400))
    body = _lines(condense(no_clauses, 100))[0]
    assert body.endswith("…") and body[:-1].strip().startswith("word0")
    assert all(piece.startswith("word") for piece in body[:-1].split())
    one_token = "x" * 5000
    out = condense(one_token, 100)
    assert len(out) <= 100 and out.startswith("x")


def test_the_footer_names_the_link_or_the_ticket():
    text = "Q? " + "Filler sentence here. " * 200
    assert (
        condense(text, 300, url="https://gh/c")
        .rstrip()
        .endswith("_… full text: <https://gh/c|GitHub>_")
    )
    assert condense(text, 300).rstrip().endswith("_… the full text is on the ticket_")


def test_the_footer_links_the_event_never_the_text():
    """A3: a link in the text posing as 'the full text' is drawn as a link and
    nothing more; the pointer is the event's URL."""
    text = (
        "Q? Read the [full text](https://evil.example/phish) first. "
        + "Filler sentence here. " * 200
    )
    out = condense(text, 300, url="https://gh/c")
    assert out.rstrip().endswith("_… full text: <https://gh/c|GitHub>_")
    assert "<https://evil.example/phish|full text>" in out


def test_nothing_is_left_out_when_everything_fits_compactly():
    # over the cap as written, under it once the boxes and bullets are drawn
    text = "Q?\n\n" + "\n".join(f"- [x] item{n}" for n in range(30))
    out = condense(text, len(text) - 1)
    assert "full text" not in out and "…" not in out
    assert "30. ☑ item29" in out


def test_every_digest_line_is_the_authors():
    """The faithfulness property: no sentence a member reads was written by the
    digest — only the numbers, the boxes, the pointers and the footer are its own."""
    for text in (CHECKLIST, REPORT):
        # the words, not the marks: an ask or heading is re-dressed in one bold span
        reference = " ".join(shorten_paths(to_mrkdwn(text)).split()).replace("*", "")
        for limit in (250, 600, 1400):
            out = condense(text, limit, url="https://gh/c")
            for line in _lines(out):
                if line.startswith("_⟨") or line.startswith("_… "):
                    continue
                core = _strip_dressing(line).replace("*", "")
                assert core and core in reference, (limit, line)


def test_empty_and_odd_inputs_never_raise():
    for text in (
        "",
        "   \n\n  ",
        "?",
        "…",
        "```",
        "```\nopen fence",
        "- ",
        "|",
        "<!--",
    ):
        assert isinstance(condense(text, 200), str)
        assert isinstance(fit(text, 200), str)
    unicode = "¿Qué hacemos? " + "Más texto aquí — con guiones y «comillas». " * 100
    out = condense(unicode, 200)
    assert out.startswith("*¿Qué hacemos?*") and len(out) <= 200


def test_a_pathological_comment_digests_in_linear_time():
    """A1 / T7: thousands of unclosed openers cost the same as prose."""
    evil = (
        ("**" * 4000) + ("<!--" * 4000) + ("[" * 4000) + ("```" * 4000) + ("(" * 4000)
    )
    evil += "\n" + ("- " * 4000) + "\n" + ("|" * 4000)
    started = time.monotonic()
    for _ in range(3):
        condense(evil, 1500, url="https://gh/c")
        to_mrkdwn(evil)
        fit(evil, 1500, "truncate")
    assert time.monotonic() - started < 5.0


# -- fit: the threshold and the modes (R1.4, R4.1, R4.2) ----------------------------


def test_a_short_text_passes_through_untouched():
    prose = "Should I use approach A or B? The cap is what it is."
    assert fit(prose, 1500) == prose
    marked = "Reply `the-loop execute`.\n<!-- the-loop:agent-comment -->"
    assert fit(marked, 1500) == "Reply `the-loop execute`."


def test_the_threshold_is_the_raw_length():
    text = "**a** " * 100 + "\n```\ncode\n```"  # 612 raw characters, 412 once drawn
    drawn = to_mrkdwn(text).strip()
    assert "```" in fit(text, 700) and fit(text, 700) == drawn  # under the cap: whole
    assert "⟨code: 1 lines⟩" in fit(text, 500)  # over the cap as written: digested


def test_truncate_is_the_13_10_0_cut():
    text = "x" * 5000
    out = truncate(text, 400)
    assert out.startswith("x" * 400) and "4600 more characters — see the link" in out
    assert fit(text, 400, "truncate") == out
    assert DIGEST_MODES == ("digest", "truncate") and DEFAULT_DIGEST_MODE == "digest"


# -- the config (R1.4, R4.2) ----------------------------------------------------------


def _config(tmp_path, **slack):
    section = {"enabled": True, "channel": "C123", **slack}
    return {"state": {"root": str(tmp_path / "state")}, "channels": {"slack": section}}


def test_long_messages_is_parsed_and_defaults_to_digest(tmp_path):
    assert SlackChannelConfig.from_mapping(_config(tmp_path)).long_messages == "digest"
    assert (
        SlackChannelConfig.from_mapping(
            _config(tmp_path, longMessages="truncate")
        ).long_messages
        == "truncate"
    )
    schema = configschema.load_schema("cli-config")
    key = schema["properties"]["channels"]["properties"]["slack"]["properties"][
        "longMessages"
    ]
    assert key["default"] == DEFAULT_DIGEST_MODE and key["enum"] == list(DIGEST_MODES)


def test_an_unknown_long_messages_value_resolves_to_digest(tmp_path, caplog):
    with caplog.at_level("WARNING", logger="the-loop.channels"):
        config = SlackChannelConfig.from_mapping(_config(tmp_path, longMessages="llm"))
    assert config.long_messages == "digest" and config.enabled
    assert "longMessages" in caplog.text


# -- the renderer (R1.1, R1.5, R3.3) -------------------------------------------------


def _event(text, **kw):
    return Event(
        event_type=kw.pop("event_type", "comment.agent"),
        work_item="github:o/r#338",
        text=text,
        url=kw.pop("url", "https://gh/o/r/issues/338#c1"),
        detail=kw.pop("detail", {"author": "the-loop"}),
        source="github",
    )


def test_render_blocks_digests_the_text_section():
    blocks = render_blocks(_event(CHECKLIST), "normal", max_chars=700)
    section = blocks[1]["text"]["text"]
    assert section.startswith(
        "*🤖 _the-loop_ — which phases does this work item need?*"
    )
    assert len(section) <= 700 and PHASE_SELECTION_MARKER not in section
    assert section.rstrip().endswith(
        "_… full text: <https://gh/o/r/issues/338#c1|GitHub>_"
    )
    # the section is a digest, so the Execute button still sits on the message
    assert blocks[-1]["type"] == "actions"


def test_render_blocks_digests_the_excerpt_too():
    event = _event(
        "the-loop: issue-338 is at *design-approval* (phase-approval-pending).",
        event_type="phase-approval-pending",
        detail={"node": "design-approval", "excerpt": REPORT, "artifact": "design.md"},
    )
    blocks = render_blocks(event, "normal", max_chars=600)
    excerpt = blocks[2]["text"]["text"]
    assert excerpt.startswith("*Which one should I take?*") and len(excerpt) <= 600
    assert "```" not in excerpt


def test_render_blocks_truncate_keeps_the_old_cut():
    blocks = render_blocks(
        _event("x" * 5000), "normal", max_chars=400, long_messages="truncate"
    )
    text = blocks[1]["text"]["text"]
    assert text.startswith("x" * 400) and "more characters — see the link" in text


def test_a_short_section_is_drawn_and_nothing_else():
    blocks = render_blocks(_event("Approach **A** or B?\n<!-- m -->"), "normal")
    assert blocks[1]["text"]["text"] == "Approach *A* or B?"


class _Client:
    def __init__(self):
        self.posted = []

    def chat_postMessage(self, *, channel, text, thread_ts=None, blocks=None):
        self.posted.append({"text": text, "blocks": blocks, "thread_ts": thread_ts})
        return {"ok": True, "ts": f"1700.{len(self.posted):06d}"}

    def chat_getPermalink(self, **kw):
        return {"permalink": ""}


def test_the_fallback_text_carries_the_digest(tmp_path, monkeypatch):
    """R1.5: the phone's notification preview leads with the ask too."""
    monkeypatch.setenv("THE_LOOP_SLACK_BOT_TOKEN", "xoxb-test")
    client = _Client()
    config = SlackChannelConfig.from_mapping(_config(tmp_path, maxChars=700))
    channel = SlackBotChannel(
        config, tmp_path / "state" / "slack.json", client_factory=lambda t: client
    )
    channel.post(_event(CHECKLIST))
    reply = client.posted[-1]
    section = reply["blocks"][1]["text"]["text"]
    assert section in reply["text"]
    assert "*🤖 _the-loop_ — which phases does this work item need?*" in reply["text"]
    assert PHASE_SELECTION_MARKER not in reply["text"]
    # a short message's fallback is what it always was
    channel.post(_event("A or B?"))
    assert client.posted[-1]["text"].endswith("\n\nA or B?")


def test_nothing_but_the_renderer_reads_the_digest():
    """A4: the pipeline, the ledger and the bus never see a digest — gates and
    control read the record, and only `slack.py` imports the module."""
    from pathlib import Path

    from the_loop import channels

    package = Path(str(channels.__file__)).parent
    importers = sorted(
        path.stem
        for path in package.glob("*.py")
        if path.stem != "digest"
        and re.search(r"^(from|import) .*\bdigest\b", path.read_text(), re.M)
    )
    assert importers == ["slack"]


# -- channels status (R4.3) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("digest", "longMessages: digest — above maxChars: the ask first"),
        ("truncate", "longMessages: truncate — above maxChars: the first maxChars"),
    ],
)
def test_status_prints_the_long_messages_line(
    tmp_path, monkeypatch, capsys, value, expected
):
    from the_loop.commands.channels_cmd import ChannelsCommand

    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "cli-config.yaml"))
    (tmp_path / "cli-config.yaml").write_text(
        json.dumps(_config(tmp_path, longMessages=value)), encoding="utf-8"
    )
    parser = argparse.ArgumentParser()
    ChannelsCommand().add_arguments(parser)
    assert ChannelsCommand().run(parser.parse_args(["status"])) == 0
    out = capsys.readouterr().out
    assert expected in out and "maxChars:     1500" in out
