---
type: execution-log
workItem: issue-201
phase: needs-review
status: in-progress
---

# Execution Log: adopt an unconfigured repository before the session is spawned

> Append-only log for issue-201. Ticket:
> [#201](https://github.com/MadaraUchiha-314/the-loop/issues/201).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-10 | @MadaraUchiha-314 (out of band) | Raised by the owner while reviewing #195 and worked in the same cloud session, so no checklist was posted. Scaled to the change per `config.autonomy`: a `bugfix.md` carrying its own design and test matrix in place of the four-file chain (decision-045 allows either name at the gate). |
| requirements-definition | 2026-08-10 | | `bugfix.md` locked — two requirements: the config exists before the harness starts, and the gates do not move with it. |
| implementation | 2026-08-10 | | `GraphLink.adopt`, two dispatcher call sites, the ordering test. |
| verification | 2026-08-10 | | Every row of the matrix executed; evidence recorded. |
| needs-review | 2026-08-10 | | Self-review; awaiting the human gate on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-193-x96m3i` | the whole work item | open |

## Progress entries

### 2026-08-10 — the fix

- **Phase:** requirements-definition → implementation → verification
- **Did:** Split issue-193's `_adopt` into `GraphLink.adopt` (public, pre-spawn, running
  the coupling's gates itself because `cwd` is not yet proved to be the work item's
  repository at that point) and `_write_default` (the shared writer, carrying the
  contribution carve-out), with `_adopt` left on the driving actions as an idempotent
  safety net. Called from `Dispatcher._spawn_session` between `_prepare_workspace` and the
  context read, and from the respawn path beside `_prepare_environment` — the two places a
  harness process is about to start in a checkout.
- **Checkpoint/tests:** the ordering test asserts from **inside** `FakeTmux.spawn`, and
  was verified red by disabling the pre-spawn call before being kept — an ordering test
  that passes with the fix reverted proves nothing. `make test` 1782 passed, 1 skipped.
- **Next:** the reviewer briefing on the PR.

## Verification results

> Recorded in [`bugfix.md`](bugfix.md) § Testing, against the matrix rows that planned
> them. This work item has no separate `testing-plan.md`: the matrix is small enough to
> live with the requirements it proves.

## Design critic review

> Not selected. `design-critic-review` is opt-in (issue-188) and this work item did not
> tick it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — the first cut left `_adopt`'s three-part docstring describing a placement that had moved; split into `adopt` (ordering + gates) and `_write_default` (the carve-out) so each says what it actually does | `graphlink.py` |
| 2 | self | the-loop (this session) | new findings — `_SeqLink`, the dispatcher's GraphLink double, lacked the new method and failed three unrelated tests. Adding it to the double (rather than making the dispatcher tolerant of a missing method) keeps a wiring bug loud, and let the existing sequence assertion cover adoption too | `test_graph_drive_integration.py` |
| 3 | self | the-loop (this session) | zero (converged) | — |
| 4 | critic | — | unavailable — `reviews.critics` is empty in this project's config | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |
| 5 | security | the-loop checklist | no findings — see the gate below | [`bugfix.md`](bugfix.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; the built-in skill
  ran for issue-193 over the same code, and this work item moves a call rather than
  changing what it does).
- **Outcome:** **pass, no findings.** The write target, the `owner`/`repo` allow-list, the
  symlink containment and the never-overwrite rule are untouched. The one risk the move
  introduced was writing into a `cwd` not yet proved to be the work item's repository —
  which is why the ownership proof moved with the write instead of being left behind in
  `_guarded`. Recorded as `bugfix.md` § Security considerations with its two abuse cases.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

| Requirement | Proved by |
|---|---|
| R1 — the config exists before the harness starts | `test_the_repository_is_adopted_before_the_harness_is_started`, asserted from inside the spawn call and verified red without the fix; `test_a_spawn_reads_context_before_render_and_enters_after` pins the full `adopt → context → deliver → spawn` order |
| R2 — the gates do not move with it | issue-193's suite unchanged and green (47 passed), including the foreign-checkout, contribution and never-overwrite scenarios |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | The adoption bullet now states *when* it happens — before the prompt is rendered and before anything spawns — and names the respawn pre-flight | `issue-201` row added at the top of § History |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/harness-config.md`](../../config/harness-config.md) | The *When a repository has no config* table now says the daemon adopts **before the session starts**, so a reader knows the guarantee, not just the behaviour |
| [`skills/the-loop/reference/automation.md`](../../../skills/the-loop/reference/automation.md) | Same clarification in the bullet an agent working under the-loop reads |
| `decision-073` | Unchanged: the decision it records — one packaged default, one writer, the contribution carve-out — is exactly what this work item preserves. The ordering was an implementation defect, not a change of mind, so it is recorded here rather than as a new decision |
