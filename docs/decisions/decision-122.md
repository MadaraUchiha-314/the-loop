# Decision 122: an unresolved Slack kickoff is asked about rather than refused — one question, answered by a Block Kit pick, held in a capped and expiring pending record, and only where a press can be received

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-349](https://github.com/MadaraUchiha-314/the-loop/issues/349)
- **Deciders:** MadaraUchiha-314 (the ask, at [PR #347](https://github.com/MadaraUchiha-314/the-loop/pull/347)); the-loop (design)
- **Refines:** [decision-120](decision-120.md) (the prefix, the refusal and the declared
  set this builds on), [decision-116](decision-116.md) D5 (why Socket Mode is required
  for anything interactive), [decision-117](decision-117.md) D4 (a button stands in for
  something typed — narrowed here: a button now supplies an *argument* to something not
  yet done)

## Context

[decision-120](decision-120.md) let a Slack kickoff name its own repository with a
`<repo>:` prefix, and refused an unresolvable one with the declared repositories listed
as prose. The owner's objection, filed as issue-349:

> When the kick off of a work item happen, /the-loop should ask a series of questions on
> the thread to help choose the repo etc, user wouldn't know to specify the correct
> format etc. the-loop should present proper options from the list of repos in
> `cli-config.yaml`.

The refusal is safe and correct. It is also, for a first-time member on a phone, the same
demand as before in a friendlier voice: read a list, learn a grammar, retype the whole
message. The prefix is right for someone who knows what they want and wrong for a first
time.

Five questions had to be settled, and the ticket named two of them as blocking the spec
chain: **what happens in `poll` mode**, where a press cannot be received at all; and what
**"a series"** means, since each extra question multiplies the state. Three more followed
from the shape: **which outcomes become a question**, **where the held message lives**,
and **who may answer**.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **In `poll` mode the typed prefix stays the only route**, the refusal is unchanged, and `channels status` says so. No `reply 1, 2 or 3` text fallback. | The answer would have nowhere to arrive: `fetch_replies` iterates *bound* threads, and a pending kickoff has no work item and so no binding — a numbered reply under it is dropped as `unmapped` today. Making it readable means binding a thread to nothing, or a second pending-read path no other feature has. It would also be the only interactive affordance in the channel with its own availability rule: `interactive` and `command_buttons` are both `read.mode: socket` **and** the grant. A third rule is a third thing to keep true. |
| D2 | **"A series" is one question: which repository.** Not repository → labels → phase selection. | Labels are already one operator-configured list, and decision-120 parked per-repository labels as a separate ask. Phase selection **is already a gate**, on the ticket, answered by an authorized user — asking it in Slack before the issue exists would be a second, weaker copy of a gate the loop owns. And each extra question turns one pending record into a wizard: a step pointer, partial answers, re-entrancy per step. The record is shaped so a second question is a later work item; nothing is built for one. |
| D3 | **If a pick could answer it, ask; otherwise refuse.** `no-target`, `ambiguous-repo` and both arms of `unknown-repo` become the question; `empty-message` stays a refusal. `resolved` and `fallback` still go straight through. | One rule instead of four case-by-case judgements, and it is checkable: the partition is a property on `KickoffTarget` (`ok` / `askable` / neither), not a list of outcome names in the caller. A member who typed a prefix that resolves **has answered the question** and must not be asked it again — that is the ticket's own ask #2. And no pick puts words in a message that has none. |
| D4 | **The held message lives in `ChannelState` (`slack.json`) as a fourth map**, keyed by the message `ts`, expiring after **24 hours**, capped at **50** records, and **claimed under the state lock before** the create. | It is the file that already holds this deployment's thread bindings and cursors: same lifetime, same locality, same `flock`, same cap rule, same `GENERATED_PATHS` registration, same `docs/cli/state.md` page. A second file would be a second thing to register, document, prune and lock. 24 hours is phone-shaped — long enough to answer in the morning, short enough that the answer still refers to a message right above it. Claim-then-create is what makes "answers twice" open one issue; a failed create restores the record, which is exactly the existing rule that a failed press keeps its buttons. |
| D5 | **Only the member who posted the message may answer its question**, and an unauthorized presser is refused *above* the record read. | Letting any authorized member direct someone else's message makes "who is this issue attributed to" a new question for no gain — the asker is one tap away. Refusing above the record read means an unlisted member learns nothing, not even that a question exists; the question is a bigger disclosure than a refusal, so it sits below the allow-list exactly where the refusal already does (issue-341 R2.6). |
| D6 | **The allow-list is where "a refusal leaves no mark" stops.** A press *above* it has its outcome written onto the question — opened, failed, or refused — in fixed words naming no repository, no other member and no config value; a press *below* it edits nothing, reacts to nothing and posts nothing. | decision-111 D1 was written for a channel where a refusal could reach someone who should not even know the-loop is listening. decision-120 D2 already narrowed it once — an *authorized* refusal now answers — and the same narrowing is what this needs: a member who taps an expired question and sees absolutely nothing happen is exactly the failure this work item exists to end. The report is an in-place edit of a message that presser can already read, so it discloses nothing new; and only a press that opened something takes the picker away, so a refused one stays answerable. |
| D7 | **The channel's own permission is re-read when the press arrives**, not trusted from when the question went out: a revoked `work-item.create`, or a channel no longer in Socket Mode, refuses the answer. | This is the only place in the change where held state could outlive the authority that created it, and "a pending record from last week" is precisely the shape that quietly carries a revoked permission forward. Re-reading costs one property access and makes the rule statable without an exception: *nothing opens a work item that the channel could not open right now.* |

## Consequences

**Good.** A member who has never seen the-loop before files into the right repository with
one tap, and is told in the same message that a `<repo>:` prefix skips the question next
time — so the ask teaches the shortcut rather than replacing it. The grant stops having a
configuration (`work-item.create` with no `kickoff.repo`) whose only behaviour was a
refusal. No config key, no grant, no scope and no schema change: a 14.0.0 config upgrades
untouched, and a `slack.json` without the new map loads as an empty one.

**Bad / risk.** the-loop now holds a member's unsent message text at rest, which it never
did — bounded by a 24-hour expiry, a 50-record cap and D7's re-authorization on use, in a
file that is already local-only and never portable, but it is new data and it is named as
residual risk. The
channel gains a message it did not send before (the question), for authorized members
only. `poll`-mode operators get none of this and are told so by `channels status` rather
than by a member; that asymmetry is D1's accepted cost, and closing it is a separate work
item, not a config key.

**Neutral.** `KickoffTarget.text` now means one thing on every outcome — the message the
issue is composed from, with any *read* prefix stripped. The visible consequence is that
an `ambiguous-repo` or qualified `unknown-repo` message consisting of **nothing but the
prefix** now resolves to `empty-message`: one refusal instead of another, with better
words. Slack's own ceiling of 100 options in a static select bounds the question; past it
the first hundred are offered in declaration order and the prefix is named for the rest.
