---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#344"
phase: needs-review
status: in-progress
---

# Execution Log: lifecycle hooks — every recorded event is an attach point

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-12 | — | Tier 4 (`human-approves-pr` **and** a named human security sign-off): the change adds a CLI-config schema key (`**/*schema*`, `.the-loop/**`), a second surface that imports operator-declared Python into the-loop's process, and a shipped hook that makes outbound HTTP calls. Brainstorming skipped: the ticket states the ask and its three uses. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded on the ticket ([comment](https://github.com/MadaraUchiha-314/the-loop/issues/344#issuecomment-5647368146)) and every remaining phase is walked |
| requirements-definition | 2026-09-12 | | [`requirements.md`](requirements.md) — seven requirements, nine abuse cases |
| design | 2026-09-12 | | [`design.md`](design.md) — the event log grows a second consumer; seven decisions in [`decision-124`](../../decisions/decision-124.md) |
| test-planning | 2026-09-12 | | [`testing-plan.md`](testing-plan.md) — sixteen rows, eleven applicable |
| tasks-breakdown | 2026-09-12 | | [`tasks.md`](tasks.md) — ten tasks |
| implementation | 2026-09-12 | | On `claude/github-issue-344-vcp0e3` |
| verification | 2026-09-12 | | [`evidence/verification.md`](evidence/verification.md) — every applicable row ran; [`evidence/security-review.md`](evidence/security-review.md) — nine abuse cases, nine closed |
| needs-review | 2026-09-12 | | PR raised; awaiting the owner (tier 4: PR approval **and** a named security sign-off) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| *(see the ticket — linked on creation)* | tasks 1–10: the whole work item | open |

## Progress entries

### 2026-09-12 — the shape, settled before the spec chain

- **Phase:** phase-selection → requirements-definition → design → test-planning →
  tasks-breakdown
- **Did:** surveyed the existing hook surface (`routing.graph.hooks`, issue-248,
  decision-096), the event log (`EVENT_TYPES`, ~150 types, decision-025) and the event
  bus (decision-103), and the points the ticket names — work start, work finish, actions
  around work items, internal features. Every one of them is already an event the CLI
  records, and none of them is a node boundary. Settled the shape on that fact: **every
  catalogued event is an attach point**, declared under a new top-level `hooks` block of
  the operator's CLI config, using the graph hooks' decorator, loader, namespace rule and
  load-or-fail rule. Wrote the four artifacts.
- **Next:** implementation, red first.
- **Blockers:** none.

### 2026-09-12 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–10, red first (none of the three new suites collected against
  `c2fbeb2`).
  - `graph/extensions.py`: the loader takes a root, a config key, an error class and a
    root label (`load_module`, `_contained`, `read_modules`); every default is the old
    value, so the graph hooks' 47 tests pass unchanged.
  - `lifecycle_hooks.py` (new): `LifecycleEvent`, the declaration parser (catalog
    expansion at parse, shipped-name and shipped-params checks, the bare-YAML-`on`
    reading), the `SHIPPED` table with `forward-event`, and `LifecycleHooks` — load,
    per-event index, bounded queue, one lazily-started worker, the two anti-recursion
    guards, drop accounting, `drain`, `close` — plus `install`/`active`/`drain`/`reset`
    and the `atexit` drain.
  - `eventlog.py`: `EventLog.build`/`write`; sinks; module-level `emit` fans out to sinks
    whether or not the file is enabled, and keeps working for an emit-only double;
    `configure_from_file` installs the block; `reset` clears everything; three `hooks.*`
    catalog entries.
  - `commands/hooks_cmd.py` (new): `the-loop hooks [--format text|json]`, importing nothing.
  - Schema (both copies), this repository's config and the template (commented block).
  - Tests: 74 new (66 unit, 4 command, 4 integration), the abuse cases A1–A9 each a named
    negative test.
  - Docs: `docs/cli/hooks.md` (lifecycle section, the graph-vs-lifecycle table),
    `docs/config/cli/hooks-options.md`, `docs/cli/commands/hooks.md`,
    `docs/capabilities/lifecycle-hooks.md`, `decision-124`, index rows, sidebar entries,
    cross-references in `process-graph`, `observability`, the config index, the
    extending page, `graph.md`, the skill's configuration table and its observability
    reference.
- **Checkpoint/tests:** `make check` — **3575 passed, 1 skipped**; ruff, markdownlint
  (1097 files), format, pyright and config validation clean. See
  [`evidence/verification.md`](evidence/verification.md).
- **Self-review:** three passes over the diff.
  - **Pass one** (the code against the design) found three things. (a) `hooks.failed`
    could not carry the observed event under the field name `event`, because `emit`'s
    first parameter is `event` — the field is `on`, mirroring the attachment key, and the
    catalog says so. (b) A bare YAML `on:` key is the boolean `true`; every YAML example
    in the docs writes it bare, so the parser reads both, with a test. (c) The runtime's
    `dispatch` computed its return value from the overflow flag read *outside* the lock;
    it now returns a local decided inside it.
  - **Pass two** (the full suite) found the one real regression: `test_instance_integration`
    installs a log double with only `emit`, and the first `emit` called `build`/`write`
    on it. The seam now keeps the old contract for any object that offers only `emit`
    and builds the sinks' record the way the log would — a duck-typing fallback rather
    than a changed test, because a double that shape is a legitimate consumer.
  - **Pass three** (the docs against the code) corrected the sample `the-loop hooks`
    output (147 attach points, not a guessed 152), the design's "two catalog entries"
    that listed three, and the hooks page's first sentence, which still defined a hook as
    a thing at a node boundary; and it recorded that the runtime validator implements
    `type` lists rather than `oneOf`, which is why `on` is `type: [string, array]`.
- **Open judgements recorded for the reviewer:** the queue bound (1024) and the exit
  drain (5 s), both one-constant changes; and D3 — a bad declaration fails one-shot
  commands too, deliberately (design § Trade-offs).
- **Next:** the owner's review, and the named security sign-off tier 4 requires.
- **Blockers:** none.

## Verification results

> Recorded in [`testing-plan.md`](testing-plan.md) § Verification results and
> [`evidence/verification.md`](evidence/verification.md).

## Design critic review

> Not selected for this work item (`critics: []` in this repository's CLI config — no
> external critic is configured, so the self-review passes above are the review).

## Review cycles

| Round | Reviewer | Outcome |
|-------|----------|---------|
| self 1 | agent session | three findings, fixed (see the progress entry) |
| self 2 | agent session | one regression, fixed |
| self 3 | agent session | docs drift, fixed; zero new findings — stop |
| critic | — | none configured (`critics: []`) |

## Security review (gate)

Run as the-loop's checklist; recorded in
[`evidence/security-review.md`](evidence/security-review.md): nine abuse cases raised,
nine closed by named negative tests; no new authority; secrets by name, read at call
time; every fault fails closed. **Tier 4: the named human security sign-off is
outstanding** and lands with the owner's PR approval.

## Final validation evidence

[`evidence/verification.md`](evidence/verification.md) — red-first collection errors,
the 74 new tests, the 47 unchanged graph-hook tests, the 73 contract tests, the six
valid config files, `make check` at 3575 passed, and `the-loop check issue-344 --recompute`
at `WAIT` on `phase-selection` (the CI gate passes on `--fail-on block`).

## Capability docs

- [`docs/capabilities/lifecycle-hooks.md`](../../capabilities/lifecycle-hooks.md) — **new**:
  the capability's normative behaviour (attach points, declaration, contract, dispatch,
  shipped hooks, inspection and failure), with its history row.
- [`docs/capabilities/observability.md`](../../capabilities/observability.md) — one new
  *Current behaviour* clause (the catalog is also the attach-point vocabulary; sinks) and
  a history row.
- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — one clause
  under *A repository's own hooks* pointing a non-boundary need at the lifecycle hooks.
- [`docs/capabilities/capabilities.md`](../../capabilities/capabilities.md) — the index row.

## Documentation

- **Changed:** [`docs/cli/hooks.md`](../../cli/hooks.md) — the first sentence, a
  *Lifecycle hooks* section (write it, declare it) and the *Graph hook or lifecycle hook?*
  table. [`docs/config/cli/hooks-options.md`](../../config/cli/hooks-options.md) — new,
  every leaf with type and default. [`docs/cli/commands/hooks.md`](../../cli/commands/hooks.md)
  — new. [`docs/config/cli/index.md`](../../config/cli/index.md),
  [`docs/cli/commands/index.md`](../../cli/commands/index.md) and the VitePress sidebar —
  rows and entries. [`docs/config/index.md`](../../config/index.md) and
  [`docs/cli/extending.md`](../../cli/extending.md) — the "which config owns it" lists name
  the lifecycle hooks. [`docs/cli/commands/graph.md`](../../cli/commands/graph.md) — the
  `hooks` action points at its sibling. [`docs/decisions/decisions.md`](../../decisions/decisions.md)
  — decision-124. `skills/the-loop/SKILL.md` — the configuration table's *(lifecycle
  hooks)* row; `skills/the-loop/reference/observability.md` — the catalog is the
  attach-point vocabulary. `skills/the-loop/templates/cli-config.yaml` and
  `.the-loop/cli-config.yaml` — the commented `hooks` block.
- **Not changed, with the reason:** `README.md` — it names hooks only as the graph's
  checks and side effects in one line, which stays true; the operator-facing entry is the
  docs site's *Adding a hook* page, which changed. `docs/config/harness-config.md` — the
  harness config gains no key (the block is the CLI config's). The plugin's
  `hooks/hooks.json` — a different mechanism (Claude Code session hooks), out of scope by
  requirement.
