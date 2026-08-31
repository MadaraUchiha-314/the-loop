# `add-collaborator`

Give one GitHub login a voice on **one** work item.

```bash
the-loop add-collaborator @dana --work-item github:OWNER/REPO#307
the-loop add-collaborator @dana @ann --work-item github:OWNER/REPO#307
the-loop add-collaborator @dana --work-item github:OWNER/REPO#307 --no-comment
```

## What it does

`routing.authorizedUsers` is global: a login directs every work item this daemon
watches, or none of them. So the person who knows one answer on one issue has had no
place at all — both ingress paths drop their comment before anything reads it, and an
agent waiting on a question never hears the reply
([issue-307](https://github.com/MadaraUchiha-314/the-loop/issues/307)).

This grants that person **work-item collaborator** status on one work item. From then on
their comments on it — and on the pull requests whose events already route to its
session — are delivered to that session as agent input.

**That is the entire grant.** A work-item collaborator cannot:

- issue any control command, these two included (so a grant is never transitive);
- spawn a session, or arm one, or satisfy `requireStartCommand`;
- satisfy a human gate — `phase-selection`, `goal-definition`, the review brief,
  artifact approval, security sign-off. Those read `authorizedUsers`, and this does not
  put anybody on it.

> **Not `.the-loop/collaborators.yaml`.** That file names a *project's* stewards and
> their roles (architect, approver, …) for the plugin, and the CLI daemon never reads
> it. This is runtime state: a roster per work item.

Three effects, in this order:

1. **Writes the roster** into the work item's portable record
   (`<state.root>/portable/<slug>.json`, `collaborators` section), with who granted it,
   when, and through which surface.
2. **Posts the same keyword** — `the-loop add-collaborator @dana` — back on the work
   item, carrying the loop-prevention marker, so the thread reads identically whether
   the grant came from the terminal or from a comment. Best-effort: a failing `gh` is
   reported and the grant stands.
3. **Records `control.command`** with the work item, the login, the actor and the
   effect (`granted` / `already-granted`).

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `@LOGIN …` | required | One or more GitHub logins, with or without the leading `@`. |
| `--work-item` | required | The work item the grant is scoped to, e.g. `github:OWNER/REPO#307`. |
| `--portable-dir` | `<state.root>/portable` | Where the rosters live. |
| `--comment` / `--no-comment` | on | Post the keyword back to the work item. |

## Exit codes

| Code | When |
|------|------|
| `0` | at least one login was newly granted |
| `1` | nothing changed — every login named was already a collaborator |
| `2` | a malformed login or work-item ref: **nothing** was written and nothing posted |

## Notes

- **All or nothing.** Every login is validated before any of them is written, so a typo
  in the third name cannot half-apply the first two.
- `@Dana`, `dana` and `@dana` are one person: logins are matched case-insensitively and
  stored without the `@`, the way GitHub treats them. (`routing.authorizedUsers` still
  matches exactly — this changes nothing there.)
- A grant is **scoped to the work item's active life**: it is cleared when the item
  closes, and `the-loop sessions reset` forgets it. `the-loop cleanup` keeps it, as it
  keeps the control record — cleanup releases local resources, and a roster is tracking.
- The same grant can be made from the ticket, by an authorized user commenting
  `the-loop add-collaborator @dana`. The keyword is configurable at
  `routing.control.keywords.add-collaborator`; setting it to `""` disables the word.
- Runs **in-process**, not through the control-plane service — deliberately, like
  [`ask`](/cli/commands/ask) and `sessions reset`: a roster must stay fixable when
  nothing else of the-loop is running.
- Authorization on this path is shell access to the machine running the-loop, exactly as
  it is for `sessions start|stop|pause|resume|cleanup`. The stricter test — a named
  login in `routing.authorizedUsers` — is the comment path's, because that is where an
  untrusted author can reach.
