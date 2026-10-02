---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#451"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a default model per harness

> The self review before human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking which launch could still miss the default, which
> could get one it should not, and what a reviewer would reject.

## Review cycles

### Cycle 1: every launch path

1. **Checked: one seam covers every arming command.** Every work-item launch — first
   spawn (`_spawn_for`), respawn, PR endpoint, `sessions restart`, and the drift check —
   resolves its adapter through `_adapter_for`, and records through `_resolved_choice`.
   `do`, `contribute`, `review` and an operator's own graph arm through the same
   `_spawn_for`. Putting the fallback in `_resolved_choice` therefore reaches the argv,
   the record, the spawn event and the `session_spawn` hooks at once, with no second
   copy of the rule.
2. **Checked: standing sessions and critics are not work-item launches.** They build
   argv from their own `harnessArgs` and critic `model`; left out of scope and said so in
   the config reference.
3. **Found and fixed: two log lines lied.** The re-validation warnings said "launching
   on the harness's own arguments", which is false once a default exists. They now say
   "the harness's default instead", true in both cases.

### Cycle 2: the edges

1. **A refused frozen model does not fall back to the default.** `_offerable_only` runs
   after the fallback and drops a refused name to `""`. Considered and kept: R2.3 covers
   re-validation against the config; a refusal is a measurement, and the existing rule
   for a measurement is "launch without it". Adding a second fallback inside the cache
   check would mean a refused choice silently swaps to another model the human did not
   pick. A follow-up can revisit it if anyone hits it.
2. **Drift on upgrade.** A session recorded with non-empty `harnessArgs` whose harness
   gains a `defaultModel` is re-launched (conversation resumed) on its next event. That
   is the existing drift rule, the same as editing `args`; documented in the config
   reference and the requirements' open question.
3. **The checklist tail names only the default harness's default.** When a harness
   section is offered and a reply picks another harness, the confirmation names the
   resolved harness's default, which is the line a human reads back. Kept the tail
   simple.

### Cycle 3: no new findings

Re-read the diff after the fixes; nothing new. Stopping per the procedure.

## Critic reviews

Not run in this session: no critic harness is installed in this cloud checkout
(`the-loop critic list` is unavailable; the CLI is not installed as a service here). The
PR's own review bot and the human reviewer are the remaining rounds.
