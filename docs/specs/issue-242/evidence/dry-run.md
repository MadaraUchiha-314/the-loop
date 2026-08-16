# T11 — a real dry run, read by a human for redaction quality

Captured 2026-08-16. Planned as "dry-run, human-read"; run in a **stronger** form
than planned because a real `claude` binary was available: the *actual* default
agent path (synthetic critic → `claude -p` one-shot, JSON out, private temp
directory) diagnosed a seeded #240-style failure, with `--dry-run` so nothing
posted.

## Setup

A scratch CLI config (`selfDiagnosis.enabled: false` — proving `--dry-run`
works pre-opt-in) and a one-record event log built from #240's trace with
**planted sensitive values**: a private work-item ref
(`github:acme-corp/secret-payments-service#7`), an absolute `cwd`, a tmux
target, a delivery id, a fake `GH_TOKEN` value and an operator e-mail — the
last three planted *inside the free-text `error` string*, where only the
scrubber (not the field allow-list) can catch them.

## Human verification of the output below

| Planted value | In the output? |
|---|---|
| `acme-corp` / `secret-payments-service` (work item, cwd, tmux target) | absent — `work_item`/`cwd`/`tmux_target` dropped by the allow-list; the two copies inside the error string masked (`<redacted:path>`, `<redacted:token>`) |
| `GH_TOKEN` value (`ghp_9zX8…`) | `<redacted:token>` |
| `rohith@example.com` | `<redacted:email>` |
| `delivery_id`, `pid` | absent (allow-list) |
| loop-prevention marker + visible attribution | present |
| parseable control keyword | none (`parse_command` finds nothing) |

One observation worth recording: the tmux target (`loop-…-7`) inside the error
string was caught by the *token* pattern rather than by anything
target-specific — over-eager, and in the safe direction.

The agent's diagnosis itself is a faithful reconstruction of #240's root cause
(send-keys resolving the read-only client; the give-up being non-retryable),
from the redacted dossier alone.

## `the-loop diagnose --dry-run` (exit 0, nothing posted, no state written)

````markdown
--- would file on MadaraUchiha-314/the-loop ---
[self-diagnosed] tmux dispatch aborts when the target session's attached client is read-only

## Summary

the-loop's poll/dispatch loop pushes work into a running harness session by shelling out to `tmux send-keys`. On this run the target session had only a read-only-attached client (an operator watching the Claude harness pane, e.g. via `tmux attach -r`), so tmux refused the write and `send-keys` exited 1 with "client is read-only". the-loop treated this as a fatal, non-retryable dispatch failure, so the triggering issue_comment event was dropped and never reached the harness.

## Root cause hypothesis

The tmux dispatcher resolves its send-keys target through whatever tmux client/session context is ambient rather than addressing the destination pane via a dedicated, always-writable control connection owned by the daemon itself. Any tmux client attached with the read-only flag (routine when an operator attaches to observe a live harness session without risking accidental keystrokes) causes the server to refuse subsequent writes to that session, so `tmux send-keys` exits non-zero with "client is read-only". the-loop's dispatch error handling does not special-case this exit condition — it classifies every non-zero exit from the tmux invocation as a hard failure (will_retry=false) instead of recognizing it as a self-inflicted, typically transient state caused by an observing client, so the event is discarded outright rather than deferred or redelivered.

## Suggested fix

Make the dispatcher address the destination pane through a control socket/client that the-loop itself owns and keeps writable, independent of any operator's interactive attach state, so observer attaches can never block dispatch. As a defense in depth, detect the "client is read-only" substring in the tmux failure output and handle it as a distinct, retryable condition (short backoff plus retry, or an explicit operator-facing alert asking them to detach/reattach without -r) instead of folding it into the generic non-retryable dispatch.failed path.

## Trigger

# Self-diagnosis dossier

- the-loop version: 10.3.1
- python: 3.11.15
- os: Linux
- matching records in this log: 1 (showing the last 1)

## Trigger records (allow-listed fields only, free text scrubbed)

```json
{"ts": "2026-08-16T01:10:00.000Z", "event": "dispatch.failed", "level": "error", "source": "poll", "gh_event": "issue_comment", "harness": "claude", "via": "tmux", "will_retry": false, "error": "tmux send-keys exited 1: client is read-only (target <redacted:token>, cwd <redacted:path>, GH_TOKEN=<redacted:token>, operator <redacted:email>)"}
```

---

Filed automatically by the-loop's **self-diagnosis** ([issue-242](https://github.com/MadaraUchiha-314/the-loop/issues/242), opt-in). All PII and environment data were redacted before posting. Intended label: `the-loop: self-diagnosed`. This issue is never armed for autonomous execution by the-loop itself.

🤖 _the-loop, autonomous comment_
<!-- the-loop:agent-comment -->

````
