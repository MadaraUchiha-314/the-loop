---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#371"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: every comment the-loop finishes with says so on the comment

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `claude/claude-opus-5` (self) | new findings | 4 found, 4 dispositioned — see below | this file |
| 2 | `claude/claude-opus-5` (self) | zero (converged) | the same diff re-read against the audit table: every row the audit calls correct is still silent, every row it calls a gap is now acknowledged | this file |

## Round 1 findings

1. **`_settle` now makes a blocking `gh` call on the webhook receiver's HTTP request
   thread.** `daemon.on_event` calls `Dispatcher.handle` synchronously, so a settled event
   costs that thread a subprocess where it previously cost local I/O only — bounded by the
   reactor's 30-second timeout, against GitHub's 10-second delivery timeout.
   *Disposition:* **accepted and documented**, not fixed. `handle` already makes exactly
   this kind of call at its top (`_verify_linkage` → `WorkItemVerifier`, a 10-second
   bounded `gh api`), the record is written before the decoration so the worst case loses
   only a delivery receipt whose redelivery is deduped against the id already marked, and
   the receiver is a `ThreadingHTTPServer`. Written up in `design.md` § "A known
   consequence: one `gh` call inside `handle`", including the background-thread
   alternative and why it is disproportionate for a decoration.
2. **A scope refusal carrying an authorized command would have reacted 😕.** The refusal
   routes through `_reject_control`, which settles `control-rejected` — an outcome that
   *is* in the table — so the table alone would have broken issue-322 R2.6 ("no reaction,
   no comment, no record") on exactly the path that matters: a second daemon marking a
   work item it does not own. *Fixed:* `_reject_control` takes `acknowledge`, and
   `_refuse_scope` passes `False`. Covered by T7, which asserts both routes (with and
   without a keyword) post nothing, and asserts the settled outcome is `control-rejected`
   so the silence is proven to come from the flag rather than from the table.
3. **`_dispatch_one`'s paused settle would have added a third reaction** inside a worker
   that has already posted 👀 and will post 🎉 — a redundant round trip describing an
   entity that already carries the state. *Fixed:* that one call passes
   `acknowledge=False`, with the reason in the comment beside it. T10 drives
   `_dispatch_one` directly (the seam issue-270's own test uses) and asserts no `gh`
   invocation at all.
4. **The suppressed family was first mapped to `error`.** Rejected on re-reading
   `SETTLED_SUPPRESSED`'s own comment: those outcomes mean *"a real event was refused on
   purpose and the harness re-reads the thread instead"* — the comment is pending, not
   failed, and 😕 on every ordinary comment on every armed-but-unstarted work item would
   make a working daemon look broken. *Fixed:* mapped to `started` (👀), the one state of
   the three that means "seen", with the reasoning recorded in `requirements.md` R1.4 and
   `design.md` § "The table".

## What was checked and found sound

- **No path is acknowledged twice.** The delivered branch reacts only in `_worker`; the
  one `_settle` inside it is exempt. `_apply_control`'s spawn path *returns* after
  `_on_unmatched` rather than falling through to its own settle, and `_on_unmatched`'s
  suppressed settle is gated on `not control_command` — so a start that spawns gets one
  lifecycle, not a lifecycle plus a 🎉.
- **No path is silently reclassified.** `SETTLED_OUTCOMES`, the deduper's recorded
  outcomes, and every `dispatch.dropped` / `control.*` eventlog entry are byte-identical;
  T13's regression suites (`test_control.py`, `test_routing.py`,
  `test_control_integration.py`) pass untouched.
- **The table cannot drift.** It is built from the same `SETTLED_*` constants
  `SETTLED_OUTCOMES` is, and T1 asserts every key is a member of that tuple, that the
  whole suppressed family is covered, that no scope refusal is, and that every value is
  one of the three configured states.
