# `remove-channel`

Give a work item's room back.

```bash
the-loop remove-channel slack@C0TMP375 --work-item github:OWNER/REPO#375
```

## What it does

The other half of [`add-channel`](/cli/commands/add-channel), with the same shape:
the local effect first, then the same keyword posted back on the work item so the
thread records the change, then `control.command` with the effect (`undeclared` /
`not-a-channel`).

Two things follow. The work item's **next** update goes to the operator's central
channel again — the thread already open in the room stays bound, so replies in it
still reach the work item. And messages elsewhere in the room stop being attributed
to it: they are dropped at the ingress as `unmapped`, which is what every
undeclared channel has always done.

It takes effect on the **next event**: the declarations are read per event and never
cached in a running session, so nothing has to be restarted.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `TYPE@TARGET …` | required | One or more channels, e.g. `slack@C0TMP375`. |
| `--work-item` | required | The work item to undeclare on, e.g. `github:OWNER/REPO#375`. |
| `--portable-dir` | `<state.root>/portable` | Where the declarations live. |
| `--comment` / `--no-comment` | on | Post the keyword back to the work item. |

## Exit codes

| Code | When |
|------|------|
| `0` | at least one channel was undeclared |
| `1` | nothing changed — none of them was declared on this work item |
| `2` | a malformed ref, an unknown type or a work-item ref that will not parse: nothing was written and nothing posted |

## Notes

- A channel that was not declared is reported and **not** announced on the ticket: a
  change that did not happen does not belong in the thread.
- The keyword form is `the-loop remove-channel slack@C0TMP375`, from an authorized
  user, on the work item — configurable at
  `routing.control.keywords.remove-channel`.
- You rarely need this at the end of a work item: closing it clears the declarations,
  which is also what frees the channel for the next work item.
