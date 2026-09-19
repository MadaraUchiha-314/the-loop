---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#389"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: the mention is the address, and three acts each end in the session

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`:
> reply-first-then-fix, one finding per commit where the files allow, stop on zero new
> findings, escalate on a repeated finding. Each round is an adversarial re-read of
> `git diff de88ddc..HEAD -- cli/the_loop` by a fresh agent in this session, against
> `requirements.md` R1–R7 and A1–A12 and `design.md`; the findings and their
> dispositions are the record, the fixes are the commits named.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | a fresh reviewing agent, same harness, reading the whole diff | **new findings (9)** | see the table below; all nine fixed in `d233de8`, `5f8479e`, `6f71041`, each with a red→green test | [PR #390](https://github.com/MadaraUchiha-314/the-loop/pull/390) |
| 2 | a fresh reviewing agent, reading the three fix commits and the touched functions again | **in progress** | the round is running as this record is committed; its outcome and dispositions are appended when it reports | [PR #390](https://github.com/MadaraUchiha-314/the-loop/pull/390) |

## Round 1 — what was found, and what was done

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | The grammar (a leading verb, a control word composed into the keyword) was applied to every reply, addressed or not: a plain DM "Do the second option" became `the-loop do the second option` — dropped `unpublishable-event`, or run as a `do` task. R3.1 scopes the grammar to the first token **after the mention**. | Fixed (`d233de8`): `InboundReply.addressed`; `process_reply` and `_classify` read a verb or compose a keyword only when the message was addressed — an `app_mention`, a shortcut, the modal, or the bot's token in the text. Test: a plain DM starting with `Do`, `record-context`, `help` is delivered as a reply |
| 2 | medium | `strip_mention` collapsed newlines, so a mentioned kickoff lost its title/body split and a multi-line decision its lines (R1.5). | Fixed (`d233de8`): horizontal whitespace only. Test: the kickoff title is the first line |
| 3 | medium | R3.5 unmet: `add-collaborator <@U0456\|dana>` composed a token the roster parser stops at, so the natural typed form was `missing-collaborator`. | Fixed (`d233de8`): for the two collaborator commands a member mention becomes `slack:U0456`. Test in `test_channels_verbs.py` |
| 4 | medium | Every non-keyword reply was typed `gate.feedback` at a human gate (or when the gate was unreadable and the grant existed), and the tier check refused a collaborator's words as an `unauthorized-act` — nothing delivered (R7.2). | Fixed (`5f8479e`): a collaborator cannot answer a gate, so `_classify(collaborator_only=True)` types their reply a `work-item.reply` before the gate is read. Test: collaborator delivered, authorized user still `gate.feedback` |
| 5 | medium | `record-context` / `record-decision` in a standing session's thread reached the standing deliverer, whose adapter takes no frame: a `TypeError` swallowed as `undeliverable`, ⚠️ and a misleading error. | Fixed (`5f8479e`): refused `no-ticket` up front, with the reason in the thread. Test added |
| 6 | medium (security) | `channels records` admitted any comment carrying the marker and a record envelope — the poller uses the marker to *skip*, this verb used it to *trust* — so a ticket commenter could paste an authorized user's "decision" (A5/A6 spirit). | Fixed (`5f8479e`): `GhClient.viewer_login` reads the ledger credential's login and the verb lists only what it posted; when the login cannot be read it warns on stderr and prints the author on every row. Tests: the forged row excluded; the warning path |
| 7 | low (security) | A shortcut on an unbound channel answered "Nothing recorded (unmapped)" to whoever tapped (a stranger learns the bot listens — A1, A8); "Recorded." was said when the ledger refused; the decision modal opened without the `decision.recorded` grant. | Fixed (`6f71041`): `unmapped` is silent, a failed record says "Could not record: …", the grant is checked before the form. Three tests |
| 8 | low | The snapshot carried the `@the-loop record-context` message itself, left inline `<@U…>` as ids (R4.3), and mis-counted a paged thread's remainder. | Fixed (`6f71041`): a typed in-thread trigger is left out (a top-level mention and a shortcut's message are content); inline mentions drawn as `@name` / `@the-loop` / the id; `has_more` says "more" without a count. Test added |
| 9 | low | `post_ephemeral` never passed `thread_ts`, so `help`, a refusal and "nothing new" appeared at channel level. | Fixed (`6f71041`): `_tell` posts in the reply's thread. Test added |

## Checked in round 1 and found sound

- The §1 input table and its place before the kickoff branch, authorization, any
  reaction and any cursor move (A10); the `app_mention` copy in an `all` room dropped
  `duplicate`; a redelivered mention deduped by the shared cursor (A7); the poll reads
  skip mention-gated conversations without moving a cursor.
- The tiers: a stranger dropped in silence before classification; the binding acts
  refused for a collaborator with an ephemeral only; `speaker_for` fails closed on a
  standing ref, an unreadable roster, a missing method; a collaborator's principal is
  named from the roster, never from the message (R7.4).
- The shortcut and the modal (A3): the author is the payload's `user.id`;
  `private_metadata` is validated as a channel id and two timestamps and used only to
  look up state; the work item comes from state and the declarations; the speaker is
  re-checked at submission; `trigger_id` and `view.id` go through one `once` ring; the
  ack precedes the handling.
- A5: `strip_html_comments` runs before `mark_self_authored` and `stamp`, so a pasted
  marker or envelope cannot pre-stamp or be parsed; broadcasts neutralised; keywords
  defanged in the quote; a keyword in the rationale lands inside a marked comment every
  ingress skips.
- The marked records are never gate answers; `DELIVERED` stops a keyword or a gate
  answer being delivered twice; `records.py` matches `mirror_body`'s exact shape.
- The roster and the listen mode fail closed on either bad id, a forged mode, an
  invalid declaration; the CLI resolves a handle before any write.
- The snapshot's `since`/`newest` bookkeeping advances only after `record.ok`, under the
  state lock; button presses and the slash command are untouched apart from the shared
  ring; every new listener path sits inside the existing `except Exception`, and the
  new bot methods never raise.
