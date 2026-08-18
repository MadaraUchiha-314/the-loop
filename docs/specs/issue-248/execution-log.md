---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#248"
---

# Execution Log: a repository may bring its own graph hooks

Ticket: [#248](https://github.com/MadaraUchiha-314/the-loop/issues/248)

## Phase transitions

| Phase | Entered | Left | Notes |
|-------|---------|------|-------|
| requirements-definition | 2026-08-17 | 2026-08-17 | Read issue-109's deferred scope; risk tier set to 4 (repository code executes in the CLI process). |
| design | 2026-08-17 | 2026-08-17 | One seam at `load_graph(repo=…)`; append-only, `x-` namespace, no routing. decision-096. |
| test-planning | 2026-08-17 | 2026-08-17 | Matrix authored; one negative test per abuse case. |
| tasks-breakdown | 2026-08-17 | 2026-08-17 | Ten tasks, linear DAG. |
| implementation | 2026-08-17 | 2026-08-18 | Nine tasks: the collector, extensions.py, the graph/chain/bootstrap seams, config + schemas, the CLI action, docs. |
| verification | 2026-08-18 | 2026-08-18 | The testing plan executed and recorded; evidence committed under `evidence/`. |
| needs-review | 2026-08-18 | | Pull request opened; awaiting the human gate and the tier-4 security sign-off. |

## Pull requests

| PR | Repository | Scope | State |
|----|-----------|-------|-------|
| [#268](https://github.com/MadaraUchiha-314/the-loop/pull/268) | MadaraUchiha-314/the-loop | the whole work item | open |

## Progress entries

### 2026-08-18 — implemented, verified, and one bug found next door

The nine implementation tasks landed in one session. Three notes worth keeping:

**The extension point is one function.** `load_graph(repo=…)` already existed as the place
that says "a repository cannot define the process"; it is now also the place a repository's
hooks are read, loaded and appended. Every caller — `the-loop check`, every `graph` verb, the
daemon through `build_runtime`, the SDK through `core.graphs` — goes through it, so there was
no second wiring to keep in step.

**Tests were written alongside the code, not before it.** `tdd.mode: standard` asks for
red→green per task; what actually happened is that each module was written with its unit
tests in the same pass, and two of them did go red first (the `with: []` case in declaration
parsing, and the abuse-case-1 test, which initially proved the point with a stand-in hook and
was rewritten to use the real `validate-artifacts` gate). Recording that plainly rather than
claiming a discipline the session did not follow.

**A pre-existing bug, found and not fixed here.** `graph/bootstrap.py` reads the routing block
from `webhooks.ghWebhook.routing`, which issue-142 moved to the top level — so
`executeKeyword`, the `sessionPerPr` default and the `authorizedUsers` fallback all read from
a key that no current config has. The new `routing.graph.repoHooks` read deliberately uses the
**correct** top-level path, with a comment saying why it differs from the lines above it.
Fixing the older reads changes authorization behaviour and belongs to its own ticket
(reported separately); doing it inside this work item would have smuggled a security-relevant
change into a feature diff.

### 2026-08-17 — spec chain authored

Requirements, design, testing plan and tasks written in one session. The design question
worth recording: a repository's hooks execute **in the CLI process**, so the whole spec is
built around what a repository hook may *not* do — append-only, short-circuited behind every
shipped hook, and forbidden from declaring an outcome — plus an operator kill switch and a
no-import inspection command.

## Verification results

Executed 2026-08-18; the full record with commands and outcomes is in
[`testing-plan.md`](testing-plan.md) § Verification results, with evidence under
[`evidence/`](evidence/).

- `make test` — 2412 passed, 1 skipped (2405 before this change).
- `make lint` / `make typecheck` — clean.
- `scripts/validate_config.py` — all seven configs valid against the changed schemas.
- Manual: a hand-built repository's own hook blocked a node with its own message, passed once
  the source was fixed, and never ran behind a shipped gate that blocked first.

## Review cycles

**Self-review round 1 (2026-08-18).** Four findings, all applied:

1. `_load_one` re-derived the module path by splitting its own cache key — replaced with an
   explicit `target`.
2. `Attachment.params` used a `None` default with a `__post_init__` fix-up — replaced with
   `field(default_factory=dict)`.
3. `model.clear_cache()` was added and called by nothing — removed rather than shipped as
   dead code (`minimalism`).
4. A module whose hooks are attached to no node executed for no effect and said nothing —
   now warns, naming the unattached hooks.

**Self-review round 2 (2026-08-18).** One finding, applied: the requirements and design
described the in-process execution boundary without naming the concrete route an *agent* has
to it (write a hook module into a checkout it can already write). Both documents now say it
outright, and the residual risk is written up for the sign-off.

## Security review (gate)

Risk tier **4**. The agent's review is recorded in
[`evidence/security-review.md`](evidence/security-review.md): every trust boundary from
`design.md`, the mechanism holding it and the negative test proving it, plus two accepted
findings — the agent→daemon route into the CLI process, and `importlib.reload` of an
already-imported dotted module.

**A named human security sign-off is still required before this work item completes**
(`security.review.humanSignOffMinTier: 4`). Name and date to be recorded here.

## Capability docs

`docs/capabilities/process-graph.md` — new subsection for repository-provided hooks.

## Documentation

`docs/cli/extending.md`, `docs/config/harness-config.md`, `docs/config/cli/routing-options.md`,
`docs/cli/commands/graph.md`, `docs/decisions/decision-096.md`.
