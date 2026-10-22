---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#517"
---

# Critic review: hand a conversation to the-loop from any surface, at any stage

> The `critic-review` node's proof. The policy (`the-loop critic policy`) is
> `criticReviewCount: 1`. The configured critic is `codex` (`gpt-6.1-sol`).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | critic `codex` (`gpt-6.1-sol`), read-only sandbox | new findings | 1 medium: the handed-off spec-chain artifact was never adopted, because nothing wrote `claudeArtifactUrl` (R7.4). **Fixed** in `08e31c36`: `Runtime.start` adopts a claude.ai artifact URL from the record, and a test proves both the adoption and the refusal of any other URL | [PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/518#issuecomment-6335459983) |

**How the round ran.** `the-loop critic run codex` failed twice with `timed out` after about 121
seconds, even with `--timeout 900`. In a daemon-spawned session the verb is routed to
the service, and that HTTP call has its own roughly 120-second cap. The same critic was
run directly with the configured harness and model: `codex exec --skip-git-repo-check
--sandbox read-only -m gpt-6.1-sol`, which took 83 seconds. That cap is a bug in the-loop,
separate from this work item.
