# Evidence: control-plane tests (issue-239)

Testing-plan rows **T2** (UI unit) and **T11** (settings migration). Run from `ui/`.

## T2 — the whole vitest suite

```text
   ✓ the control plane, on demo data > renders the session's turns and tool calls from the transcript route  308ms
   ✓ the control plane, on demo data > routes the attention tab to the union of /attention and the graph gates  547ms

 Test Files  10 passed (10)
      Tests  139 passed (139)
   Start at  11:26:22
   Duration  3.94s (transform 546ms, setup 1.19s, collect 1.12s, tests 3.73s, environment 3.90s, prepare 712ms)

```

## T2 — the invalidation map, the connection state machine, the frame decoder

```text
✓ src/state/stream.test.ts > invalidationFor > sends a graph event to that one work item's loop position 1ms
✓ src/state/stream.test.ts > invalidationFor > covers every graph.* type, not a list of the ones that exist today 1ms
✓ src/state/stream.test.ts > invalidationFor > sends a session or dispatch event to the list calls 2ms
✓ src/state/stream.test.ts > invalidationFor > refreshes the lists for an event type it has never heard of 1ms
✓ src/state/stream.test.ts > invalidationFor > routes a transcript frame to that ref's transcript, and nothing else 0ms
✓ src/state/stream.test.ts > invalidationFor > treats a desync as everything being stale 0ms
✓ src/state/stream.test.ts > invalidationFor > still refreshes the lists when a graph event names no work item 0ms
✓ src/state/stream.test.ts > mergeInvalidation > collapses a burst into one refresh covering all of it 0ms
✓ src/state/stream.test.ts > mergeInvalidation > is a no-op against the empty invalidation 0ms
✓ src/state/stream.test.ts > mergeInvalidation > does not mutate either argument 0ms
✓ src/api/client.test.ts > normalizeBaseUrl > strips trailing slashes so paths do not double up 1ms
✓ src/api/client.test.ts > HttpApi > sends work-item refs as query parameters, never path segments 4ms
✓ src/api/client.test.ts > HttpApi > repeats a list parameter rather than joining it 1ms
✓ src/api/client.test.ts > HttpApi > posts graph/check with prRepo defaulted, since the body requires the key 0ms
✓ src/api/client.test.ts > HttpApi > reports an unreachable service as `network`, advising the base URL, CORS and the tunnel 0ms
✓ src/api/client.test.ts > HttpApi > surfaces FastAPI's `detail` on a 4xx rather than the bare status line 0ms
✓ src/api/client.test.ts > HttpApi > falls back to the status line when the error body is not JSON 0ms
✓ src/api/client.test.ts > HttpApi.stream > puts the filters on the query string 0ms
✓ src/api/client.test.ts > HttpApi.stream > decodes a log frame, carrying the SSE id through as the cursor 1ms
✓ src/api/client.test.ts > HttpApi.stream > decodes a transcript frame from `ref`, which is not `work_item` 0ms
✓ src/api/client.test.ts > HttpApi.stream > decodes a desync frame with its reason 0ms
✓ src/api/client.test.ts > HttpApi.stream > drops a frame that is not a record rather than passing a half one on 0ms
✓ src/api/client.test.ts > HttpApi.stream > closes the connection when unsubscribed 0ms
✓ src/state/useStream.test.ts > useStream > does not connect at all when the mode is not streaming 9ms
✓ src/state/useStream.test.ts > useStream > reports live once the connection opens 1ms
✓ src/state/useStream.test.ts > useStream > collapses a burst of frames into one refresh covering all of them 2ms
✓ src/state/useStream.test.ts > useStream > does not flush when nothing arrived 1ms
✓ src/state/useStream.test.ts > useStream > shows reconnecting while the browser retries, counting attempts 2ms
✓ src/state/useStream.test.ts > useStream > gives up after the failure limit and hands back the advice 1ms
✓ src/state/useStream.test.ts > useStream > forgets past failures once a connection opens again 1ms
✓ src/state/useStream.test.ts > useStream > reports a transport that cannot stream at all rather than waiting 1ms
✓ src/state/useStream.test.ts > useStream > closes the connection when it unmounts 1ms
✓ src/state/useStream.test.ts > useStream > reconnects with the new watch when the viewed transcript changes 2ms
Tests  33 passed (33)
```

## T11 — settings written before `refreshMode` existed

The one thing in this work item that can silently break an existing viewer. The storage
key is deliberately still `the-loop:settings:v1`, so nobody loses their base URL, and the
absence of the field is the migration signal.

```text
✓ src/state/settings.test.ts > loadSettings > returns the defaults for an empty store 1ms
✓ src/state/settings.test.ts > loadSettings > round-trips what was saved 0ms
✓ src/state/settings.test.ts > loadSettings > normalizes a stored URL's trailing slash 0ms
✓ src/state/settings.test.ts > loadSettings > keeps the good fields when a neighbour is nonsense 0ms
✓ src/state/settings.test.ts > loadSettings > survives a store holding something that is not JSON at all 0ms
✓ src/state/settings.test.ts > loadSettings > treats an absent store (privacy mode) as defaults, not a crash 0ms
✓ src/state/settings.test.ts > loadSettings > clamps an absurd poll interval instead of scheduling it 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > defaults a fresh browser to streaming 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > round-trips each mode 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > falls back to streaming for a mode nobody ships 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > settings written before refreshMode existed > reads pollSeconds: 0 as manual, keeping the base URL 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > settings written before refreshMode existed > reads any other interval as polling at that interval 0ms
✓ src/state/settings.test.ts > refreshMode (issue-239) > settings written before refreshMode existed > does not switch a viewer to a transport their tunnel may not carry 0ms
Tests  13 passed (13)
```

## Lint, typecheck and build, as CI runs them

```text
$ oxlint --type-aware
$ tsc --noEmit
computing gzip size...
dist/index.html                   0.64 kB │ gzip:  0.37 kB
dist/assets/index-mAkxSgSh.css   27.87 kB │ gzip:  5.47 kB
dist/assets/index-DhBzLYsx.js   276.32 kB │ gzip: 85.40 kB │ map: 1,219.69 kB
✓ built in 545ms
```
