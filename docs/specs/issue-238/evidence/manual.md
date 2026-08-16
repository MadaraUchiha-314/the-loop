# Evidence: the reported symptom, before and after (T12)

Run 2026-08-16 against **two services at once**: the installed `10.2.0` on `:4114` (the
code the ticket was filed against) and this branch's code on `:4199`, both reading the same
state root, so every difference below is the fix and nothing else.

Home-directory paths are shown in full where they are the point (the stale record's `cwd`)
and are the operator's own workspace paths; no token, cookie or credential appears.

## The stale record is real, and still stale

```console
$ curl -s http://127.0.0.1:4199/api/v1/sessions | …
2 sessions
  github:MadaraUchiha-314/devbox#2      | cwd exists: False
  github:MadaraUchiha-314/the-loop#238  | cwd exists: True
```

One vanished checkout, one live one, in the same listing — the exact condition the ticket
describes, not a synthetic fixture.

## The request the ticket was opened about

```console
$ curl -s -w " | HTTP %{http_code}\n" -X POST http://127.0.0.1:4114/api/v1/graph/check \
    -H 'Content-Type: application/json' \
    -d '{"repo":"/Users/rohithr31/.the-loop/workspace/.worktrees/github.com/MadaraUchiha-314/devbox/github-MadaraUchiha-314-devbox-2","workItem":"issue-2","prRepo":"","recompute":false}'
{"detail":"repo path is not a directory: /Users/rohithr31/…/github-MadaraUchiha-314-devbox-2"} | HTTP 400   ← 10.2.0

$ …same request against http://127.0.0.1:4199/…
{"workItem":"issue-2","currentNode":"","ok":false,"parked":null,"nodes":[],"repoResolved":false} | HTTP 200   ← this branch
```

And a checkout that **is** there, on the fixed service — a real position, and no
`repoResolved` key (R2.2):

```console
$ curl -s -X POST http://127.0.0.1:4199/api/v1/graph/check -d '{"repo":"<this worktree>","workItem":"issue-238",…}'
{"workItem":"issue-238","currentNode":"verification","ok":false,"parked":null,
 "nodes":[{"node":"phase-selection","status":"pass",…}]}
```

## One poll tick of the real dashboard, against both services

The devtools console could not be photographed — see *Not executed* below — so the
observation was made one layer down, where the same fact lives: the board's **real**
`fetchGraphs`, the **real** `HttpApi`, the **real** session records, with `globalThis.fetch`
wrapped to record every `/graph/check` status. That is precisely the set of responses Chrome
would have logged.

```console
$ bun run live.ts                                   # against :4199 — this branch
sessions: github:MadaraUchiha-314/devbox#2      cwd=/Users/…/devbox/github-MadaraUchiha-314-devbox-2
          github:MadaraUchiha-314/the-loop#238  cwd=/Users/…/github-MadaraUchiha-314-the-loop-238

graph/check responses: [{"url":"/api/v1/graph/check","status":200},{"url":"/api/v1/graph/check","status":200}]
4xx/5xx count: 0

reports.outer keys: ["github:MadaraUchiha-314/the-loop#238"]
  github:MadaraUchiha-314/the-loop#238 -> currentNode=verification
```

```console
$ bun run live-before.ts                            # the same script against :4114 — 10.2.0
graph/check responses: [{"url":"/api/v1/graph/check","status":400},{"url":"/api/v1/graph/check","status":200}]
4xx/5xx count: 1

reports.outer keys: ["github:MadaraUchiha-314/the-loop#238"]
  github:MadaraUchiha-314/the-loop#238 -> currentNode=verification
```

Two things are proved by the pair, and the second matters as much as the first:

1. **The 4xx is gone** — one per tick before, zero after. Multiply by the poll interval for
   the unbounded growth R1.2 is about.
2. **Nothing else moved.** `reports.outer` is byte-for-byte the same in both runs: the
   stale ref produces no report either way, so `buildWorkItemViews` falls back to
   `railFromFrozen` exactly as it did, and the live ref reports the same position. This is
   R2.1 demonstrated on the real path rather than inferred from the unit test.

## Not executed

- **The devtools console screenshot** (`manual-console.png` in the evidence plan). The
  Chrome extension this session drives the browser through was not connected —
  `tabs_context_mcp` returned *"Browser extension is not connected"* — so no browser could
  be driven and no screenshot taken. The service and the Vite dev server were both brought
  up for it (`:4199`, `:5173`) and the CORS origins were configured; only the browser was
  missing.

  **Replanned, not skipped**, and the replacement is stated above: the console screenshot
  would have shown a list of `/graph/check` responses, and the live run captures that list
  directly, from the same client code the browser runs, with a before/after contrast a
  screenshot could not have given. What remains unverified by machine is the last inch —
  that Chrome renders zero red lines for a set of `200`s — which is browser behaviour, not
  this project's.

  Flagged on PR #241 so a human can take the screenshot in thirty seconds if they want it
  in the record.
