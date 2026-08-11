---
type: execution-log
workItem: issue-205
phase: needs-review
status: in-progress
---

# Execution Log: one source of truth for the poller's pid

> Append-only log for issue-205. Ticket:
> [#205](https://github.com/MadaraUchiha-314/the-loop/issues/205).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-11 | — | The owner dispatched the ticket straight to a cloud session, so no checklist was posted and no phase was declared away by a human. Rigor scaled to the change per `config.autonomy` — risk tier 2, no sensitive path, and the deleted field has no consumer — so the chain is one `requirements.md` carrying its own design and test matrix, as issue-201 did. The human gate is the PR review. |
| requirements-definition | 2026-08-11 | | `requirements.md` locked — two requirements: one source of truth for the pid, and the two-file separation recorded where the next reader meets it. |
| implementation | 2026-08-11 | | `pid` removed from `Heartbeat`, `PollHeartbeat` and the written document; the rationale written into the module docstring, `docs/cli/state.md`, the capability doc and decision-076. |
| verification | 2026-08-11 | | Every row of the matrix executed; evidence recorded. |
| needs-review | 2026-08-11 | | Self-review; awaiting the human gate on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-205-jn4vq8` | the whole work item | open |

## Progress entries

### 2026-08-11 — the answer, and the field it removes

- **Phase:** requirements-definition → implementation → verification
- **Did:** Answered both branches the ticket allowed. **Two files are required** — the
  atomic rewrite that keeps the heartbeat crash-safe replaces the inode the flock is held
  on, so merging them would free the poller's own lock on its first cycle; their lifetimes
  (removed on release vs kept after exit) and their failure policies (fatal vs swallowed)
  are opposite too. **And the duplicate was removed** — not the file, the `pid` *field*
  inside it, written every cycle and read by nothing, since `poll status`, `daemon_status`
  and every client over them take the pid from `RunLock.holder()`. Deleted from
  `Heartbeat`, from `PollHeartbeat.__init__` and from the document; `from_mapping` drops a
  pid left by an older poller.
- **Checkpoint/tests:** the inode claim is a test, not a sentence —
  `test_writing_a_heartbeat_over_the_pidfile_would_free_the_lock` performs exactly what
  `PollHeartbeat._write` does over a held `RunLock` and asserts the lock goes free. Added
  `test_a_pid_left_in_an_older_heartbeat_is_never_reported`, which plants a **live**
  `os.getpid()` in the heartbeat and asserts no surface reports it. `make test` 1800
  passed, 1 skipped; gates green.
- **Next:** the reviewer briefing on the PR, and the answer posted on the ticket.

## Verification results

> Recorded in [`requirements.md`](requirements.md) § Testing, against the matrix rows that
> planned them, with the raw output in [`evidence/verification.md`](evidence/verification.md).
> This work item has no separate `testing-plan.md`: the matrix is small enough to live with
> the requirements it proves.

## Design critic review

> Not selected. `design-critic-review` is opt-in (issue-188) and this work item did not
> tick it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — the first cut deleted the field and left `docs/cli/state.md` and `the_loop.state.GENERATED_PATHS` both claiming the heartbeat holds a pid. The docs↔code parity check is on the *paths*, not their descriptions, so nothing would have caught it | `state.md`, `state.py` |
| 2 | self | the-loop (this session) | new findings — the rationale existed only as prose. Rewrote it as `test_writing_a_heartbeat_over_the_pidfile_would_free_the_lock`, so the reason the files stay separate fails the build if it ever stops being true | `test_poll_heartbeat.py` |
| 3 | self | the-loop (this session) | zero (converged) | — |
| 4 | critic | — | unavailable — `reviews.critics` is empty in this project's config | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |
| 5 | security | the-loop checklist | no findings — see the gate below | [`requirements.md`](requirements.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`). The change is a
  deletion: no new reader, writer, path or parser.
- **Outcome:** **pass, no findings — and the forgeable surface narrows.** The heartbeat has
  always been untrusted input to `poll status`, and liveness has always come from the lock
  (issue-191). Removing `pid` means a forged or stale heartbeat can no longer even appear
  to name a live process to an operator reading the file by hand. Abuse case 2 is pinned by
  `test_a_pid_left_in_an_older_heartbeat_is_never_reported`, which deliberately uses a live
  pid.
- **Human sign-off:** n/a — risk tier 2, below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

| Requirement | Proved by |
|---|---|
| R1 — the pid has exactly one source of truth | `test_the_heartbeat_records_no_pid` (document keys and the model), `test_an_older_heartbeat_carrying_a_pid_still_reads` (R1.3), `test_a_pid_left_in_an_older_heartbeat_is_never_reported` (R1.2), and `test_poll_status.py` unchanged and green for R1.4 |
| R2 — the separation is recorded where the next reader will meet it | [`docs/cli/state.md`](../../cli/state.md) § Why this is a second file, and not part of the pidfile; the `the_loop.poller.heartbeat` module docstring; [`decision-076`](../../decisions/decision-076.md) |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`cli.md`](../../capabilities/cli.md) | The `poll status` behaviour now says **liveness and the reported pid** come from the lock, and a new bullet states that the heartbeat carries no pid, that an older one's is ignored, and the three reasons the two files stay separate | `issue-205` row added at the top of § History |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/cli/state.md`](../../cli/state.md) | The heartbeat's JSON sample lost its `pid`; the classification table row says the pid is `poll.pid`'s to name; a new subsection answers *why this is a second file, and not part of the pidfile* with the three-row comparison, and the `poll.pid` section links to it |
| [`docs/decisions/decision-076.md`](../../decisions/decision-076.md) | New — the split, the deleted field, and the four alternatives rejected (including both merge directions) |
| `README.md`, `cli/README.md`, `docs/cli/commands/poll.md` | Unchanged, deliberately: all three describe `poll status` reporting a pid, which it still does — from the lock, as it always has |
