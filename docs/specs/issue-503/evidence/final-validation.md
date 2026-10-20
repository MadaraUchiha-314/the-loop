---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Final validation: `read.mode: gateway`

Every acceptance criterion is met. The table maps each one to the executed verification
in [`testing-plan.md`](../testing-plan.md#verification-results):

- **[unit.md](unit.md):** T1 and T8 unit tests, 37 green here, 23 of them red on `origin/main`.
- **[integration.md](integration.md):** three T2 Gherkin scenarios.
- **[migration.md](migration.md):** T10 migration tests plus a real `migrate-config` run.
- **[lint-and-typecheck.md](lint-and-typecheck.md):** T11, the whole pre-commit suite.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 `gateway` is a read mode | parse keeps `gateway` beside a block; schema enum; migrated config validates | [unit.md](unit.md), [migration.md](migration.md) |
| R1.2 no Socket Mode in `gateway` | `enabled_services` matrix (6 configs); `channels listen` refuses | [unit.md](unit.md) |
| R1.3 no poll reader | `start_watcher` returns `None` | [unit.md](unit.md) |
| R1.4 gateway deliveries handled | a press through the client pipeline is recorded and the message rewritten | [integration.md](integration.md) |
| R1.5 reconciliation allowed | `poll_once` is not skipped under `gateway` | [unit.md](unit.md) |
| R2.1–R2.2 gates key on reachability | `interactive`, `command_buttons`, `kickoff_picker` on under `gateway` + grants, off without a grant | [unit.md](unit.md) |
| R2.2 buttons render | the Approve / Request changes pair renders on `phase-approval-pending` (red on main) | [integration.md](integration.md) |
| R2.3 press-time picker re-check | refused `unpublishable-event` once the block is gone | [unit.md](unit.md) |
| R2.4 unreachable → no buttons | `poll`/`off` beside a block: all three gates off | [unit.md](unit.md) |
| R3.1 fail closed without a block | resolves to `off`, error names both keys, nothing read, no buttons | [unit.md](unit.md), [integration.md](integration.md) |
| R3.2 `channels status` says why | `[!] read.mode is gateway but no gateway block…` | [unit.md](unit.md) |
| R3.3 a socket only on explicit `socket` | `enabled_services` matrix: only `socket` with no block enables the listener | [unit.md](unit.md) |
| R4.1 20.3.0 form keeps working | listener off, interactivity on | [unit.md](unit.md) |
| R4.2 warned in log and status | gateway client starter warning; `[!] read.mode is socket beside a gateway block` | [unit.md](unit.md), [migration.md](migration.md) |
| R4.3 `channels listen` refuses beside a block | exits 1 for `socket` and `gateway`, no token variable read | [unit.md](unit.md) |
| R4.4 never refused at load | `assert_current` does not raise | [migration.md](migration.md) |
| R5.1–R5.3 migration | rewrite reported and validated; idempotent; no-op without a block; `needs_migration` | [migration.md](migration.md) |
| R6.1 `channels status` in gateway mode | `read: gateway — …`, buttons/commands/mentions/shortcuts "through the gateway", no app-token step | [unit.md](unit.md), [migration.md](migration.md) |
| R6.2–R6.3 `status` agrees | `off · gateway configured` in gateway mode; the missing-block detail without one | [unit.md](unit.md) |
| NFR behaviour preserved | full suite green (6,400+ tests) | [lint-and-typecheck.md](lint-and-typecheck.md) |
| NFR documentation | schema, template, guides, option docs, capability docs | [documentation.md](documentation.md) |
