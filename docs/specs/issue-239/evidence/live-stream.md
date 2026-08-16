# Evidence: the stream against a live service (issue-239)

Testing-plan rows **T12** (the thing the work item is for) and **T13** (an older service),
executed at the **service boundary** with `curl`. The browser half of both rows did not
run — see the note at the end, and the Verification results table in `testing-plan.md`.

## The environment

A service built from this branch, on a state root seeded with **real objects**: the work
item is issue-239 itself, and the registered session is *this* Claude Code conversation, so
the transcript watch is pointed at a file that is genuinely being appended to while the
verification runs.

```text
$ THE_LOOP_CLI_CONFIG=<seeded>/cli-config.yaml python -m the_loop.api.serve
INFO:     Uvicorn running on http://127.0.0.1:4139 (Press CTRL+C to quit)

$ curl -s http://127.0.0.1:4139/api/v1/health
{"status":"ok","version":"10.2.1"}
```

The session resolves to a transcript the service can stat:

```text
$ curl -s "http://127.0.0.1:4139/api/v1/sessions/transcript?ref=github:MadaraUchiha-314/the-loop%23239&tail=2"
{"workItem":"github:MadaraUchiha-314/the-loop#239","harness":"claude",
 "harnessSessionId":"41ac9ec6-…","path":"~/.claude/projects/…/41ac9ec6-….jsonl", …}
```

## T12 — a change on the workstation reaches an open subscriber

One `curl -N` holding the stream open. While it was open, another process appended two
records to the event log — which is exactly what the poller, the receiver and the harness
do — and this session's own transcript grew on its own.

```text
$ curl -sN "http://127.0.0.1:4139/api/v1/stream?transcript=github:MadaraUchiha-314/the-loop%23239"
retry: 3000

id: 1995
event: log
data: {"ts":"2026-08-16T18:29:50.547Z","source":"poll","event":"graph.advanced","level":"info",
       "pid":69358,"work_item":"github:MadaraUchiha-314/the-loop#239","node":"verification","to":"needs-review"}

id: 2168
event: log
data: {"ts":"2026-08-16T18:29:50.547Z","source":"poll","event":"session.spawned","level":"info",
       "pid":69358,"work_item":"github:MadaraUchiha-314/the-loop#239","harness":"claude"}

event: transcript
data: {"ref":"github:MadaraUchiha-314/the-loop#239","totalLines":1720}
```

Four things this shows at once:

- **R1.1/R1.2** — appended records reached the open connection, each with a byte-offset
  `id` a reconnect can quote as `Last-Event-ID`.
- **R2.3** — the `transcript` frame is real: 1720 lines of *this* conversation, from a file
  nothing in this work item wrote. It carries a count and no content, so the client reads
  through `GET /api/v1/sessions/transcript` and its issue-209 path validation.
- **The `api.request` exclusion, live.** The health call, the registration, the work-item
  list and the stream request itself all emitted `api.request` into the same log the
  tailer was reading. **None of them appear above.** This is the loop that would never
  idle, not happening.
- **`retry: 3000`** went out first, so a browser's `EventSource` reconnects on a three-second
  schedule rather than one it picks itself.

## The subscriber bound, live

`service.stream.maxSubscribers` was 4 on this service. Five connections were opened; the
fifth was refused before it became a connection at all.

```text
$ for i in 1 2 3 4; do curl -sN "…/api/v1/stream" >/dev/null & done
$ curl -s -w '%{http_code}\n' "http://127.0.0.1:4139/api/v1/stream"
503
{"detail":"at capacity: 4 of 4 stream connections are open (service.stream.maxSubscribers)"}
```

## T13 — a service that does not serve the stream

`service.stream.enabled: false` stands in for a service older than this feature: both
answer 404 for the same route, and the control plane's response to either is the same.

A second service, same build, `service.stream.enabled: false`, on its own state root:

```text
$ curl -s http://127.0.0.1:4140/api/v1/health
{"status":"ok","version":"10.2.1"}

$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4140/api/v1/stream
404
$ curl -s http://127.0.0.1:4140/api/v1/stream
{"detail":"this service does not serve /api/v1/stream (service.stream.enabled is false)"}
```

The service answers everything else normally, which is the point: the control plane has to
tell "this service is too old / has it off" apart from "nothing is listening", and a 404
from a healthy service is exactly that signal.

## What did NOT run here, and why

The **browser** half of T6, T10, T12 and T13 — screenshots of the rendered detail page and
the four connection states, the keyboard/screen-reader pass, an animated capture of a turn
arriving, and the fallback banner against a 404 — could not be executed: this session has
no working connection to a browser (the Chrome extension reports "not connected"), and
nothing here can drive one.

Those rows are **not ticked**. What stands in for part of them is automated:
`ui/src/views/WorkItemDetail.test.tsx` asserts the trace panel's accessible name and focus
affordance, that the chat bar is beside the panel rather than a transcript's length below
it, and the scroll rule R6.3/R6.4 turns on. What that cannot cover is *rendering* — jsdom
applies no stylesheet, so `max-height`, `overflow-y` and `position: sticky` are inert, and
neither is the visual check of the four connection states.
