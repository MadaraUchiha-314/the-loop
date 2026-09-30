# Running several instances

One `cli-config.yaml` is one **instance** of the-loop: one set of daemons, one state root,
one set of sessions. Until [issue-322](https://github.com/MadaraUchiha-314/the-loop/issues/322)
every instance was the same instance — each judged every labelled event identically, so two
laptops watching one repository both spawned a session for one `the-loop start`, in two
checkouts, with two dev servers fighting over one port.

An instance now has a **name**, a **scope mode**, and a **declared list** of the work items
it manages, all under the [`instance`](/config/cli/instance-options) block. The environment
each instance runs in — the machine, the container, the checkout root, the port range —
stays yours to provide; the-loop hands the session its instance's name and nothing else.

## The shape of it

```mermaid
flowchart LR
  GH["GitHub: the-loop start instance:laptop-b on #15"]
  GH --> A["laptop-a · addressed<br/>not named → drop, silently"]
  GH --> B["laptop-b · addressed<br/>named → spawn, record instance: laptop-b"]
  GH --> C["ci-box · locked<br/>not declared → drop, silently"]
  B --> S["session for #15<br/>THE_LOOP_INSTANCE=laptop-b"]
```

Every instance sees every delivery — a webhook fans out, a poller reads the same thread.
What changes is that each instance now answers *is this mine?* before it does anything,
and the answer is deterministic given the config and the comment.

## The three modes

| Mode | Takes a new work item when… |
|------|-----------------------------|
| `open` (default) | any armed, authorized start arrives — the behaviour before the block existed |
| `addressed` | the start names it: `the-loop start instance:<name>`, or `the-loop sessions start` runs on it |
| `locked` | never; `scope.workItems` is the only door |

A work item an instance **already manages** — declared in its config, or with a session
or control record on it — is handled in every mode exactly as before: comments are
delivered, `stop` stops it, a close closes it. The mode decides only what happens to a
work item the instance has never seen.

The steady state for several instances is **every instance `addressed`**: every start
then says which one runs it, and nothing is taken twice. `open` is for one instance;
`locked` is for an instance you want frozen to what it has.

## Addressing an instance

Add `instance:<name>` anywhere in a control comment:

```text
the-loop start instance:laptop-b
the-loop do instance:ci-box run the flaky suite ten times and report
the-loop stop instance:laptop-b
```

The token composes with every keyword. It is read as a whole word, the prefix is
case-insensitive, and the name must fit `^[a-z0-9][a-z0-9-]{0,39}$` or the token is not
an address at all — nothing else from the comment reaches a decision, a log line or a
record. An explicit address is **authoritative**: an instance not named drops the comment
even for a work item it manages, and a comment naming two different instances is dropped
by all of them.

Alternatively, run the command on the instance itself: `the-loop sessions start <ref>`
typed on `laptop-b` is by definition addressed to `laptop-b`. The keyword it posts back to
the ticket carries `instance:laptop-b`, so the thread says which instance acted.

## Pinning and locking

Declare a work item in the config to pin it to an instance:

```yaml
instance:
  name: ci-box
  scope:
    mode: locked
    workItems:
      - github:octo/repo#15
      - https://github.com/octo/repo/pull/16
```

A declared work item is taken without an address, in any mode. A `locked` instance takes
*only* what is declared — an address does not unlock it — so the edit is the paper trail.
The block is hot-reloaded: the next event sees the new scope.

## What the record says

- **The portable record** (`<state.root>/portable/<slug>.json`, `control.instance`) names
  the instance that recorded each control command. It travels with the work item.
- **The thread** carries the instance on every keyword the CLI posts and on the session
  announcement's table.
- **`the-loop status`** prints one line —
  `instance    laptop-b [addressed] — 2 declared, 5 managed` — and `GET /api/v1/instance`
  (also the `get_instance` MCP tool and `loop.instance()` on the SDK) returns the full
  document: name, scope, and the managed set with the source of each entry.
- **The event log** records every drop with its reason: `unaddressed`,
  `instance-locked`, `addressed-elsewhere`, `ambiguous-address`. An authorized keyword
  that was refused is a `control.rejected`; anything else is a `dispatch.dropped`. A
  refused instance leaves **nothing** on the thread — no reaction, no comment — because
  another instance may own the work item.

## What the design does not do

- **Two `open` instances still clash.** The mode makes the steady state reachable, not
  automatic. Name every instance and set them `addressed`.
- **A work item declared on two instances is managed by both.** That is your declaration.
- **A refused comment is not re-judged** when the scope changes; it was settled. Claim the
  work item with `the-loop sessions start` on the instance, which is the addressed form.
- **Instances share nothing** and never talk to each other. A [manager](#running-a-manager)
  is a client of them, never a peer: it reads each instance's `GET /api/v1/instance` and
  routes through the same surface ([decision-110](/decisions/decision-110),
  [decision-138](/decisions/decision-138)).

## Running a manager

One URL for the whole fleet. A **manager** is an instance whose config says
`instance.role: manager` and lists the others under `instance.manager.instances`
([issue-374](https://github.com/MadaraUchiha-314/the-loop/issues/374),
[decision-138](/decisions/decision-138)). It keeps everything a worker does — its
ingresses, its scope, its sessions — and also serves the registered instances through
the **same `/api/v1`**: point the dashboard, the CLI, an MCP client or the SDK at it and
they see the fleet as one instance.

```yaml
instance:
  name: hq                      # a manager must be named
  role: manager
  scope:
    mode: addressed             # its worker half is scoped exactly as before
  manager:
    instances:
      - name: laptop-a          # the member's own instance.name
        url: http://10.0.0.5:4114
      - name: ci-box
        url: http://ci:4114
    timeoutSeconds: 10
    probeIntervalSeconds: 15
```

**Reach.** Whoever can reach the manager's port reaches every member's sessions, config
and restart through it. The manager adds no credential and forwards none
([decision-059](/decisions/decision-059)): a member on another box is `service.exposed:
true` behind *your* VPN, tunnel or gateway, and the manager sits inside the same boundary.

**What the manager does with the surface:**

| Operation | On a manager |
|-----------|--------------|
| a list read (`work-items`, `sessions`, `standing-sessions`, `attention`, `daemons`, `events`) | its own rows plus every live member's, each stamped `instance`; a member it could not reach is named in the `The-Loop-Instances-Unreachable` header and `health` is `degraded` |
| an operation keyed by a work item or a standing session | routed to the one instance that manages it; none is `404`, two is `409` naming both — say `instance=<name>` to pick |
| an operation keyed by a checkout path or a daemon (`graph/*`, `repo/*`, `daemons/control`) | the manager's own machine without `instance`, exactly as on a worker; a member's with it |
| `config`, `restart`, `health`, `instance` | the manager's own without `instance`; proxied to a member with it — how one instance is managed on its own |
| `stream` | every member's frames fanned in over one upstream connection per live member, the cursor one offset per instance |

**The name check.** The manager trusts a URL only once `GET /api/v1/instance` there
answers with the registered name and `role: worker`. Until then the member shows as
`unreachable` or `mismatched` in `the-loop instances list`, the Instances tab and
`GET /api/v1/instances`, and nothing is served from it or sent to it. An unnamed worker
cannot be a member: name it first. A registered URL that answers as another manager is
`mismatched` too — the fleet is flat
([nested managers](https://github.com/MadaraUchiha-314/the-loop/issues/438) are a
follow-up).

**Registering.** Four ways, one key: edit `manager.instances` by hand, click *Register*
on the dashboard's Instances tab, run
[`the-loop instances register <name> <url>`](/cli/commands/instances), or
`POST /api/v1/instances/register`. The last three write the file through the same splice
the Settings tab uses, so your comments survive and the change is live on the next request
— no restart. `instance.role` itself is boot-only.

**The `instance` parameter** is part of the one contract: a worker accepts it too, as its
own name only. So a client that never learned it and points at a manager gets the
manager's own state for every self-keyed operation and the union for every list, and a
worker that becomes a manager breaks no client.

## Next

- **[Instance options](/config/cli/instance-options)** — the keys, `role` and `manager.*` included.
- **[`the-loop instances`](/cli/commands/instances)** — list the fleet, register, unregister.
- **[State on disk](/cli/state)** — where `control.instance` lives.
- **[Concepts](/cli/concepts)** — arming, starting, and the guards this sits behind.
