---
type: execution-log
workItem: issue-135
phase: needs-review
status: in-progress
---

# Execution Log: change the default session-control comment keywords

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | tier-3 gate: PR review | Scope is unambiguous — the issue names the exact before/after values; no open question to escalate. |
| design | 2026-08-04 | tier-3 gate: PR review | One value, mirrored to config/schema/template, cited by docs, asserted by tests. No parser change needed — the boundary regex already treats a space as a valid token edge. |
| tasks-breakdown | 2026-08-04 | tier-3 gate: PR review | 8-task DAG, T1 (runtime default) gating everything downstream. |
| implementation | 2026-08-04 | | Done — see Progress entries. |
| needs-review | 2026-08-04 | | PR opened; tier 3 (`human-approves-pr`) — waiting on the named human approval. |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (opened by this session) | T1–T8, full scope | open |

## Progress entries

### 2026-08-04 — spec written, implementation applied

- **Phase:** implementation
- **Did:** Locked requirements/design/tasks (T1–T8 planned). Applied T1
  (`cli/the_loop/control.py` `DEFAULT_KEYWORDS` + docstring), T2 (`.the-loop/cli-config.yaml`,
  `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.schema.json`),
  T3 (`cli/tests/test_control.py` defaults + reshaped boundary cases), T4
  (`cli/tests/test_control_integration.py`, `cli/tests/test_poller.py` keyword
  constants), T5 (living docs: `docs/config/cli/routing-options.md`,
  `docs/capabilities/webhook-triggers.md`, `docs/cli/concepts.md`,
  `docs/cli/getting-started.md`, `docs/cli/commands/sessions.md`,
  `cli/README.md`, `skills/the-loop/reference/automation.md`,
  `commands/upgrade-the-loop.md`). Historical specs (issue-106/117/119),
  decision-040 and the published CHANGELOG entry left untouched by design
  (Requirement 2.2).
- **Checkpoint/tests:** `make check` (ruff, markdownlint, ruff format --check,
  pyright, config validation, full `pytest cli`) — 969 passed, 2 skipped,
  0 lint/type/format/schema issues. See Final validation evidence below.
- **Next:** PR opened; wait for the tier-3 human approval.
- **Blockers:** none.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable**.

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | this session | zero — see PR description | (PR) |

## Security review (gate)

- **Mechanism:** the-loop checklist (no built-in security-review skill run — the change is a
  string-literal default with no new code path; see `requirements.md`'s Security
  considerations for the threat-model-lite).
- **Outcome:** pass — no new trust boundary; the one noted risk (an authorized
  user's own prose accidentally matching `the-loop start`) is self-inflicted,
  low-severity, and mitigated by the existing `keywords` override.
- **Human sign-off:** n/a (tier 3, below `security.review.humanSignOffMinTier` default of 4).

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) —
  current-behaviour prose updated to the new default keywords; history row added
  for issue-135.

## Final validation evidence

- `ruff check` / `ruff format --check`: clean.
- `pytest cli/tests` (full suite, in particular the control/poller suites):
  green.
- Full-repo grep for the four old default strings confirms only
  intentionally-historical files (prior specs, decision-040, the already-published
  CHANGELOG entry) still contain them.
