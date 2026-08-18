---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#269"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a branch name invented a work item, and the daemon obeyed it

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| not-started | 2026-08-18 | — | ticket #269 opened by the owner, with a follow-up comment naming the direction |
| phase-selection | 2026-08-18 | — | see Deviations: the loop was run by hand in a cloud session, not by a daemon |
| requirements-definition | 2026-08-18 | pending | `bugfix.md` |
| design | 2026-08-18 | pending | `design.md` |
| test-planning | 2026-08-18 | pending | `testing-plan.md` |
| tasks-breakdown | 2026-08-18 | pending | `tasks.md` |
| implementation | 2026-08-18 | — | tasks 1–8 |
| verification | 2026-08-18 | — | every activity in the testing plan ran; results recorded there |
| needs-review | 2026-08-18 | pending | human approval of the pull request (tier 3: `human-approves-pr`) |

## Pull requests

| Repository | PR | Loop state | Status |
|---|---|---|---|
| MadaraUchiha-314/the-loop | (this branch) | outer loop only — one repository, one delivery | open |

## Progress entries

### 2026-08-18 — the ticket asks for three things; two of them turned out to be one

The "Expected" section offers three fixes as "some combination of": verify a branch-derived
ref, bind a control command on a PR to the PR's own ref, and act on the announcement's 404.
Taking the second one literally would have **reintroduced** a bug issue-93 fixed: a
`the-loop start` on a pull request that legitimately delivers issue #100 must still start
issue #100, and binding to `pr_work_item()` unconditionally would have started the pull
request instead.

Then the arithmetic: once the ghost is dropped, `work_items[0]` **is** the pull request in
the ticket's scenario. The second bullet is the first bullet's consequence, and asking for
it separately would have been a second, contradictory rule. That is decision-095 D4.

### 2026-08-18 — the owner's comment is the other half, and it did not work at all

> "Whenever user responds to a PR, the-loop should check what work item that PR is linked to
> (not through github, but through internal tracking mechanisms)."

That mechanism exists — issue-172's `pullRequests[]` on the work item's record, resolved by
`registry.record_owning`. Chasing what it would take to make `_apply_control` use it turned
up something worse than the ordering bug: on the **poll** ingress, the ingress the ticket was
reported from, the binding was never written from a comment in the first place.

The poller synthesises a comment event over the pull request's own payload (key
`pull_request`, head branch included) and renames the event `issue_comment`. `_pr_entity`
reads `payload["issue"]` for that name, finds nothing, and `pr_work_item` answers `None` —
so `_record_pr_binding` wrote nothing and `_endpoint_for` never chose a pull request's
endpoint. The internal tracking the owner is pointing at had nothing to track with on that
path. One fallback line (unreachable from a real webhook, which never puts a `pull_request`
beside an `issue_comment`) fixes it; it is R2.6, decision-095 D6, and the reason the
webhook-shaped integration scenarios fail on `main` by delivering *nothing* rather than by
delivering to the ghost.

### 2026-08-18 — the shape: provenance, one check, one target

- **Provenance, not a second traversal.** The router now records where each ref came from in
  the walk it was already doing; `extract_work_items` and the new `branch_derived_refs` are
  views over it. Two walks would eventually disagree about which refs an event yields.
- **A pure function, not a field on `RoutedEvent`.** Two ingresses build that object and a
  third caller builds one by hand. `branch_derived_refs(event, payload)` cannot be forgotten
  by one of them.
- **Unknown keeps the ref.** The one direction this guard fails open in restores exactly the
  prior behaviour; failing closed would mean "route nothing while GitHub is unreachable" —
  a worse failure than the one being fixed, arriving silently.
- **The record answers before GitHub is asked.** Not only the owner's direction but also
  what makes the check nearly free: an established work item's every comment would otherwise
  pay for a question whose answer changes nothing, and a ghost beside a matched record is
  inert anyway.

### 2026-08-18 — one seam that was not obvious

`_verify_linkage` runs **before** control parsing, not after. A control command is targeted
at `work_items[0]`, so filtering afterwards would have left `the-loop start` recorded against
the ghost and only the spawn corrected — the two halves of the ticket's symptom, fixed apart.

The second was the test suite's hermetic rule. `RoutingConfig` defaults leave every
dispatcher test with a real announcer and reactor, which is why `conftest` already stubs
them; the existence check reads through the same `gh`, so it needed the same treatment or
2400 tests would have started shelling out on any machine with `gh` installed. The stub
answers "cannot tell", which is exactly the pre-change routing behaviour — so every existing
test still asserts what it always did.

### 2026-08-18 — red, then green

The red run that matters is in `evidence/red.md` §1: the **real** `GitHubPollProvider`,
`Poller` and `Dispatcher` against a canned `gh`, with the fix's injection seams removed from
the harness, reproducing the ticket in one line —

```text
E       AssertionError: assert 'github:octo/repo#285' == 'github:octo/repo#48'
```

— alongside its control (the same pull request with a *real* issue 285), which passes both
before and after. Green: `make test` — 2410 passed, 1 skipped, up from 2408 before the
change. No existing test was modified to accommodate the fix; four helpers gained one
optional argument each and `FakeRun` gained a `stderr` parameter.

### 2026-08-18 — verification

Every activity in `testing-plan.md` ran; results and evidence links are in that file's
Verification results table. `make lint` raised two findings during the run (an `f`-prefixed
string with no placeholders, and three files needing `ruff format`) plus four
`MD049/emphasis-style` findings in this work item's own spec files — all fixed before the
gate and listed in `evidence/lint-and-typecheck.md` rather than quietly dropped.

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — the
  linkage section states the verification rule, the record-answers-first rule, the polled
  pull-request comment, and the announcement's 404; the branch-convention clause now says it
  is silent about existence as well as about repository; plus a history row.

No other capability doc is affected: nothing about the process graph, the session registry's
on-disk shape, the control plane or the CLI's surface changed.

## Documentation

- [`docs/cli/receiver.md`](../../cli/receiver.md) — the routing list gains a **Verification**
  step between Extraction and Dedup.
- [`docs/cli/concepts.md`](../../cli/concepts.md) — the matching paragraph says what a
  branch-derived name is and is not evidence of.
- `README.md`, the guide and `skills/the-loop/SKILL.md` are **unchanged, deliberately**: this
  is a routing correctness fix inside a capability they already describe at a level the
  change does not contradict, and no operating-model rule, phase, gate or configuration key
  moved. The event catalogue (`the-loop events --types`) is generated from
  `eventlog.EVENT_TYPES`, so the two new types document themselves.

## Decisions

- [decision-095](../../decisions/decision-095.md) — *the weakest linkage source earns its
  place, and the record answers before GitHub is asked*. Refines decision-036 (its three
  sources stand; one of them is now checked), decision-064 (its recorded binding finally
  reaches the three call sites still reading a list index) and decision-069 (the branch
  convention stays local **and** is no longer taken on trust).

## Deviations from the standard gates

- **The loop was walked by hand.** This session is a Claude Code cloud session in the-loop's
  own repository, where the plugin's SessionStart hook does not fire and no daemon is driving
  the graph (the gap `CLAUDE.md` exists to cover). The spec chain, the phase labels and this
  log were produced by following `skills/the-loop/SKILL.md` directly. No `phase-selection`
  checklist was posted and no `the-loop execute` was signed, because there was no daemon to
  post one — so the artifacts stand in for the gate, and the human approval is the pull
  request review.
- **The security review used the checklist, not the skill.** `security.review.mechanism` is
  `auto`, which prefers the built-in security-review skill; the checklist is its shipped
  fallback and is what ran here. Recorded in `evidence/security-review.md` as what it was.
- **`tdd.mode: standard`, honestly reported.** The unit tests for the new module were written
  first and run red (`ImportError`); the dispatcher and integration tests were written
  before the production edits but their red capture required removing the fix's own injection
  seams from the harness, which `evidence/red.md` states at the top of each capture rather
  than presenting as a clean tests-first run.
- **The related casualty is a separate ticket.** The pre-start comment that is dropped
  `awaiting-start` and never replayed is filed as its own issue, per the reporter's own
  "possibly its own issue" — it is a product decision about replay semantics, not linkage
  correctness. Linked from `bugfix.md` §Out of scope.
- **One unrelated line.** `uv.lock` picks up `version = "11.0.0"` for the workspace package.
  The `10.6.0 → 11.0.0` bump commit did not refresh the lock, so `uv run` rewrites it on the
  first invocation in any checkout. Included because leaving it dirty is worse than carrying
  a one-line lock sync; it is not part of this change.
