---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#395"
---

# Self-review: the hosted ingress set follows the config (issue-395)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`, `criticReviewCount: 3`,
> but `critics: []` in this repo's `cli-config.yaml` — the critic rounds are
> **unavailable** and do not count. The self-review read the diff adversarially in
> three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (diff read) | new findings | (a) `start_hosted_ingresses` is documented "never raises", and `_wanted` now calls `core.lifecycle.enabled_services` → checked `service_config`: it clamps, never raises, so the contract holds; (b) the exception log read "hosting the poller failed startup" → "failed (startup)"; (c) the shutdown test asserted on *every* `the-loop-*` thread in the process, a flake waiting for another suite's lingering thread → asserts on the threads this test created | this PR |
| 2 | self (behaviour read) | new findings | (d) a **dead** hosted entry that is still wanted is restarted on the next config edit — judged right (the edit is most likely the fix) and recorded in `design.md`; (e) `TheLoop(config=dict)` with no path watches the default config path — the SDK's `ConfigHolder` already does exactly that, so consistent, no change; (f) `stop()` can wait past the supervisor join if a reconcile is mid-stop, then blocks on the lock until it finishes — orderly, recorded in `design.md` § Error handling | design.md |
| 3 | self | zero (converged) | — | — |
| — | critic | unavailable | `critics: []` — no critic harness configured in this repo's CLI config | `.the-loop/cli-config.yaml` |
