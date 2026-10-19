---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Final validation: Introducing the-loop gateway

> The `evidence` node's proof: what is presented to the user to show the acceptance
> criteria are met. **Summarised from the executed verification** — `testing-plan.md`'s
> Verification results, or `evidence/verification.md` when the plan was declared away —
> and mapped onto the acceptance criteria rather than re-derived. Raw captures
> (output, screenshots, recordings) sit beside this file under `evidence/`.

## Final validation evidence

Every activity of `testing-plan.md` ran on 2026-10-19 (its Verification results table;
nothing was left unexecuted). The review chain that followed — two self-review rounds,
one critic round, one security round, and the author's P0 amendment of R3.8 — changed
the code after that table was written; each round's record names its fixes, and the full
CLI suite was re-run green after each: 6353, 6356, 6366 passed, the last on `6da93cc`,
with CI `ui`, `gate` and `checks` green on the PR head.

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1 — one gateway process owns every inbound transport (GitHub and Jira webhooks, one Slack Socket Mode connection per app, the pollers, opt-in) | T1/T2: adapters stored under the providers' own contracts; T4: the author's Slack app, one connection for the life of the process; T11: `gateway start` hosts the enabled set, a config edit starts a poller without a restart | [`unit.md`](unit.md), [`integration.md`](integration.md), [`e2e-slack.md`](e2e-slack.md), [`manual.md`](manual.md) |
| R2 — events deposited on per-work-item subjects, durably, before any acknowledgement; nobody's event is held, not dropped | T2 scenarios: 202 after the write, the Socket Mode ack after `store.append`, a store failure withholds it; a held event routed by a later claim, binding or registration; T7: ack 0.03 s with 2 000 rows | [`integration.md`](integration.md) |
| R3 — an instance polls its own queue and commits what it handled; at-least-once, dead-letter, the in-flight cursor; what it hosts behind a gateway (as amended) | T1/T2 client scenarios (commit rides on the next fetch, redelivery with the attempt counted, in-flight not refetched, commit-undelivered dropped); T10: a block adds the client and drops only the Slack listener | [`unit.md`](unit.md), [`integration.md`](integration.md), [`migration.md`](migration.md) |
| R4 — many instances, one queue each; a second peer under a live name refused; a stopped instance finds its backlog in order | T2 `claims` scenarios (a driver and a reviewer each receive their own queue; a stopped instance's backlog in order); T8 abuse case 4; T7: a fifty-instance fetch is one index range | [`integration.md`](integration.md), [`security.md`](security.md) |
| R5 — every event reaches its consumers raw; routing by claim, then actor, else hold; bindings; the instance judges | T2 routing and claims scenarios; T8 abuse case 3 (an injected start keyword stored verbatim and dropped on the instance); the import-graph test | [`integration.md`](integration.md), [`security.md`](security.md) |
| R6 — the contracts are specified first: the OpenAPI document and the envelope schema | T3: served schema and authored contract in parity; every stored envelope validates against `components.schemas.Envelope` | [`contract.md`](contract.md) |
| R7 — every provider offers each transport side by side, with cross-transport dedup | T2: a webhook and a poll of one comment store one row; the poller's ids match the instance poller's; T7: 10 000 duplicates → 1 row | [`integration.md`](integration.md) |
| R8 — a separate, validated, hot-reloaded `gateway-config.yaml`, secrets by name only | T1 config tests (a pasted token fails naming the key; paths confined under `state.root`); T11: a bad edit keeps the previous config, a good one is applied; `make validate` on the template | [`unit.md`](unit.md), [`manual.md`](manual.md), [`lint-and-typecheck.md`](lint-and-typecheck.md) |
| R9 — the lifecycle and operability verbs | T11: `gateway start|stop|restart|status|subjects|instances` exercised on a real process, pidfile and logfile under the state root; `doctor slack` counts the gateway's connection | [`manual.md`](manual.md) |
| R10 — observability through the existing event log (`gateway.*`, `subject.*`), payloads never logged | T2 and T4 evidence quote the records; the catalogue test covers every emitted name | [`integration.md`](integration.md), [`e2e-slack.md`](e2e-slack.md) |
| R11 — the first landing leaves the door to replicas open (the `Store` seam) | design §Store, and the `Store` protocol the consumer API is written against; no replica built (out of scope, recorded) | [`../design.md`](../design.md) |
| R12 — the Slack Socket Mode path is proved end to end against the author's app | T4: all steps plus the mention re-run and the close on `the-loop-testing#7`, redacted; four defects found and fixed during it | [`e2e-slack.md`](e2e-slack.md) |
| R13 — records and documentation | `docs/capabilities/gateway.md` (and `instances.md`, `channels.md`), the `gateway` command and options pages, the guide `docs/guide/gateway.md`, decisions 144–146, learnings 015–016, the OpenAPI document; T12 lint green | [`lint-and-typecheck.md`](lint-and-typecheck.md) |
| R14 — a gateway and an instance share one machine | T2 loopback scenario (separate state roots and pidfiles, the client connects, a bound Slack thread lands on the gateway, no fallback when the gateway stops); T11 co-location checklist | [`integration.md`](integration.md), [`manual.md`](manual.md) |
| §Security — the eight abuse cases, fail-closed, the accepted gap | T8: the eight negative scenarios green; the security round's ten findings fixed; sign-off pending on the ticket | [`security.md`](security.md), [`security-review.md`](security-review.md) |
| UI — the Gateway card on the instance pane | T5/T9: 330 UI tests, five captured states, keyboard pass | [`ui.md`](ui.md), `ui/*.png` |

**Review chain:** [`self-review.md`](self-review.md) (2 rounds, 11 findings),
[`critic-review.md`](critic-review.md) (1 round, 3 findings),
[`security-review.md`](security-review.md) (1 round, 10 findings; tier-4 sign-off
requested). **Pull requests:** [`pull-requests.md`](pull-requests.md) — one, #499.
