"""The short-form builder (issue-549 task 7).

The top-level Slack message, read on a phone: the agent's summary; else the
fixed runtime lead for an event no agent wrote; else a line built from the first
question or sentence, which records ``channels.short_form_missing``. Defused,
drawn as mrkdwn, capped at 600 characters on a sentence. It is also every
message's ``text`` fallback.

Spec: docs/specs/issue-549/{requirements,design}.md (R2.7, R3.2–R3.6, abuse cases 2, 5).
"""

from __future__ import annotations

import pytest

from the_loop import eventlog
from the_loop.channels import digest
from the_loop.channels.base import Event
from the_loop.channels.shortform import (
    SUMMARY_MAX_CHARS,
    ShortForm,
    build_short_form,
    cap_short_form,
    is_session_authored,
    long_form_adds,
)
from the_loop.channels.voice import room_lead

REF = "github:Octo/Repo#7"
URL = "https://github.com/Octo/Repo/issues/7#issuecomment-1"


@pytest.fixture
def log(monkeypatch):
    seen = []
    monkeypatch.setattr(
        eventlog, "emit", lambda name, level="info", **f: seen.append((name, f))
    )
    return seen


def _comment(text="", summary="", **kw):
    kw.setdefault("source", "cli")
    return Event(
        event_type="comment.agent",
        work_item=REF,
        text=text,
        url=URL,
        summary=summary,
        event_id="ev-1",
        **kw,
    )


# -- the order: summary, lead, built ----------------------------------------------


def test_summary_wins(log):
    event = _comment(
        text="# Design\n\nA long document. Should we ship?",
        summary="Design is ready. **Approve** it?",
    )
    short = build_short_form(event)
    assert isinstance(short, ShortForm)
    assert short.source == "summary"
    assert short.text == "Design is ready. *Approve* it?"  # drawn as mrkdwn
    assert short.url == URL
    assert log == []


def test_runtime_lead(log):
    event = Event(
        event_type="phase.started",
        work_item=REF,
        text="",
        detail={"node": "design"},
        source="loop",
        event_id="ev-2",
    )
    short = build_short_form(event)
    assert short.source == "lead"
    assert short.text == room_lead(event)
    assert log == []


def test_runtime_lead_is_defused():
    event = Event(
        event_type="phase-approval-pending",
        work_item=REF,
        text="Ready <!channel> for <@U123ABC>",
        source="loop",
    )
    short = build_short_form(event)
    assert short.source == "lead"
    assert "<!" not in short.text and "<@" not in short.text


def test_built_fallback_logs(log):
    event = _comment(
        text=(
            "<!-- the-loop:marker -->\nI finished the design. It has three parts.\n\n"
            "Which option do you prefer, A or B? Tell me soon."
        )
    )
    short = build_short_form(event)
    assert short.source == "built"
    assert short.text.startswith("Which option do you prefer, A or B?")
    assert short.text.endswith(f"<{URL}|Open on GitHub>")  # the work item's link
    assert log == [
        (
            "channels.short_form_missing",
            {"work_item": REF, "event_type": "comment.agent", "event_id": "ev-1"},
        )
    ]


def test_built_fallback_first_sentence_when_no_question(log):
    event = _comment(
        text="## Summary\n\nI **finished** the design. It has three parts."
    )
    short = build_short_form(event)
    assert short.source == "built"
    assert short.text.startswith("I *finished* the design.")
    assert "three parts" not in short.text
    assert len(log) == 1


def test_built_fallback_skips_code_and_tables(log):
    event = _comment(text="```\nwhat? no.\n```\n\n| a? |\n|---|\n\nReal question here?")
    assert build_short_form(event).text.startswith("Real question here?")


def test_session_authored_without_summary_never_uses_lead(log):
    event = Event(
        event_type="session.awaiting_input",
        work_item=REF,
        text="Should I use Postgres? Context follows.",
        source="session",
    )
    assert is_session_authored(event)
    assert build_short_form(event).source == "built"


def test_is_session_authored():
    assert is_session_authored(_comment(text="x", source="cli"))
    assert is_session_authored(_comment(text="x", source="github"))  # the mirror
    assert not is_session_authored(
        Event(event_type="phase.completed", work_item=REF, text="", source="loop")
    )


# -- the cap (R3.6) ----------------------------------------------------------------


def test_cap_600_on_sentence():
    assert SUMMARY_MAX_CHARS == 600
    sentence = "This sentence is exactly fifty characters long ok. "
    summary = sentence * 20  # 1,000 characters
    short = build_short_form(_comment(text="body", summary=summary))
    assert len(short.text) <= 600
    assert short.text.endswith("ok.")  # cut at a sentence, not in a word
    whole = max(k for k in range(21) if len((sentence * k).strip()) <= 600)
    assert short.text == (sentence * whole).strip()


def test_cap_keeps_short_text_whole():
    assert cap_short_form("Short. Text.") == "Short. Text."


def test_cap_never_leaves_a_link_open():
    text = "Lead <https://example.com/x|" + "a label of many words " * 20 + ">"
    capped = cap_short_form(text, 100)
    assert len(capped) <= 100
    assert capped.count("<") == capped.count(">")


def test_digest_shares_the_cap():
    # one constant: the digest's summary cap is the short form's
    assert digest.SUMMARY_MAX_CHARS is SUMMARY_MAX_CHARS


def test_preamble_counts_toward_the_cap():
    summary = "Word. " * 200
    short = build_short_form(_comment(summary=summary), preamble="*Recap:* 2 gates.")
    assert short.text.startswith("*Recap:* 2 gates.\n")
    assert len(short.text) <= 600


# -- R2.7: the text fallback -------------------------------------------------------


def test_text_fallback_is_short_form():
    short = build_short_form(_comment(text="long " * 50, summary="**Done.** Look?"))
    assert short.fallback == short.text == "*Done.* Look?"


# -- R3.3: the long form adds something or is not posted ---------------------------


def test_long_form_adds_only_when_it_is_more_than_the_short_form():
    same = _comment(text="All done.", summary="All done.")
    assert not long_form_adds(same, build_short_form(same))
    more = _comment(text="All done.\n\nDetails follow here.", summary="All done.")
    assert long_form_adds(more, build_short_form(more))
    empty = _comment(text="<!-- only a marker -->", summary="Hi.")
    assert not long_form_adds(empty, build_short_form(empty))


# -- abuse cases -------------------------------------------------------------------


def test_abuse_summary_foreign_link_keeps_event_url():
    event = _comment(
        text="body",
        summary="Approve here: [GitHub](https://evil.example/phish) or <https://evil.example>",
    )
    short = build_short_form(event)
    assert short.url == URL  # the button carries the event's own URL


def test_abuse_built_link_is_the_event_url(log):
    event = _comment(text="See https://evil.example/x now. Then more.")
    short = build_short_form(event)
    assert short.text.endswith(f"<{URL}|Open on GitHub>")
    assert short.url == URL


@pytest.mark.parametrize(
    "summary", ["<!here> please look", "ping <@U012AB3CD>", "<!subteam^S1|@t> go"]
)
def test_defuse_summary_broadcast_and_mention(summary):
    short = build_short_form(_comment(text="body", summary=summary))
    assert "<!" not in short.text and "<@" not in short.text
