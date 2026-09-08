---
configBase: instance
---

# Instance options

Options under `instance` — which instance of the-loop **this** config is, and which work
items it manages ([issue-322](https://github.com/MadaraUchiha-314/the-loop/issues/322);
see [Running several instances](/cli/instances) and
[the capability](/capabilities/instances)). Several instances can watch one repository,
each in its own environment — a machine, a container, a checkout root; the-loop's concern
stops at the session it spawns. This block gives an instance a name, a mode that says how
new work items reach it, and a declared list of the ones it manages.

```yaml
instance:
  name: laptop-b
  scope:
    mode: addressed
    workItems:
      - github:octo/repo#15
      - https://github.com/octo/repo/pull/16
```

Unset, the block is an **unnamed, open** instance — exactly the behaviour before it
existed. The block is hot-reloaded with the rest of the config, so a scope edit is live on
the next event; it is also editable from the dashboard's Settings tab.

The **managed set** is derived, never kept ([decision-110](/decisions/decision-110)): the
`workItems` declared here, plus every work item this instance holds a live session record
or a control record for (a recorded `start`, `stop`, `pause`, `resume`, `contribute`,
`do`, `review` or `cleanup`). A work item in the set is handled in every mode exactly as
before; the mode decides only what happens to a work item **outside** it.

## Identity

### `name`

- **Type:** `string`, matching `^[a-z0-9][a-z0-9-]{0,39}$`
- **Default:** `""` (unnamed)

The instance's name, everywhere it shows: `instance:<name>` on a start comment addresses
it; `THE_LOOP_INSTANCE=<name>` is in the environment of every session it spawns (tmux 3.2
or newer — older tmux omits the variable with one warning), so a dev server the session
starts can derive a port or a container name; the keyword comments the CLI posts carry
`instance:<name>`; the session announcement names it; and `GET /api/v1/instance` and
`the-loop status` report it. The grammar is the standing-session one, and narrow on
purpose: the value is interpolated into a tmux argv and a comment body. A name outside it
is warned about and treated as unset.

Unnamed, nothing can address the instance, and `scope.mode: addressed` resolves to
`locked`.

## Scope

### `scope.mode`

- **Type:** `string` — `open` \| `addressed` \| `locked`
- **Default:** `open`

How a work item this instance does not yet manage reaches it:

| Mode | A new work item is taken when… | Use it for |
|------|--------------------------------|------------|
| `open` | any armed, authorized start arrives — the pre-issue-322 behaviour | one instance; the default, so a lone instance that names itself changes nothing |
| `addressed` | the start comment names this instance (`the-loop start instance:<name>`), or `the-loop sessions start` is run on it | the steady state for several instances: every start says which one runs it |
| `locked` | never — editing `scope.workItems` is the only door | an instance frozen to what it has |

Three rules hold in every mode:

- **An address to another instance is authoritative.** A comment carrying
  `instance:<other>` is dropped by this instance even for a work item it manages; a
  comment naming two different instances is dropped everywhere (`ambiguous-address`).
- **A drop leaves no mark.** No reaction, no comment, no record — another instance may own
  the work item. The event log carries one line naming the reason (`unaddressed`,
  `instance-locked`, `addressed-elsewhere`, `ambiguous-address`): a `dispatch.dropped`,
  or a `control.rejected` when an authorized user typed a keyword. The delivery is
  settled, not retried.
- **Unknown narrows.** A mode the daemon does not know, or `addressed` on an unnamed
  instance, is warned about and resolves to `locked` — never to `open`.

Two `open` instances on one repository both take the same start; that is the clash the
mode exists to end, and the design does not prevent it for you.

### `scope.workItems`

- **Type:** `array` of `string` — `<provider>:[<host>/]<owner>/<repo>#<n>` refs or GitHub
  issue / pull-request URLs
- **Default:** `[]`

Work items this instance manages **by declaration**. The way into a `locked` instance, and
a pre-address on an `addressed` one: an unaddressed start on a declared work item is
taken. A URL is normalised to a ref (`https://github.com/octo/repo/pull/16` →
`github:octo/repo#16`, a GitHub Enterprise host kept). An entry that does not parse is
warned about by position and skipped; the rest are honoured. A work item declared on two
instances is managed by both — that is your declaration, honoured.
