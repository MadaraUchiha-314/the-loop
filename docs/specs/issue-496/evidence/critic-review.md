---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Critic review: introducing the-loop gateway

> The `critic-review` node's proof — a different model/harness reading the diff. Same
> procedure as the self-review round (`reference/reviewing.md`); a round that could not
> run is recorded as **`unavailable`** with the cause and does NOT count toward the
> operator's `reviews.criticReviewCount` (1 on this machine; the one configured critic is
> `codex`, `the-loop critic list`).

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | `[codex/gpt-6.1-sol]` — `the-loop critic run codex`, prompt with the diff scope, the spec chain, the abuse cases, the eleven self-review findings and the output contract; 113 s, 94.7k input / 4.8k output tokens, exit 0 | 3 new findings | **C1** (high): a woken long-poll read the queue without re-checking its peer lease → will-fix `5f39907`. **C2** (medium): a comment edit (the attestation tick) deduped as its creation → will-fix `abc332c`. **C3** (medium): a PR binding routed nothing held on the PR's own subject (R5.7) → will-fix `9b2a5e1` | [round 1](https://github.com/MadaraUchiha-314/the-loop/pull/499#issuecomment-6272249026) |

**One round is the operator's cap (`criticReviewCount: 1`).** The round ran to completion
and found three things neither self-review round had; each is verified, dispositioned
on the PR with the critic's attribution, and fixed in its own commit with a test. A
first attempt at the round was cut at two minutes by the calling tool's own timeout and
recorded nothing (no envelope); the round above is the detached re-run. The critic's
output was read as review material only. After the three fixes the full CLI suite is
green on `9b2a5e1`: 6356 passed (`cd cli && uv run python -m pytest -q`,
`THE_LOOP_CLI_CONFIG` unset).
