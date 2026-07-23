# Decision 025: JSONL event log as the CLI's observability source of truth (not SQLite)

- **Status:** accepted
- **Date:** 2026-07-22
- **Deciders:** @MadaraUchiha-314 (issue #50)
- **Work item:** issue-50
- **Spec:** `docs/specs/issue-50/`

## Context

the-loop's CLI processes (webhook receiver, poller, sessions CLI) autonomously accept,
reject, dispatch, spawn and close on the user's behalf, but recorded those decisions
only as free-text `logging` lines on stderr — gone with the terminal, unstructured, and
invisible to agents and dashboards. Issue #50 asks for end-to-end o11y: which events
triggered a session, what was rejected and why, failures/retries — durable, well
documented, and efficiently queryable by coding agents. The issue explicitly poses the
storage question: *"do we create a JSONL log file … or do we log it to a SQLite so that
agents can query it efficiently?"* Both fit the zero-runtime-dependency rule (`sqlite3`
is stdlib), so the choice is architectural, not dependency-driven.

## Decision

**JSON Lines is the source of truth.** Every routing/dispatch/session decision is
appended as one JSON object per line to `.the-loop/logs/events.jsonl` (configurable via
`observability.eventLog`, git-ignored), with a common envelope (`ts`, `source`,
`event`, `level`, `pid`) and a documented per-type field vocabulary. `the-loop events`
is the query surface; `EVENT_TYPES` in `the_loop/eventlog.py` is the enforced catalog.
No SQLite store is introduced. Rationale:

- **Multi-process safety without coordination.** The receiver, poller and sessions CLI
  run as independent processes on the same repo. POSIX `O_APPEND` line writes interleave
  safely with zero locking; SQLite would introduce writer locking, WAL management and
  busy-timeout tuning for a problem append-only lines don't have.
- **Directly greppable by agents and humans.** A JSONL file is tail-able, grep-able and
  jq-able with no driver — exactly how agent harnesses already read local files (the
  observability reference's "prefer file-system based logging the harness can read
  directly"). A SQLite file needs a client and schema knowledge before the first answer.
- **Crash-tolerant by format.** A torn final line loses one event; readers skip it. A
  corrupted SQLite page can take the database.
- **Dashboards layer on top, not underneath.** JSONL is the universal ingestion format —
  `sqlite3`'s `.import`, DuckDB (`read_json`), Grafana/Loki, or a pandas one-liner can
  build any queryable/dashboarding layer *from* the file later without changing writers.
  Choosing SQLite first would freeze a schema before we know the queries.
- **Consistent with the-loop's runtime-state style**: human-inspectable JSON on disk
  (file-per-session registry, poll-state.json), atomic/append-safe writes, git-ignored.

Emission is fire-and-forget (a broken log never breaks ingress) and a no-op until a CLI
entry point configures it (library/test use pays zero I/O).

## Consequences

- Queries are linear scans. At the CLI's event volume (human-scale webhook/poll
  traffic) this is negligible; if a deployment ever outgrows it, a SQLite/DuckDB index
  built from the JSONL is a follow-up that changes no writers.
- No built-in rotation/retention: operators truncate or rotate externally; the reader
  and `the-loop events --follow` tolerate truncation.
- Every new instrumentation point must register its event type in `EVENT_TYPES` — a
  unit test fails on drift, which is how "these events are well documented" stays true.
