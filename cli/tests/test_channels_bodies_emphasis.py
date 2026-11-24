"""A channel's record passes this repository's markdown lint (issue-555).

The ledger bodies a channel writes can be copied into a spec file: a gate's
``record-feedback`` hook copies a relayed approval into *Review comments*. The
repository's lint (MD049) requires asterisk emphasis, so no body the-loop
composes may use underscore emphasis. The record reader still reads the old
underscore labels on comments written before the change.
"""

import re

from the_loop.channels.base import Event
from the_loop.channels.bodies import issue_body, mirror_body, relay_body
from the_loop.channels.records import _record_from_body
from the_loop.channels.envelope import Envelope, stamp
from the_loop.authz import SELF_COMMENT_ATTRIBUTION, mark_self_authored

#: Underscore emphasis as MD049 sees it: `_x_` that does not sit inside a word.
UNDERSCORE_EMPHASIS = re.compile(r"(?<![\w_])_[^_\s][^_]*?_(?![\w_])")


def _event(event_type, detail=None):
    return Event(
        event_type=event_type,
        work_item="github:octo/repo#555",
        text="approve",
        detail=detail or {},
        source="slack",
    )


def test_a_relayed_answer_uses_no_underscore_emphasis():
    body = relay_body(_event("gate.feedback", {"gate": "requirements-approval"}))
    assert "*the-loop — answer to the open gate from" in body
    assert not UNDERSCORE_EMPHASIS.search(body)


def test_a_mirrored_decision_and_an_opened_issue_use_no_underscore_emphasis():
    decision = mirror_body(
        _event(
            "decision.recorded",
            {
                "rationale": "it is cheap",
                "thread": "https://x.slack.com/t",
                "kind": "tech",
            },
        ),
        None,
    )
    assert "*why:* it is cheap" in decision
    assert "*discussed at:* <https://x.slack.com/t>" in decision
    # The self-authored sign is left out: record-feedback never copies a marked
    # comment, and jiraformat matches the sign's exact line on older comments.
    decision = decision.replace(SELF_COMMENT_ATTRIBUTION, "")
    for body in (decision, issue_body(_event("work-item.create"))):
        assert not UNDERSCORE_EMPHASIS.search(body)


def test_a_record_written_with_the_old_underscore_labels_is_still_read():
    body = stamp(
        mark_self_authored(
            "🗣️ **the-loop** — decision:\n\n> keep poll mode"
            "\n\n_why:_ it is cheap\n\n_discussed at:_ <https://x.slack.com/t>"
        ),
        Envelope(
            type="decision.recorded",
            source="slack",
            actor={"slack": "U1"},
            ts="2026-11-24T00:00:00Z",
        ),
    )
    record = _record_from_body(body)
    assert record is not None
    assert record.why == "it is cheap"
    assert record.discussed_at == "https://x.slack.com/t"
