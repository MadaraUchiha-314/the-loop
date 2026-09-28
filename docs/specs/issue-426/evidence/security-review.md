---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#426"
---

# Security review: work-item mode launches Claude Code without its question menu

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)). I ran
> the checklist below against the branch diff, file by file.

## Security review (gate)

### Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `cli/the_loop/harness/base.py` | `unattended`, `_UNATTENDED_ARGS`, `with_unattended`, `_launch_args` | the argv of an interactive launch |
| `cli/the_loop/harness/claude_code.py` | the constant token; both `interactive_*` methods use `_launch_args` | the argv of a Claude Code launch |
| `cli/the_loop/interaction.py` | `InteractionConfig.unattended` | a boolean derived from operator config |
| `cli/the_loop/webhook/dispatcher.py` | `_adapter_for` applies it | every work-item spawn and respawn |
| `cli/the_loop/core/sessions.py` | `_restart_adapter` applies it | `the-loop sessions restart` |
| `cli/tests/*` | tests | none |
| `docs/**`, `skills/the-loop/reference/*.md` | prose | none |

### Findings

**None.**

### Checklist

- **Capability direction.** The change *removes* one tool from the session. It adds no
  permission flag and never widens what the operator declared. `harnesses[].args` is
  neither reordered nor rewritten; the token is appended after it.
- **Injection into the argv.** The token is a constant. Nothing from a payload, a ticket,
  a comment or the registry is interpolated into it. It is passed as one argv element to
  tmux's `new-session -- <binary> …`, with no shell in between, as before.
- **Prompt integrity.** The token closes any variadic flag the operator's arguments
  leave open, so the prompt, which carries the directive and the untrusted-payload
  framing, now reaches the session as its positional argument even under the ticket's
  workaround. Before the fix that config silently dropped the whole prompt, including
  the framing. The fix removes that failure rather than adding one.
- **Fail direction.** `InteractionConfig` resolves an unrecognised mode to `work-item`
  (issue-134), so a typo denies the tool. A wrong deny costs a question asked in text;
  a wrong allow is the silent freeze this ticket reports.
- **Recorded state.** `Session.harness_args` is unchanged, so no registry file changes
  shape and no drift-driven relaunch fires on upgrade.
- **Secrets / credentials / network / new subprocess.** None added.
- **Sensitive paths.** None touched (`**/*schema*`, `.the-loop/**`,
  `.github/workflows/**`, auth/secret/credential). Tier stays 3.
