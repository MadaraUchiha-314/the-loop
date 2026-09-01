# `remove-collaborator`

Take a work-item collaborator's voice back.

```bash
the-loop remove-collaborator @dana --work-item github:OWNER/REPO#307
```

## What it does

The other half of [`add-collaborator`](/cli/commands/add-collaborator), with the same
shape: the local effect first, then the same keyword posted back on the work item so the
thread records the revocation, then `control.command` with the effect (`revoked` /
`not-a-collaborator`).

The revocation takes effect on the **next event**: membership is read per event and
never cached in a running session, so nothing has to be restarted.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `@LOGIN …` | required | One or more GitHub logins, with or without the leading `@`. |
| `--work-item` | required | The work item to revoke on, e.g. `github:OWNER/REPO#307`. |
| `--portable-dir` | `<state.root>/portable` | Where the rosters live. |
| `--comment` / `--no-comment` | on | Post the keyword back to the work item. |

## Exit codes

| Code | When |
|------|------|
| `0` | at least one login was revoked |
| `1` | nothing changed — nobody named was on the roster |
| `2` | a malformed login or work-item ref: nothing was written and nothing posted |

## Notes

- A login that was not on the roster is reported and **not** announced on the ticket: a
  revocation that did not happen does not belong in the thread.
- The keyword form is `the-loop remove-collaborator @dana`, from an authorized user, on
  the work item — configurable at `routing.control.keywords.remove-collaborator`.
- You rarely need this at the end of a work item: closing it clears the roster.
