---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#378"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a work item's whole life is told to every channel, and Slack can begin one

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Can the lifecycle fire at the wrong moment — a message at every node, or silence at a gate? | The rule is the label's, and the first draft got it wrong: comparing a node's own `phase` to its predecessor's fires on entering every phase-less approval node. The fix is a **phase pointer** in the state file (`WorkItemState.phase`), written on `start`, every `advance`, `cleanup` and `force`, so "the phase the walk is in" is a recorded fact rather than a walk over the node dict — whose insertion order is wrong the moment a loop-back re-enters a phase-less node from a later phase. The dict walk stays only as the fallback for a state file written before this change, for one transition |
| 2 | Does a config with no `channels` section pay anything? | No: `publish_lifecycle` returns before building an `Event`, and every pre-existing runtime, graph, cleanup and hook suite passes unmodified (T4) |
| 3 | Can a lifecycle event carry text it should not? | No. The text is composed from the work item id, the node id, the phase and the outcome; `detail` is those plus `loop` and `actor`. A test writes `SECRET-BODY` into `requirements.md` and asserts it reaches no event |
| 4 | Is the closure announced where the people are? | Yes, and the ordering is asserted rather than argued: the fake publisher snapshots the declaration store at call time and the test asserts the room is still declared then and cleared afterwards |
| 5 | Does a room conversation ever send `thread_ts=""`? | It would have: `post` passed `bound[1]` verbatim. Now `bound[1] or None`, and the room tests assert `thread_ts is None` on every post. `say` already had the `or None` |
| 6 | Can the room mode change the shape of a live conversation? | Only through a declaration, which is the move issue-375 already makes. A thread already bound *inside* the room keeps its shape (R5.5, tested); a work item with no declaration is byte-identical (T13, the issue-375 suite unmodified) |
| 7 | Does `/the-loop new` let payload text reach a repository, a path or an argv? | No: the text goes through `resolve_target`, and the ledger receives `target.repo`, a `DeclaredRepo.declared` string from the operator's config. The title and body are the same prose a kickoff message already hands the issue writer, through the same `issue_title` / `issue_body` |
| 8 | Is the verb gated the way the kickoff is? | Authorized before parsing (the existing step 1), the `work-item.create` grant (step 5, through `FAMILY_GRANTS`), one act per trigger (step 2). Each is asserted in its own test |
| 9 | Can the provider table hide a broken provider? | A loader that raises is logged and skipped; the others still load. A loader answering `None` contributes nothing. Both asserted |
| 10 | Does the inbound path read a room record as a thread? | `thread_for` still answers `None` for a room, and `bind` with an empty thread writes no thread-map entry, so nothing iterates a `""` thread. Asserted in the state round-trip test |

## What I changed after re-reading

- **The moved-conversation message** had grown a branch that could never be taken
  (`_conversation` moves only when the channel differs). Reverted to the original wording.
- **The `new` answer** interpolated the configured `start` keyword unguarded; a disabled
  keyword (`""`) would have printed an empty code span. The hint is now omitted when the
  keyword is disabled.
- **The `phase` attribute** was unclassified in `state.ATTRIBUTES`; the state-portability
  gate caught it, as it is meant to.
- **`_say_moved` for a room** posts top-level in the old room (`say` with an empty thread),
  which is what a room needs and required no code — noted so a reader does not look for it.
