---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Critic review: the mention is the address, and three acts each end in the session

> The `critic-review` node's proof — a different model/harness reading the diff. Same
> procedure as the self-review round (`reference/reviewing.md`); a round that could not
> run is recorded as **`unavailable`** with the cause and does NOT count toward the
> operator's `reviews.criticReviewCount`.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | — | **unavailable** | `the-loop critic list` in this checkout: *No critics configured — add critics[] to your cli-config.yaml (the operator's file, not the repository's)*. The repository's `.the-loop/cli-config.yaml` ships `critics: []`; the cloud session has no operator file and no second harness to spawn. Does not count toward `criticReviewCount: 3` (`the-loop critic policy`). | — |

The self-review round ([`self-review.md`](self-review.md)) is the one independent read the
diff received before the human reviewer; the owner's review on
[PR #390](https://github.com/MadaraUchiha-314/the-loop/pull/390) is the critic round of
record for this tier-4 change.
