---
type: execution-log
workItem: issue-128
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: portable state — what travels with the work, what belongs to the machine

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-31 | pending (PR) | A question ticket; the investigation *is* the requirements phase, so `requirements.md` answers all four questions up front and carries the classification as Analysis |
| design | 2026-07-31 | pending (PR) | Four reinforcing pieces: a declaration, a page, a `.gitignore` block, a test that holds the three together |
| tasks-breakdown | 2026-07-31 | pending (PR) | 8-task DAG |
| implementation | 2026-07-31 | pending (PR) | T1–T8 |
| needs-review | 2026-07-31 | **owner review received** | *"Do we need so many different files and folders? Can we consolidate?"* — returned to tasks-breakdown |
| tasks-breakdown (2) | 2026-07-31 | pending (PR) | R6/R7 + design §9; tasks T9–T16 |
| implementation (2) | 2026-07-31 | pending (PR) | T9–T16: the layout follows the classification |
| needs-review (2) | 2026-07-31 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#129](https://github.com/MadaraUchiha-314/the-loop/pull/129) | spec + T1–T16 | open |

## Progress entries

### 2026-07-31 — reading every writer under `state.root`

- **Phase:** not-started → requirements-definition
- **Did:** Traced each of the five generated paths to the code that writes it
  (`sessions/registry.py`, `control.py`, `poller/poller.py`, `eventlog.py`,
  `commands/gh_webhook.py`) and read what each one actually stores. The split fell out of
  the field lists rather than being imposed on them: two files hold *facts about the
  world* (what an authorized user armed; which comments have been seen) and three hold
  *handles to one machine* (a conversation id and an absolute `cwd`; an append-only local
  trail; a pid).

  Two findings the ticket did not ask about but that decide its answer:

  1. **Carrying `sessions/` is worse than losing it.** `find_by_work_item` counts a
     record as live whether or not the machine reading it made one, so a copied registry
     makes the duplicate guard refuse the spawn the new machine needs, and routes events
     to a conversation that is not there. The failure is silent — the work item looks
     armed and watched.
  2. **`poll-state.json` alone is not an answer.** It stops a thread being re-forwarded,
     but holds no record of what was armed. Carrying only it produces a quiet daemon that
     has forgotten what it was supposed to be running — and nothing upstream can rebuild
     that, because GitHub does not record that a `stop` was honoured.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** design, then T2 (the pin, red first).
- **Blockers:** none.

### 2026-07-31 — implementation complete (T1–T8)

- **Phase:** design → needs-review
- **Did:**
  - **T1** `GeneratedPath` + `GENERATED_PATHS` in `cli/the_loop/state.py`: five entries,
    each naming the `StateLayout` property it derives from, its documented default,
    whether it travels, what it holds and *why*. Inert data — nothing reads it at
    runtime.
  - **T2/T5** `cli/tests/test_state_portability.py`: S1 (every layout path is
    classified), S2 (every declaration resolves against the layout), S3 (the page
    classifies each one the same way), S4 (the published block is the one this repository
    uses), S5 (the block's patterns actually match the classification, via a small
    matcher modelling last-match-wins and the excluded-ancestor rule).
  - **T3** `docs/cli/state.md` — the file-by-file reference that did not exist: contents,
    field tables, lifecycles, what is lost if you delete each one, the hand-off
    procedure, the `~/.the-loop` case, the two costs, and the security section.
  - **T4** `.gitignore`: the three the-loop state blocks replaced by the published one.
    The pre-issue-106 `poll-state.json` blanket ignore went with them — it is the same
    file in its old location, and equally portable.
  - **T6** sidebar entry, pointers from `docs/cli/index.md`, `docs/cli/concepts.md` and
    the `state.root` option; *"All of it is git-ignored runtime state"* deleted.
  - **T7** `decision-046` + index row; behaviour bullet and history row in
    `docs/capabilities/cli.md`.
- **Checkpoint/tests:** `make check` green — ruff, markdownlint (306 files), `ruff format
  --check`, pyright (0 errors), config validation, **846 passed / 1 skipped**. No
  pre-existing test touched. `bun run docs:build` green.
- **Next:** PR briefing, then the tier-3 human gate.
- **Blockers:** none.

### 2026-07-31 — the owner asks whether the stores can be consolidated

- **Phase:** needs-review → tasks-breakdown (2)
- **Human decision (paper trail):**
  [PR #129 comment](https://github.com/MadaraUchiha-314/the-loop/pull/129#issuecomment-5139488802)
  — *"Do we need so many different files and folders? Can we consolidate the structures?
  … I don't see why anything other than poll-state.json needs to be persisted."*
  Answered on the PR, and the answer split in two:
  - **The stores are not redundant.** Session records and control records survive a
    daemon restart, are the IPC between the `sessions` CLI and the daemon (separate
    processes), and are not derivable from GitHub — nothing upstream records that a
    `stop` was honoured. Recorded in `requirements.md` § *Why each store exists*.
  - **The grouping was.** Three stores shaped by *who writes them* is what forced a
    two-negation `.gitignore` recipe and made "what is happening with #15?" a
    three-directory question.
  Asked the owner how to route the reorganisation (follow-up issue / this PR / explain
  only); the answer was **do it in this PR**. Requirements gained R6/R7, design gained
  §9, tasks gained T9–T16.
- **Checkpoint/tests:** the pre-review work was green and committed (`f2ebca5`).
- **Next:** T9 (the shared record), then the writers.
- **Blockers:** none.

### 2026-07-31 — the layout follows the classification (T9–T16)

- **Phase:** tasks-breakdown (2) → needs-review (2)
- **Did:**
  - **T9/T10** `the_loop/workitem.py`: one record per work item under
    `<state.root>/portable/`, two sections, read-modify-write per section.
    `ControlStore` keeps its API and delegates storage; `PollState` became
    directory-backed (lazy loads, dirty set, write-through `forget`).
  - **T11** the upgrade shim: a section absent from the new record is read from the
    pre-issue-128 location — and, for poll state, the pre-issue-106 one — then written
    forward. Never a destructive move; the new record always wins.
  - **T12** `StateLayout` now yields `portable_dir` + `local_dir` (with `LegacyLayout`
    beside it), `GENERATED_PATHS` is four entries, and the dispatcher, poller and
    `sessions`/`poll` commands were rewired. New flags: `sessions --portable-dir`,
    `poll --state-dir`.
  - **T13** `polling.stateFile` retired through the version-gated migration (schema
    `0.2.0` → `0.3.0`) — refused with the replacement named, removed by
    `migrate-config`.
  - **T14** `test_workitem.py` (11 cases) plus four migration cases; `test_state.py`
    rewritten; the poller/control/CLI suites moved to the new paths.
  - **T15** `docs/cli/state.md` rewritten around the new layout; decision-046 extended;
    capability docs, config pages, concepts and `upgrade-the-loop` updated.
- **Checkpoint/tests:** `make check` green — ruff, markdownlint (307 files), format,
  pyright (0 errors), config validation, **858 passed / 1 skipped**.
- **Next:** re-request review on #129.
- **Blockers:** none.

## Evidence

**Real git agrees with the recipe** (`git check-ignore -v`, re-run on the consolidated
layout against files created under `.the-loop/` and then removed):

| Path | Verdict | Matched by |
|---|---|---|
| `.the-loop/portable/github-octo-repo-15.json` | **tracked** | (no pattern matches) |
| `.the-loop/portable/tmp9k2f.tmp` | ignored | `.the-loop/portable/*.tmp` |
| `.the-loop/local/github-octo-repo-15.json` | ignored | `.the-loop/local/` |
| `.the-loop/logs/events.jsonl` | ignored | `.the-loop/logs/` |
| `.the-loop/gh-webhook.pid` | ignored | `.the-loop/*.pid` |

`git status --porcelain .the-loop` then showed exactly `?? .the-loop/portable/` — one
directory offered for tracking, everything local invisible.

**The pins bite** (each mutation applied, run, reverted):

| Mutation | Result |
|---|---|
| delete the pidfile entry from `GENERATED_PATHS` | S1 fails: `assert not ['pidfile']` |
| flip the control record to `portable=False` | 3 failures — the split assertion, S3 (docs disagree), S5 (the block tracks it) |
| drop `!.the-loop/sessions/poll-state.json` from `.gitignore` | S4 fails: the published block is no longer the one in use |

## Reviews

| Round | Type | Reviewer | Findings | Where fixed |
|-------|------|----------|----------|-------------|
| 1 | self | the-loop (implementing agent) | **1 finding, fixed.** The state page claimed *"Every file is JSON or JSONL, written atomically (`tempfile` + `os.replace`)"*. True of the three record stores; **false** of the other two — the event log is appended a line at a time and the pidfile is written once at startup. An operator reasoning about a torn file would have reasoned wrongly about exactly the file (`events.jsonl`) most likely to be truncated by a kill. Split the sentence into the three cases. | this PR |
| 2 | self | the-loop (implementing agent) | **1 finding, fixed.** R1.3 asks the page to answer the ticket's four questions *directly*; the draft answered them by construction — a reader had to assemble the answer from four sections. Added a short-answer callout at the top: the two paths to track, and a pointer to why the registry must not travel. Verified every claim about lifecycle against the code while re-reading: control records really are cleared when a work item ends (`dispatcher.py:649`), and the pidfile really is unlinked by `gh-webhook stop` (`gh_webhook.py:340`). | this PR |
| 3 | self | the-loop (implementing agent) | **1 finding, fixed.** The `docs:build` warned three times — *"The language 'gitignore' is not loaded, falling back to 'txt'"* — a warning this work item introduced, since no page used that fence before. Relabelling the block would have cost the fence its meaning on GitHub (and the test greps for it), so aliased `gitignore → ini` in `markdown.languageAlias` instead. Build is now warning-free. Also confirmed no round found the same thing twice, so `stopOnNoNewFindings` is satisfied without escalation. | this PR |
| 4 | self | the-loop (implementing agent) | **1 finding, fixed — a real defect in the upgrade shim.** The first shim consulted the old tree whenever a section was absent from the new record. But `ControlStore.clear` removes the control section *when a work item ends* — so on the very next question the stale `start` was read back out of `sessions/control/` and the finished item re-armed. A durable `stop` that undoes itself is worse than no shim at all. Fixed with a tombstone: a cleared section is written as an explicit `null`, and a record whose sections have all gone is left as `{"ref": …, "sealed": true}` — but only while the old tree still holds something for that item, so the normal case still deletes the file. | this PR |
| 5 | self | the-loop (implementing agent) | **1 finding, fixed — the first fix traded one silent failure for another.** Sealing the whole *record* (rather than the section) looked right until the ordinary upgrade sequence: the poll cycle usually touches a work item before any control command does, so the poller's own write hid the `start` still sitting in the old tree, and the armed item silently disarmed. Made the tombstone per **section**, and pinned both directions (`test_the_seal_is_per_section_not_per_record`, `test_ending_a_work_item_is_not_undone_by_the_old_tree`, `test_an_ended_item_stays_ended_across_a_restart`). | this PR |
| 6 | self | the-loop (implementing agent) | **No new findings.** Re-read the diff for the failure modes the reorganisation could introduce: two writers on one file (read-modify-write per section, pinned from the direction that hurts), a lazily-loaded ledger reporting a work item as known when it is not (`_read` never caches an absent item, so `is_known` stays false), `forget` being undone by a later flush (writes through, and clears the dirty flag), and the config gate refusing a valid file (only the removed key and a declared-stale version, as before). `stopOnNoNewFindings` is satisfied — no finding repeated, so no escalation. | — |
| — | critic | *(none configured)* | `reviews.critics[]` is empty in this repository's `.the-loop/harness-config.yaml`, so no critic harness is available to run (`the-loop critic run` has nothing to name). The tier-3 human PR review is the gate. | — |

## Decisions & conflicts

- **decision-046** — facts about the work travel; handles to a machine do not. Recorded
  in `docs/decisions/decision-046.md`.
- **Deliberate non-goal:** `/the-loop:init` does not manage a consuming project's
  `.gitignore`, and this work item does not change that. The manifest governs files
  the-loop owns; a project's `.gitignore` is user-owned, and the-loop's rule is to never
  clobber user-owned files. The block is published to be pasted, and is dogfooded here so
  it cannot rot.
- **No conflicts logged.**
