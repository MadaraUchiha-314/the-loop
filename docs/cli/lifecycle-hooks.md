# Hooking the lifecycle

A **lifecycle hook** is code of your own that the-loop asks at the moments a work item's
delivery turns — a start is accepted, a session is about to launch, the loop waits on a
person, the phase changes, the ticket closes — **before it acts**
([issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344),
[decision-137](/decisions/decision-137)). Each moment is a **point** with a typed context:
**facts** you read, **decisions** you may change. Return the context and the-loop applies
your decisions; return `None` and nothing changes. Write the hook once; run it inside
the-loop's process or as a service you host.

It is not the other hook. A [graph hook](/cli/hooks) is a *check at a node boundary* —
"is `design` satisfied?" — with a `pass | block | wait | skip` verdict. A lifecycle hook
does not gate a node, and a graph hook never sees a spawn. Reach for a graph hook to add a
gate to the process; reach for a lifecycle hook to change what the-loop does around the
work — telemetry at start and finish, a roster that refuses a start, house rules prefixed
to every boot prompt, a silenced announcement.

And it is not the event log. The [first attempt](https://github.com/MadaraUchiha-314/the-loop/pull/357)
attached hooks to every event type; an event is a record of something already done, so no
hook on one can change it. The six points below are chosen by what delivery *is*.

## Write it

```python
# ~/.the-loop/hooks/acme.py
from the_loop.sdk.hooks import LifecycleHooks, SessionSpawn, WorkItemStart

ROSTER = {"alice", "bob"}
HOUSE_RULES = "Follow the ACME delivery standard: …"


class Acme(LifecycleHooks):
    def work_item_start(self, ctx: WorkItemStart):
        if ctx.actor not in ROSTER:
            ctx.proceed = False
            ctx.reason = f"{ctx.actor} is not on the delivery roster"
            return ctx
        return None                                  # pass through unchanged

    def session_spawn(self, ctx: SessionSpawn):
        ctx.prompt = HOUSE_RULES + "\n\n" + ctx.prompt
        return ctx

    def work_item_complete(self, ctx):
        telemetry.send("work_item.ended", ctx.to_params())   # a side effect; no decision
        return None
```

One method per point you care about; the others pass through. A method may edit the
context in place or return a rebuilt one — the-loop reads back the **decision fields
only**, so setting `ctx.work_item` changes nothing. A method that raises is recorded
(`hooks.failed`) and skipped; the operation proceeds — unless the entry is `required`
(below).

## Declare it

In your [CLI config](/config/cli/hooks-options), top level, beside `critics` and `graphs`:

```yaml
hooks:
  - name: acme
    path: hooks/acme.py                    # relative to THIS file's directory
    required: true                         # its failure at a `proceed` point refuses
  - name: telemetry
    module: acme_loop_hooks.telemetry      # or an installed dotted module
    with: {team: platform}                 # kwargs to the class
    on: [work_item_start, work_item_complete]
  - name: compliance
    url: https://hooks.acme.example/the-loop
    tokenEnv: ACME_HOOKS_TOKEN
```

Executors run in **this order** at every point they handle; each sees the decisions the
one before it made. A `path` resolves against the config file's directory, never a
checkout — a session cannot plant a module where its own daemon will import it. `the-loop
hooks` prints the declaration without importing or contacting any of it; a daemon loads it
at start and **refuses to start** on one it cannot load. Every key is on the
[options page](/config/cli/hooks-options).

## The points

`the-loop hooks points` prints this table from the code.

### `work_item_start`

Fires **once per arming**, when an authorized start is accepted — before the workspace is
prepared or any session exists. Facts: `work_item`, `loop`, `command`, `actor`, `harness`,
`instance`. Decisions: **`proceed`** (`false` disarms the work item, posts one
marked comment on the ticket with your `reason`, settles the event — nothing is retried),
**`reason`**.

### `session_spawn`

Fires before **every** harness launch — the first spawn, a pull request's own session, a
respawn after a dead one — with the prompt rendered. Facts: `work_item`, `endpoint`,
`harness`, `cwd`, `model`, `effort`, `harness_args`, `respawn`, `loop`. Decisions:
**`prompt`** (the text the harness boots on, replaced), **`proceed`** (`false` prevents
the launch: a first spawn or respawn is settled as refused with the comment; a pull
request's session falls back to delivery into the work item's session), **`reason`**.

### `session_spawned`

Fires after the session is registered, before the-loop posts its "session exists, attach
here" comment. Facts: `work_item`, `endpoint`, `harness`, `harness_session_id`,
`tmux_target`, `cwd`, `model`, `effort`, `harness_args`, `respawn`. Decision:
**`announce`** (`false` skips the comment).

### `waiting_for_input`

Fires before an agent's question is posted (`the-loop ask`, `kind = question`) and when
the graph enters a human gate (`kind = gate`). Facts: `work_item`, `kind`, `node`, `actor`,
`loop`. Decisions: **`question`**, **`summary`** — the text published for an agent's
question; for a gate the request text is the graph's, so both are empty and a change is
ignored.

### `phase_changed`

Fires when the `loop:<phase>` label changes or a terminal node is reached — before the
channels are told. Facts: `work_item`, `loop`, `from_node`, `to_node`, `from_phase`,
`to_phase`, `outcome`, `actor`, `terminal`. Decision: **`notify`** (`false` skips the
`phase.*` publish to the channels for that transition).

### `work_item_complete`

Fires when the ticket or pull request that *is* the work item closes or merges — before
the closure is announced. Facts: `work_item`, `state`, `kind`, `reason`, `source`, `actor`,
`loop`. Decision: **`announce`** (`false` skips the `work-item.closed` publish).

## The context objects

The base class has one method per point. Each takes that point's context and returns
`None` (pass through) or the context with its decisions changed:

```python
class LifecycleHooks:
    def work_item_start(self, ctx: WorkItemStart) -> Optional[WorkItemStart]: ...
    def session_spawn(self, ctx: SessionSpawn) -> Optional[SessionSpawn]: ...
    def session_spawned(self, ctx: SessionSpawned) -> Optional[SessionSpawned]: ...
    def waiting_for_input(self, ctx: WaitingForInput) -> Optional[WaitingForInput]: ...
    def phase_changed(self, ctx: PhaseChanged) -> Optional[PhaseChanged]: ...
    def work_item_complete(self, ctx: WorkItemComplete) -> Optional[WorkItemComplete]: ...

    def handles(self, point: str) -> bool: ...   # does this class override `point`?
```

Every point hands its hook one of these. A field marked `# decision` is read back and
applied; every other field is a **fact** the-loop ignores if changed. Fields are `str`,
`bool`, `list[str]` or a `WorkItem`, so a context travels as JSON unchanged.

`work_item` is the work item the point is about — the-loop's core entity, modelled, on
every context (and `endpoint` on the two spawn points is one too):

```python
@dataclass(frozen=True)
class WorkItem:                          # on every context; built by the-loop, never by a hook
    ref: str                             # github:[HOST/]OWNER/REPO#N — the-loop's name for it, keys everything; a bare issue-N when a graph verb was given one (the rest then empty)
    provider: str                        # github (jira reserved)
    host: str                            # github.com, or a GitHub Enterprise host
    owner: str
    repo: str
    repository: str                      # owner/repo, host-qualified when the host is not the default
    number: int
    kind: str                            # issue | pull-request; "" when the point does not know
    url: str                             # the browser link; "" when none derives
    id: str                              # issue-N — the spec folder under docs/specs/
```

```python
@dataclass
class WorkItemStart(Context):            # point: work_item_start
    work_item: WorkItem                  # the item this start is for (WorkItem, above)
    loop: str                            # the loop it will walk (pdlc-work-item-loop, pdlc-adhoc-loop, yours); "" if unresolved
    command: str                         # the arming word (start | contribute | do | review | an operator's); "" for a label-alone spawn
    actor: str                           # the login that armed it (the event's actor when no command was recorded)
    harness: str                         # claude | cursor
    instance: str                        # routing.instance.name; "" when unnamed
    proceed: bool = True                 # decision — False refuses the start: disarmed, one marked comment, event settled
    reason: str = ""                     # decision — posted on the ticket with the refusal
```

```python
@dataclass
class SessionSpawn(Context):             # point: session_spawn
    work_item: WorkItem
    endpoint: WorkItem                   # the conversation launched: the work item itself, or one of its pull requests (kind = pull-request)
    harness: str                         # claude | cursor
    cwd: str                             # the checkout the session runs in
    model: str                           # the frozen model; "" when the work item chose none
    effort: str                          # the frozen effort; "" when none
    harness_args: list[str]              # the argv the launch adds
    respawn: bool                        # True when this replaces a session found dead
    loop: str                            # the loop recorded in the work item's state; "" if unknown
    prompt: str = ""                     # decision — the text the harness boots on; what you leave is what it gets
    proceed: bool = True                 # decision — False prevents the launch (a PR's session falls back to the work item's)
    reason: str = ""                     # decision — posted on the ticket with the refusal
```

```python
@dataclass
class SessionSpawned(Context):           # point: session_spawned
    work_item: WorkItem
    endpoint: WorkItem                   # the work item itself, or one of its pull requests
    harness: str
    harness_session_id: str              # the harness conversation id (claude --resume <id>)
    tmux_target: str                     # loop-<slug>
    cwd: str
    model: str
    effort: str
    harness_args: list[str]
    respawn: bool
    announce: bool = True                # decision — False skips the "session exists, attach here" comment
```

```python
@dataclass
class WaitingForInput(Context):          # point: waiting_for_input
    work_item: WorkItem
    kind: str                            # question (an agent's `the-loop ask`) | gate (a human node entered)
    node: str                            # the graph node, for a gate; "" for a question
    actor: str                           # who is asking, for a question; "" for a gate
    loop: str
    question: str = ""                   # decision — the text posted for a question; empty and ignored for a gate
    summary: str = ""                    # decision — the channels' one-line summary; same rule
```

```python
@dataclass
class PhaseChanged(Context):             # point: phase_changed
    work_item: WorkItem
    loop: str
    from_node: str                       # "" when the graph is entered
    to_node: str
    from_phase: str                      # "" when the graph is entered
    to_phase: str                        # the new loop:<phase> label
    outcome: str                         # the outcome that routed the edge (pass, approved, …); "" at the start
    actor: str                           # the entered node's actor: agent | human
    terminal: bool                       # True when the terminal node was claimed — the loop is complete
    notify: bool = True                  # decision — False skips the phase.* publish to the channels
```

```python
@dataclass
class WorkItemComplete(Context):         # point: work_item_complete
    work_item: WorkItem
    state: str                           # merged | closed
    kind: str                            # issue | pull-request
    reason: str                          # the dispatcher's reason (issue-closed, pr-merged, …)
    source: str                          # webhook | poll
    actor: str                           # who closed it; "" when the event names nobody
    loop: str
    announce: bool = True                # decision — False skips the work-item.closed publish
```

Three rules hold for every context:

| Rule | What it means for a hook |
|---|---|
| **Decisions only** | Return the context (edited or rebuilt) or a JSON object of decision fields; a changed fact, an unknown key, is ignored. Over the wire, `result` is `null` or `{decision: value, …}`. |
| **Types are kept** | A decision set to the wrong type (`proceed: "yes"`) is that hook's failure — nothing of its answer is applied. |
| **Order is declaration order** | Each executor sees the decisions the ones before it made; the last one's stand. |

## Run it as a service

The same class, hosted:

```python
# hooks_server.py
from the_loop.sdk.hooks import HookServer
from acme import Acme

HookServer(Acme(), host="0.0.0.0", port=8000, token_env="ACME_HOOKS_TOKEN").serve_forever()
```

and declared by `url`. `HookServer` is stdlib (`http.server`); put TLS in front of it, or
mount `handle_request` in your own framework:

```python
from the_loop.sdk.hooks import handle_request

@app.post("/the-loop")
async def hooks(request):
    return Response(handle_request(Acme(), await request.body()), media_type="application/json")
```

### The wire format

JSON-RPC 2.0, one `POST` per point invocation ([sherma's](https://madarauchiha-314.github.io/sherma/hooks.html)
shape). `method` is the point; `params` is the context's fields; the answer is `null`
(pass through) or an object whose **decision** fields replace the context's — any other key
is ignored, and a decision of the wrong type is the hook's failure.

```json
→ {"jsonrpc": "2.0", "id": 1, "method": "work_item_start",
   "params": {"work_item": {"ref": "github:acme/app#42", "provider": "github", "host": "github.com",
                            "owner": "acme", "repo": "app", "repository": "acme/app", "number": 42,
                            "kind": "issue", "url": "https://github.com/acme/app/issues/42", "id": "issue-42"},
              "actor": "mallory", "loop": "pdlc-work-item-loop", …}}
← {"jsonrpc": "2.0", "id": 1, "result": {"proceed": false, "reason": "mallory is not on the delivery roster"}}
```

With `tokenEnv` set, every request carries `Authorization: Bearer <value of that
variable>`, read at call time; `HookServer(token_env=…)` checks the same header. An
`https://` URL, or `http://` on loopback only — a token never travels in clear.

## When a hook fails

| It | Then |
|---|---|
| raises, times out (`timeoutSeconds`, remote only), returns something odd, or the server answers an error or a non-2xx | `hooks.failed` is recorded, the chain continues **unchanged by that hook**, the operation proceeds |
| …and the entry is `required: true`, at `work_item_start` or `session_spawn` | `proceed` becomes `false` with a reason naming the hook — the refusal path above |
| changes a decision | `hooks.decided` names the hook and the fields |
| has `proceed: false` applied | `hooks.refused`, one marked comment on the ticket, the event settled |
| cannot be **loaded** (a bad entry, a missing module, a constructor that raises) | a daemon refuses to start; a one-shot command (`the-loop ask`, `the-loop graph complete`) runs hookless and records `hooks.load_failed` |

A hook never raises into the-loop. Nothing is asynchronous: a hook runs in the path of the
thing it decides, and the thing waits for it — which is what lets it decide.

## Before you adopt one

A `module`/`path` entry runs inside the-loop's process with its credentials, and a `url`
entry receives the facts of every work item — the ref, the actor, the harness, the model,
the boot prompt (which contains the triggering comment), an agent's question. Review an
entry like code. Modules are imported **once per process**: an edited hook is picked up at
the next start.

## See also

- [`hooks` options](/config/cli/hooks-options) — every key.
- [`the-loop hooks`](/cli/commands/hooks) — the report.
- [Adding a hook](/cli/hooks) — the *graph* hooks, for a gate on a node.
- [lifecycle-hooks](/capabilities/lifecycle-hooks) — the capability's current behaviour.
- [decision-137](/decisions/decision-137) — why a catalog and not the event log.
