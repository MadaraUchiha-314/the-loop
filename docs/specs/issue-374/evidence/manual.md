# Manual exploratory walk-through (T11): three real services on one machine

Two workers (`laptop-a` :4121, `ci-box` :4122) and a manager (`hq` :4120, registering
both plus a `cloud-1` that is not running) started as `python -m the_loop.api.serve`
— what `the-loop start` spawns — each from its own config and state root under a
scratch directory. Ingresses disabled, MCP disabled, so the walk-through is the control
plane alone. Paths are redacted to `<scratch>`; no credential exists in this setup.

Requirement trace: R1.3, R2.2–R2.9, R3.1, R3.3, R4.2–R4.6, R5.4 (through the API),
abuse cases 6 and 7.

Procedure and output, in order:

```text
### 1. register a session on each worker (directly)
{
    "workItem": "github:octo/repo#1",
    "harness": "claude",
    "harnessSessionId": "a-1",
    "exitCode": 0,
    "messages": [
        {
            "stream": "out",
            "text": "registered github:octo/repo#1 -> claude:a-1"
        }
    ]
}
{
    "workItem": "github:octo/repo#2",
    "harness": "claude",
    "harnessSessionId": "b-2",
    "exitCode": 0,
    "messages": [

### 2. the fleet, from the manager
{
    "role": "manager",
    "name": "hq",
    "instances": [
        {
            "name": "hq",
            "url": "http://127.0.0.1:4120",
            "state": "live",
            "version": "19.14.1",
            "mode": "addressed",
            "managedCount": 0,
            "sessionCount": 0,
            "probedAt": "2026-09-30T00:06:02Z"
        },
        {
            "name": "laptop-a",
            "url": "http://127.0.0.1:4121",
            "state": "live",
            "version": "19.14.1",
            "mode": "addressed",
            "managedCount": 1,
            "sessionCount": 1,
            "probedAt": "2026-09-30T00:06:02Z"
        },
        {
            "name": "ci-box",
            "url": "http://127.0.0.1:4122",
            "state": "live",
            "version": "19.14.1",
            "mode": "addressed",
            "managedCount": 1,
            "sessionCount": 1,
            "probedAt": "2026-09-30T00:06:02Z"
        },
        {
            "name": "cloud-1",
            "url": "http://127.0.0.1:4129",
            "state": "unreachable",
            "version": "",
            "mode": "",
            "managedCount": 0,
            "sessionCount": 0,
            "probedAt": "2026-09-30T00:06:02Z",
            "detail": "<urlopen error [Errno 111] Connection refused>"
        }
    ]
}

### 3. a list read is the union, stamped, with the partial header (cloud-1 is down)
HTTP/1.1 200 OK
the-loop-instances-unreachable: cloud-1
[('github:octo/repo#1', 'laptop-a'), ('github:octo/repo#2', 'ci-box')]
[]

### 4. GET /instance on the manager: the managed set spans the fleet
hq manager [('github:octo/repo#1', 'laptop-a'), ('github:octo/repo#2', 'ci-box')]

### 5. a keyed read routes to the member that manages the ref
github:octo/repo#2 ci-box b-2
unknown ref -> 404
unknown instance -> 404
{"detail":"instance 'cloud-1' is unreachable: <urlopen error [Errno 111] Connection refused>","instance":"cloud-1"}
down member -> 502

### 6. manage one instance individually: its config through the manager
<scratch>/fleet/laptop-a/.the-loop/cli-config.yaml {'name': 'laptop-a', 'scope': {'mode': 'addressed'}}
written True changed ['instance.scope.mode'] on laptop-a
5:    mode: locked
manager's own file untouched:
0

### 7. register through the API (the file keeps its comment); the next read shows it; unregister
written True changed ['instance.manager.instances'] cloud-2
# hq — the manager (a comment that must survive a registration)
      - name: cloud-2
        url: http://127.0.0.1:4130
[('hq', 'live'), ('laptop-a', 'live'), ('ci-box', 'live'), ('cloud-1', 'unreachable'), ('cloud-2', 'unreachable')]
{"detail":"an instance named 'cloud-2' is already registered"} -> 400
{"detail":"this instance manages no others (instance.role is 'worker'); set instance.role: manager in its CLI config to register instances with it"} -> 400 (a worker)
unregister -> 200

### 8. the CLI, routed through the manager's service
name      url                    state        version  mode       managed  sessions
hq        http://127.0.0.1:4120  live         19.14.1  addressed  0        0         (this instance)
laptop-a  http://127.0.0.1:4121  live         19.14.1  addressed  1        1
ci-box    http://127.0.0.1:4122  live         19.14.1  addressed  1        1
cloud-1   http://127.0.0.1:4129  unreachable  —        —          —        —         <urlopen error [Errno 111] Connection refused>
config      <scratch>/fleet/hq/.the-loop/cli-config.yaml
state       <scratch>/fleet/hq/.the-loop
instance    hq [addressed] — 0 declared, 0 managed
instances   hq [manager] — this instance + 3 registered, 2 of 3 live
  name      url                    state        version  mode       managed  sessions
  hq        http://127.0.0.1:4120  live         19.14.1  addressed  0        0         (this instance)
  laptop-a  http://127.0.0.1:4121  live         19.14.1  locked     1        1
  ci-box    http://127.0.0.1:4122  live         19.14.1  addressed  1        1
  cloud-1   http://127.0.0.1:4129  unreachable  —        —          —        —         <urlopen error [Errno 111] Connection refused>
service     running (pid 19030) [enabled] — http://127.0.0.1:4120, healthy, MCP disabled
gh-webhook  not running [disabled]

### 9. the stream: a member's event arrives on the manager's stream, stamped, with a per-member id
id: hq=4694
event: log
data: {"ts":"2026-09-30T00:06:03.487Z","source":"service","event":"stream.subscribed","level":"info","pid":19030,"subscribers":1,"instance":"hq"}
id: ci-box=1734,hq=4694
event: log
data: {"ts":"2026-09-30T00:06:03.489Z","source":"service","event":"stream.subscribed","level":"info","pid":19029,"subscribers":1,"instance":"ci-box"}
id: ci-box=1734,hq=4694,laptop-a=2320
event: log
data: {"ts":"2026-09-30T00:06:03.489Z","source":"service","event":"stream.subscribed","level":"info","pid":19028,"subscribers":1,"instance":"laptop-a"}
id: ci-box=1734,hq=5262,laptop-a=2320
event: log
data: {"ts":"2026-09-30T00:06:06.511Z","source":"service","event":"config.updated","level":"info","pid":19030,"path":"<scratch>/fleet/hq/.the-loop/cli-config.yaml","keys":["instance.manager.instances"],"instance":"hq"}

### 10. the members' own event logs carry the proxied write; the manager's carries the registration
{"ts":"2026-09-30T00:06:06.493Z","source":"service","event":"config.updated","level":"info","pid":19028,"path":"/tmp/claude-0/-home-user-the-loop/8ab8664a-9128-
{"ts":"2026-09-30T00:05:28.977Z","source":"service","event":"instance.unreachable","level":"error","pid":19030,"instance":"cloud-1","reason"
{"ts":"2026-09-30T00:06:02.917Z","source":"service","event":"instance.registered","level":"info","pid":19030,"instance":"cloud-2"}
{"ts":"2026-09-30T00:06:02.934Z","source":"service","event":"instance.unreachable","level":"error","pid":19030,"instance":"cloud-2","reason"
```

## What each step showed

1. A session registered on each worker directly.
2. `GET /instances` on the manager: hq first and live, both workers live with their
   counts, `cloud-1` unreachable with the transport's reason.
3. A list read on the manager is the union stamped per instance, `200`, and the
   response header names `cloud-1` as left out. (`work-items` is empty: a registered
   session writes no portable record, and none was armed.)
4. `GET /instance` on the manager spans the fleet.
5. A keyed read reached the member that manages the ref; an unknown ref is `404`, an
   unknown instance `404` with nothing sent, a down member `502` with the reason.
6. The member's config read and written *through* the manager: the member's file
   changed, the manager's did not.
7. Registering through the API kept the file's comment, the next read showed the new
   member unreachable, a duplicate was `400`, a worker refused naming `instance.role`.
8. `the-loop instances list` and `the-loop status`, routed through the manager's
   service, print the same rows (laptop-a now `locked`, from step 6).
9. The manager's stream carried its own and both members' frames, each stamped, the id
   one offset per instance; the frame for laptop-a's `config.updated` arrived with
   `laptop-a=2743` in the id (the full capture held 6 frames; the excerpt shows the
   first four).
10. Both event logs carry the proxied write and the registration by name.
