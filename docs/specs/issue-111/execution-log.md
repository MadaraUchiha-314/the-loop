---
type: execution-log
workItem: "issue-111"
phase: needs-review
status: in-progress
---

# Execution Log: the registry lists the files it wrote (issue-111)

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-111/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-29 |  | Issue #111: `list_sessions` reports `.the-loop/sessions/poll-state.json` as a corrupt registry entry on every listing. |
| design | 2026-07-29 |  | Name-aware directory scan: the registry recognises the `<slug>.json` files `_write` produces (superset pattern) and skips neighbours at `debug`. The issue-106 layout is unchanged. |
| tasks-breakdown | 2026-07-29 |  | 6-task DAG |
| implementation | 2026-07-29 |  | Implemented on `claude/github-issue-111-n2atcv` |
| needs-review | 2026-07-29 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#112](https://github.com/MadaraUchiha-314/the-loop/pull/112) | T1–T6 (whole work item) | open |

## Progress entries

### 2026-07-29 — reproduced, spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Reproduced the reported warning against the current code in three
  lines (register a session, drop a `poll-state.json` beside it, list) — the
  listing returns the session *and* logs
  `skipping unreadable registry file …/poll-state.json: 'workItem'`. Traced it to
  `registry.py:247` globbing `*.json` and handing every match to
  `Session.from_dict`, whose `data["workItem"]` raises `KeyError` into `_read`'s
  corruption handler. Established the frequency: `Poller._reconcile_closures`
  calls `list_sessions` once per provider per cycle (issue-94), so it is the
  daemon's steady-state log line, and `sessions list` shows it too. Framed the
  root cause as **structural** — issue-106 made `<root>/sessions/` shared
  session-related state (poll state beside the registry files, control records in
  a subdirectory), while `list_sessions` still assumes it owns the directory, so
  blocklisting `poll-state.json` would only defer the next occurrence. Confirmed
  the blast radius is limited to the scan: `find_by_work_item` addresses files
  through `_path_for` and every mutator routes through it; `*.tmp` files from the
  atomic write and the `control/` subdirectory are already outside the glob;
  `grep -n 'glob(' cli/the_loop/` shows this is the only directory scan.
- **Checkpoint/tests:** reproduction script, run against `main`: 1 session listed,
  1 spurious warning.
- **Next:** implement T1–T6.
- **Blockers:** none. Human approval of spec + code happens at the PR (tier-3,
  `human-approves-pr`).

### 2026-07-29 — implemented (T1–T5)

- **Phase:** implementation → needs-review
- **Did:**
  - `sessions/registry.py`: module-level `_REGISTRY_FILE_RE`
    (`[A-Za-z0-9._-]+-\d+\.json`, applied with `fullmatch`) and a `debug`-level
    skip in `list_sessions` before `_read`. The comment records *why* the pattern
    is a deliberate superset of what `_write` produces rather than a
    reconstruction of the slug: the unsafe failure direction is excluding a real
    session, so the check is weaker than the writer on purpose. Module docstring
    and `list_sessions` docstring now state that the directory is shared.
    `_read`, `find_by_work_item` and every mutator are untouched.
  - Tests (`cli/tests/test_routing.py`): the neighbour regression
    (`test_registry_ignores_files_it_did_not_write`), the corruption case
    tightened to assert the warning **is** still logged for registry-named files
    (renamed from the old `garbage.json`, which after this change would have
    exercised the skip path rather than the corruption path it is named for, plus
    a valid-JSON-without-`workItem` file), and a parametrised round-trip over
    every ref shape the registry can write — driven from `WorkItemRef.slug`, so a
    future change to the naming rule fails the suite instead of silently hiding
    sessions.
- **Checkpoint/tests:** the regression **fails before** the change on its log
  assertion (`assert not [<LogRecord: the-loop.sessions, 30, …"skipping
  unreadable registry file %s: %s">]`) and passes after. Full gate green from the
  repo root — see *Final validation evidence*.
- **Next:** PR + reviewer briefing; await human approval (tier 3).
- **Blockers:** none.

### 2026-07-29 — spec named for the runtime, not the prose

- **Phase:** needs-review
- **Did:** The requirements artifact is `requirements.md`, not `bugfix.md`. The
  workflow reference offers `bugfix.md` for bugs, but the **shipped process
  graph** — the thing CI actually runs (`the-loop-gate.yml` →
  `the-loop check --recompute --fail-on block`) — declares
  `requirements-definition` as `produces: [requirements.md]`, so a `bugfix.md`
  spec blocks the gate with "required artifact is missing". Verified against the
  merged issue-104: `the-loop check issue-104 --recompute` blocks for exactly
  that reason today. Named the file for the runtime and kept `type: bugfix` in
  its front-matter, and shaped the headings the graph's `validate-artifacts`
  hooks require (`Requirements`, `Security considerations`; `Architecture`,
  `Security design`, `Testing strategy`; `Task list`).
- **Checkpoint/tests:** `the-loop check issue-111 --recompute --fail-on block` →
  exit 0 (`WAIT requirements-approval`, the expected state for an open PR).
- **Next:** flagged in the PR body as a **separate** defect worth its own work
  item — the graph accepts only `requirements.md` while `workflow.md` and
  `create-ticket` still offer `bugfix.md`, and the shipped `execution-log.md`
  template has no `Capability docs` section though the `capability-docs` node
  asks for one. Not fixed here: out of this work item's scope.
- **Blockers:** none.

## Review cycles

| Cycle | Type | Finding | Outcome |
|-------|------|---------|---------|
| 1 | self | Is a filename filter safe, or could it hide a live session? Checked the writer: `_write` names every file `f"{item.slug}.json"` and `WorkItemRef.slug` always ends `-<number>` after sanitising to `[A-Za-z0-9._-]`, so the pattern is a strict superset and cannot exclude a written file. Pinned it with a parametrised test driven from `slug` rather than literal names. | resolved in the implementation |
| 2 | self | Content sniffing (`"workItem" in data`) would be simpler — but it re-conflates *not mine* with *mine and corrupt*, which is the bug. Kept the check on the name, before the file is opened. | accepted as designed |
| 3 | self | The existing `test_registry_skips_corrupt_file` wrote `garbage.json` — not a registry-shaped name, so after this change it would silently have started testing the new skip path while still claiming to cover corruption. Renamed its fixtures to registry-shaped names and added an explicit assertion that the warning fires, so the two paths can no longer be confused. | resolved in the implementation |
| 4 | self | Should the poll state simply move back out of `sessions/`? No — that reverses issue-106's consolidation and risks re-baselining every watched thread on upgrade (`resolve_poll_state_path` exists for exactly that hazard). Recorded as out of scope. | confirmed, no change |
| 5 | self | Does the work item pass the-loop's own shipped gate? It did not: `bugfix.md` blocks `requirements-definition`. Renamed and re-shaped the spec, and recorded the underlying graph/prose mismatch as a separate defect. | resolved in the implementation |

Critic review (`reviews.criticReviewCount`): no second harness/model is
configured for this repository (`reviews.critics: []`), so the critic rounds are
recorded as not-run rather than silently claimed.

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no
  security-review skill invoked for a change of this shape).
- **Outcome:** pass.
- **Human sign-off:** n/a — tier 3, below `security.review.humanSignOffMinTier: 4`.

The boundary at issue is *what the daemon accepts as a routing record*: a session
file decides which cwd and which harness session id an event is dispatched to, so
the registry directory is trusted local state. This change **strictly narrows**
what is read — fewer files are considered, and only ones shaped like those the
registry itself writes — so nothing previously rejected becomes accepted and no
new dispatch target can be introduced. The dangerous direction for a filename
filter is the opposite one (excluding a real session, which would leave a live
work item invisible to reconciliation); the pattern is a superset of what
`_write` produces and the AC1 test asserts that property from `WorkItemRef.slug`
itself, so a future change to the naming rule breaks the suite rather than the
daemon. The check is an anchored `fullmatch` over a filename with no alternation
or nested quantifiers (no catastrophic backtracking) and no user-supplied
pattern, and it runs *before* the file is opened — the net effect is one fewer
JSON parse, not a new parser. No network, subprocess, credential, config key,
dependency or file is added. The security-relevant half of the fix is log
integrity: keeping the "unreadable registry file" warning for registry-named
files (AC4, asserted by `test_registry_skips_corrupt_file`) is what makes a
tampered or truncated session record visible, and it only stays visible once the
benign per-cycle false positive is gone. Abuse cases covered by tests: a file
that is not registry-named is never read as a routing record, and a
registry-named file that fails to parse is never silently dropped. Anyone able to
write into the registry directory already has arbitrary local write access to the
daemon's state and gains nothing from a filename.

## Capability docs

Updated in this same PR:

- `docs/capabilities/cli.md` — the `<root>/sessions/` directory is **shared**
  session-related state; a listing considers only the files the registry wrote,
  and the corrupt-entry warning is reserved for those. History row added.
- `docs/capabilities/webhook-triggers.md` — the same statement on the routing
  side, where the registry is the dispatch target store. History row added.

No new capability doc was minted and no decision record was written: this is a
defect in the implementation of decision-040's one-root layout, not a revision
of it.

## Final validation evidence

- **Red → green (AC6):** `uv run --project cli python -m pytest -q
  cli/tests/test_routing.py -k "registry_skips_corrupt or
  ignores_files_it_did_not_write or lists_every_name"` — before the fix,
  `1 failed, 5 passed`, failing on
  `assert not [<LogRecord: the-loop.sessions, 30, …skipping unreadable registry
  file…>]`; after the fix, `19 passed` across the whole registry suite.
- **Full gate (`make check`, the same tools CI runs):** `ruff check` — all checks
  passed; `markdownlint` — 254 files, 0 errors; `ruff format --check` — 98 files
  clean; `pyright` — 0 errors, 0 warnings; `validate_config` — 6 VALID; `pytest`
  — **722 passed, 1 skipped**.
- **the-loop's own gate:** `uv run the-loop check issue-111 --recompute
  --fail-on block` → exit 0 (`WAIT requirements-approval`).
