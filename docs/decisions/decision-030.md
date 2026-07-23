# Decision 030: Stay on Python for the CLI — a rewrite in Go/Rust/Bun buys nothing measurable

- **Status:** proposed
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #57)
- **Work item:** issue-57
- **Revisits:** [decision-005](decision-005.md) (Python CLI), which this reaffirms

## Context

Issue #57 asks whether moving the CLI from Python to a more performant language
(Go, Rust — and, per the follow-up comment, Bun) would make a difference, whether
SDK support for the GitHub-side integrations is good enough in those languages,
and what the *measurable* impact of leaving Python would be — motivated by the CLI
"doing polling and hosting a webhook server etc."

Current state: the CLI is ~4.8k lines of stdlib-only Python (zero runtime
dependencies, PyYAML optional), published to PyPI via Trusted Publishing
(decision-019). Its long-running components are the webhook receiver
(`ThreadingHTTPServer`), the poller (shells out to the user's authenticated `gh`
CLI each cycle), and the dispatcher (resumes/spawns `claude` / `cursor-agent`
sessions, optionally inside tmux). Decision-005 mandated Python to keep the door
open for self-learning/ML capabilities, which ship predominantly as Python SDKs.

## Analysis

### 1. Where the time actually goes (workload profile)

Every hot path is I/O-bound or subprocess-bound; the language runtime is a
rounding error. Measured on this repo (Python 3.11, Linux container):

| Operation | Measured cost | Dominated by |
|---|---|---|
| Webhook event: HMAC-SHA256 verify + JSON parse of a 25 KB payload | **~0.1 ms** | — (this *is* the CPU work) |
| Dispatch of a routed event | seconds–minutes | the `claude -p … --resume` / `cursor-agent` child doing agent work |
| One poll cycle | 200–800 ms × N `gh` calls | GitHub API network round-trips inside `gh` |
| Subprocess spawn overhead (`fork`+`exec`) | ~4 ms | the kernel, identical in every language |
| CLI cold start (`the-loop --help`) | ~120–250 ms, ~23 MB peak RSS | CPython interpreter + imports |

Per webhook event, Python-attributable CPU (~0.1 ms) is roughly **0.001–0.01 %**
of the event's end-to-end life (the dispatched harness session runs for minutes).
Per poll cycle, CPU between `gh` calls is microseconds against hundreds of
milliseconds of network latency — and the cycle then sleeps for `intervalSeconds`
(default 60 s). The GIL is irrelevant here: the receiver's threads and the
dispatcher's workers spend their lives blocked in `accept()`/`read()`/`wait()`,
all of which release it.

Event volume is human-scale by design: one operator's repos, label-gated,
authorized-actors-only (decision-023) — tens of events per hour, not thousands
per second. `ThreadingHTTPServer` sustains hundreds of requests/second; the-loop
needs ~0.01.

### 2. What Go / Rust / Bun would measurably change — and not

| | Python (today) | Go | Rust | Bun (TS) |
|---|---|---|---|---|
| Cold start | ~120–250 ms | ~5–10 ms | ~1–5 ms | ~10–30 ms |
| Daemon RSS | ~23 MB | ~10 MB | ~3–5 MB | ~30–50 MB |
| Distribution | needs a Python ≥3.9 (`pip install`) | single static binary | single static binary | single file via `bun build --compile`, but ~50–90 MB (embeds the runtime) |
| Rewrite cost | — | ~4.8k LOC + 14 test modules + release pipeline | same, highest effort | same, lowest effort |

What a rewrite would **not** change, because it isn't ours: GitHub API latency,
`gh` execution time, harness-agent runtime (the minutes-long part), tmux/ttyd,
and the 60 s poll interval. Those dominate >99.9 % of every user-visible
wall-clock path, so **end-to-end latency of "webhook received → session
resumed" and "poll tick → session spawned" improves by approximately
nothing**. For the long-running daemons, even the cold-start win amortizes to
zero. The only human-perceptible difference would be one-shot commands
(`the-loop events`, `sessions list`) feeling ~150 ms snappier — and lazy imports
can claw back most of that in Python (see below).

The honest wins of Go/Rust are **distribution** (a single binary with no Python
prerequisite) and daemon **memory footprint** — real properties, but neither is
a performance problem the-loop currently has, and the CLI's users by definition
already run Python-adjacent developer tooling.

### 3. SDK support for the integrations

The premise dissolves on inspection: **the CLI uses no GitHub SDK today.**
GitHub is reached exclusively through the user's own authenticated `gh` CLI
(decision-022's provider seam), deliberately, so the-loop inherits `gh`'s
auth/enterprise config and carries no token. That approach is language-neutral —
any rewrite would keep it or trade it for a native SDK. If a native SDK were
ever wanted, every candidate is well served:

- **Go** — `google/go-github` (mature, canonical; `gh` itself is written in Go);
- **Rust** — `octocrab` (solid community crate);
- **TS/Bun** — `octokit` (GitHub's own, best-in-class);
- **Python** — `PyGithub` / `ghapi` (mature community).

GitHub Packages specifically is plain REST, fine everywhere. Jira likewise has
community SDKs in all four and a simple REST API. **SDK availability neither
blocks nor motivates any language choice.**

### 4. What about Bun?

Bun's appeal (fast startup, batteries-included tooling, `octokit`) is real, but
it buys the same unmeasurable dividend as Go/Rust here, while: compiled
single-file binaries are ~50–90 MB (they embed the runtime); the toolchain is
the youngest of the candidates (Windows support and edge-case Node-compat still
maturing); and it abandons decision-005's stated reason for Python — future
self-learning/ML features, whose SDKs are Python-first. If startup time of
one-shot commands is the concern, fixing imports in Python is a ~50-line change,
not a rewrite.

## Decision (recommendation)

**Stay on Python; reaffirm decision-005.** The CLI's workload is I/O- and
subprocess-bound at human-scale event rates; a rewrite in Go, Rust, or Bun
would improve no user-visible metric while costing a full rewrite of ~4.8k
lines, the test suite, and the PyPI Trusted-Publishing release pipeline
(decision-019, decision-028), and forfeiting the ML-readiness rationale.

Performance levers that *would* move real numbers, all within Python:

1. **Cut poll-cycle latency** — batch/parallelize the per-repo `gh` calls or
   collapse them into one GraphQL query. Fewer sequential network round-trips
   is the only lever that touches the dominant term.
2. **Cold start of one-shot commands** — lazy-import command modules in the
   registry so `the-loop events`/`sessions` don't pay for the webhook stack's
   imports (most of the ~150 ms is import time).
3. **If webhook throughput ever mattered** — swap `ThreadingHTTPServer` for
   stdlib `asyncio`; still zero dependencies.

**Revisit triggers** (concrete, falsifiable): the CLI gains genuinely CPU-bound
work at scale; or distribution pain becomes real (users who cannot have a
Python runtime need a single binary). If a trigger fires, **Go is the
recommended target** — `gh` itself is Go, `go-github` is mature, and its
single-static-binary story is the strongest — with Bun second (fastest port,
best GitHub SDK, heaviest binaries) and Rust last (peak performance the
workload cannot use, highest rewrite cost).

## Alternatives considered

- **Rewrite in Go now** — rejected: no measurable end-to-end benefit at current
  workload; named as the preferred target if a revisit trigger fires.
- **Rewrite in Rust** — rejected: same, at the highest rewrite cost.
- **Rewrite in Bun/TS** — rejected (asked in the issue thread): same
  unmeasurable dividend, ~50–90 MB compiled binaries, youngest toolchain, and
  it abandons the Python-for-ML rationale.
- **Hybrid: rewrite only the webhook server** — rejected: the receiver is the
  *least* loaded component (~0.1 ms CPU per event); a two-language repo for
  that is all cost.
