# `instances`

The fleet a [manager](/cli/instances#running-a-manager) serves — listed on any
instance, registered and unregistered on a manager
([issue-374](https://github.com/MadaraUchiha-314/the-loop/issues/374)).

```bash
the-loop instances list [--format text|json]
the-loop instances register NAME URL
the-loop instances unregister NAME
```

## `list`

One row per instance: this one first, then — on a manager — every instance registered
under [`instance.manager.instances`](/config/cli/instance-options#the-registry-manager-instances),
from a probe no older than `manager.probeIntervalSeconds`.

```text
name      url                       state        version   mode        managed  sessions
hq        http://127.0.0.1:4114     live         19.15.0   addressed   3        1   (this instance)
laptop-a  http://10.0.0.5:4114      live         19.14.1   addressed   4        2
cloud-1   http://10.0.0.9:4114      unreachable  —         —           —        —   connection refused
```

`state` is `live`, `unreachable` or `mismatched` — the last when the host at the URL
answers as a different name, an unnamed instance or another manager, in which case
nothing is served from it or sent to it. `--format json` prints the document
`GET /api/v1/instances` serves. On a worker the list is one row, itself.

## `register` and `unregister`

Thin clients of `POST /api/v1/instances/register` and `/unregister`: each writes
`instance.manager.instances` in the manager's `cli-config.yaml` through the same splice
the dashboard's Settings tab uses, so the file's comments survive and the change is live
on the next request — a hand edit, the Instances tab, this command and the API are one
path.

`register` validates as the config reader validates — `NAME` must fit
`^[a-z0-9][a-z0-9-]{0,39}$` and be the member's own `instance.name`; `URL` must be
`http://` or `https://` without userinfo; not this manager's own address; not a name
already registered — and exits `2` with the reason, writing nothing. The member need not
be up yet: it shows `unreachable` until it answers to its name. `unregister` of a name
that is not registered exits `1`.

On a **worker** both exit `2` naming `instance.role`: the routes exist on every instance
and do nothing on one that manages none.

| Exit | Means |
|------|-------|
| `0` | listed, registered or unregistered |
| `1` | `unregister`: no such name |
| `2` | a validation failure, a worker, or no reachable service |

## Next

- **[Running a manager](/cli/instances#running-a-manager)** — the role, the registry,
  the name check, the `instance` parameter.
- **[Instance options](/config/cli/instance-options)** — `role`, `manager.*`.
- **[`status`](/cli/commands/status)** — prints the same rows on a manager.
