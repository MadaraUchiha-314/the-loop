---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#405"
---

# Security review: the clause reader stops at the phases; the close path waits for the endgame (issue-405)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Trust boundary (P1):* unchanged. The text is a Slack member's the allow-list and
    the roster already admitted; a cleaned item is still validated against the
    checklist's own rows before anything is written, and a non-name is still refused
    without being echoed — the `<!channel>`, `@here`, 60-character and
    `design;rm -rf /` cases stay pinned (`test_abuse_a_hostile_name_is_named_never_echoed`).
    `strip_signature` removes text only; nothing it does can add a phase the person did
    not type. The `read` field carries token-shaped items verbatim and anything else as
    a length, so no broadcast, mention or prose reaches the event log through it
    (pinned by the same test and by
    `test_a_non_token_word_drops_as_unknown_phase_and_the_record_says_what_was_read`).
  - *Permissions (P2):* none widened. A held closure keeps a session **open** that
    GitHub already declared finished, for a bounded time, on the machine that spawned
    it, with the access it already had. The hold is decided from the-loop's own graph
    state (`GraphContext`, through the ownership-gated `context()` read), never from
    event text; a state that cannot be read, a pointer off a terminal node, a dead pane
    or `finishGraceSeconds: 0` answers *close now* — today's behaviour
    (`test_a_dead_pane_an_unreadable_graph_or_no_grace_close_at_once`).
  - *The cleanup gate:* unchanged. `_cleanup_after_close` still requires a named,
    allowlisted closer; a held closure re-reads the same routed event when it finishes.
  - *Denial of service:* the hold is bounded by the deadline whatever the session does;
    a second close for a held ref is a no-op and the poller stops re-asking, so a
    closure cannot be held twice or re-delivered every cycle.
  - *Fail-closed:* every miss on both paths degrades to today's behaviour — a refusal
    that records nothing, or an immediate close.
  - *New surface:* one additive config key (`number`, `minimum: 0`), two additive
    `GraphContext` fields, three additive event fields and two event types; no grant,
    scope, lock, schema-shape or state-file change.
- **Human sign-off:** n/a (risk tier 3).
