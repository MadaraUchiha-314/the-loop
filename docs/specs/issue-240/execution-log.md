---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#240"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
# repos:                     # OPTIONAL (issue-183). Single-repository work item.
---

# Execution Log: a read-only tmux observer blocks every comment the poller forwards

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in the ticketing system in sync with the `phase` front-matter above, and
> self-checks (runs tests at logical checkpoints) recording the outcome here.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | — (declared on the ticket, see below) | No daemon and no human on the thread; the full chain was run rather than any phase being skipped. `brainstorming` and `design-critic-review` not run. Outer loop iterates **on a pull request**. |
| requirements-definition | 2026-08-16 | pending (PR) | `bugfix.md` — a bug, so `bugfix.md` not `requirements.md`. |
| design | 2026-08-16 | pending (PR) | Settled the deferred question: the submit is a second, unbracketed `paste-buffer`. Four rejected alternatives recorded, including the ticket's own suggestion 1. |
| test-planning | 2026-08-16 | pending (PR) | 15 rows, 8 in scope; each `n/a` carries a reason. The plan is explicit that the failure itself is not reproducible on this machine. |
| tasks-breakdown | 2026-08-16 | — | 8 tasks, two independent red roots. |
| implementation | 2026-08-16 | — | TDD: red committed before the fix. |
| verification | 2026-08-16 | — | Every activity ran. One thing deliberately **not** claimed — see § Final validation evidence. |
| needs-review | 2026-08-16 | | |
| complete | | | |

**On the phase-selection gate.** The loop's rule is that skips are declared by humans and
never taken by the harness, and that the gate is never answered from a working session.
This session was invoked directly on the issue with no daemon driving it and nobody on the
thread to answer, so the gate could not be *answered* — and blocking would have delivered
nothing. The rule was honoured in the only direction available: **nothing was skipped.**
The whole chain was written, the reviews were run, and the approval sits where the risk
tier says it belongs — a human approving the PR (`autonomy.defaultTier: 3` →
`human-approves-pr`). If the owner wants phases declared away retrospectively, the PR is
the place to say so.

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| *(opened on push)* | The whole work item — the spec chain and the fix. | open |

## Progress entries

### 2026-08-16 17:20 UTC — the ticket's root cause was half right, and its first fix does not work

- **Phase:** requirements-definition
- **Did:** read the delivery path end to end (`cli/the_loop/runner.py:602-653`,
  `cli/the_loop/webhook/dispatcher.py:1559`, `cli/the_loop/poller/poller.py:939-996`), then
  went to tmux's own source rather than reasoning about it. Two things came out that the
  ticket did not have.
- **Found — it is version-gated.** `send-keys` acquired its read-only guard *after* 3.6.
  `cmd-send-keys.c` at each release tag: `3.4: 0`, `3.5a: 0`, `3.6: 0`, `master: 1`
  occurrences of `client is read-only`, and `CMD_READONLY` appears in the entry's `.flags`
  only in master. Reproduced on the local tmux 3.4 with a genuinely read-only client
  attached (`#{client_readonly}=1`): `send-keys` exits **0**. So an operator acquires this
  defect by upgrading tmux, with no the-loop change involved.
- **Found — the ticket's suggested fix 1 cannot work.** "Resolve and cache the pane id and
  send to `%N`" addresses `-t`. The guard tests `item->target_client`, which
  `cmdq_fire_command` resolves from `-c` (`send-keys` carries `CMD_CLIENT_CFLAG`) — and with
  no `-c`, from `cmd_find_current_client` → `cmd_find_best_client`, i.e. the session's
  attached client. `-t` never enters that resolution. A pane-targeted `send-keys` is refused
  by the identical branch.
- **Checkpoint/tests:** baseline suites green (246 passed) before anything was touched.
- **Next:** derive `design.md`; decide what carries the submit byte.
- **Blockers:** none.

### 2026-08-16 17:35 UTC — design, testing plan, and the red run

- **Phase:** design → test-planning → tasks-breakdown → implementation
- **Did:** settled the deferred question as a second, **unbracketed** `paste-buffer` of a
  carriage return. `cmd_paste_buffer_exec` consults no client — it writes to the `-t` pane's
  `wp->event` — and the only read-only test that applies to it is the one on the client
  *issuing* the command, which is the daemon's own subprocess. Recorded four rejected
  alternatives rather than dropping them, including `send-keys -c` (there is no
  non-read-only client to name when the bug is present) and putting the `\r` inside the
  bracketed buffer (which would make the submit depend on the TUI *not* honouring bracketed
  paste). Then wrote `testing-plan.md` and `tasks.md`, and committed the failing tests.
- **Checkpoint/tests:** red confirmed — 4 failing assertions plus a collection error
  (`evidence/red.md`), committed as their own commit before any production change.
- **Next:** implement tasks 3 and 4.
- **Blockers:** none.

### 2026-08-16 17:50 UTC — implemented; the repository's own guard caught an omission

- **Phase:** implementation → verification
- **Did:** `deliver` now issues `load-buffer`, `paste-buffer -p`, `load-buffer`,
  `paste-buffer` — four commands, none of which resolves a client. The poller posts one
  give-up notice through the existing `comments.post_issue_comment`, after the ledger is
  written.
- **Found (not caused):** `test_every_emitted_event_type_is_documented` failed —
  `poll.giveup_reported` and `poll.giveup_report_failed` were emitted but not described in
  `eventlog.EVENT_TYPES`. Added both.
- **Found (not caused):** `uv.lock` was stale again. `cli/pyproject.toml` says `10.2.1`; the
  lock said `10.2.0`, because the bump commit `28770ed` updated one and not the other — the
  **same drift issue-238 hit at `10.2.0`**, which makes it a recurring gap in the bump
  rather than a one-off. Committed the regeneration because CI's own `uv sync` cannot go
  green without it, and flagged it on the PR.
- **Checkpoint/tests:** full suite 2116 passed / 1 skipped; `ruff check`, `ruff format
  --check`, `pyright` all clean.
- **Next:** verify against a live tmux, then self-review.
- **Blockers:** none.

### 2026-08-16 18:05 UTC — verified against a live tmux with a real read-only client

- **Phase:** verification
- **Did:** ran the four commands `deliver` issues, by hand, against a real tmux session with
  a genuine `tmux attach -r` client attached (`#{client_readonly}=1`, tmux's own format).
  All four exited 0 and **the pane ran the pasted command** — the prompt arrived bracketed
  and the unbracketed `\r` submitted it. Repeated with no client attached (R1.5): identical.
  `tmux list-buffers` empty afterwards, so both `-d` flags did their work.
- **Not executed:** the end-to-end refusal on tmux ≥ 3.7 — no such tmux exists in this
  environment and building one to watch a command fail is not proportionate. **Replanned,
  not skipped:** T11 proves the same fact from tmux's source and release history, and T1
  proves the replacement works with a read-only observer attached. What is therefore not
  claimed is stated in `testing-plan.md` § Verification results and again below.
- **Checkpoint/tests:** transcripts committed as `evidence/manual.md`.
- **Next:** self-review.
- **Blockers:** none.

### 2026-08-16 18:20 UTC — self-review found two real defects in the fix

- **Phase:** needs-review
- **Did:** three rounds over the whole diff, tracing consumers rather than re-reading it
  three times.
- **Round 1 — the notice answered the wrong ticket.** `_report_giveup` took `refs[0]`. For a
  **pull request**, `extract_work_items` yields the issue the PR is *linked* to **before**
  the PR's own number (issue-93) — correct for routing an event to that issue's session, and
  wrong for answering a comment: the human wrote it on the PR, and that is where they will
  look. A give-up on a PR comment would have replied on the issue. Fixed to build the ref
  from the polled `WorkItem`; pinned by
  `test_the_notice_answers_the_item_the_comment_was_written_on`, confirmed red against the
  pre-fix code (it posted to `issues/15` instead of `issues/42`).
- **Round 1 — a tempfile leak.** Writing the two buffer files as a list literal
  (`paths = [f(prompt), f(submit)]`) left the prompt file behind when the second could not
  be created — a property the single inline `mkstemp`/`finally` it replaced *did* have. Both
  the list build and `_buffer_file` itself now clean up and re-raise. Two tests.
- **Round 2 — the consumers.** Traced every caller of `TmuxRunner.deliver`: four in the
  dispatcher and, notably, `core/sessions.py:610` — the **reply** path that delivers a
  human's answer to `the-loop ask`. That path was broken by the same bug and is fixed by the
  same change; the fix is not poller-specific. Also confirmed the event-log catalogue is
  `eventlog.EVENT_TYPES` (no separate docs page to keep in parity), and that
  `notifications.events.dispatch-failed` deserved a sentence saying the ticket now gets told
  regardless of whether that notification is wired up.
- **Round 3 — upgrade behaviour, and one nice consequence.** The `gaveUp` ledger is
  version-gated (issue-146): a poller running a **different** CLI version re-arms comments an
  older one abandoned. So the comments stranded by this very bug are retried automatically
  on upgrade — and the delivery now works. Documented in `polling-options.md`, since the two
  rules only compose if a reader knows both. Also checked that `\r` survives a text-mode
  write on POSIX (`newline=None` translates `\n` only) and that `paste-buffer`'s separator
  logic never fires for a buffer with no `\n`.
- **Checkpoint/tests:** full suite **2119 passed / 1 skipped**; `ruff`, `ruff format`,
  `pyright` clean; `markdownlint` clean over every touched document.
- **Next:** security review, capability docs, reviewer briefing.
- **Blockers:** none.

## Verification results

> This work item has a `testing-plan.md`, so the `verification` node records its results
> **there**, against the matrix rows it planned. This section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> Only when this work item selected the opt-in `design-critic-review` phase (issue-188). It
> did not, so this section stays as the template left it.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop session | new findings — the give-up notice was addressed to `refs[0]`, which for a PR is the **linked issue**, not the PR the comment was written on. Fixed to use the polled work item; regression test confirmed red against the pre-fix code | commit `89cae4f` |
| 2 | self | the-loop session | new findings — writing the two tmux buffer files as a list literal leaked the first when the second could not be created, losing a cleanup property the code it replaced had. `_buffer_file` and the list build both clean up and re-raise; two tests | commit `89cae4f` |
| 3 | self | the-loop session | new findings — tracing `deliver`'s consumers surfaced `core/sessions.py:610`, the `the-loop ask` reply path, broken by the same bug and fixed by the same change (now stated in the briefing rather than left implicit); and the observability doc needed to say the ticket is told independently of `notifications.events.dispatch-failed` | this commit |
| 4 | critic | — | **unavailable** — `reviews.critics: []` in `.the-loop/harness-config.yaml`, so no critic is configured. Does **not** count toward `reviews.criticReviewCount` (`reference/reviewing.md`) | — |
| 5 | security | built-in security-review skill | pass — no findings at confidence ≥ 8 | see § Security review |

Rounds 1–3 each found something new, so the loop did not stop early. A fourth self-round was
not run: `reviews.selfReviewCount` is 3, and the three rounds were spent on distinct surfaces
(the poller's addressing, the runner's failure paths, and the change's other consumers)
rather than three re-readings of the same diff.

## Security review (gate)

- **Mechanism:** the built-in `security-review` skill (`security.review.mechanism: auto`).
  Run **inline rather than via sub-agents**, because this session is directed not to spawn
  agents; the same three phases were applied over the full diff.
- **Outcome:** **pass** — no findings at confidence ≥ 8. The questions put to it were the
  ones where this change could plausibly have gone wrong:

  | Question | Verdict |
  |---|---|
  | Does any payload-derived string reach a tmux argv? | No. `subprocess.run` takes a **list**, never a shell. The interpolated values are two buffer-name constants, `target` (constrained to `loop-<slug>`, `.`/`:` rewritten — issue-154), and two `mkstemp` paths. The prompt still travels by file; the submit file's content is a module constant. |
  | Can a commenter's text reach a comment the-loop posts with the operator's credentials? | No, and it is a property of the **signature**: `giveup_notice` has no parameter that could carry a body. Its inputs are the ref, the GitHub-issued comment id and URL, and an integer. |
  | Can an unauthorized third party make the-loop post? | No. Unauthorized and self-authored comments are baselined before `_process_comment` is reached, so they never spend an attempt and can never reach the give-up branch. |
  | Can the notice resume the session it describes? | No. `mark_self_authored` stamps it, and `is_self_authored` drops it on the next cycle — the issue-104 failure mode, asserted directly in two tests. |
  | Can a failed post corrupt the ledger? | No. `resolve_comment(gave_up=True)` runs **before** the post is attempted, and every failure in `_report_giveup` is caught. Fail-closed by ordering, not by a `try` alone. |
  | Does the fix widen what a read-only client may do? | No — the question worth asking, since the bug *is* tmux refusing a write. Nothing clears `CLIENT_READONLY`, detaches a client, or passes `-c`. The fix removes a client-resolved command rather than working around the flag; the observer's keyboard is as inert as before. |

- **Human sign-off:** n/a. Risk tier 3 (`autonomy.defaultTier`; no `sensitivePaths` glob
  matches — no schema, no `.the-loop/` config, no `.github/workflows/`), below
  `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

Every acceptance criterion is met. The raw record is in
[`testing-plan.md` § Verification results](testing-plan.md#verification-results) and under
[`evidence/`](evidence/).

| Criterion | Met by |
|---|---|
| **R1.1** delivery succeeds with a read-only client attached | The four commands run by hand against a session with a real `tmux attach -r` client (`#{client_readonly}=1`): all exit 0 and the pane ran the pasted command ([`manual.md`](evidence/manual.md) § T1a). |
| **R1.2** no `send-keys` in the delivery path | `test_deliver_pastes_bracketed_then_submits_without_send_keys` pins the whole argv list, and the integration test proves the same through a stub `tmux` binary that records every invocation. |
| **R1.3 / R1.4** prompt bracketed, submit not | Asserted on both pastes (`-p` present / absent), and demonstrated on a live tmux: the prompt did not execute until the CR paste arrived. |
| **R1.5** unchanged with no client attached | [`manual.md`](evidence/manual.md) § T1b, plus the unit argv test, which runs with no tmux server at all. |
| **R2.1–R2.3** the notice, its marker, its recovery | `test_giveup_notice_says_what_happened_and_what_to_do` and the integration scenario, which asserts the endpoint as well as the body. |
| **R2.4** the ledger stands when the post fails | Two tests: a `gh` that exits non-zero, and a runner that raises. In both, `summary.failures == 1` and the comment is baselined exactly as before. |
| **R2.5** exactly one notice | The integration scenario runs a third cycle and asserts the count is still 1. |
| **R2.6** no text from the reported comment | `test_the_notice_carries_no_text_from_the_comment_it_reports` (a hostile body), plus the signature test that makes it structural. |
| **R3.1–R3.4** nothing else about delivery changed | The pre-existing `session_missing` / transient-failure / dead-pane tests are untouched and green; `test_deliver_removes_both_temporary_files` and the two leak tests cover the tempfiles; `-d` on both pastes is asserted, and `tmux list-buffers` was empty after the live run. |
| **R4.1–R4.3** the regression is pinned | [`red.md`](evidence/red.md) — every new assertion failing against unfixed code, committed as its own commit before the fix. |

**Not claimed:** that the reporter's `client is read-only` line was observed here. This
machine has tmux 3.4, where the guard does not exist. What *is* shown is the guard's
presence in master and absence at 3.4/3.5a/3.6, the code path that makes `-t` irrelevant to
it, and the replacement working with a genuinely read-only client attached.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`interactive-sessions.md`](../../capabilities/interactive-sessions.md) | The delivery bullet now describes four commands rather than three, and a new bullet states the invariant behind them: **a delivery SHALL issue no tmux command that resolves a client**, so observing a session — read-only or not — SHALL NOT affect what can be delivered into it. | issue-240 |
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | New bullet beside the `polling.maxRetries` one: a comment the poller abandons SHALL be reported on the work item, ledger-first and best-effort, echoing no text from the comment it reports. | issue-240 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/cli/commands/sessions.md`](../../cli/commands/sessions.md) | Under `attach`: attaching read-only is safe to leave running, and why — with the version this became true and a link to the ticket. This is the page that recommends the flag, so it is the page that owed the reader the correction. |
| [`docs/config/cli/polling-options.md`](../../config/cli/polling-options.md) | Under `maxRetries`: what the give-up notice says and that posting is best-effort; and a closing paragraph tying it to the issue-146 upgrade re-arm, since a comment lost to a the-loop bug comes back by itself only if the reader knows both rules. |
| [`docs/config/cli/observability-options.md`](../../config/cli/observability-options.md) | Under `notifications.events.dispatch-failed`: the work item is told about an abandoned comment **independently** of this setting, so an operator who never wired notifications up is not left thinking the 😕 reaction is still all there is. |
| [`docs/decisions/decision-021.md`](../../decisions/decision-021.md) | Status marked **superseded in part**: "bracketed-paste injection" no longer ends in `send-keys Enter`. The decision itself stands; the one sentence that is now false says so and points here. |

`README.md`, the guide and the operating-model skill were checked and need no change:
grepping both trees for `send-keys`, `paste-buffer` and `maxRetries` produced no hits outside
the documents above and the historical `docs/specs/issue-32/` record, which is a per-work-item
artifact and is left as written.
