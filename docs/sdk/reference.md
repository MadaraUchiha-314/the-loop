# SDK reference

Everything on this page is public and changes under semantic versioning. Everything else in
the `the_loop` package — `the_loop.core`, `the_loop.api`, and the rest — is internal and may
change in any release.

```python
from the_loop.sdk import TheLoop, check_environment, REQUIREMENTS, Requirement, DEFAULT_PREFIX
```

## `TheLoop`

```python
TheLoop(config_path=None, *, config=None)
```

The SDK entry point. Reads one [CLI config](/config/cli/) and drives one state root, exactly
as one `the-loop` process does.

- `config_path` — the file to read. Omit for the standard resolution order
  (`$THE_LOOP_CLI_CONFIG`, `./.the-loop/cli-config.yaml`, `~/.the-loop/cli-config.yaml`).
- `config` — a config document to use instead of reading a file, for tests and for
  deployments that assemble config from a secret store.

Passing both raises `ValueError`. A missing file raises `FileNotFoundError` naming it; an
unparseable one raises `ValueError` naming it.

### Configuration

| Member | Returns | Notes |
|--------|---------|-------|
| `config` | `dict` | the CLI config as it is *now* |
| `config_path` | `Path` | what `config` is read from, and what `settings` writes to |
| `reload()` | `dict` | re-read the file if it changed; the HTTP seam does this once per request on its own |

### Host and deployment

| Member | Returns | Notes |
|--------|---------|-------|
| `check_environment()` | `dict` | which external binaries this config needs, and which are present — see [environment](/sdk/environment) |
| `status()` | `dict` | per-service status of the **standalone** deployment this config describes |
| `host_ingresses()` | `bool` | whether this process runs the enabled ingresses |

`start`, `stop` and `restart` are deliberately absent: they spawn and kill the-loop's own
processes, which inside your service is either meaningless or actively wrong. Your process's
lifecycle is yours.

### The HTTP seam

```python
router(**kwargs)                       # -> fastapi.APIRouter
mcp_app(*, allowed_hosts=None)         # -> ASGI app, or None when service.mcp.enabled is false
lifespan(app=None)                     # -> async context manager
mount(app, *, prefix="/the-loop", dependencies=None, lifespan=True, mcp=True,
      host_ingresses=None, mcp_allowed_hosts=None, **router_kwargs)   # -> dict report
```

`router(**kwargs)` passes through to `fastapi.APIRouter` — most usefully
`dependencies=[Depends(...)]`. `mcp_app` is built once and cached, because the object that
gets mounted has to be the object whose session manager the lifespan starts. `mount` returns
a report:

```python
{'prefix': '/the-loop', 'operations': 29,
 'mcp': {'mounted': True, 'path': '/the-loop/mcp'},
 'lifespan': 'wrapped', 'hostIngresses': True, 'dependencies': 1}
```

See [Embedding](/sdk/embedding) for all of it in context.

## Capability namespaces

Every method delegates to the-loop's core and returns JSON-shaped `dict`s and `list`s.
Failures are exceptions: `ValueError` for a caller mistake, `LookupError` for a resource
that is not there.

### `loop.work_items`

| Method | Returns |
|--------|---------|
| `list()` | every portable work-item record, ordered by ref |
| `get(ref)` | one record; `ValueError` on a malformed ref, `LookupError` when absent |

### `loop.sessions`

| Method | Returns |
|--------|---------|
| `list(status=None)` | every registered session with its last control command |
| `get(ref)` | one session |
| `transcript(ref, tail=200)` | the tail of a session's transcript |
| `control(ref, verb, comment=True)` | apply a control verb (start/stop/pause/resume/…) |
| `reply(ref, text, actor="", comment=True)` | deliver a human reply into a waiting session |
| `ask(ref, question)` | post an agent's question on its work item and record the wait |
| `register(ref, harness, harness_session_id, cwd=".", force=False)` | link a work item to the session working it |
| `link_pr(ref, pull_request)` | record a pull request as delivering a work item, so its comments, reviews and CI route to that work item's session — the step a session runs as it opens the PR |
| `close(ref, keep_tmux=None)` | close a session and release its resources |

### `loop.standing`

The sessions that belong to **no work item** ([standing sessions](/capabilities/standing-sessions),
issue-277) — addressed by **name**, never by a ref, because the two namespaces are
separate: nothing routed by ref reaches one, and nothing here reaches a work item's
session.

| Method | Returns |
|--------|---------|
| `list()` | every declared or recorded standing session, `running` answered by tmux |
| `get(name)` | one session; `LookupError` when it is neither declared nor recorded |
| `control(name, verb)` | `start` / `stop` / `restart`, idempotent in both directions; an empty `name` means every declared session for `start` and every recorded one for `stop` |
| `create(name, harness='', cwd='', prompt='', description='', harness_args=None, slack_enabled=False, slack_channel='', auto_start=True, start=True)` | bring a session into existence with no config entry, and start it; `ValueError` when the name is already declared or recorded |
| `delete(name)` | stop a **created** session and forget it; `ValueError` for a declared one (the config would recreate it), `LookupError` when it was never created |
| `say(name, text, actor="")` | paste a message into a running session's terminal and submit it; fail-closed — never starts one |

### `loop.graph`

| Method | Returns |
|--------|---------|
| `show(repo, pr=None, pr_repo="")` | the process graph as recorded for a repository |
| `check(repo, work_item, recompute=False, pr=None, pr_repo="")` | where a work item stands — what `the-loop check` reports |
| `complete(repo, work_item, node="", actor="", ref="", pr=None, pr_repo="")` | mark a node's work done |
| `advance(repo, work_item, ref="", pr=None, pr_repo="")` | move to the next node when its gate holds |
| `force(repo, work_item, to_node, reason, actor="", …)` | the audited escape hatch; the reason is required |
| `skip(repo, work_item, nodes, reason, actor="", …)` | record a declared skip, with provenance |

### `loop.events`

| Method | Returns |
|--------|---------|
| `query(types=None, work_item=None, delivery_id=None, source=None, min_level=None, since=None, limit=50)` | matching records from the JSONL event log |
| `types()` | the event-type catalogue, name → description |

### `loop.daemons`

| Method | Returns |
|--------|---------|
| `list()` | status of each ingress daemon (poller, gh-webhook) |
| `control(daemon, verb)` | `start` or `stop` one, idempotently |

### `loop.attention`

| Method | Returns |
|--------|---------|
| `list()` | everything waiting on a human right now |

### `loop.repo`

| Method | Returns |
|--------|---------|
| `scenarios(repo, globs=None)` | the Gherkin scenarios integration tests document |
| `instructions(repo)` | the resolved `customInstructions` docs, and any that failed to resolve |
| `critics(repo)` | the critics that repository's harness config registers |
| `critic_run(repo, name, prompt="", prompt_file="", work_item="", spec_dir="", timeout=None, cwd="")` | run one critic round; the JSON envelope as a dict |

### `loop.settings`

| Method | Returns |
|--------|---------|
| `get()` | the CLI config document, as the API serves it |
| `schema()` | the packaged CLI-config JSON schema |
| `update(patch)` | splice a sparse patch into the file this instance reads |

`update` writes the path this instance already reads — there is no parameter naming a
destination, by design: the config says who may command the loop, so a caller that could
redirect the write would be editing the rules it is judged by. Comments in the file survive
(the patch is spliced into the original text, not round-tripped through a YAML dumper), and
a patch that would produce an invalid document leaves the file byte-identical.

## `check_environment(config=None)`

The environment contract, resolved against `PATH`. `TheLoop.check_environment()` is this
function bound to the instance's config. See [environment](/sdk/environment).

## `REQUIREMENTS` and `Requirement`

The environment contract as data — one frozen `Requirement` per binary:

| Field | Meaning |
|-------|---------|
| `default_binary` | the name looked up on `PATH` when nothing renames it |
| `config_key` | the dotted CLI-config path that can rename it, or `""` when fixed |
| `capability` | what stops working without it |
| `required(config)` | whether *this* configuration needs it |
| `resolve(config)` | the binary name this configuration will actually invoke |

Read it to render your own preflight, your own health check, or your own image
documentation.

## `DEFAULT_PREFIX`

`"/the-loop"` — where `mount()` namespaces the-loop inside a host application. Not `""`: a
root mount would let the MCP endpoint shadow every host route declared after `mount()`.
