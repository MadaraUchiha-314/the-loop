# Evidence — security review (gate)

**Mechanism:** the harness's built-in `security-review` skill, run on
`claude/github-issue-363-yqyz3u` against `origin/main..HEAD` (one commit, `63b859d`).
**Outcome: pass — no findings survived verification.**

The diff range is this work item's alone: `origin/main` was fetched first and is the
immediate parent of the reviewed commit, so — unlike issue-360's run — no previously
merged work item is inside the range.

## What was reviewed

```console
$ git diff --stat origin/main..HEAD -- cli/the_loop skills
 cli/the_loop/control.py                            |  57 +++++++-
 cli/the_loop/eventlog.py                           |  47 ++++++
 cli/the_loop/graphlink.py                          | 248 ++++++++++++++++++++++-
 cli/the_loop/poller/poller.py                      |  85 ++++++++-
 cli/the_loop/recovery.py                           | 191 ++++++++++++++++++
 cli/the_loop/runner.py                             |  71 ++++++-
 cli/the_loop/schemas/cli-config.schema.json        |   6 +
 cli/the_loop/webhook/dispatcher.py                 |  48 ++++-
 cli/the_loop/webhook/router.py                     |  22 +++
 cli/the_loop/workitem.py                           |   9 +
 skills/the-loop/templates/cli-config.yaml          |   7 +
 skills/the-loop/templates/webhook-autoexecute-prompt.md |   2 +
```

## The abuse cases of `bugfix.md`

| Case | Verdict | Why |
|---|---|---|
| A label becomes an input to a control-flow decision | **closed** | `event_labels` returns strings; `phase_labels`/`advanced_phase` strip the `loop:` prefix and return a *phase*, and that value reaches exactly three sinks: a boolean in `_may_start`, a log format argument, and an event field. No branch derives a node id, a `state_dir` or a subprocess argument from it, and `dispatcher.py` coerces it with `bool(...)` before selecting between a module constant and `""`. A forged `loop:complete` buys `graph.rewind_refused` and nothing else; `the-loop graph force` is unchanged and is still the only way to place a pointer. Covered by `test_abuse_a_forged_complete_label_never_places_a_pointer`. |
| A tracked portable record moves a pointer this machine established | **closed** | The write target is built from the daemon's cwd, the operator's `routing.graph.specDir` and `item_id` (`issue-<int>`, no separator possible); the record's content is never used to build a path, only serialized as file *content*. `_awaiting_start`, `_checkout_belongs_to` and `_is_contained` still run first and in order, and the vacuum check is doubled — once before the lock and once inside it. Covered by `test_abuse_a_portable_position_never_overwrites_local_state`. The *content* exposure is not new: `graph/state.py`'s own docstring already declares that file agent-writable and "not the source of truth", `load()` type-filters every field, skips/opt-ins are re-filtered through the compiled graph, and `reconstruct()` re-derives the position from the artifacts. |
| The age rule makes a comment executable that was not | **closed** | The branch is strictly subtractive: `pending = set() if lost else self._pending_control_ids(...)` can only shrink the withheld set. `_try_spawn` is still gated by the unchanged `spawn_authorized`, and `lost` requires `control_store.get(ref) is None`, so `start_requested` is necessarily false there. `is_authorized`, the collaborator grant and the self-authored marker are untouched. Covered by `test_abuse_an_unauthorized_command_is_still_never_executed`. |
| The notice echoes a commenter's body | **closed** | `context_lost_notice` interpolates exactly two values, both minted: `WorkItemRef.ref` (provider-constrained names, an `int` number) and a UTC timestamp. No body, title or actor reaches it, so `mark_self_authored` is applied only to the-loop's own prose. Covered by `test_the_notice_carries_only_minted_values` and `test_the_notice_is_marked_as_the_loops_own`. |

## The one observation the review raised, and why it is recorded rather than fixed

`context_lost`'s second signal is "the-loop has posted on this thread", answered by
`authz.is_self_authored` — and that marker (`<!-- the-loop:agent-comment -->`) is a comment
body anyone can type. So an unauthorized commenter **can** force `lost=True` on a work
item's first-sight cycle.

It is recorded as an accepted property, not a defect, for two reasons. The consequence is
**withholding only**: the thread is baselined, no command is run, and one fixed-text notice
is posted — the fail-safe direction this whole change exists to move things toward, and
identical to what the phase label already achieves for anyone with repo write access. And
the marker's forgeability is load-bearing elsewhere in exactly the same direction: the
poller has always dropped a self-marked comment rather than forwarding it (issue-64), so
"anyone can make the-loop ignore their own comment" is a pre-existing and deliberate
property of the loop-prevention marker, not something this change introduces. Raising it to
an authenticated signal would mean a second marker with a secret in it, which is a
different work item and a worse trade for a guard whose only power is to say *stop*.

## Categories examined, and why each is empty

| Category | Verdict |
|---|---|
| Input validation — path traversal in file operations | Empty. The only new write path is `graph-state.json` under a `state_dir` built from trusted components; `_is_contained(root, spec_dir)` still gates it. |
| Deserialization / code execution | Empty. `json.loads`/`json.dumps` with `isinstance(..., dict)` and a `currentNode` check before use. No `pickle`, no `yaml.load`, no `eval`, no dynamic import of record-derived names. |
| Authorization bypass / privilege escalation | Empty. Every new decision either returns a boolean that *withholds*, or narrows an existing set. No guard was relaxed and no new actor gained a capability. |
| Command / argv injection | Empty. No new value reaches a subprocess argument. The notice is posted through the existing `post_issue_comment` seam, whose argv is a list with `shell=False`. |
| Template injection | Empty. `$recovery_notice` substitutes either `""` or a module-level constant through the existing `safe_substitute` path; no payload-derived text was added to the template. |
| Crypto / secrets | Empty. No key, token or credential is read, written or logged. |
| Data exposure | Empty. The new event fields are a ref, a phase name, a node id and a timestamp; the new file content is the graph state, which is already checked in. |

**Human sign-off:** n/a — risk tier 3, below the tier-4 threshold. The PR approval is the
tier-3 gate.
