---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#349"
phase: needs-review
status: in-progress
---

# Execution Log: a Slack kickoff asks which repository

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 3 (`human-approves-pr`): new persisted state, a new inbound payload branch and a new interaction shape, but no schema key and no new grant — below the tier-4 floor, so no named security sign-off. Brainstorming skipped: the ticket carries the ask, the code, the two design decisions and the reasoning. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded on the ticket and every remaining phase is walked ([comment](https://github.com/MadaraUchiha-314/the-loop/issues/349#issuecomment-5636183291)) |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — five requirements, ten abuse cases. The ticket's two blocking design decisions were settled **before** this artifact, on the ticket |
| design | 2026-09-11 | | [`design.md`](design.md) — the fork in `process_kickoff`, the pending map, the picker's two shapes, the five gates; [`decision-122`](../../decisions/decision-122.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — seventeen rows, nine applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — thirteen tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-349-lxt6fp` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — every applicable row ran; [`evidence/security-review.md`](evidence/security-review.md) — ten abuse cases, ten closed |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 3: PR approval) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#351](https://github.com/MadaraUchiha-314/the-loop/pull/351) | tasks 1–13: the whole work item | open |

## Progress entries

### 2026-09-11 — the two design decisions, settled before the spec chain

- **Phase:** phase-selection → requirements-definition
- **Did:** the ticket named two decisions that "should be settled before the spec chain,
  not during it". Both were, with the reasoning posted to the ticket so it could be
  argued with before any code was read.
  - **D1, `poll` mode:** the typed prefix stays the only route; no `reply 1, 2 or 3`
    fallback. The deciding argument is not taste — it is that the answer would have
    nowhere to arrive: `fetch_replies` iterates *bound* threads, a pending kickoff has no
    work item and therefore no binding, and a numbered reply under it is dropped as
    `unmapped` today. Making it readable means binding a thread to nothing or adding a
    second pending-read path no other feature has.
  - **D2, "a series":** one question, which repository. Labels are already one
    operator-configured list (decision-120 parked per-repository labels); phase selection
    **is already a gate**, on the ticket, answered by an authorized user — asking it in
    Slack before the issue exists would be a second, weaker copy of a gate the loop owns.
  - A third followed from applying the ticket's ask literally: *ask instead of refuse* is
    four case-by-case judgements, and it is cleaner as one rule — **if a pick could answer
    it, ask; otherwise refuse** — which is checkable as a property (`ok` / `askable` /
    neither) rather than a list of outcome names in the caller.
- **Next:** the spec chain.
- **Blockers:** none.

### 2026-09-11 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–13, red first (neither new suite collected against `9dcb4a1`).
  - `channels/kickoff.py`: `KickoffTarget.askable`, `question_text()` beside
    `refusal_text()`, and `text` given **one meaning on every outcome** — the message the
    issue is composed from, with any *read* prefix stripped — because a pick composes its
    issue from that field.
  - `channels/state.py`: a fourth map, `pending`, with `PENDING_TTL_SECONDS` (24h),
    `PENDING_CAP` (50) and five methods whose whole policy is one line each. Expiry is
    read as absence and swept on write, so no read path writes; `claim` is a pop, which
    is what makes "answers twice" open one issue.
  - `channels/slack.py`: `render_kickoff_question` (buttons at five or fewer, a
    `static_select` above, capped at Slack's 100), `action_value` reading
    `selected_option.value`, `is_kickoff_repo_action` covering the numbered button ids
    Slack's uniqueness rule forces, `KICKOFF_REFUSALS` and `kickoff_picker`.
  - `channels/inbound.py`: the fork; `_open_work_item` lifted verbatim from the tail of
    `process_kickoff` so both paths publish the same event through the same ledger *by
    construction*; `process_kickoff_answer` with its five gates; the routing above
    `process_reply`, which touches nothing below it.
  - Docs: `channels status`, `docs/cli/state.md`, `docs/capabilities/channels.md` (two
    new clauses + a history row), `docs/config/cli/channels-options.md`,
    `docs/guide/slack.md`, the event catalog, `decision-122`, `decisions.md`.
- **Checkpoint/tests:** `make check` — **3543 passed, 1 skipped**; ruff, markdownlint
  (1073 files), format, pyright and config validation clean. See
  [`evidence/verification.md`](evidence/verification.md).
- **Self-review:** three passes over the diff.
  - **Pass one** found three things. (a) `_question_options` rebuilt the declared set that
    `resolve_target` had already computed and returned as `target.candidates` — deleted,
    and reusing the field the refusal renders is now what stops the question and the
    refusal ever disagreeing about what is on offer. (b) An accepted press got no
    `received` acknowledgment, breaking issue-325's contract for the one inbound shape
    that is new. (c) **The real one:** an authorized member who tapped an expired question
    got *nothing at all* — no message, no edit, no reaction. That is the exact failure
    this work item exists to end, reintroduced at the other end of the flow. Fixed by
    narrowing decision-111 D1 where decision-120 D2 already narrowed it: a press **above
    the allow-list** has its outcome written onto the question in fixed words; a press
    below it still leaves no mark whatsoever. Recorded as decision-122 D6.
  - **Pass two** verified the design's claims against the code and found one gap that
    mattered: `process_kickoff_answer` never re-read the channel's own permission. An
    operator who revoked `work-item.create` while a question was outstanding would still
    have had a press open an issue — held state outliving the authority that created it,
    which is the one shape this change newly makes possible. Added as the gate above all
    the others, abuse case A10, decision-122 D7, two tests. The other four claims held:
    the value never reaches the ledger (the matched `DeclaredRepo.declared` does), the
    fork sits below the allow-list, the claim is inside the lock and the create outside
    it, and a press on any other `action_id` still takes the pre-issue-349 path.
  - **Pass three** read the docs against the code and corrected the drift the first two
    passes had created: the design still showed the deleted `_question_options` and "four
    gates", the requirements had no criterion for either new behaviour, the abuse-case
    list was A1–A9 in four files, and the plan's per-row `-k` filters over-matched badly
    enough to be misleading (a filter on `option`/`press` selected most of the file), so
    the evidence now names the file and what each of its sections pins.
- **Open judgement recorded:** the 24-hour TTL and the 50-record cap are the two numbers a
  reviewer might reasonably want different. Both are one-constant changes. The TTL is the
  more interesting of the two: it is what bounds residual risk 1 (the-loop now holds a
  member's *unsent* message text at rest, which it never did), and the case for a day
  rather than an hour is that the question has to survive being seen the next morning.
- **Next:** the owner's review.
- **Blockers:** none.

## Design critic review

> Not selected for this work item (`reviews.critics: []` — no external critic is
> configured, so the three self-review passes above are the review).

## Capability docs

- [`docs/capabilities/channels.md`](../../capabilities/channels.md) — two new *Current
  behaviour* clauses: the question itself (when it is asked, what it offers, what is
  rendered, when it is refused instead) and the pending record (the TTL, the cap, the
  five gates, what a press writes back and what an unauthorized one does not), plus a
  history row.

## Documentation

- **Changed:** [`docs/guide/slack.md`](../../guide/slack.md) — a new
  *"and if the message names none it knows, it asks"* block under **Which repository?**,
  with the rendered question shown; the buttons table gains a fifth row and the prose
  says why that one is not a stand-in for a typed reply; the *what you can do* table
  names the question.
  [`docs/config/cli/channels-options.md`](../../config/cli/channels-options.md) — the
  `kickoff.repo` outcome table's *refused* column becomes *asked* for three of six rows,
  with the two conditions (`read.mode: socket`, something declared) and the pending
  record's bounds stated; the `work-item.create` grant row names the picker.
  [`docs/cli/state.md`](../../cli/state.md) — "three maps" → four, with what `pending`
  holds, what bounds it and what a pre-issue-349 file does.
  [`docs/decisions/decisions.md`](../../decisions/decisions.md) — decision-122.
- **Not changed, with the reason:** `README.md` — it describes the loop and the plugin,
  and names no channel behaviour this work item touches. `skills/the-loop/` and its
  `reference/` — they describe the *process* (phases, gates, reviews), not the daemon's
  Slack surface; `reference/collaboration.md` § Where questions go is about where a
  **session** asks a human, which is unchanged. No schema page changed because no schema
  key was added — asserted by the parity suite rather than assumed.
