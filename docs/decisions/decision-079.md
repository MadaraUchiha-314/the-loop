# Decision 079: The transcript route serves transcripts, not the filesystem

- **Status:** proposed
- **Date:** 2026-08-12
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-209](https://github.com/MadaraUchiha-314/the-loop/issues/209)

## Context

the-loop runs the harness as a CLI in tmux, so the structured record of a session's
turns and tool calls is the **harness's own file** — for Claude Code,
`~/.claude/projects/<munged cwd>/<session-id>.jsonl` — fully derivable from what the
service already records (the registration's `cwd` and `harnessSessionId`), but served
by nothing. issue-207's dashboard shipped its "Turns & tool calls" panel built and
visibly disabled for exactly this reason, deriving and displaying the path it could
not read. The open design questions the ticket names: tail vs. whole file, and
redaction — the JSONL is raw harness output and may carry whatever the agent read.

This is also the plane's **first route that returns file contents from disk**; every
existing `/api/v1` read serves records the service itself wrote.

## Decision

**`GET /api/v1/sessions/transcript` (+ the `session_transcript` MCP tool) serves the
file the registration names, and nothing else.** The boundary is mechanical, not
advisory:

1. **Fail-closed resolution.** The session id is validated before any filesystem
   touch (no separators, no `..` — a record is writable through
   `POST /sessions/register`); the cwd is munged per character into a single path
   segment; only `<id>.jsonl` names are ever formed; and the fully-resolved
   candidate (symlinks followed) must sit inside the resolved projects root
   (`$CLAUDE_CONFIG_DIR` or `~/.claude`, then `projects/`) or the answer is the
   same 404 a missing file gets. A derivation miss degrades to a scan of the
   root's immediate subdirectories, so a munge-scheme drift between harness
   versions is one directory listing, not a 404.
2. **Tail by default.** Transcripts get long and the operator's question is "what
   has it been doing lately": the route returns the last 200 lines unless told
   otherwise (`tail=0` for the whole file), computed in one pass with a bounded
   buffer, with `totalLines`/`truncated` making the cut visible. Closed sessions
   and PR endpoints resolve — the file outlives the registration, and review is
   the use case.
3. **No redaction layer.** The service cannot know which substrings of another
   tool's output are secrets; a pattern-based half-redactor would be a promise the
   route cannot keep. The honest boundary is the one the plane already has —
   loopback bind, exposure guard, exact-origin CORS (decision-059) — plus the
   `api.request` audit on every read. Stated in the capability doc rather than
   implied.
4. **The deliberate absences:** no CLI verb (the CLI is on the machine the file is
   on; `tail`/`jq` are better tools, and the dashboard shows the path), no Cursor
   support (undocumented SQLite store — refused by name, never guessed at), no
   streaming/range protocol (a live-tail feature with no consumer; the response
   shape leaves room for one).

The dashboard's disabled panel goes live on the route, keeping the event-log trail
as the stated fallback whenever the route answers 404 — and its path caption
switches from a run-collapsing munge to the harness's real per-character munge, so
the displayed path and the served file cannot disagree.

## Cost

- Whoever can reach the API can read whatever the agent read — bounded to the
  transcript files, but real; accepted as unchanged **in kind** on a plane that
  already serves the event log and can spawn/kill/type into the same sessions.
- An explicit `tail=0` on a huge transcript is an expensive request; accepted, it
  is opt-in per call.
- The fallback scan means a stale registration whose cwd moved can still resolve a
  same-id file in another project directory — session ids are UUIDs, so a
  cross-session collision is not a practical concern.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Serve the raw file as `text/plain` and let clients parse | Every client re-implements JSONL splitting and malformed-line handling; parsing once server-side keeps the response one JSON document like every other route |
| A byte-range / SSE follow protocol | A live-tail feature with no consumer yet; `tail` answers the actual question in one bounded response, and `totalLines`/`truncated` leave room to add ranges later |
| A redaction filter over the entries | The service cannot know what is secret in another tool's output; a half-redactor invites trusting it. The network posture is the boundary, stated outright |
| A CLI verb alongside the route | The CLI runs where the file lives; the path is already displayed and `tail -f` beats any renderer. A verb later is a three-line binding over the same core function |
| Deriving Cursor's location too | Reverse-engineering an undocumented SQLite schema that can change under us; refusing by name is honest and matches the ticket's scope |
| Requiring the session to be live | Refuses the review use case for no security gain — the file is still on disk and the plane's authorization model is unchanged either way |
