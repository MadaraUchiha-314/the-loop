---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#440"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: the harness is a per-work-item choice at `phase-selection`

> The ready-to-ship gate's security item
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)), run
> against the branch diff.

## Security review (gate)

### Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `harness/base.py`, `harness/__init__.py` | `hosts_sessions`, `ADAPTER_TYPES`, `hosting_harnesses` | which adapters may be offered |
| `modelchoice.py` | `offered_harnesses`, `default_harness`, one finding | pure functions over operator config |
| `graph/bootstrap.py` | seeds `harness`, `offeredHarnesses` | the gate's config |
| `graph/hooks/selection.py` | the `harness-*` section, parse and freeze | comment text → a token |
| `graph/runtime.py`, `graph/state.py`, `state.py` | persist `harness` | the agent-writable state file |
| `webhook/dispatcher.py` | `_harness_for`, `_default_harness`, spawn on it | which adapter launches |
| `channels/slack.py` | a prefix and a sentence | none |

### Checklist

| Item | Result |
|---|---|
| Comment text reaching an argv or a binary path | **No.** A reply yields a token checked for membership in `offeredHarnesses`; the binary and argv come from the adapter class and `harnesses[].args`. |
| Authorization | Unchanged: the gate reads only `_authorized_comments` (abuse 1, tested). |
| Tampered state file | `_harness_for` re-checks declared, adapter present, hosts; anything else spawns on the default (abuse 3, tested with `cursor`, `pi`, `/bin/sh`, and an adapter the operator did not declare). |
| Argument bleed between harnesses | None: the argv is the chosen adapter's own `extra_args` plus the model/effort resolved for it (abuse 4, tested: `--dangerously-skip-permissions` does not reach codex). |
| New egress, secrets, dependencies | None. |

### Findings

**None.**
