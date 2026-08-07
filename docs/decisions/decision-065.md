# Decision 065: The PDLC is two loops — pdlc-work-item-loop outside, pdlc-pr-loop per pull request

- **Status:** proposed
- **Date:** 2026-08-07
- **Deciders:** @MadaraUchiha-314 (PR #173 review — the loop names and the requirement are the owner's, verbatim)
- **Work item:** issue-172
- **Spec:** `docs/specs/issue-172/`
- **Refines:** [decision-041](decision-041.md) (the PDLC is an executable graph) and
  [decision-064](decision-064.md) (each PR is a session endpoint on the work item's
  record). 041 is unchanged in kind — there are now two declared graphs instead of one,
  executed by the same runtime; 064 built the substrate this decision runs on.

## Context

The owner's review of PR #173: *"Each PR will have to go through its own sub-graph of
things … We need to define the inner-loop graph and the outer-loop graph. Outer-loop
graph is for a work item. Inner-loop graph is for a PR with the understanding that it's
in service to delivery of a work-item. … It's basically the same loop but with some
steps skipped and some steps added. Let's try to represent these loops as pdlc-PR-loop
and pdlc-work-item-loop."*

The motivating case is a work item needing contributions to several repositories/
components: the outer loop must stop at *"brainstorming → requirements → design +
testing plan → task breakdown → **wait for tasks to be complete (inner loop start and
finish)** → testing (across all the PRs) → evidence"*, while each PR runs the same loop
restricted to its component.

## Decision

**Two shipped graphs, one runtime, one seam.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — two named graph files** | `pdlc.yaml` → `pdlc-work-item-loop.yaml` (content unchanged apart from D3); `pdlc-pr-loop.yaml` added; `Graph.name` carries the loop's identity; `load_graph(name=…)` selects | The owner's naming, verbatim — including leaving room for `pdlc-project-management-loop` later. Same compiler, same hook registry, same runtime: an inner loop is not a second engine. |
| **D2 — the inner loop is the same loop with steps skipped** | starts at `implementation`; keeps verification, the review chain (`security-review` still `required`), a human `pr-approval` gate, terminal `complete`/`escalated`. Skips everything before `implementation` | Requirements, design, the testing plan and the task DAG are the work item's — decided once, at the outer level. A PR re-deciding them would fork the spec. The PR's implementation node deliberately does **not** gate `tasks.md` checkmarks: those are the whole work item's, and one PR delivers a subset; the outer `implementation` still gates the full DAG. |
| **D3 — one seam: `await-inner-loops`** | the outer `implementation` node's exit gains the hook; it reads `docs/specs/<id>/pr-loops/*/graph-state.json` and `wait`s until each shows `complete`; no inner loops = vacuous pass | The owner's "wait for tasks to be complete (inner loop start and finish)", expressed the way every other gate is expressed — a hook over checked-in files. No registry, no GitHub, no network, so `the-loop check` in CI evaluates it identically to the daemon. The vacuous pass is what keeps every single-session work item — all of them, before this change — behaving exactly as before. |
| **D4 — state beside the outer state, artifacts shared** | inner state at `docs/specs/<id>/pr-loops/pr-<n>/graph-state.json` (`Runtime.state_subpath`); artifact gates keep resolving against the work item's spec dir | The state file's virtues (survives machines and sessions, reviewable in the diff, cache-never-authority) apply per PR unchanged. Splitting the *artifacts* per PR would fork the spec chain, which D2 exists to prevent. |
| **D5 — one-way flow: PR events never advance the outer loop** | the dispatcher advances the inner loop for endpoint deliveries and the outer only for work-item-session deliveries; the outer hears about inner loops only through D3's files | Without this, the first PR comment would walk the work item past gates the work item has not earned — the accident the two-loop split must make impossible, not just unlikely. |
| **D6 — merge completes the inner loop as an audited force** | `on_pr_close(merged=True)` forces the pointer to `complete` with the reason recorded; unmerged close leaves the pointer | A merge is the PR's approval, delivered as a GitHub state change rather than a classifiable comment. A force moves the pointer and never forges a verdict (issue-109 R10), so `check --recompute` still shows which inner gates never ran — the audit survives the convenience. Abandoned (closed unmerged) is not finished: the outer gate holding on it is the process noticing. |
| **D7 — every graph verb addresses either loop** | `--pr <n>` on `graph status/advance/complete/force/show`, `pr` on the API bodies and the OpenAPI contract, `pr_number` through core and bootstrap | An inner-loop session must be able to claim `the-loop graph complete --pr <n>` exactly as an outer session claims without it. Contract-first: the authored OpenAPI spec carries the field, not just the served schema. |

## What this deliberately does not do

- **No per-PR spec chain.** A PR contributes to the work item's one chain of artifacts.
- **No outer-loop restructuring.** The owner's outer sequence is the shipped graph's
  existing order; only the wait at `implementation` is new.
- **No `pdlc-project-management-loop`.** Anticipated by the naming; a future work item.
- **No repo-authored loops.** Both files ship with the CLI and a repo-supplied one is
  still ignored with a warning — user-defined graphs remain a future, deliberate feature.

## Alternatives considered

- **One graph with PR-conditional nodes** — branches inside `pdlc.yaml` guarded by "am I
  a PR?" flags. Rejected: two processes in one file, with every node's semantics
  depending on a mode bit; the owner asked for two *named* loops precisely to avoid this.
- **The inner loop advancing the outer's `implementation` node on completion** — a push
  edge instead of D3's pull. Rejected: it gives a PR write access to the work item's
  pointer, breaking D5's one-way flow; and the pull expression (a gate over files) is
  evaluable by `check` in CI, where a push edge would only exist at daemon runtime.
- **Completing a merged PR's loop via a synthetic approval comment** through
  `classify-feedback`. Rejected: it forges an authorized human utterance that never
  happened. The force records exactly what did happen — the pointer moved because the PR
  merged — and nothing else.
- **Gating the inner implementation node on `tasks.md` checkmarks** — rejected in D2; the
  per-PR task subset is not knowable from the shared DAG today. A per-PR task scoping
  vocabulary is a natural follow-up once the inner loop is in use.
