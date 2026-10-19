---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Security review: introducing the-loop gateway

> The `security-review` node's proof. Required before ready-to-ship unless an authorized
> human declared the phase away at `phase-selection`. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`; no built-in security-review
  skill in this harness). Run on 2026-10-19 by a fresh-context reviewer
  (`[claude/fable-5.1]`) over `git diff origin/main...HEAD -- cli/the_loop` against
  `requirements.md` §Security considerations (three trust boundaries, eight abuse cases,
  the accepted no-auth gap) and `design.md` §Security design; each finding verified in
  code by the session before it was dispositioned.
- **Outcome:** findings fixed — ten findings (one high, four medium, four low, one info
  group), all **will-fix**, each in its own commit with a test; none dismissed.
  Checklist after the round: items 1–8 pass (items 1, 2 and 5 were partial before it).
- **Findings:** posted on the PR with dispositions before any fix
  ([round 1](https://github.com/MadaraUchiha-314/the-loop/pull/499#issuecomment-6274627843)).

| Id | Severity | Finding | Disposition → commit |
|----|----------|---------|----------------------|
| SEC-1 | high | the `duplicate-instance` 409 and `GET /instances` carried the live holder's peer id — the credential that admits a fetch under the name, so abuse case 4 was defeated | will-fix → `b9982b1` (fingerprint on the network, never the id) |
| SEC-2 | medium | `POST /bindings` anonymous, outside the allow-list, overwriting, unrecorded | will-fix → `f916509` (instance + peer, allow-list, peer lease, `gateway.bound`) |
| SEC-3 | medium | a malformed fetch answer raised out of the client and ended the instance's only ingress | will-fix → `cd7dc91` (validated shape, unreachable path, 64 MiB cap) |
| SEC-4 | medium | unbounded growth from unauthenticated writes; retention pruned events only; `/health` walked every subject | will-fix → `17a5f55` (bounds + enum, prune lapsed names and empty subjects, `COUNT`) |
| SEC-5 | medium-low | long-polls could exhaust the sync worker pool | will-fix → `082580c` (one per name, 32 in all, `limit_concurrency` 256) |
| SEC-6 | low | 64-bit overflow of `cursor`/`seq` was a 500 | will-fix → `17a5f55` (`le=2**63-1`) |
| SEC-7 | low | a non-ASCII signature header was a `TypeError` 500 | will-fix → `9932137` (bytes compared) |
| SEC-8 | low | unauthenticated header values logged uncapped on bad-signature | will-fix → `0e36262` (clipped to 200) |
| SEC-9 | low | no request-body cap on the webhook routes | will-fix → `0e36262` (413 above 25 MiB before reading) |
| SEC-10 | info | design claimed a log redaction list that does not exist; Jira poller not failing closed at start; `/health` exposed the store path and bind address | will-fix → `6da93cc` |

- **Found sound (no change):** signature verified before parse on all three providers with
  a constant-time compare and nothing stored on failure; Slack acknowledged only after the
  store write; `token` stripped from every Slack shape; the header allow-list; bound SQL
  parameters only (grep-tested); path confinement under `state.root`; subjects from the
  sanitised slug, never payload text; nothing from a payload or a gateway answer becomes a
  filename, shell argument or prompt on either side; commit checks `seq AND instance`; no
  new dependencies; no token value in any status output; the import-graph test (no
  dispatcher, no authz in the gateway tree).
- **Residual risk, accepted by the author's decision (requirements, 2026-10-18):** no
  instance authentication. A peer on the operator's network can register a name, claim a
  subject or an actor, and read and commit the deliveries routed to *it*. The round's
  fixes keep that gap to exactly that: it can no longer take over another live name,
  redirect a subject anonymously, or grow the gateway without bound. The exposure guard
  and `docs/capabilities/gateway.md`'s first paragraph bound the rest; per-instance
  authentication is the follow-up the design names.
- **Also in this node, from the author's PR comments:** a fresh gateway replayed an
  item's comment history (`791c92a`), and the P0 amendment of R3.8 — an instance keeps
  its own receiver and poller behind a gateway, the gateway's polling is opt-in
  (`570766b`, provenance recorded in `requirements.md`).
- **Verification:** full CLI suite green on `6da93cc` — 6366 passed, 2 warnings, 226 s
  (`cd cli && uv run python -m pytest -q`, `THE_LOOP_CLI_CONFIG` unset); CI `ui`, `gate`
  and `checks` green on that head.
- **Human sign-off:** risk tier 4 — requested from the author on the ticket; **pending**
  until a named approval is recorded here.
