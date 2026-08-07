---
type: execution-log
workItem: issue-172
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: PR linked to an issue has no session-registry entry

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-172/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-07 | pending (PR) | filed as a bugfix (`bugfix.md`) — a repair, not new vocabulary |
| design | 2026-08-07 | pending (PR) | option C (a separate link record); A and B rejected — decision-064 |
| test-planning | 2026-08-07 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-07 | pending (PR) | 8 tasks: T1 → T2/T4/T5 → T3 → T6/T7 → T8 |
| implementation | 2026-08-07 | — | T1–T7 |
| verification | 2026-08-07 | — | T8; every activity ran |
| needs-review | 2026-08-07 | pending | 5 self-review rounds (round 1 found two poll-path regressions); critic rounds unavailable (none configured) |
| complete | — | — | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#173](https://github.com/MadaraUchiha-314/the-loop/pull/173) | the whole work item — T1–T8 | open |

## Progress entries

### 2026-08-07 — spec chain written and locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** wrote `bugfix.md`, `design.md`, `testing-plan.md`, `tasks.md`. Took the ticket's
  open choice: a **separate link record** under a `.link.json` suffix, rejecting both
  `linkedRefs` on the issue's session record (a reverse scan on the hot path, and a
  read-modify-write two ingresses race on) and an alias file under the PR's own slug (it
  collides with the namespace a PR's *own* session needs).
- **Checkpoint/tests:** none — no code yet.
- **Next:** T1, test-first.

### 2026-08-07 — implementation

- **Phase:** implementation
- **Did:** T1–T7. The registry gained `SessionLink`, the five link verbs and `session_for()`;
  the router gained `pr_work_item`; the dispatcher records the binding at both decision
  points; `sessions reset` removes bindings in both directions and reports a `link` piece;
  the new path is classified in `GENERATED_PATHS` and documented in `docs/cli/state.md`;
  decision-064 and the capability-doc update written.
- **Checkpoint/tests:** `pytest -q` → 1404 passed, 1 skipped (baseline: 1379/1). `ruff`,
  `pyright` clean.
- **Next:** T8 — execute the testing plan, commit evidence.

### 2026-08-07 — verification

- **Phase:** verification
- **Did:** T8. Ran every activity, committed evidence under `evidence/`. Confirmed all six
  regression tests **fail** against a registry whose `session_for` is the bare
  `find_by_work_item` — the second PR event is dropped, a successful delivery reports
  `unhandled`, and the poller arms a spawn against the PR — so the tests test something.
  Drove the ticket's own reproduction and captured the registry directory before and after.
- **Checkpoint/tests:** `testing-plan.md` § Verification results.
- **Next:** self-review, then the PR briefing.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (agent) | **new findings — two poll-path regressions the first draft introduced.** Swept every remaining `find_by_work_item` call site instead of only the ones the design named. (a) `Dispatcher.delivery_status` asks the registry about the *routed* refs, but a delivery through a binding records its id on the **bound** session — so a successful delivery would have reported `unhandled` and the poller would re-forward the same comment until `maxRetries` was spent. (b) `Poller._process_item`'s `has_session` had the same shape and a worse consequence: a PR whose linkage is gone would be treated as **first sight**, baselining its whole existing thread as read and arming a spawn against the PR while the issue's session ran. Fixed by moving the resolution onto the registry as `session_for()` — the question both ingresses ask — and pointing all four call sites at it. Two regression tests added; both fail against the pre-fix behaviour. | this PR |
| 2 | self | the-loop (agent) | **new findings, both about consistency with neighbouring code.** (a) `unlink()` emits `session.unlinked` while `forget()` deliberately emits nothing, which looked like an oversight; kept and justified instead — a reset also removes bindings filed under **other** work items' names, which the single `session.reset` event does not mention. Written into `unlink`'s docstring. (b) `design.md` claimed the record involves "no read-modify-write at all", which is not true: `link()` reads the existing record to preserve `createdAt` and to decide idempotence. Corrected to the property that actually holds — the only writer of a PR's file is a binding for that PR, and `os.replace` means a same-PR race can only write the same record twice. | this PR |
| 3 | self | the-loop (agent) | **new finding, scoped not fixed** — `sessions pause\|resume\|stop\|attach\|reset` still resolve directly, not through bindings. Deliberate: those name a work item explicitly, and acting on a different one ("I asked to stop #16 and you stopped #15") is worse than making the operator name what they meant. Promoted from an unstated assumption to R2.10 and a row in `design.md`, so the boundary is a decision rather than an omission. | this PR |
| 4 | self | the-loop (agent) | **new finding — a test writing into the checkout it runs from.** A full run left an untracked `.the-loop/portable/github-octo-repo-15.json` behind, bisected to the new control-command scenario: `ServerFactory` never set `portable_dir`, and `RoutingConfig`'s default is the *process's* own `.the-loop/portable`. Nothing had exercised the control path in that file before, so the gap was latent. Fixed in the factory rather than the one test, so the next control scenario cannot reintroduce it. | this PR |
| 5 | self | the-loop (agent) | zero (converged) | this PR |
| 6 | critic | — | **unavailable** — `reviews.critics: []`; no critic harness is configured in this repository, so no critic round could run. Does not count toward `criticReviewCount`; the human PR review is the backstop. | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist, cross-checked against `design.md` § Security design
  (`security.review.mechanism: auto`).
- **Outcome:** **pass.** The change adds no network reach, no new privilege and no new
  external input format. Both ends of every record are `WorkItemRef`s the router already
  constructed; they are re-parsed on read, so a hand-edited record holding a path or a shell
  fragment fails `WorkItemRef.parse` and is treated as absent. The file name is derived
  through `WorkItemRef.slug`, whose final `re.sub(r"[^A-Za-z0-9._-]+", "-", …)` makes
  directory traversal unrepresentable. Only the dispatcher writes bindings, and only for a
  session an event **already routed into** under the existing guards
  (`authorizedUsers`, the self-comment marker, the auto-execute label,
  `requireStartCommand`) — so no binding can name a session the un-fixed the-loop would not
  already have delivered into. Resolution is single-hop and self-binding is refused, so
  there is no chain or cycle to bound. The records are classified **local**, which is what
  keeps them outside the "a tracked record is an input" surface that portable state has.
  Every failure mode degrades to the pre-fix behaviour and none past it. The two poll-path
  findings from self-review round 1 are availability, not security: both made the-loop do
  *less* than it should (drop a delivery, re-forward one), never more.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

Every acceptance criterion is proved by a committed artifact under
[`evidence/`](evidence/); the per-activity record is in
[`testing-plan.md`](testing-plan.md) § Verification results.

- **The ticket's reproduction is fixed** (R2.1, R5.1) — two PR events, the second carrying
  no linkage at all, both delivered into the issue's session:
  [`evidence/reproduction.md`](evidence/reproduction.md).
- **The regression tests test something** (R5.1) — all six fail against a registry whose
  `session_for` is the bare `find_by_work_item`, and the 16 that still pass are the close and
  linked-issue scenarios this work item must not change:
  [`evidence/tests.md`](evidence/tests.md).
- **The poll ingress is fixed too** (R2.8, R2.9) — a binding-resolved delivery reports `done`
  rather than being re-forwarded, and a polled PR with a stored binding is a known item
  rather than first sight (which would baseline its whole thread and arm a spawn against the
  PR): [`evidence/tests.md`](evidence/tests.md) § T2b.
- **The binding is durable and inspectable** (R1.3, R1.4, R4.1) — the record survives a
  fresh `SessionRegistry`, is not rewritten when unchanged, and is invisible to
  `list_sessions`: [`evidence/tests.md`](evidence/tests.md).
- **The abuse cases hold** (R1.5, R2.3, security design) — a corrupt record reads as absent,
  a self-binding is refused, a chained binding is not followed:
  [`evidence/tests.md`](evidence/tests.md).
- **issue-101 is unchanged** (R3.1, R3.2) — a PR close matched through a binding leaves the
  session open; a PR with its own session is still auto-closed:
  [`evidence/tests.md`](evidence/tests.md).
- **Nothing else moved** — 1404 passed, 1 skipped (pre-existing, unrelated; baseline
  1379/1); `ruff`, `ruff format --check`, `pyright` and `markdownlint` clean:
  [`evidence/tests.md`](evidence/tests.md),
  [`evidence/lint-and-types.md`](evidence/lint-and-types.md).

## Capability docs

> Which living capability docs this work item changed, and the history row that traces the
> behaviour back to it. Updated **in the same PR** as the change — a ready-to-ship gate
> item (`workflow.capabilitiesDir`).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) | new behaviour clause beside the linked-issue routing bullet it repairs: the binding is recorded when the routing decision is made, resolution order (own record, then binding, single hop), what it does **not** change (issue-93's derivation, issue-101's close rule), and where the record lives | issue-172 · [decision-064](../../decisions/decision-064.md) |

No other capability doc changed. `interactive-sessions.md` describes the recovery ladder,
which this work item makes *reachable* for PR-keyed events without altering a rung of it;
`cli.md` describes `sessions reset`, whose new `link` piece is documented where the reset
table lives (`docs/cli/state.md`) rather than restated in the capability doc.
