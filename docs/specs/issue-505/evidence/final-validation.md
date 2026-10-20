---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Final validation: the gateway learns a work item's collaboration channel

Every acceptance criterion on the ticket is proved by a test that ran and passed, and the
new tests were red on `origin/main`. This is summarised from `testing-plan.md`'s
Verification results. The full suite, lint and types pass
([lint-and-typecheck.md](lint-and-typecheck.md)).

## Final validation evidence

| Acceptance criterion (ticket #505 → requirements) | How it was proved | Where |
|---------------------------------------------------|-------------------|-------|
| A top-level message from any user in a declared room routes `by: "claim"` to the work item's claimants; the author's actor registration plays no part (R2.1, R2.2) | T2 scenario 1: U_COLLAB, registered by no instance, posts in C0123ABCD; the gateway records `subject.routed … by: "claim"` onto `loop-github-o-r-14`, and laptop-a is handed the event | [integration.md](integration.md) |
| Messages held in the channel before the binding arrived are routed when it arrives (R3.1–R3.3) | T2 scenario 2 (two held mentions routed in order); unit drain cases; critic C1 (a thread binding's event stays put) and C2 (a room published mid-ingest still routes) | [integration.md](integration.md), [unit.md](unit.md) |
| Ending the work item, or removing the declaration, retracts the binding; later messages are held or resolved as before (R4.1–R4.4) | T2 scenario 3 (`clear` → room gone → next message `unassigned`/`hold`); unit move and retract cases; `test_retraction_reaches_the_gateway` | [integration.md](integration.md), [unit.md](unit.md) |
| A gateway restart followed by instance re-registration restores the channel bindings (R1.4) | T2 scenario 4: a fresh store; laptop-a re-registers, the room is back, and a message routes by claim | [integration.md](integration.md) |
| Who may act is unchanged: the instance still applies `channels.slack` principals, `routing.authorizedUsers` and the roster (R6.1) | the gateway hands over the raw payload with its author (T2 scenario 1, abuse case 4); the instance's Slack pipeline is unchanged by this diff | [integration.md](integration.md), [security-review.md](security-review.md) |
| One room, one instance: a live holder keeps its room, and an instance retracts only its own (R5) | unit abuse cases 2 and 3; `duplicate-room` reported by `PUT /rooms`; critic C4 (a refused room is taken once the holder lets go) | [unit.md](unit.md) |
| The new operation is in the contract (NFR) | `test_api_contract_parity.py`: `PUT /api/v1/gateway/rooms` (`gatewayPublishRooms`) | [contract.md](contract.md) |
| An existing store opens without a manual migration (NFR) | T10: a store without `rooms` reopens and gains it | [unit.md](unit.md) |
