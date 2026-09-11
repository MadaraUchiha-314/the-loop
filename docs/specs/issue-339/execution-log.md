---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#339"
phase: needs-review
status: in-progress
---

# Execution Log: the poller dies silently and every health surface reports OK

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`). An availability bug, not a confidentiality one: no new call, grant, token, scope or state, and the one boundary it touches — the loopback service's response body — gains two paths `GET /api/v1/config` already serves to the same callers. It does edit `cli-config.schema.json`, an `autonomy.sensitivePaths` entry, but only a `description`: no key added, removed or retyped. Brainstorming skipped — the ticket's five numbered asks are the requirement. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-11 | | [`bugfix.md`](bugfix.md) — five requirements, five abuse cases; root cause confirmed by reproduction, not inferred |
| design | 2026-09-11 | | [`design.md`](design.md) — six components, the anchoring rule, [`decision-119`](../../decisions/decision-119.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, ten applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-339-2rj3oh` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — every row, including the reporter's repro on a live service; [`evidence/security-review.md`](evidence/security-review.md) — five abuse cases |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#346](https://github.com/MadaraUchiha-314/the-loop/pull/346) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-11 — root cause found one layer below the ticket's

- **Phase:** requirements-definition → design
- **Did:** The ticket names `poller/daemon.py:396`'s config-less `_state_layout()`
  and the argv-only spawn at `client/__init__.py:109`. Both are real, but the defect
  under them is `state.py:360` — `layout_from_config` returns `StateLayout(root=".the-loop")`,
  a **relative** path that ~30 call sites each resolve against their own `cwd`.
  Reproduced in one line: the same config names `/repo/.the-loop/poll-status.json`
  from the checkout and `/tmp/.the-loop/poll-status.json` from `/tmp`. Fixing the
  poller alone would have left the session registry, the event log, the channels
  store and the work-item ledger on the same fault — the ticket itself notes the
  heartbeat is "the third file it has bitten". So the fix lands at the **load**
  boundary (`apply_state_root`, beside the existing `apply_integrations` /
  `apply_instance` passes), and the anchor is the config file's base directory,
  which is decision-108's `env.file` rule one directory out and moves no path for
  a setup that works today.
- **Escalations:** none. The five asks are unambiguous; the only judgement call —
  where a relative root anchors — is settled in decision-119 D2 against the
  "no silent state move" test.

### 2026-09-11 — implemented, and the first fix reproduced the bug it was for

- **Phase:** implementation → verification
- **Did:** tasks 1–6. `cli_config.py`: `config_base_dir`, `resolve_state_root`,
  `apply_state_root` (applied to the empty document too) and `child_env`;
  `load_cli_config` calls it. The three spawns (`client._spawn_service`,
  `lifecycle.spawn_service`, `core.daemons.control_daemon`) carry
  `THE_LOOP_CLI_CONFIG`. `routes.py`: health over `core_lifecycle.ingress_health`
  plus `configPath`/`stateRoot`, HTTP 200 preserved. `ingress.py`: starters return
  `(ingress, reason)`, `ingress.hosted_failed` at level error, and `_host` releases
  a lock whose loop ended on its own. `state.py`: `rival_roots`. `status` prints
  `config`/`state`/`conflict`. Docs: the anchoring rule in both schema copies, the
  state and config pages, the status page, the service page, a new
  [keeping it running](../../cli/supervision.md) page with the systemd unit, both
  capability docs, decision-119.
- **Checkpoint/tests:** red first — `test_state_root_integration.py` did not import
  against `48d1e8f`, then failed on the two-cwd assertion. `make check` green:
  3366 passed, 1 skipped; 0 type errors; 0 markdown errors. Two existing assertions
  changed, both to the corrected contract (see the evidence table).
- **Self-review:** three passes over the diff. Pass one found `rival_roots` calling
  `Path.home()` **outside** its `try` — it raises with no `HOME`, which is exactly
  where a daemon runs, so the function that promises never to fail `status` would
  have failed it; and `lifecycle_cmd._load_config` returning a bare `{}` for a
  missing config file, leaving `start`/`status` on a cwd-relative root while the
  daemon they spawn used the anchored one — this work item's own bug, in the verb
  that fixes it. Pass two confirmed `RunLock.is_held` has no side effects (health
  probes create no pidfiles) and that the injected root never reaches the
  operator's YAML (`core.config` reads with the raw parser and writes by splice).
  Pass three found the Slack listener's "not asked for" answer being reported as
  `ingress.hosted_failed` with an empty reason — a `read.mode: poll` configuration
  filed as a failure. All three fixed, each with its own regression test.
- **Then the manual repro found the one that mattered.** Started against a real
  service: `start` said `poller hosted (pid 17296)`, exit 0, health `ok` — while
  the poller was **dead**, because this box has no `gh` and its run loop returned
  during startup. Liveness is the lock, a hosted ingress holds the lock under the
  *service's* pid, and nothing released it: the reported outage, reproduced by the
  code written to catch it. `_host` now releases the lock of any hosted loop that
  ends without a shutdown — the discipline the Slack listener has had since
  issue-334, generalised — and the same run afterwards exits 1 with `poller failed`
  and answers `degraded`. R2.6 was added to the requirements to record it.
- **Out of scope, noted:** `test_graph_drive_integration.py` writes a portable
  record into the checkout's own `.the-loop/` (it builds a bare `RoutingConfig`,
  whose default layout is the cwd-relative one). Pre-existing — it leaks on
  `48d1e8f` too, and it is the same residue PR #336 had to clean up by hand. Not
  fixed here: it is a test-hygiene defect in another file, and mixing it into a
  bugfix about state roots would blur what this diff is for.
