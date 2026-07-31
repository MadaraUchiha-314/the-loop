---
type: bugfix
phase: requirements-definition
workItem: issue-123
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
collaborators: [engineer, technical-writer]
overrides: {}
---

# Bugfix: the daemon takes `specDir` from the operator's machine, so a repo that moved its specs is silently skipped

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #123](https://github.com/MadaraUchiha-314/the-loop/issues/123) reports a live
instance of the defect class [issue #121](https://github.com/MadaraUchiha-314/the-loop/issues/121)
described and [decision-044](../../decisions/decision-044.md) named: **a repo-scoped fact
sourced from the operator's machine config**. Where a repository keeps its specs is that
repository's to declare, and on the daemon path it is not honoured — the operator's
`cli-config.yaml` always wins, and it wins *silently*.

## Current behaviour (the defect)

`spec_dir` has two sources that must agree, and the wrong one wins on the ingress path:

| Step | Code | Effect |
|---|---|---|
| 1 | `GraphLinkConfig.from_mapping` sets `spec_dir=str(data.get("specDir", "docs/specs"))` | **always** set — never empty, even when the operator configured nothing |
| 2 | `GraphLink._build_runtime` passes `spec_root=self.config.spec_dir` | the CLI-config value reaches the runtime as an explicit argument |
| 3 | `bootstrap.build_runtime` resolves `spec_root or workflow.get("specDir", "docs/specs")` | an explicit `spec_root` **overrides** the repository's own `workflow.specDir` |

Because step 1 never yields an empty string, step 3's fall-through is unreachable on the
daemon path: **there is no configuration under which a watched repository's
`workflow.specDir` is honoured.**

`GraphLink._guarded` then gates on `root / self.config.spec_dir / item_id`. For a
repository that sets `workflow.specDir: specs`, that directory does not exist, so the
coupling logs

```text
no docs/specs/issue-N under <checkout>; not advancing its graph
```

at **`logger.debug`**, returns, and the delivery still counts as a success. The graph
never advances, the entry hooks that write the `loop:<phase>` labels never run, and
nothing in `the-loop events` says why. This is the silent-inertness
[issue-113](../issue-113/) existed to remove, reintroduced one config key lower down.

### Why the documented workaround cannot be followed

`docs/config/cli/routing-options.md` currently instructs the operator to *"match
`workflow.specDir` in the repository's harness config"*. That instruction is
unfollowable by the daemon's actual users: `routing.graph.specDir` is **one flat value**
for every watched repository, and the daemon is explicitly designed to watch several
([decision-032](../../decisions/decision-032.md)). Two watched repositories with
different `specDir` values cannot both be served. The documentation describes a
workaround as if it were the design.

### Why the override exists

`build_runtime`'s docstring justifies passing both values as: *"The daemon passes both:
it has already parsed its own CLI config (honouring `--config`), so re-reading the
default path could disagree with the config the process is actually running."*

That reasoning is **correct for `authorized_users`** — a CLI-config value, where
re-reading the default path really could disagree with the config the running process
parsed. It was extended to `spec_root`, where it does not hold: `specDir` is a
harness-config value read from the work item's own checkout, and there is no `--config`
ambiguity to protect against. One argument covering two parameters with different
provenance is how the ⟵ direction leaked back in.

## Expected behaviour

Per decision-044's ⟶ direction: a repository's harness config may configure work done on
that repository. The work item's own `workflow.specDir` SHALL win on the daemon path, the
same way it already does for `the-loop check` and `the-loop graph`. The CLI key survives
as a **deliberate override** for a checkout that carries no harness config, rather than as
a default that always wins.

## Requirements

### Requirement 1 — the repository's `workflow.specDir` wins on the daemon path

**User story:** As an operator watching several repositories, I want each one's graph to
advance using the spec directory that repository declares, so that I do not have to pick
one repository's layout for all of them.

#### Acceptance criteria

1. WHEN a work item's checkout declares `workflow.specDir` in its harness config AND the
   operator has configured no `routing.graph.specDir` THEN the coupling SHALL resolve the
   spec directory from the **checkout**, and SHALL enter/advance the work item's graph
   there.
2. WHEN a work item's checkout declares no `workflow.specDir` (no harness config, or the
   key absent) AND the operator has configured no `routing.graph.specDir` THEN the
   coupling SHALL fall back to `docs/specs`, exactly as today.
3. WHEN the operator **does** set `routing.graph.specDir` THEN that value SHALL be used
   for every watched repository, overriding any `workflow.specDir` — the key stays as an
   explicit escape hatch, not as a silent default.
4. WHEN two watched repositories declare different `workflow.specDir` values THEN both
   SHALL have their graphs driven correctly in the same daemon process.
5. WHEN a repository uses the default `docs/specs` THEN its behaviour SHALL be unchanged
   — this fix strictly widens which repositories work.

### Requirement 2 — the skip decision and the runtime resolve the same path

**User story:** As a contributor, I want the directory the gate checks and the directory
the runtime writes into to be one value, so that a future edit cannot make them disagree.

#### Acceptance criteria

1. WHEN `GraphLink` decides whether to skip a work item for want of a spec directory THEN
   it SHALL resolve that directory **once**, and SHALL pass that same resolved value to
   the runtime it builds.
2. WHEN the resolved directory exists THEN the graph state file the runtime writes SHALL
   land under that same directory.

### Requirement 3 — a skipped work item is visible in `the-loop events`

**User story:** As an operator, I want to see that a delivery moved no graph and why, so
that a work item that is labelled, armed and spawned but inert is a question I can answer
from the event log instead of from a debug-level daemon log.

#### Acceptance criteria

1. WHEN the coupling skips a work item because its spec directory is absent THEN it SHALL
   emit one event-log record naming the work item, the action (`start` / `advance`) and
   the reason, at a level visible in `the-loop events` by default.
2. WHEN that record is emitted THEN its type SHALL be registered in
   `eventlog.EVENT_TYPES` with a description, so `the-loop events --types` documents it.
3. WHEN the delivery itself succeeds THEN it SHALL still count as a success — the record
   is diagnostic, and does not change the dispatch outcome.

### Requirement 4 — the checkout is proved to be the work item's before it is read

**User story:** As an operator, I want the daemon to keep reading a checkout only after
it has proved the checkout is the work item's own repository, so that resolving the spec
directory from the checkout does not widen what an unrelated directory can influence.

#### Acceptance criteria

1. WHEN the coupling resolves the spec directory from a checkout's harness config THEN it
   SHALL do so only **after** `_checkout_belongs_to` has proved via the `origin` remote
   that the directory is a checkout of the work item's repository.
2. WHEN the checkout does not belong to the work item's repository THEN no harness config
   there SHALL be read, and the graph SHALL not be driven — the existing fail-closed
   behaviour (issue-113 A6) is preserved verbatim.
3. WHEN a checkout declares a `workflow.specDir` that is absolute, or that resolves
   outside the checkout root, THEN the coupling SHALL refuse it and skip rather than
   drive a graph outside the checkout — a value read from a repository must not select a
   write target on the operator's machine outside that repository.

### Requirement 5 — the documentation describes the design, not the workaround

**User story:** As a CLI user, I want `graph.specDir` documented as the override it is, so
that I do not configure a value believing I have to.

#### Acceptance criteria

1. WHEN `docs/config/cli/routing-options.md` is read THEN `graph.specDir` SHALL be
   documented as an optional override whose default is unset, SHALL state that the
   repository's `workflow.specDir` is used when it is unset, and SHALL NOT instruct the
   operator to match it to a repository's harness config.
2. WHEN `.the-loop/cli-config.schema.json` is read THEN `routing.graph.specDir`'s default
   and description SHALL agree with (1).
3. WHEN `skills/the-loop/templates/cli-config.yaml` is read THEN its `graph` block SHALL
   not set `specDir` to a value that overrides every watched repository by default.
4. WHEN `docs/capabilities/process-graph.md` and
   `docs/capabilities/webhook-triggers.md` are read THEN they SHALL describe where the
   daemon takes the spec directory from, and SHALL carry an issue-123 history row.

## Security considerations

**Threat model (lite).** The asset is the operator's machine and the graph state of every
watched repository. The untrusted input is a repository checkout the daemon can reach, and
the values inside it.

- **Trust direction, restated.** This change moves one value from the ⟵ direction
  (a machine-scoped default configuring work on N repositories) to the ⟶ direction (a
  repository configuring work on itself). That is the direction decision-044 declares
  allowed, and it is the *narrower* of the two: `workflow.specDir`'s blast radius becomes
  the repository that declared it, where today one operator-level value silently governs
  all of them.
- **New abuse case: a hostile `workflow.specDir`.** The value is now read from a checkout
  and joined onto a path. A value like `../../../etc` or an absolute `/etc` would, without
  care, direct `GraphState.save` outside the checkout.
  - **Mitigated by ordering (R4):** the read happens only after `_checkout_belongs_to`
    proves via the `origin` remote that the checkout is the work item's own repository.
    So the only actor who can set it is someone who can already commit to that
    repository — the same actor who can already set `reviews.critics[]` (executable
    config, decision-043) and `.the-loop/graph.yaml`. It is not a new class of input.
  - **Mitigated by containment (R4.3):** the daemon path refuses a declared value that is
    absolute or resolves outside the checkout root, so the value can only ever select a
    directory *within the work item's own checkout* to write `graph-state.json` and read
    spec artifacts from. The check lives on the daemon path specifically, because that is
    where the-loop reads a repository it does not own; `check`/`graph` run inside the
    repository at the user's own invocation, where the value is already the user's.
  - **Failure mode is a skip, never an escalation.** The coupling's asymmetry is
    unchanged — **no input can move a work item forward**; a refused or missing `specDir`
    can only cause the gate to fail and the graph not to move.
  - **Not newly reachable:** `the-loop check` and `the-loop graph` already resolve
    `workflow.specDir` from the same checkout with the same trust, and have since
    issue-109. This change makes the daemon path consistent with them rather than
    introducing a new read. `harness_config.READS` already declares `workflow.specDir` as
    read by "check, graph, and the daemon via graphlink".
- **No change to the ⟵ direction.** `authorizedUsers`, `polling.sources[].repos` and every
  other ingress setting remain CLI-config-only with no fallback and fail closed. Nothing
  here gives a checkout a say in them.
- **The new event record discloses nothing new.** `graph.skipped` carries the work-item
  ref, the action and a fixed reason string — all values the event log already records on
  neighbouring `dispatch.*` records. No comment text, no payload, no credentials.
- **Risk tier: 3** (`autonomy.defaultTier`, and `autonomy.inferFromChange` does not lift
  it: no sensitive path is touched except `.the-loop/cli-config.schema.json`, whose change
  is a default and a description). `security.review.humanSignOffMinTier` is 4, so no named
  human security sign-off is required; the PR review is the tier-3 gate.
