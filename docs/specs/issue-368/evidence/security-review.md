---
type: evidence
record: security-review
workItem: "github:MadaraUchiha-314/the-loop#368"
---

# Security review: one rule for where a work item's attributes live

## Security review

Risk tier 4 (`.the-loop/**` and the routing of unattended sessions), so this round needs
a **named human sign-off** in addition to the automated review. It is requested on the
pull request; the review below is the autonomous round.

**Two trust boundaries moved, and one closed.**

| Boundary | Before | After | Verdict |
|---|---|---|---|
| a harness conversation id | written into `docs/specs/<id>/work-item-state.json`, which is public and proposable by anyone who can open a pull request | never written to a repository; `session: inherit` resolves through this machine's session registry | **closed** — a leak of a resumable session id, removed |
| `sessionPerPr` / `model` / `effort` | read by the daemon from the operator's `portable/` record | read from the work item's own agent-writable state file | **moved, not widened** — see below |
| a Slack channel id, thread ts and permalink | machine-wide `channels/slack.json` | the operator's portable record | **unchanged in exposure** — both are outside the repository, which R7.3 requires |

### Why reading the choices from an agent-writable file does not widen the surface

The dispatcher already treated the portable record as agent-writable and re-validated on
the way in; the state file is re-validated by the same code paths, at the same points:

- **a model** resolves only against the operator's declared `models`, then against the
  harnesses the operator declared it for, then against this machine's measured verdict
  cache. A name that survives all three is one the operator offered. An undeclared name
  launches on the harness's own arguments and is announced on the work item;
- **an effort level** resolves only against the operator's declared `effort`;
- **`sessionPerPr`** resolves only to `never | cross-repository | always`; a fourth value
  is the operator's default;
- **`repos`** — which decides where an unattended agent opens pull requests, a strictly
  larger blast radius — has lived in this same file since issue-365.

### New values that reach a filesystem path

`pullRequests[].repository` and `stateDir` become directory names. Both go through
issue-183's filesystem boundary (`repo_state_key`, which refuses `.`, `..` and anything
outside `[A-Za-z0-9._-]`) **on write and again on read**, and `stateDir` is only honoured
when it equals one of the two spellings this repository and number actually derive —
anything else is recomputed rather than read as given. An entry that fails validation is
skipped and the rest of the file is honoured.

### Abuse cases

| # | Case | Mechanism | Proof |
|---|---|---|---|
| 1 | a state file names an undeclared or refused model | resolution against declared names + the verdict cache; the refusal is announced | `test_an_undeclared_model_in_the_state_file_buys_nothing` |
| 2 | a state file names a fourth `sessionPerPr` mode | `session_per_pr_mode` → the operator's default | `test_a_fourth_session_per_pr_mode_routes_by_the_operators_default` |
| 3 | a `pullRequests[]` entry spawns a session | it cannot: an entry is a binding, and a session is spawned only by an authorized routed event | the entry is written by the same code that already recorded the local endpoint; no spawn path reads it |
| 4 | a legacy `session` block is resumed | it is not read at all, and is dropped on the next save | `test_a_legacy_session_block_is_never_read_and_never_rewritten`, `test_a_legacy_session_block_is_ignored_and_dropped` |
| 5 | a local record is copied to another machine | unchanged, and the reason the file stays local | documented in `docs/cli/state.md` § What must never be carried |
| 6 | a binding names a thread the bot cannot post in | `ChannelError`, and no second root is opened | unchanged path; `test_a_channel_outage_never_fails_the_spawn` |
| 7 | a forged `stateDir` escapes the spec directory | refused and recomputed | `test_a_forged_state_dir_is_refused_and_recomputed` |
| 8 | a forged `repository` becomes a directory name | refused; the entry is skipped | `test_an_unusable_pull_request_entry_is_skipped_and_the_rest_honoured` |

### Fail-closed

Every read added here answers "nothing recorded" on an absent, unreadable or malformed
file, and every caller then takes the operator's default. No read failure can fail a
delivery, spawn a session, or route an event to a session that does not exist.

### What this change does not touch

Who may arm a work item, whose comments become input, and who may answer a gate are all
decided by the ingress before any of these files is written. No new network call, no new
subprocess, no new argv built from file content beyond the two validated values above.
