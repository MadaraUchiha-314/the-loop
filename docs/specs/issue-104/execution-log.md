---
type: execution-log
workItem: "issue-104"
phase: needs-review
status: in-progress
---

# Execution Log: mark every body the-loop posts (issue-104)

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-104/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-26 |  | Issue #104: the daemon's session-announcement comment omits the loop-prevention marker, so the poller pastes it into the session it announces. |
| design | 2026-07-26 |  | Producer-side helper (`mark_self_authored`) beside the consumer-side `is_self_authored` in `authz.py`; `announcement_body` wraps its return value. No routing change — both paths already drop marked bodies. |
| tasks-breakdown | 2026-07-26 |  | 9-task DAG |
| implementation | 2026-07-26 |  | Implemented on `claude/github-issue-104-iavf4q` |
| needs-review | 2026-07-26 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-26 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Audited every place the-loop writes to GitHub. The CLI has exactly
  one comment-posting site — `announce.py` (`gh api --method POST
  …/issues/<n>/comments`); `reactions.py` posts emoji only, and everything else
  is read-only. Traced the poll path (`poller.py:444-494`): the announcement
  lands after the cycle's listing is read, so the next cycle sees it as a new
  comment that passes `is_authorized` (the operator's own credentials posted it)
  and fails `is_self_authored` (no marker) — i.e. a *candidate*, forwarded by
  `_process_comment` into the session it announces. The webhook path
  (`router.py:309`) has the same hole. Framed the root cause as **structural**:
  the marker rule was documented for the harness only, with nothing tying
  "the daemon posts a comment" to "the marker is appended".
- **Next:** implement T1–T9.
- **Blockers:** none. Human approval of the spec + code happens at the PR
  (tier-3, `human-approves-pr`).

### 2026-07-26 — implemented (T1–T8)

- **Phase:** implementation → needs-review
- **Did:**
  - `authz.py`: `SELF_COMMENT_ATTRIBUTION` and `mark_self_authored(body)` —
    idempotent (guarded by the same `is_self_authored` the consumers use),
    pure `str -> str`, placed immediately after its consumer so writer and
    reader share a module and a constant. Docstring carries the
    "only on text the-loop composed" rule.
  - `announce.py`: `announcement_body` returns `mark_self_authored(...)`; module
    docstring records why. No change to `SessionAnnouncer` — it posts whatever
    the body function returns.
  - Tests: 2 `authz` unit cases (stamping + idempotence), 1 announcement-body
    case (marked, content intact), and one regression per ingress path —
    `test_poller_integration.py` (Gherkin docstring + `Requirement:` link) and
    `test_routing.py`, both built from the **real** `announcement_body`.
- **Evidence:** both path-level regressions **fail before** the change (run
  against the pre-fix `announcement_body`: the router dispatched the
  announcement and the poller resumed the session with it — `2 failed`) and pass
  after. Full gate green from the repo root (`make check`): `ruff check` +
  `markdownlint` (237 files), `ruff format --check` (55 files), `pyright`
  (0 errors), `validate_config` (6 VALID), `pytest` **468 passed**.
- **Docs:** `skills/the-loop/reference/collaboration.md` (the rule covers both
  producers; never mark foreign text), `docs/capabilities/webhook-triggers.md`
  and `docs/capabilities/interactive-sessions.md` (current behaviour + history
  rows). No new decision record — this implements decision-031, it does not
  revise it.
- **Next:** PR + reviewer briefing; await human approval (tier 3).
- **Blockers:** none.

## Reviews

| Round | Type | Findings | Resolution |
|-------|------|----------|------------|
| 1 | self | Is `announce.py` really the only CLI comment-posting site? Re-grepped for `/comments` POSTs and `gh issue/pr comment`: yes — `reactions.py` writes reactions (no body), everything else reads. The helper is what covers the *next* one. | confirmed, no change |
| 2 | self | Marking in `_argv` instead of `announcement_body` would leave the tested pure function unmarked and put the stamp on a code path that could later be handed payload text. Kept it in the body builder, whose input is registry-only. | accepted as designed |
| 3 | self | Idempotence must be measured against what the *consumers* match, not a substring of our own formatting — so the guard is `is_self_authored`, and the test asserts byte-equality after a second application plus exactly one marker occurrence. | resolved in the implementation |

## Security review

Per `security.review` (tier 3 → no named human sign-off required;
`humanSignOffMinTier: 4`). The change strengthens the **self-reply ingestion**
boundary and touches no other: one more body the-loop authors is now recognised
as its own, so strictly less re-enters a session. The authorized-actor guard
(`routing.authorizedUsers`) is unchanged and still runs in the same order on both
paths. The marker remains explicitly **non-authorizing** (decision-031) — anyone
may type it, and the only effect is that the-loop ignores their comment, a
self-denial rather than an escalation. `mark_self_authored` is pure, I/O-free and
config-free, and its sole call site composes its body from registry fields
already validated (`_NAME_RE` on owner/repo, the regex-sanitised `loop-<slug>`
target), so foreign text cannot be laundered into a "self-authored" body; that
rule is stated in the docstring and in `reference/collaboration.md`. No new
ingress, credential, subprocess, network call or file — the `gh` invocation is
byte-for-byte the existing one with a different `body` value, run as an argv list
(no shell). Worst-case failure (the marker not appended) is exactly today's
behaviour, not a new exposure. Abuse case covered by a test: the-loop's own
announcement fed back through the poller must be resolved, never delivered
(`test_the_daemons_own_announcement_is_not_forwarded`).
