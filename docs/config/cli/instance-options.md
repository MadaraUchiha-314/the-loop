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
  role: worker
  scope:
    mode: addressed
    workItems:
      - github:octo/repo#15
      - https://github.com/octo/repo/pull/16
  # manager:                    # read only when role is manager
  #   instances:
  #     - name: laptop-a
  #       url: http://10.0.0.5:4114
  #   timeoutSeconds: 10
  #   probeIntervalSeconds: 15
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

### `role`

- **Type:** `string` — `worker` \| `manager`
- **Default:** `worker`

What this instance is ([issue-374](https://github.com/MadaraUchiha-314/the-loop/issues/374),
[decision-138](/decisions/decision-138)). A **worker** is every instance before the role
existed. A **manager** keeps everything a worker does — its ingresses, its scope, its
sessions — and also serves the instances registered under `manager.instances` through the
same `/api/v1`: a list read is its own rows plus every member's, each stamped `instance`;
an operation keyed by a work item routes to the instance that manages it; the dashboard's
Instances tab and [`the-loop instances`](/cli/commands/instances) manage the registry.
See [running a manager](/cli/instances#running-a-manager).

A manager **must be named**: its own rows and events carry its name. `the-loop start`
refuses to boot on a role outside the two values or on an unnamed manager, rather than
guessing; every other reader (`status`, the daemons) warns and reads `worker`. The role is
**boot-only** — a change through the dashboard or the API is reported as
`restartRequired` — while everything under `manager` is hot.

## The fleet

### The registry — `manager.instances`

An array of `{name, url}` objects, empty by default.

The registered instances — the fleet a manager serves. `name` is the member's own
`instance.name`; `url` is its service address as this manager reaches it (`http` or
`https`, an optional path prefix, no userinfo). The manager **trusts a URL only once**
`GET /api/v1/instance` there answers with the registered name and `role: worker`: until
then the member shows as `unreachable` or `mismatched`, and nothing is served from it or
sent to it. An entry outside the name grammar, a duplicate name, a non-`http(s)` URL or
this manager's own address is warned about by position and skipped.

The manager itself is the fleet's first member implicitly and is never listed here. Four
ways write this key, and they are one path: a hand edit, `POST /api/v1/instances/register`
/ `unregister`, the dashboard's Instances tab and `the-loop instances register` /
`unregister` — the last three splice the file exactly as `POST /api/v1/config` does, so the
comments survive and the change is live on the next request.

### `manager.instances[].name`

- **Type:** `string`, matching `^[a-z0-9][a-z0-9-]{0,39}$`
- **Default:** none — required

The member's own `instance.name`; the manager's key for it everywhere.

### `manager.instances[].url`

- **Type:** `string`, `http://` or `https://`
- **Default:** none — required

The member's service origin, optionally with a path prefix.

### `manager.timeoutSeconds`

- **Type:** `number` (seconds), at least 1
- **Default:** `10`

How long one request to a member may take. A list read leaves a member that exceeds it
out of the answer (the response header `The-Loop-Instances-Unreachable` names it); a
keyed operation to it fails with `502`. A value below 1 clamps up.

### `manager.probeIntervalSeconds`

- **Type:** `number` (seconds), at least 1
- **Default:** `15`

How long a probe of a member — `GET /api/v1/instance`, the name check — stays fresh
before the next request re-probes it. `GET /api/v1/instances` and the Instances tab read
the fleet at this freshness. A value below 1 clamps up.

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
