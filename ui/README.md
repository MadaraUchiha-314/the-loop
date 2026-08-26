# the-loop — control-plane dashboard

A static web app over [`/api/v1`](../docs/api-specs/openapi/the-loop.v1.yaml): every work
item the-loop is tracking, where each one sits in its process graph, the pull requests
delivering it with their own inner loops, what needs a human, and the event log.

It is a **client only**. It reads and drives the service that
[`the-loop start`](../docs/cli/commands/start.md) already exposes, and adds no
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

## Keeping the screen current

Settings offers three ways, stored per browser:

| Mode | What it does | When it is the right one |
|---|---|---|
| **Streaming** | Holds one `GET /api/v1/stream` open; the service pushes each change | Loopback, or a stable tunnel — the default |
| **Polling** | Asks again on a timer (5–60s) | A flaky link: a failed cycle costs one request, where a failed stream is a screen that stops updating |
| **Manual** | No background request at all | A metered or remote workstation you want to look at deliberately |

Streaming refreshes only what a change touches — a graph move re-reads that one work
item's loop position, anything else re-reads the four lists — so watching a busy work item
costs less than the 15-second poll it replaces, not more. The sidebar's health dot opens
into the stream's state — **live**, **reconnecting**, or fallen back to polling and why —
beside each daemon's last cycle (issue-283 B10); it never shows a stale board that looks
current. A service older than the stream, or one with
`service.stream.enabled: false`, answers 404 and the page polls instead.

Demo mode streams too: the frames a demo viewer sees are the ones their own clicks
produced. Nothing invents traffic that did not happen.

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

Two surfaces (issue-298's design, deliberately bare): **Work** — a sidebar of work
items (dot · ref · age · title · a small-caps chip when one needs a human), each with
its pull requests nested beneath it (issue-300: dot · `#216`, or `loop-docs#47` when
the PR is in another repository · age), then standing sessions, with Settings and the
health dot in the footer; the sidebar is the whole navigation — beside one main canvas
showing the selected item's header, rail, trace and chat bar (nothing selected shows
the most recently active item) — plus **Settings**, a reading column behind
"← Work items". The pre-298 screens fold in
rather than disappear: the inbox's gate approval and question reply live on the item's
canvas, and the standalone Events screen is retired — the event trail still renders as
the trace's fallback, and legacy `#/events` hashes land on Work.

| Surface | Reads |
|---|---|
| Work sidebar | `GET /work-items` + `GET /sessions` + `GET /attention`, then one `POST /graph/check` per active loop — the rows' chips are the deduped, tiered attention (needs-input &gt; gate &gt; waits &gt; errors), and the nested PR rows are `sessionTree`'s inner level over the same `/sessions` records (a loop with no outer/inner split renders treeless) |
| Work item canvas | the same, plus `GET /events?workItem=…` (the trace's fallback trail), `GET /sessions/transcript?ref=…` for the viewed trace (outer session or a PR endpoint's), `POST /graph/complete` from the parked-gate card, and `POST /sessions/reply` from the chat bar (issue-230 — the chat bar is also how an agent's question is answered) |
| Standing (a sidebar section of Work) | `GET /standing-sessions`, plus `POST /standing-sessions/{create,delete,control,say}` — the sessions that belong to no work item (issue-277) |
| Sidebar footer | `GET /daemons`, folded with the stream state into one health dot + popover |
| Settings | `GET /health`, plus `GET /config` + `GET /config/schema` and `POST /config` for the CLI-config editor (issue-222) |

The config editor is the one screen that renders itself: its sections, labels, prose,
types, enums and defaults all come from the served schema, so it cannot drift from what
the service accepts, and a subtree with no typed control (a list of poll sources, say) is
edited as JSON rather than left unreachable. Save sends only the keys that changed.

Two facts shape that:

- **Loop position needs two records.** `POST /graph/check` takes a `repo` — a filesystem
  path on the service's machine — and a spec-folder id. The path is only in the *session*
  record (`cwd`); the id is only in the *work-item* record (`graph.workItem`). So the
  board paints twice: the flat lists first, the positions as they arrive. An item with no
  session on this machine shows its frozen node list with no pointer, never an error.
  Neither does one whose checkout has since been deleted: the session record outlives the
  path it names, so `/graph/check` answers `200` with `repoResolved: false` and the board
  drops that answer where a rejection would have been dropped
  ([issue-238](https://github.com/MadaraUchiha-314/the-loop/issues/238)). Read the field as
  `=== false` — it is absent, not `true`, on a normal answer.
- **A standing session joins nothing.** It has no work item, so it appears on no other
  screen and needs none of the board's join — `GET /standing-sessions` is the whole of it.
  That is also why it sits under its own sidebar divider rather than among the work-item
  rows: a session with no ticket, no phases and no completion must not be a row lying
  about being part of one
  ([issue-277](https://github.com/MadaraUchiha-314/the-loop/issues/277),
  [decision-100](../docs/decisions/decision-100.md)). The screen surfaces the service's
  refusals **verbatim** rather than re-wording them, and offers `delete` only for a
  *created* session — the service refuses it for a declared one, and a button whose only
  outcome is that refusal is worse than no button.
- **A pull request is a session, not a lookup.** Since
  [issue-172](https://github.com/MadaraUchiha-314/the-loop/issues/172) the session record
  holds one endpoint per PR delivering the work item, each with its own tmux target and
  its own `pdlc-pr-loop`. `prRepo` is sent only when the PR lives in another repository
  ([issue-183](https://github.com/MadaraUchiha-314/the-loop/issues/183)); sending it
  otherwise points the call at the wrong state directory.

## Every approved surface is now served

The design shipped two surfaces built and **visibly disabled**, each naming the route
that would light it up — inert rather than absent, so the gap stayed legible and each
started working the day the service could back it. Both are live now:

- The inline **reply** to an agent's question went live when
  [issue-208](https://github.com/MadaraUchiha-314/the-loop/issues/208) landed
  `the-loop ask` → `session.awaiting_input` and `POST /api/v1/sessions/reply`
  (bracketed paste into the pane).
- The **trace of turns and tool calls** went live when
  [issue-209](https://github.com/MadaraUchiha-314/the-loop/issues/209) landed
  `GET /api/v1/sessions/transcript`: the harness's own JSONL
  (`~/.claude/projects/<cwd, munged per character>/<session-id>.jsonl`), resolved
  server-side from the `cwd` and session id the service already records, served as a
  bounded tail. When the route answers 404 — no session, no file yet, a Cursor
  session (undocumented SQLite store), an older service — the panel says why and
  falls back to the event-log trail, which is the pre-route behaviour.

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
build did not emit, so a history-API router would break every deep link on refresh. The
hash is also the *only* record of what the canvas shows: its ref may name a work item or
one of its PR sessions, and the sidebar's nested rows and the canvas's trace tabs are the
same links onto it — so no pane-local state can disagree with the URL (issue-300).

## Layout

```text
src/
  api/        types.ts (the records /api/v1 serves) · client.ts (HTTP) · model.ts (the join)
  demo/       the bundled fixture, behind the same interface as the HTTP client
  state/      settings (localStorage) · hash route · the board's fetch loop
              stream.ts (what a frame makes stale) · useStream.ts (the connection)
  components/ the shared primitives: card frame, node-rail tick bar, session dot,
              health dot, transcript + chat bar
  views/      one file per screen
  styles/     classical.css (vendored design system — do not hand-edit) · app.css
```

`src/styles/classical.css` is the Classical design-system export
([issue-298](https://github.com/MadaraUchiha-314/the-loop/issues/298); the signed-off
source lives under `docs/specs/issue-298/design/`), copied verbatim so the app renders
what was signed off. Retuning the look means re-exporting it; app rules go in `app.css`.
