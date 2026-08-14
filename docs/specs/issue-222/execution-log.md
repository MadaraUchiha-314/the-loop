---
type: execution-log
workItem: issue-222
phase: needs-review
status: in-progress
---

# Execution Log: the CLI config is editable from the Control Plane UI

> Append-only log for issue-222. Ticket:
> [#222](https://github.com/MadaraUchiha-314/the-loop/issues/222).

## How this session ran the loop

One cloud session, one pass, no human at the other end — the same posture as
issue-208/209/211/217/220, with the same two consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started by the ticket
   itself; there was nobody to tick the checklist. Phases assumed: the full spec chain,
   implementation, verification, self-review. `brainstorming` was not taken (the ticket
   states the problem and the answer in four bullets) and neither was the opt-in
   `design-critic-review` — no second model was available to this session.
2. **The chain was authored before the code, but approved by nobody.** The artifacts are a
   proposal to ratify, not a locked chain; `status: draft` on all four says so. Risk tier
   **4** means this PR needs a human approval *and* a named human security sign-off before
   it is complete — see `requirements.md` §Risk tier.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-14 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-14 | | [`requirements.md`](requirements.md) — 5 requirements, 5 NFRs, 5 abuse cases, risk tier **4** (a new write path into executable daemon config) |
| design | 2026-08-14 | | [`design.md`](design.md) — three routes, one core module, two primitives, a schema-driven form |
| test-planning | 2026-08-14 | | [`testing-plan.md`](testing-plan.md) — 12 rows in scope, 4 `n/a` with reasons |
| tasks-breakdown | 2026-08-14 | | [`tasks.md`](tasks.md) — 14 tasks |
| implementation | 2026-08-14 | | 14 tasks; two new primitives (`yamlpatch`, `configschema`), one core module, three routes, the schema-driven editor |
| verification | 2026-08-14 | | Testing plan executed in full: 72 new Python tests, 34 new UI tests; whole suite 1965 passed + 1 skipped; lint, format, types, markdownlint and config validation clean |
| needs-review | 2026-08-14 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/gallant-hopper-c7su5v` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-14 — orientation

Read the ticket, `CLAUDE.md`, the harness config, the skill and the issue-220 chain for
conventions, then mapped the four bullets of the ticket onto what exists:

- **"Expose an endpoint to update cli-configs."** The control plane already has the
  facade/router/MCP arrangement (decision-058); the missing piece is a `core/config.py`
  and three routes over it. What it does *not* have is a safe writer — the config is
  ~270 lines of which about half are comments, and a PyYAML round trip deletes all of
  them. That, not the routing, is where the work is.
- **"Use this endpoint from the Control Plane settings UI."** The Settings tab today
  configures the browser, not the daemon.
- **"The configs change already hot reloads (verify this happens through the API update
  path as well)."** It does for the *daemons* — `Reloader` content-hashes the file, so any
  writer inherits it. It does **not** for the service, which captures its config at
  `create_app()`. That gap is R4.2/R4.3 and is fixed by giving the service the same
  primitive its daemons use.
- **"Divide the configs into logical portions… use the nesting."** The schema already has
  the nesting *and* the prose. Rendering the form from the schema answers the bullet and
  removes the second source of truth a hand-written form would create.

Two decisions were larger than the code they produced, and both are recorded in
`design.md`: the schema becomes package data (a UI and a validator must work from a bare
`pip install`, the argument `graph/model.py::shipped_graph_path` already makes for the
process graphs), and the validator is ours rather than `jsonschema`'s, guarded by a
keyword test and a differential test against the real implementation.

### 2026-08-14 — building it

Order: the two primitives first (they carry the risk), then core, then the routes, then
the UI. Three things came out of building rather than out of designing:

1. **A container's `end_mark` overshoots.** PyYAML's composer puts a block sequence's end
   *after* the comments that trail the block, so the first working splice ate an
   operator's comment. Containers are now measured to their last leaf
   (`yamlpatch._content_span`), and flow containers — which are bracket-delimited and do
   not overshoot — use their own marks. The verification step is what turned this from a
   silent corruption into a caught bug.
2. **A patch leaf of `null` had to mean "remove".** The requirements first said key
   removal was out of scope, and the UI's JSON fields then had no way to express one: an
   operator deleting an entry from `notifications.events` would have watched it come
   straight back on the next read, because a merge cannot remove. R2.6 was added rather
   than shipping a control that lies. `null` is unambiguous here — no key in the-loop's
   schemas is typed to accept it.
3. **The editor needed a baseline of its own.** Measuring the draft against the `document`
   prop left the form reporting "1 section changed" after a save had already landed. It
   now measures against what the service last said the file holds, and remounts the field
   tree on save/discard so the JSON controls settle too.

`test_config_schema_parity.py` was written before the copy under `cli/the_loop/schemas/`
had a reason to drift, on purpose: the parity test is the whole argument for allowing a
second copy at all.

### 2026-08-14 — verification

`testing-plan.md` executed in full; results and evidence in
[`evidence/verification.md`](evidence/verification.md). 72 new Python tests (1893 → 1965)
and 34 new UI tests (55 → 89); lint, format, types, markdownlint (632 files) and config
validation clean.

One row is honest about what it did not do: **T16 did not start a poller or a receiver.**
The service, the dashboard and the file were exercised for real (Playwright against
`the-loop service start` and the built bundle), and R4.1 — "the daemons pick the change
up" — is carried by a test that holds the very `Reloader` object they hold, not by a
manual daemon run.

### 2026-08-14 — self-review

One reviewer, this session, reading the diff against the requirements rather than against
what it meant to write. `reviews.selfReviewCount` is 3 and
`reviews.criticReviewCount` is 3; **one self-review round ran and no critic round did** —
`reviews.critics` is empty in this repository and no second model was reachable from this
session. That is a gap in the loop this PR walked, not a claim that the code was reviewed
three times.

Four findings, all fixed in this branch:

1. **A symlinked config would have been replaced by a regular file.** `os.replace` on the
   link, not through it. An operator who symlinks `~/.the-loop/cli-config.yaml` into a
   repository would have lost the link on the first save. Now resolved and written through,
   with a test.
2. **An empty patch created a file on a machine that had none** — the `version` stamped for
   a first save counted as a change. R2.5 says an empty patch writes nothing; it does now.
3. **"Unset" in the UI could send a value the schema refuses.** The enum chooser's blank
   option sent `""` and a cleared number sent `undefined`, which `JSON.stringify` drops —
   so the key silently kept its old value. Both send `null` now, which is the removal the
   operator meant.
4. **The editor reported a change it had already saved** (see the previous entry).

## Capability docs

- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — six new
  behaviour clauses (the three routes and their resolution rule; splice-not-reserialize
  and the three gates before any write; hot reload plus `restartRequired`; the
  `config.updated` trail and the MCP exclusion; the schema-derived Settings tab), and a
  history row for issue-222.

## Documentation

- [`docs/config/cli/index.md`](../../config/cli/index.md) — a new **Editing it from the
  dashboard** section: this file is no longer hand-edit-only, comments survive a save, and
  which keys wait for a restart.
- [`docs/cli/commands/service.md`](../../cli/commands/service.md) — the API-surface
  paragraph now names the config routes and what the write path guarantees.
- [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) —
  the Settings row of the "where the screens get their data" table, plus a paragraph on
  the one screen that renders itself from a schema.
- [`docs/decisions/decision-081.md`](../../decisions/decision-081.md) — new, indexed in
  `decisions.md`.
- **Not changed, with the reason:** `README.md` (front page, describes the loop rather than
  the dashboard's screens), the skill and its `reference/` (this is CLI/daemon
  configuration, not the PDLC process), and `CHANGELOG.md` (generated by commitizen at
  release from the commit subject — hand-editing it would be overwritten).
