# Decision 031: Self-reply marker guard — an embedded body marker, not GitHub metadata

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #64)
- **Work item:** issue-64
- **Revisits:** [decision-023](decision-023.md) (authorized-actor guard), which this
  complements — a different failure mode, the same `the_loop/authz.py` module.

## Context

Issue #64: the spawned harness (Claude Code / Cursor) posts its own replies — issue/PR
comments, PR review comments and replies, review submissions — through the **operator's
own** credentials (`gh` CLI or an MCP GitHub tool authenticated as the operator; decision-
023 deliberately rejected a separate bot token). Both trigger paths then react to *new*
activity on the repo: the webhook receiver on `issue_comment`/`pull_request_review*`
events, the poller by diffing each item's comment list against what it last saw.

That creates a loop hazard decision-023 didn't address: a reply the-loop itself just
posted is, by **author**, indistinguishable from one the operator typed. The
authorized-actor allowlist (`routing.authorizedUsers`) checks *who* posted, and the
operator is, by definition, on that list — so it happily lets the-loop's own comment
re-enter the loop as new input, resuming the very session that wrote it. That session may
reply again (e.g. another "will-fix, pushed a commit" acknowledgment), which the next
poll/webhook cycle again reads as new activity — an unbounded, self-sustaining loop of
resumes, each burning harness/API budget and posting more noise to the thread.

The issue asked two concrete research questions before any fix: does GitHub allow
attaching metadata to a comment, distinct from the body text, that could carry an
"authored-by-the-loop" flag? And if not, is a footer in the body the only option?

## Research: does GitHub offer comment metadata?

No. Neither GitHub's REST nor GraphQL API exposes a custom/arbitrary metadata field on an
issue comment, PR review comment, or PR review — the object carries only `id`, `body`,
`user`/`author`, timestamps and reaction counts. The one structural signal GitHub does
expose is `user.type == "Bot"`, but that requires posting through a **GitHub App
installation token or a dedicated bot account**, which is exactly the separate-identity
model decision-023 rejected (each operator runs their own instance under their own login,
with no extra credential to provision or rotate). Some GitHub-native automations (Actions
annotations, check runs) do carry structured metadata, but plain issue/PR/review comments
— the surface the-loop posts to — do not.

**Conclusion: the comment body is the only channel available.** A footer/marker embedded
in the body text is not a workaround; it is the mechanism.

## Decision

Add a **self-reply marker guard**, alongside the existing authorized-actor guard in
`the_loop/authz.py`:

- **`SELF_COMMENT_MARKER`** — a fixed string, `<!-- the-loop:agent-comment -->` — an
  HTML comment so it renders invisibly on every GitHub surface (issue/PR page, email
  digest, mobile) while remaining present, verbatim, in the raw `body` the API returns.
- **`is_self_authored(body)`** — `True` iff the marker substring is present. Exact-match
  on a fixed string, not a regex or fuzzy check, so it cannot misfire on human text and
  never needs to change once shipped (older comments must stay recognizable).
- **Both trigger paths check it before the authorized-actor check**, and drop the event
  unconditionally when it matches — regardless of who technically posted it:
  - **Webhook router** (`Router.route`): a new `event_body(event, payload)` extracts the
    comment/review body for `issue_comment` / `pull_request_review_comment` /
    `pull_request_review`; a match is dropped (`routing.dropped reason=self-authored`)
    before `extract_work_items`'s authorization gate even runs.
  - **Poller** (`Poller._process_item`): a comment carrying the marker is excluded from
    `new_comments` — the same set that gates both comment-forwarding and spawn retries —
    alongside the existing `is_authorized` filter. It is still baselined into
    `PollState` like any other dropped comment, so it is never re-evaluated on a later
    cycle.
- **The harness is responsible for writing the marker.** The CLI can only *detect* it;
  the actual posting happens through whatever tool the running harness uses (`gh`, an
  MCP GitHub tool, a Jira client). `reference/collaboration.md` now carries a hard rule:
  every comment/review/reply the-loop posts ends with the marker **plus** a visible
  human-readable attribution line (reusing the existing `[<harness>/<model>]` prefix
  from `reference/reviewing.md` where one already applies) — invisible-to-humans for the
  machine check, visible for the paper-trail/education ethos the rest of the skill
  already commits to. The rule is written provider-agnostically (GitHub today; Jira or
  any future provider inherits it, since `Comment`/`is_self_authored` are provider-
  neutral).

## Consequences

- New `SELF_COMMENT_MARKER` / `is_self_authored` in `the_loop/authz.py`; `event_body` in
  `webhook/router.py`; both `Router.route` and `Poller._process_item` gain the check.
  No config surface added — the marker is a fixed implementation detail, not a tunable
  (nothing plausible is gained by letting an operator rename it, and it would risk
  breaking detection of already-posted comments across a config change).
- Behaviour change: a the-loop-authored comment/review that is *not* marked (e.g. posted
  by a future code path that forgets the rule) is **not** protected — it will still
  re-enter the loop. The guard is a code-side backstop for a skill-side (prompt-level)
  discipline; it cannot verify the harness actually wrote the marker, only recognize it
  when present. Making this failure mode visible (rather than silently "mostly working")
  is itself a reason `reference/collaboration.md` states the rule as a hard **MUST**, not
  a suggestion.
- The marker check runs before, and independent of, the authorized-actor guard — it is
  not an authorization mechanism (a hostile third party could in principle discover and
  paste the marker into their own comment; that only makes their comment invisible to
  the-loop, not privileged). This is fine: the marker's job is loop-prevention, not
  security, and the authorized-actor guard (decision-023) remains the sole prompt-
  injection control.

## Alternatives considered

- **Post replies through a dedicated bot account/GitHub App token, use `user.type ==
  "Bot"`** — rejected: reintroduces the separate-credential model decision-023 explicitly
  moved away from (an extra token to provision, store and rotate per operator, for a
  single-operator tool that already inherits `gh`'s auth). Revisit if the operating model
  ever changes to a shared/team-run instance where per-user attribution stops being "the
  operator" by definition.
- **Diff-based heuristics (e.g. "a comment posted within N seconds of a dispatch is
  probably ours")** — rejected: timing is not identity; a genuinely fast human reply
  would be dropped, and a slow automated one would leak through. No such heuristic is
  reliable enough to fail closed on.
- **Exclude the operator's own login from `authorizedUsers` while the-loop runs, re-add
  after** — rejected: that also blocks genuine human replies from the operator during the
  run, defeating the entire point of allowing mid-run human input.
- **A visible-only footer, no HTML comment** — considered and folded in as a
  *complement*, not a replacement: a plain-text footer is just as machine-detectable as
  an HTML comment (both live in the raw body), but a visible marker permanently clutters
  every comment for human readers. The HTML comment carries the exact-match machine
  signal; the required visible attribution line (already this repo's convention for
  review findings) carries the human-readable one — no need to trade one off for the
  other.
