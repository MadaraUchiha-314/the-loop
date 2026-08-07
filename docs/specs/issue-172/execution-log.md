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
| design (revisited) | 2026-08-07 | @MadaraUchiha-314 (PR #173 review) | owner rejected the link-record shape; rebuilt to the single-record `pullRequests[]` endpoint model with `sessionPerPr`, and set the inner/outer-loop direction |
| verification (re-run) | 2026-08-07 | — | every activity re-executed against the rebuilt model; 7-test negative run |
| needs-review (again) | 2026-08-07 | pending | 2 further self-review rounds on the rebuild |
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

### 2026-08-07 — owner review overturns the storage model; rebuild

- **Phase:** design (revisited) → implementation → verification
- **Did:** the owner rejected decision-064's D1 on the PR — *"We should have a single
  session file for one work-item with links to all the PRs … along with all the tmux and
  claude/cursor session. It should be a config whether to create multiple tmux sessions
  for each PR … Default: separate tmux session for each PR."* Rebuilt accordingly: the
  link records are gone; `Session` now serves as record **and** endpoint, a record carries
  `pullRequests[]`, each PR gets its own lazily-spawned tmux session and conversation
  (`routing.tmux.sessionPerPr`, default true, `false` = the pre-issue-172 single-session
  shape), a PR close ends its endpoint only, and dedup/touch became per-endpoint.
  `reset.py` got simpler — the entries live inside the record, so no `LINK` piece and no
  new generated path. Spec chain, decision-064 (reversal recorded, not erased),
  capability doc and `state.md` rewritten to match. The owner's follow-up comment set the
  **inner/outer-loop** direction: definition captured in `design.md` § The two loops and
  decision-064; per-PR graph execution declared follow-up, and this change enforces the
  boundary (a PR endpoint enters no graph).
- **Checkpoint/tests:** `pytest -q` → 1403 passed, 1 skipped. All seven regression tests
  fail against a pre-fix resolver. `ruff`, `pyright`, `markdownlint`,
  `validate_config.py` clean.
- **Next:** self-review of the rebuild, then update the PR briefing.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (agent) | **new findings — two poll-path regressions the first draft introduced.** Swept every remaining `find_by_work_item` call site instead of only the ones the design named. (a) `Dispatcher.delivery_status` asks the registry about the *routed* refs, but a delivery through a binding records its id on the **bound** session — so a successful delivery would have reported `unhandled` and the poller would re-forward the same comment until `maxRetries` was spent. (b) `Poller._process_item`'s `has_session` had the same shape and a worse consequence: a PR whose linkage is gone would be treated as **first sight**, baselining its whole existing thread as read and arming a spawn against the PR while the issue's session ran. Fixed by moving the resolution onto the registry as `session_for()` — the question both ingresses ask — and pointing all four call sites at it. Two regression tests added; both fail against the pre-fix behaviour. | this PR |
| 2 | self | the-loop (agent) | **new findings, both about consistency with neighbouring code.** (a) `unlink()` emits `session.unlinked` while `forget()` deliberately emits nothing, which looked like an oversight; kept and justified instead — a reset also removes bindings filed under **other** work items' names, which the single `session.reset` event does not mention. Written into `unlink`'s docstring. (b) `design.md` claimed the record involves "no read-modify-write at all", which is not true: `link()` reads the existing record to preserve `createdAt` and to decide idempotence. Corrected to the property that actually holds — the only writer of a PR's file is a binding for that PR, and `os.replace` means a same-PR race can only write the same record twice. | this PR |
| 3 | self | the-loop (agent) | **new finding, scoped not fixed** — `sessions pause\|resume\|stop\|attach\|reset` still resolve directly, not through bindings. Deliberate: those name a work item explicitly, and acting on a different one ("I asked to stop #16 and you stopped #15") is worse than making the operator name what they meant. Promoted from an unstated assumption to R2.10 and a row in `design.md`, so the boundary is a decision rather than an omission. | this PR |
| 4 | self | the-loop (agent) | **new finding — a test writing into the checkout it runs from.** A full run left an untracked `.the-loop/portable/github-octo-repo-15.json` behind, bisected to the new control-command scenario: `ServerFactory` never set `portable_dir`, and `RoutingConfig`'s default is the *process's* own `.the-loop/portable`. Nothing had exercised the control path in that file before, so the gap was latent. Fixed in the factory rather than the one test, so the next control scenario cannot reintroduce it. | this PR |
| 5 | self | the-loop (agent) | zero (converged) — on the link-record version | this PR |
| 6 | self (rebuild) | the-loop (agent) | **new findings** — (a) a corrupt `pullRequests` entry initially poisoned the whole record in `from_dict`, taking the work item's own session down with a hand-edited PR entry; parsing became per-entry, matching `_read`'s unreadable-file posture. (b) The re-link case surfaced a real edge: two records can claim one PR, and their endpoints contend for the PR's single deterministic `loop-<slug>` tmux name — the loser falls back to its record's session. Written down as decision-064 § Known edge and tested in collapsed mode rather than hidden. | this PR |
| 7 | self (rebuild) | the-loop (agent) | **new finding, scoped not fixed** — a PR endpoint deliberately enters no process graph (`_spawn_endpoint` skips `graphlink.on_spawn`): letting it in would open a second graph on the work item's spec directory. Promoted to R2.9 and the § The two loops boundary, so the inner-loop follow-up starts from a stated invariant rather than an accident. | this PR |
| 8 | self (rebuild) | the-loop (agent) | zero (converged) | this PR |
| 9 | critic | — | **unavailable** — `reviews.critics: []`; no critic harness is configured in this repository, so no critic round could run. Does not count toward `criticReviewCount`; the human PR review is the backstop. | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist, cross-checked against `design.md` § Security design
  (`security.review.mechanism: auto`). Re-run in full after the rebuild — the first
  pass's subject (link records) no longer exists.
- **Outcome:** **pass.** No new network reach and no new external input format. Every
  `pullRequests` entry's ends are `WorkItemRef`s the router constructed, re-parsed on
  read; a hand-edited entry is skipped **per entry** (never fatal to the record), nesting
  is one level by construction, and a self-recording is refused in the store. Only the
  dispatcher records PRs, downstream of the self-comment marker, `authorizedUsers`, the
  label and `requireStartCommand` — so a PR can only be recorded against a record an
  event already routed into under those guards. What **does** grow is the number of
  harness processes (one per active PR, by default): each is spawned by the same guarded
  path with the same trust pre-flight in the same checkout, the growth is bounded by open
  recorded PRs and gated by the same start controls, and it is operator-visible
  (`sessions list`, spawn announcements). Every failure mode degrades to a behaviour
  the-loop already had: unreadable entry → that PR unrecorded; unspawnable endpoint →
  deliver to the record; recording failed → derivation alone.
- **Human sign-off:** risk tier **4** — the change adds a key to
  `.the-loop/cli-config.schema.json`, which matches `autonomy.sensitivePaths`
  (`**/*schema*`), and `security.review.humanSignOffMinTier: 4` therefore applies.
  **Pending: the owner's PR review is the sign-off**, requested in the PR briefing.

## Final validation evidence

Every acceptance criterion is proved by a committed artifact under
[`evidence/`](evidence/); the per-activity record is in
[`testing-plan.md`](testing-plan.md) § Verification results. All of it re-captured after
the rebuild.

- **The ticket's reproduction is fixed** (R2, R5.1) — the linkage-removed second event is
  delivered into the PR's recorded session; the registry holds one file per work item and
  the PR is on it: [`evidence/reproduction.md`](evidence/reproduction.md).
- **The regression tests test something** (R5.1) — all seven fail against a resolver
  restored to pre-issue-172 behaviour: [`evidence/tests.md`](evidence/tests.md).
- **Per-PR sessions work, and collapse works** (R2.1, R2.2) — the endpoint spawn, the
  fallbacks, and `sessionPerPr: false` delivering into the work item's single session:
  [`evidence/tests.md`](evidence/tests.md).
- **issue-101 is now the model** (R3.1, R3.2) — a PR close ends its endpoint and keeps
  the record; a PR with its own record still auto-closes:
  [`evidence/tests.md`](evidence/tests.md).
- **The abuse cases hold** (R1.5, R1.6) — per-entry degradation, flattened nesting,
  refused self-recording: [`evidence/tests.md`](evidence/tests.md).
- **Nothing else moved** — 1403 passed, 1 skipped (baseline 1379/1); `ruff`,
  `ruff format --check`, `pyright`, `markdownlint` and `validate_config.py` clean:
  [`evidence/tests.md`](evidence/tests.md),
  [`evidence/lint-and-types.md`](evidence/lint-and-types.md).

## Capability docs

> Which living capability docs this work item changed, and the history row that traces the
> behaviour back to it. Updated **in the same PR** as the change — a ready-to-ship gate
> item (`workflow.capabilitiesDir`).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) | the linked-issue routing bullet gained the recorded-PR behaviour: the PR on the work item's single record, per-PR sessions under `sessionPerPr` (default on) with lazy spawn and fallback, additive resolution, the endpoint-close rule, the new event types, and the stated inner/outer-loop boundary | issue-172 · [decision-064](../../decisions/decision-064.md) |

`docs/cli/state.md` (the session record's shape and lifecycle) and
`docs/config/cli/routing-options.md` (`tmux.sessionPerPr`) changed in the same PR;
they are reference pages rather than capability docs, listed here for the reviewer's
completeness. `interactive-sessions.md` is untouched: the recovery ladder it describes
now applies per endpoint, without a rung changing.
