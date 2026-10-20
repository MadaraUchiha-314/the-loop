---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Critic review: the gateway learns a work item's collaboration channel

One round, the operator's cap (`criticReviewCount: 1`). The critic was codex, run with
`the-loop critic run codex` in 118 s. It found four real defects that the self-review
missed. Each got a will-fix reply before any code changed, then a regression test that
was red first and a fix in its own commit.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | `codex/gpt-6.1-sol` | new findings (4) | **C1** (high) a room drain re-subjects an event a thread binding already moved → fixed `edfdc00`: the drain takes only `unassigned` rows. **C2** (medium) a room published between the ingest's resolve and its append misses the event → fixed `d54f071`: `append` re-resolves a held Slack event inside its write transaction (`by: "late"`). **C3** (medium) a corrupt record reads as "no rooms" and retracts them → fixed `1c24ac8`: a strict snapshot raises, so the publish is skipped. **C4** (medium) a refused room is never retried → fixed `1bdb5d8`: the client caches only accepted rooms and warns once per holder | [findings and replies](https://github.com/MadaraUchiha-314/the-loop/pull/506#issuecomment-6282363644) |

C4 also settles self-review finding R1-2: `document()["rooms"]` now reports what the
gateway accepted. The full suite, lint and types pass after the four fixes
([lint-and-typecheck.md](lint-and-typecheck.md)). The cap is one round, so no second
critic round ran on the fixes. The self-review's convergence check and the security
review cover them instead.
