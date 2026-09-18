---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#377"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a released work item is launched with the arguments the operator declared

> The `security-review` node's record, against `bugfix.md` § Security considerations.
> See `skills/the-loop/reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), applied to the diff.
- **Outcome:** pass — no new attack surface; one existing input now reaches every place
  it was documented to reach.
- **Human sign-off:** n/a (risk tier 3).

## The boundary this work item touches

One: **what ends up on a harness's argv.** The flag operators put here skips permission
prompts, so the question is whether anything other than the operator's own config can
widen it. Before the fix, losing the flag made a session *narrower* (it stopped and
asked); the fix restores the declared argv and adds nothing.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| A1 | A work item's `work-item-state.json` (agent-writable) names a model or effort to put an argument on the argv — now reachable on the post-gate spawn, which reads the file for the first time | `_resolved_choice` is unchanged: a name must be declared, be a candidate for this harness and not be `refused`, and resolves to exactly `(model_flag, <name>)`; the name grammar admits no flag, path or shell fragment | `test_spawn_gate_integration.py::test_abuse_a_forged_model_in_the_state_file_buys_nothing_on_the_post_gate_spawn`; the issue-358 abuse table in `test_dispatcher_choice.py`, unmodified, against the rewired fixture |
| A2 | A repository checkout contributes launch arguments | Impossible by construction: `launch_args` reads the CLI config on the daemon's machine; the base is `adapter.extra_args`, set at build time, and nothing under a checkout is read for it | `test_the_choice_path_starts_from_the_shared_adapters_own_arguments` (the base is the adapter's, not a config read) |
| A3 | Both homes declare a harness and the two are merged, doubling a flag or pairing two `--permission-mode` values | Precedence, never union: `harnesses[].args` wins, the conflict is logged once at build and reported by `config_findings` | `test_modelchoice.py::test_launch_args_new_home_wins_and_the_conflict_is_reported` |
| A4 | A malformed `harnesses` section or a non-list `args` | Contributes nothing (`_entries` shrinks, never invents); a non-list `args` falls back to the deprecated key, else the session launches bare and stops at its first prompt — the failure mode this ticket reports, and the safe direction | `test_launch_args_falls_back_when_the_new_home_is_not_a_list`, `test_launch_args_is_empty_when_nothing_declares_any` |
| A5 | The argv is built with something other than the config's list — e.g. through a shell | Unchanged: the runner receives an argv list; `launch_args` produces `str(a)` per element and nothing joins them | existing runner tests |

## Nothing new on disk, nothing new on the wire

No file, key, route or event type is added. Three existing events gain fields copied
from the session record, which already carried them: an argv the operator wrote and a
model name the operator declared. No token, no comment text, no path from a checkout.
