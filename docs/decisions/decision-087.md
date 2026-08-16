# Decision 087: Server-Sent Events, not WebSocket, for the control-plane stream

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-239](https://github.com/MadaraUchiha-314/the-loop/issues/239)
- **Deciders:** maintainer (approved at `design-approval`, PR #244); harness (proposal)

## Context

The control plane learned nothing until it asked again. Every screen was driven by a
two-round poll on a fixed timer — four flat list calls, then one `POST /graph/check` per
loop — so at the shipped 15-second default an operator watching an agent work saw each
turn up to fifteen seconds late, and the cost of looking sooner was paid by the whole
board.

The ticket asked for the service to push instead, and left one question open in as many
words: *"websocket or SSE? would be an interesting choice to make here"*.

They are usually presented as a performance trade — bidirectional and binary against
simple and text — and on that axis the answer here would be a shrug. Nothing in this
feature needs the browser to send anything: replies to an agent already have a route
(`POST /api/v1/sessions/reply`, issue-208), and the stream is a **read** surface over
records `GET /api/v1/events` already serves.

## Decision

**Server-Sent Events**, served from `GET /api/v1/stream` as an ordinary `async def` route
returning `text/event-stream`.

The deciding reason is not performance. It is that **the WebSocket handshake is exempt
from CORS**.

Every other route on this service is governed by `service.cors.allowOrigins` (issue-211,
decision-077) — an allowlist an operator configures, shipping with exactly the origin
the-loop publishes its own dashboard to. The browser enforces it; the service installs one
middleware and every route inherits the boundary. A WebSocket upgrade is not a CORS
request: the browser sends it from **any** origin and the server alone decides. Choosing
WebSocket would therefore mean writing an `Origin` check by hand, in one route, to recover
a boundary the rest of the surface gets for free — and a version of that route which
forgot it would look completely normal in review while silently having no origin check at
all, on a service that carries no in-app authentication (decision-059).

SSE keeps the boundary structural. There is no second code path to get wrong.

The rest of the comparison points the same way, which is why this was not a close call:

| | SSE | WebSocket |
|---|---|---|
| Origin allowlist | the existing `CORSMiddleware`, no new code | hand-written, or absent |
| Direction | server→client, which is all this needs | bidirectional; nothing wants it |
| Resume after a drop | `Last-Event-ID` resent by the browser | hand-rolled |
| Reconnect | built into `EventSource` | hand-rolled |
| New dependency | none — Starlette's `StreamingResponse` | `uvicorn[standard]` / `websockets` |

## Consequences

**What it costs.** SSE takes one of the browser's ~6 HTTP/1.1 connections per origin. The
board's first round issues five parallel calls, so with the stream open that is exactly six
— at the cap, nothing queued; the second round's four workers then run against a free pool
of five. Measured rather than assumed, and small enough to accept. A WebSocket would not
have counted against that pool.

**What it constrains.** The stream is text and one-directional for good. A future feature
wanting the browser to *push* — steering an agent over the same socket, say — does not
extend this; it takes a route of its own, and re-opens this decision on its own merits.

**What it does not change.** The service still has no in-app authentication. Anyone who
can reach the base URL and is allowed by CORS can read the stream, exactly as they can
already read `GET /api/v1/events`; streaming makes that cheaper to do continuously. The
mitigations are the existing ones — loopback by default, `exposed: true` as a deliberate
act, a gateway in front — and `service.stream.maxSubscribers` bounds what one workstation
will serve.

## Alternatives considered

**WebSocket with a hand-written `Origin` check.** Rejected on the argument above: it
reproduces an existing boundary in a second place, where its absence is invisible.

**Long-polling `GET /api/v1/events` with a `since` cursor.** No new endpoint and no new
concept, but it is polling with extra steps — and it cannot carry the transcript watch or
the `desync` signal without inventing a payload anyway. It also would not have solved the
real problem: a stream of event-log records alone does **not** refresh the board, because
loop position comes from `graph/check` over `graph-state.json` and is not in the event
log's shape.

**An in-process pub/sub instead of tailing the file.** Rejected because it would see a
fraction of the traffic. The poller and the webhook receiver may run hosted in the service
process or as separate ones, and the harness and the `sessions` CLI always run elsewhere;
`events.jsonl` is the only place all of them meet (decision-025).
