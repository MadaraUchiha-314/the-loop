---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#532"
---

# Final validation: graph notifications on a gateway consumer post first time

> The `evidence` node's proof. Each acceptance criterion of `bugfix.md` is mapped to how
> the executed `testing-plan.md` proved it, summarised from its Verification results.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 — a graph runtime's config resolves `posting_path(...).kind == "gateway"` with a gateway block and no token | T1 `test_the_runtime_config_carries_the_gateway_block`: red on `main`, green with the fix | [unit.md](unit.md) |
| R1.2 — the gateway client calls under `instance.name` | T1 `test_the_runtime_config_carries_the_instance_name`; T2 asserts every gateway call carries `laptop-a` | [unit.md](unit.md) |
| R1.3 — the real `notify` hook delivers through the gateway on the first attempt, no `ChannelError`, outbox empty | T2 scenario: red on `main` with the ticket's "no bot token" error, green with the fix | [unit.md](unit.md) |
| R1.4 — no usable block → no gateway, behaviour unchanged | T1/T8 four negative cases (absent, `null`, non-mapping, empty URL) | [unit.md](unit.md) |
| R2.1 — regression tests fail before and pass after | red/green runs recorded | [unit.md](unit.md) |
| No regressions | T12: 6810 passed | [regression.md](regression.md) |
