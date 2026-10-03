---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#460"
---

# Self-review: an orphan tag blocks every release (issue-460)

> No `cli-config.yaml` declares critics in this cloud checkout, so the critic rounds
> are unavailable. Round 3 found nothing new, which meets the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) `--atomic` alone stops the orphan tag but leaves a queued run building on a stale SHA, which fails again. Added `ref: main` (R2). (b) The owner was asked to choose between deleting the tag and moving to 19.22.0, and chose the latter. Recorded in `bugfix.md` § The fix |
| 2 | self (mechanism read) | new findings | (c) The first T5/T6 replay piped `cz bump` into `head`, which killed it before it tagged, so T6 bumped again. Re-ran without truncation: T5 → 19.22.1, T6 → exit 3. (d) `markdownlint` MD018 on a line starting with `#457`. Reworded |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Does `ref: main` break the first-release bootstrap (`HEAD^`)?** No. That step runs
  only when no `v*` tag exists, and `HEAD` is still a commit on `main`.
- **Does GitHub accept `--atomic`?** Yes. GitHub's receive-pack advertises the `atomic`
  capability. The replay shows git's behaviour when the server honours it.
- **What if a merge lands during the run after this one?** That run's atomic push is
  rejected and writes nothing. The run queued for that merge then starts from the tip
  and releases everything. The `concurrency` group always keeps the newest pending run.
- **Is 19.22.0's changelog entry honest?** It lists #457, the change that tag covers.
  The capability doc's history row records that 19.22.0 was never published.
