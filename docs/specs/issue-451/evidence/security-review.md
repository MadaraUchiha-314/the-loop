---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#451"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a default model per harness

> The ready-to-ship gate's security item
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)), run
> with the-loop's checklist against the branch diff.

## Security review (gate)

### Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `modelchoice.py` | `default_model`, `DEFAULT_MODEL_KEY`, one finding | pure function over operator config |
| `webhook/dispatcher.py` | `_resolved_choice` falls back to the default | the argv a work-item session launches with |
| `graph/hooks/selection.py` | the checklist tail and confirmation name the default | comment text the gate posts |
| `commands/models_cmd.py` | the default joins the probe matrix | the argv `models check` probes with |
| both `cli-config.schema.json` copies | the `defaultModel` property with the name pattern | config validation |

### Checklist

| Item | Result |
|---|---|
| Untrusted text reaching an argv | **No.** The default comes from the operator's `cli-config.yaml` only; nothing from a comment, a label or `work-item-state.json` selects or changes it. A forged state file now lands on the operator's default instead of on no flag (abuse 2, tested with a flag-shaped frozen model). |
| Flag or shell injection through the config | **No.** `default_model` holds the value to `NAME_RE` on read, not only in the schema, because the daemon reads configs the schema never validated. Flag-, path- and shell-shaped values resolve to `""` (abuse 1, tested in `test_modelchoice.py` and through the real dispatcher). The value is only ever the operand of the adapter's own model flag, appended by `effective_args` after the operator's `args`. |
| Argument bleed between harnesses | **None.** Looked up by the launch's harness name only (abuse 3, tested: claude's default never reaches a cursor launch). |
| Authorization | Unchanged: the gate's authorized-reply rule is untouched, and the default is not a choice a reply can make. |
| Availability | A default the harness refuses is dropped by the existing `_offerable_only` and announced as `session.choice_refused` (tested). |
| New egress, secrets, dependencies, files | None. |

### Findings

**None.**

### Sign-off

Risk tier 4 (the change touches `**/*schema*` and `.the-loop/**`), so a **named human
security sign-off** is required on the PR before completion, distinct from the PR
approval.
