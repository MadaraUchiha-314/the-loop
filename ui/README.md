# the-loop — control-plane dashboard

A static web app over [`/api/v1`](../docs/api-specs/openapi/the-loop.v1.yaml): every work
item the-loop is tracking, where each one sits in its process graph, the pull requests
delivering it with their own inner loops, what needs a human, and the event log.

It is a **client only**. It reads and drives the service that
[`the-loop service start`](../docs/cli/commands/service.md) already exposes, and adds no
state and no server of its own.

## Running it

```bash
cd ui
bun install
bun run dev          # http://localhost:5173
```

Point it at a workstation on the **Settings** screen; the base URL is kept in that
browser's `localStorage`. With no service reachable, switch the data source to **Demo
fixture** — a bundled dataset in the same record shapes, always shown behind a banner.

| Command | What it does |
|---|---|
| `bun run dev` | Vite dev server |
| `bun run build` | `tsc --noEmit`, then a production bundle into `dist/` |
| `bun run test` | Vitest (unit + React) |
| `bun run lint` | oxlint, type-aware |
| `bun run typecheck` | `tsc --noEmit` alone |

## Reaching a service from a hosted page

The service **binds loopback by default** and carries **no in-app auth** — deliberately,
both of them ([decision-059](../docs/decisions/decision-059.md); auth belongs to a
gateway). What it no longer does is refuse to be read: since
[issue-211](https://github.com/MadaraUchiha-314/the-loop/issues/211) the origins allowed
to read it are configuration, and **this page's origin is the shipped default**
([decision-077](../docs/decisions/decision-077.md)):

```yaml
# ~/.the-loop/cli-config.yaml
service:
  cors:
    allowOrigins: ["https://madarauchiha-314.github.io"]
```

So the hosted page against a service on the **same machine** needs nothing. Two cases
still do:

```bash
# a service on ANOTHER machine — bring the port to the browser's machine
ssh -L 4114:127.0.0.1:4114 workstation

# a copy of this page hosted somewhere else — add that origin to allowOrigins
```

When a call still fails, the browser reports it as an opaque `TypeError`; the app
translates that into the same advice rather than "failed to fetch".

## Where the screens get their data

Nothing here is a new endpoint. The interesting part is the **join**, which lives in
[`src/api/model.ts`](src/api/model.ts):

| Screen | Reads |
|---|---|
| Dashboard | `GET /work-items` + `GET /sessions` + `GET /attention`, then one `POST /graph/check` per loop |
| Work item | the same, plus `GET /events?workItem=…` |
| Attention | `GET /attention`, unioned with the parked gates from the graph reports |
| Events | `GET /events` |
| Chrome | `GET /daemons` |
| Settings | `GET /health` |

Two facts shape that:

- **Loop position needs two records.** `POST /graph/check` takes a `repo` — a filesystem
  path on the service's machine — and a spec-folder id. The path is only in the *session*
  record (`cwd`); the id is only in the *work-item* record (`graph.workItem`). So the
  board paints twice: the flat lists first, the positions as they arrive. An item with no
  session on this machine shows its frozen node list with no pointer, never an error.
- **A pull request is a session, not a lookup.** Since
  [issue-172](https://github.com/MadaraUchiha-314/the-loop/issues/172) the session record
  holds one endpoint per PR delivering the work item, each with its own tmux target and
  its own `pdlc-pr-loop`. `prRepo` is sent only when the PR lives in another repository
  ([issue-183](https://github.com/MadaraUchiha-314/the-loop/issues/183)); sending it
  otherwise points the call at the wrong state directory.

## Not yet served by the API

Two surfaces from the approved design are built and **visibly disabled**, with the route
that would light them up named in the UI itself. They are inert rather than absent so the
gap is legible, and so they start working the day the service can back them.

| Surface | Needs | Why it is not faked |
|---|---|---|
| Inline reply to an agent's question | `the-loop ask` → a `session.awaiting_input` event, and `POST /api/v1/sessions/reply` (bracketed paste into the pane) | Today `the_loop/interaction.py` directs the *agent* to post its question with `gh` itself, so there is no event to key on and no route to answer through. The card reads the event the proposed verb would emit, so it appears on its own once it ships |
| Trace of turns and tool calls | a transcript route | the-loop runs the harness as a CLI in tmux, so the structured record is the harness's own file. For Claude Code that is `~/.claude/projects/<cwd-slugged>/<session-id>.jsonl`, fully derivable from what the service already records — the app **shows the path** and falls back to the event-log trail. Cursor keeps chats in an undocumented SQLite store, so it has no equivalent |

One more thing the API deliberately does not serve: a work item's **title**, and a PR's
**checks and review state**. Those are GitHub's, and the portable record keeps the `ref`
and the `url` rather than a copy of the ticket's mutable fields. The dashboard links out
instead of inventing them.

## Deployment

`.github/workflows/docs.yml` builds both apps and publishes one Pages artifact:

```text
/the-loop/       the VitePress docs site
/the-loop/ui/    this app
```

Pages serves a single artifact per origin, so the two cannot each own a deploy — the
dashboard's `dist/` is copied into the docs output under `ui/` before upload. `UI_BASE`
must match that path; Vite bakes it into every asset URL.

Routing is **hash-based** (`#/item/github:octo/repo%2315`) because Pages 404s any path the
build did not emit, so a history-API router would break every deep link on refresh.

## Layout

```text
src/
  api/        types.ts (the records /api/v1 serves) · client.ts (HTTP) · model.ts (the join)
  demo/       the bundled fixture, behind the same interface as the HTTP client
  state/      settings (localStorage) · hash route · the board's fetch/poll loop
  components/ the Industry primitives: blueprint frame, node rail, session dot
  views/      one file per screen
  styles/     industry.css (vendored design system — do not hand-edit) · app.css
```

`src/styles/industry.css` is the design-system export, copied verbatim so the app renders
what was signed off. Retuning the look means re-exporting it; app rules go in `app.css`.
