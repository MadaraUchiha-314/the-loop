---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Security review: the gateway learns a work item's collaboration channel

## Security review (gate)

- **Mechanism:** both. The built-in `/security-review` skill, run as an independent
  sub-agent over `git diff origin/main -- cli/the_loop`, and the-loop's checklist
  (`reference/security.md`), checked against the diff below.
- **Outcome:** pass. No finding at confidence 8 or above.
- **Findings:** none.
- **Human sign-off:** n/a. Effective risk tier 3: the diff touches no fixed sensitive
  path (`*schema*`, `.the-loop/**`, `.github/workflows/**`, `auth`, `secret`,
  `credential`).

## Checklist

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Every trust boundary in `design.md` § Security design is enforced where it says | pass | `PUT /rooms` calls `_check_allowed` first (`consume.py`), `publish_rooms` checks `_other_peer_holds` in the transaction, keeps a live holder's room (`_lease_live`), and deletes only `WHERE instance = ?` rows (`store.py`) |
| 2 | Untrusted inputs validated at ingress; SQL injection covered | pass | `RoomsBody`: id regex `^[CGD][A-Z0-9_-]{1,20}$`, `KEY_MAX`, `ROOMS_MAX`, `slug_of`, so a malformed body is 422 before the store. Every new statement is parameterized, and the channel prefix match uses `substr(held_key, 1, ?) = ?`, not `LIKE` and not string formatting |
| 3 | Untrusted content cannot steer privileged behaviour | pass | a room only chooses which queue a Slack event lands on. The instance's pipeline (principals, listen mode, `authorizedUsers`, roster) is unchanged and judges every delivery (T2 scenario 1 delivers the raw author) |
| 4 | No secrets in code, config, logs, fixtures | pass | the table and `gateway.rooms` hold channel id, ref, slug, instance and time. Test fixtures use a placeholder signing secret |
| 5 | AuthZ fails closed | pass | an unknown instance gets 409 `unknown-instance`; a second peer under a live name is refused; an unreadable or corrupt declaration skips the publish and keeps the gateway's rooms (critic C3) |
| 6 | Least privilege | pass | no new Slack scope, file path or network listener; the route is on the existing consumer API |
| 7 | Every abuse case has a passing negative test | pass | abuse 1–3, 5, the peer rule and fail closed: `-k abuse`, 12 passed; abuse 4: T2 scenario 1 ([unit.md](unit.md), [integration.md](integration.md)) |
| 8 | New dependencies justified | pass | none added |

## Residual risk (accepted, not a finding)

An allow-listed instance may name **any** work item ref in a room, as it can already name
any ref in `POST /bindings` (issue-496 SEC-2). The worst case is extra events for that
work item's claimants, which those claimants then authorize. It cannot take a live
instance's room or retract one. This matches the trust issue-496 gave allow-listed
instances, and `gateway.rooms` records every publication with its instance.
