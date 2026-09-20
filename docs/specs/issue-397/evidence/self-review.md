---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#397"
---

# Self-review: minor Slack polish (issue-397)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`, no critics configured
> (`the-loop critic list` — "No critics configured"), so the critic rounds are
> **unavailable** and do not count. The self-review read the diff adversarially in
> three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (diff read) | new findings | (a) `pyright`: `Verb \| None` passed to `wants_public_help` in the unit test → asserted non-`None`; (b) CLI test's fake opener read `.get` on an `Optional` config → guarded; (c) the dispatcher's opener is an instance attribute, not a `RoutingConfig` key → tests set `dispatcher.opener` after construction | this PR |
| 2 | self (behaviour read) | new findings | (d) a declaration made while the conversation is bound in the central channel now **moves** it at the declaration rather than at the next event — judged correct (issue-375 R2.2 brought forward; the pointer in the old thread is unchanged) and recorded in `design.md`; (e) `help public` in a room posts top-level (`thread == ""`) — that is "where the member asked", as R2.1 says; no change | design.md |
| 3 | self | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |
