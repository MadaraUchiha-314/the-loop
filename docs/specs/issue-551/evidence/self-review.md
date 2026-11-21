---
type: evidence
phase: needs-review
workItem: issue-551
---

# Self-review: a session never goes idle unnoticed

> The `self-review` node's proof. The operator's policy (`the-loop critic policy`) is
> two self rounds and one critic round. Both self rounds ran. Round 2 still found
> new issues, so the loop did not converge on zero; it ended at the policy's cap with
> every finding fixed.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/fable-5.2]`, two independent passes over `667acd46..9fec9930` | new findings | 26 (8 major, 18 minor). 25 fixed, one commit each. S2 fixed in part: the false stall notice for a pull request's own session is gone; judging that session's inner loop is a recorded limit and needs a design decision. S10 fixed in part: a turn that ends with no Stop hook at all stays out of scope, as the requirements say. | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/552#issuecomment-7051542572); commits `623d1de9..bd74948d` |
| 2 | `[claude/fable-5.2]`, a fresh pass over the 32 fix commits and the docs | new findings | 8 code (1 major, 7 minor), 10 doc statements, stale evidence counts. All fixed, one commit each (`92c505d8..cf4d13a9`). Two parts left open and recorded: an answered question's Slack message is not edited (no code edits one today); a daemon with no instance name cannot be told from an operator's shell. | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/552#issuecomment-7052375503) |

## What the rounds changed most

- **The watcher records an act before it performs it.** A log that cannot be written
  now means no nudge, where before it meant a nudge every 30 seconds.
- **Asks are tracked by id.** Several can be open at once; an authorized answer
  closes all of them; an ask recorded before this version neither excuses a stop nor
  gets a reminder.
- **One timed ask per step.** A second ask with a deadline is refused while one is
  open, and after one's default was taken, until the pointer moves or a person
  speaks.
- **Comments explain the code.** About 145 added lines cited work-item and
  requirement ids. The implementing briefs had asked for the citations; that was
  wrong, and they are gone.

## Standing checks

- **Production-code comments explain the code:** raised as S8, fixed; round 2 found
  no citation left in added lines.
- **`design.md` holds no code-level detail:** checked in both rounds; nothing found.

## Limits recorded for the reviewer

1. A pull request's own session (a PR in another repository) gets the stall notice
   and ask handling, but no nudge, and its Stop gate does not judge the PR's inner
   loop.
2. The service authenticates no caller. The binding check confirms the ref names a
   live registered session, and the CLI refuses a ref that differs from the
   session's own.
3. A turn that ends with no Stop hook (an interrupt, a usage-limit cut-off) leaves
   the session marked "working", so the watcher does not look at it.
4. The event log never rotates. Reads are now streamed and filtered, but they still
   grow with the file.
5. What a harness does when it kills the Stop hook at its own timeout was not
   verified. The hook's worst case with the service down is 55 seconds.
