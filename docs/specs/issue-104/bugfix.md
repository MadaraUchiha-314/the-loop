---
type: bugfix
phase: requirements-definition
workItem: issue-104
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the-loop's own machine-posted comments omit the loop-prevention marker

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

the-loop posts under the **operator's own credentials** (decision-023: no bot
token of its own), so by *author* alone its comments are indistinguishable from
something the operator typed. The remediation shipped in issue-64 /
[decision-031](../../decisions/decision-031.md) is a marker embedded in the body
of every comment the-loop posts — `<!-- the-loop:agent-comment -->`, matched by
`the_loop.authz.is_self_authored` — which both trigger paths drop before
dispatch.

That rule is documented for the **harness** (the spawned Claude/Cursor session,
`skills/the-loop/reference/collaboration.md` § loop prevention) but was never
applied to the comments the **CLI daemon itself** posts. There is exactly one
such comment today — the interactive-session announcement
(`the_loop.announce.announcement_body`, issue-86):

> 🖥️ **the-loop** started an interactive session for `github:owner/repo#104`.

It carries no marker. The poller therefore sees it on the next cycle as a new,
authorized, human-looking comment and forwards it into the very tmux session it
was announcing. Reported as
[issue #104](https://github.com/MadaraUchiha-314/the-loop/issues/104):

> when the-loop posts the message "the-loop started an interactive session for
> ...." it doesn't add the label and the poller ends up sending that to the tmux
> session

## Steps to reproduce

1. Run `the-loop poll start` with `routing.runner: tmux` and the operator's own
   login in `routing.authorizedUsers`.
2. Label a work item so the poller spawns a session for it.
3. The dispatcher spawns the tmux session and `SessionAnnouncer.announce` posts
   the announcement comment on the item.
4. Wait one poll cycle.

**Observed:** the announcement text is pasted into the freshly spawned tmux
session as if the operator had asked the agent to act on it. The harness reads
"the-loop started an interactive session for …" as a new instruction.
**Expected:** the-loop's own announcement is recognised as self-authored and
dropped before dispatch, exactly like a harness-posted reply.

## Expected vs actual

- **Expected:** WHEN the-loop posts **any** comment — from the harness *or* from
  the CLI daemon — THEN the body SHALL carry the loop-prevention marker (plus a
  visible attribution line), so neither trigger path can feed it back into a
  session.
- **Actual:** only harness-authored comments carry it. The daemon's own
  announcement body is assembled as plain markdown with no marker, so
  `is_self_authored()` returns `False` for it and the poller's forward path
  treats it as operator input.

## Root cause (confirmed)

`cli/the_loop/announce.py:63-93` (`announcement_body`) builds the comment body
from the session's registry fields and returns it without the marker.
`SessionAnnouncer._argv` posts that body verbatim
(`repos/{owner}/{repo}/issues/{number}/comments`).

On the poll path (`poller/poller.py:444-494`) the announcement lands *after* the
cycle's listing has been read, so it is not in that cycle's `live_ids` baseline.
On the next cycle it is an unresolved comment; the two guards it passes through
are:

- `is_authorized(comment.author, …)` — **true**, because the announcement was
  posted with the operator's own `gh` credentials and the operator is
  necessarily in `routing.authorizedUsers`;
- `is_self_authored(comment.body)` — **false**, because the marker is missing.

so it becomes a *candidate* and `_process_comment` pastes it into the session.
The webhook path has the same hole (`webhook/router.py:309` runs the same
`is_self_authored` check on the event body); it is not usually observed there
only because a `gh api` POST fires an `issue_comment` webhook that must also
survive the authorized-actor check — which it does, for the same reason.

The defect is **structural, not local**: nothing ties "the daemon posts a
comment" to "the marker is appended". `announce.py` is simply the first (and so
far only) CLI comment-posting site, so it is the first to expose it. Marking it
by hand fixes today's symptom and leaves the next posting site free to repeat
the bug.

## Acceptance criteria (EARS)

### Mark what the daemon posts

1. WHEN the CLI daemon posts a comment on a work item THEN the posted body SHALL
   end with the exact marker `<!-- the-loop:agent-comment -->` and a visible
   attribution line, so a human reading the thread sees who wrote it and
   `the_loop.authz.is_self_authored` recognises it. (AC1)
2. WHEN the interactive-session announcement is posted THEN its body SHALL
   satisfy AC1, and its human-readable content SHALL be otherwise unchanged (the
   tmux target, harness, attach commands and retention note). (AC2)
3. WHEN a body already carries the marker THEN marking it again SHALL be a no-op
   (idempotent), so a future caller that marks defensively cannot emit the marker
   twice. (AC3)

### Never leak the marker onto foreign content

1. WHEN the marking helper is applied THEN it SHALL only ever append to a body
   the-loop itself authored; it SHALL NOT be applied to any text derived from an
   event payload or another author's comment. (AC4)

### Close the loop for both trigger paths

1. WHEN the poller lists a work item whose thread contains the-loop's own
   announcement THEN it SHALL resolve that comment without forwarding it to the
   session. (AC5)
2. WHEN the webhook router receives an `issue_comment` event whose body is
   the-loop's own announcement THEN it SHALL drop the event before dispatch. (AC6)

### Regression coverage & documentation

1. The fix SHALL include regression tests that fail before it and pass after,
   covering (a) the announcement body being self-authored and (b) an
   announcement comment reaching the poller without being forwarded. (AC7)
2. The rule SHALL be documented as covering **both** producers — the harness and
   the CLI daemon — in `skills/the-loop/reference/collaboration.md` and the
   affected capability docs, so the next CLI comment-posting site inherits it by
   documentation as well as by API shape. (AC8)

## Out of scope

- **Retro-marking comments already posted.** Announcements posted before this
  fix stay unmarked; the operator resolves them by letting the session run (the
  poller baselines a comment once it has been attempted) or closing the stray
  session. Rewriting historical comment bodies is not attempted.
- **A queryable metadata channel.** GitHub still offers none — the body text
  remains the only carrier (decision-031); this change does not revisit that.
- **Reactions.** `the_loop.reactions` posts emoji, not comment bodies; there is
  nothing to mark and it is unaffected.
- **Non-GitHub ticketing.** The helper is text-level and provider-agnostic, but
  no other provider posts comments yet.
- **Widening the authorized-actor guard.** Author-based filtering cannot
  distinguish the-loop from the operator by design (decision-023); the marker is
  the mechanism and stays so.

## Security considerations

**No new attack surface; one narrowing of what re-enters the loop.**

- **Untrusted actors / trust boundary.** The boundary at issue is
  *self-reply ingestion*: content the-loop wrote must not re-enter as
  instructions. This change strengthens exactly that boundary — one more body
  the-loop authors is now recognised as its own — and touches no other guard.
  The authorized-actor check (`routing.authorizedUsers`) is untouched and still
  runs; ordering of the two guards is unchanged.
- **The marker is not an authorization mechanism.** It identifies authorship for
  loop prevention only (decision-031). A hostile commenter can already type the
  marker into their own comment; the consequence is that *their* comment is
  ignored — a self-denial, not an escalation. This change does not alter that
  property, and nothing new is granted to a marker-carrying body.
- **Never applied to foreign text (AC4).** The helper is applied only to bodies
  the-loop composes from its own registry fields. It is never applied to payload
  data, so it cannot be used to launder someone else's text into a
  "self-authored" body.
- **No new ingress, credential, subprocess or network call.** The posting path
  (`gh api --method POST`, argv list, no shell) is unchanged; only the `body`
  string differs. The announcement remains payload-free — built solely from
  registry fields, with no filesystem path, harness session id or hostname.
- **Fail-closed / bounded.** Marking is pure string concatenation on a
  bounded, self-composed body: no parsing of untrusted input, no loops, no I/O,
  and it cannot fail in a way that affects the dispatch (announcement remains
  best-effort — a failure is still a logged no-op).
- **Abuse case covered by a test:** an announcement body fed back through the
  poller must be dropped, not forwarded (AC5) — the negative test that proves the
  boundary holds.

## Open questions

None. The reporter's diagnosis is exact and the mechanism (decision-031's
marker) already exists; the only design choice is *where* it is applied, settled
in `design.md` in favour of a shared helper next to the marker itself.
