---
type: design
phase: design
workItem: "issue-86"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Design: retained tmux sessions + session announcement comments

> Phase 2 of 3 (requirements → design → tasks). Derives from `requirements.md`.

## Overview

Three seams, each small:

1. **`runner.py`** — spawn sets tmux's `remain-on-exit`, and a new
   `has_live_session()` distinguishes "session exists" from "session exists and
   its pane is still running". That distinction is what makes retention safe:
   with `remain-on-exit`, `has-session` alone would start returning `true` for
   sessions whose harness is dead, and the issue-80 respawn path would never
   fire again.
2. **`dispatcher.py`** — the PR-close branch keeps (rather than kills) the tmux
   session by default, and a first spawn announces on the ticket.
3. **`announce.py`** (new) — a `gh`-shelling, best-effort comment poster, built
   in the mould of `reactions.py` (issue-84).

```mermaid
sequenceDiagram
    participant GH as GitHub
    participant D as Dispatcher
    participant T as TmuxRunner
    participant A as SessionAnnouncer (gh api)

    GH->>D: event → spawn (runner: tmux)
    D->>T: new-session -d -s loop-<slug> … ; set remain-on-exit
    D->>A: announce(session)
    A->>GH: 💬 "tmux attach -t loop-<slug>"
    Note over T: harness exits → pane dead, session + scrollback kept
    GH->>D: later event for the same work item
    D->>T: has_live_session? (pane_dead=1 → no)
    D->>T: respawn (issue-80) → clears the dead session, fresh TUI
    Note over D,A: no re-announcement — same name, same attach command
    GH->>D: pull_request closed/merged
    D->>D: registry.close(...)
    alt keepSessionOnClose (default)
        D-->>T: (no kill) → emit session.retained
    else keepSessionOnClose: false
        D->>T: kill-session
    end
```

## 1. `runner.py` — remain-on-exit and pane liveness

- `TmuxResult` gains `output: str` (stdout of the tmux invocation), populated by
  `_run`. Nothing else reads it today; `has_live_session` does.
- `TmuxRunner.__init__(binary="tmux", remain_on_exit=True)`. The dispatcher
  constructs the runner from config; the default keeps the flag on for the CLI
  paths (`sessions attach`) that build a bare runner and never spawn.
- `spawn()` — after a successful `new-session`, run
  `set-option -t <target> -w remain-on-exit on`. **Best-effort** (AC2.2): a
  non-zero exit is a `logger.warning`, and the spawn still returns ok. Note
  `remain-on-exit` is a *window* option in tmux ≥ 3.0, hence `-w`.
- `has_live_session(target) -> bool` — `has_session(target)` AND
  `list-panes -t <target> -F "#{pane_dead}"` reports at least one pane whose
  flag is not `1`. A tmux that does not know `pane_dead` (very old) returns
  empty/garbled output → treated as **live**, i.e. it degrades to today's
  behaviour rather than declaring healthy sessions dead.
- `deliver()` switches its guard from `has_session` to `has_live_session`, so a
  retained-but-dead session reports `session_missing=True` and the dispatcher's
  existing respawn path handles it unchanged (AC2.3). `spawn()`'s
  stale-clearing check keeps using `has_session` — a dead-pane leftover must
  still be cleared before `new-session` (AC1.5).

## 2. `dispatcher.py` — retention + announcement wiring

- New `TmuxConfig` dataclass mirroring `routing.tmux`
  (`keep_session_on_close: bool = True`, `remain_on_exit: bool = True`), parsed
  in `RoutingConfig.from_mapping`, so the poller inherits it and `reload()`
  hot-swaps it.
- `Dispatcher.__init__` builds its `TmuxRunner` with `remain_on_exit` from
  config (an injected runner still wins, for tests), and gains an optional
  `announcer` parameter defaulting to `SessionAnnouncer(config.announce)` —
  same override-survives-reload pattern as `workspace`/`reactor`.
- PR-close branch in `handle()`: when `tmux.keep_session_on_close` (default),
  skip the `kill` and instead log the attach command + emit `session.retained`;
  otherwise kill exactly as before.
- `_spawn_tmux()`: after `registry.register(...)` and the existing
  `session.spawned` emission, call `self.announcer.announce(session)`. Placed
  **after** the state is durable and never in a way that can change the
  returned bool (AC3.4). `_respawn_tmux()` deliberately does **not** announce
  (AC3.2, owner decision at PR #87) — the respawn reuses the same
  `loop-<slug>` name, so the comment already on the ticket is still accurate.

## 3. `announce.py` — the comment poster

Mirrors `reactions.GitHubReactor` deliberately (same auth posture, same
best-effort contract, same injectable `runner`/`timeout` for hermetic tests):

- `AnnounceConfig` — `enabled: bool = True`, `gh_binary: str = "gh"`, with
  `from_mapping`.
- `announcement_body(session) -> str` — **pure**, unit-testable, builds the
  markdown from the session's own recorded fields only (work-item ref,
  `tmux_target`, harness name). No payload data, no cwd, no harness
  session id (AC3.6).
- `SessionAnnouncer.announce(session) -> bool` — short-circuit
  ladder: disabled → `runner != "tmux"` → non-`github` provider → owner/repo
  failing the defensive `[A-Za-z0-9._-]+` check → `gh` missing (warn **once**).
  Then `gh api --method POST repos/<owner>/<repo>/issues/<number>/comments -f
  body=<markdown>` (the issues endpoint serves PR conversations too, as in
  `reactions.py`). Success → `session.announced`; any failure (non-zero exit,
  `OSError`, timeout) → `session.announce_failed` at warning level, returning
  `False`. Never raises.

Body (fixed template):

```markdown
🖥️ **the-loop** started an interactive session for `github:owner/repo#86`.

| | |
|---|---|
| tmux session | `loop-github-owner-repo-86` |
| harness | `claude` |

Attach from the machine running the-loop:

    tmux attach -t loop-github-owner-repo-86
    # or, read-only:
    the-loop sessions attach --work-item github:owner/repo#86 --read-only

The session is kept after the work completes, so this transcript stays
readable. A respawn reuses this same tmux session name, so these commands
keep working.
```

## Decisions

- **Default to keeping.** The issue asks for retention as the behaviour, not as
  an opt-in; `keepSessionOnClose: false` restores the old kill. The cost
  (sessions accumulate) is bounded by the deterministic name and is the
  operator's own machine. Confirmed by the owner at PR #87.
- **First spawn only (owner decision, PR #87).** Drafted to announce on
  respawn as well; the owner asked to keep tickets quiet. A respawn reuses
  `loop-<slug>`, so the existing comment stays correct — which also removes
  the flapping-session comment storm. The body says so explicitly, and
  `announce()` lost its `respawned` parameter rather than carrying a dead
  branch.
- **Keep the name, don't rename on close.** Renaming a retained session to
  `loop-<slug>-done` would preserve it across a re-spawn but would break every
  attach command already posted on the ticket and every muscle-memory
  `tmux attach -t loop-<slug>`. Predictable name wins; a re-spawn on the same
  work item reclaims it (AC1.5), which is documented.
- **`remain-on-exit` needs a liveness check.** Retention without
  `has_live_session` would regress issue-80: `has-session` would succeed for a
  dead pane and events would be pasted into a corpse. The two ship together.
- **Announce only for tmux.** A process-mode session has nothing to attach to,
  so a comment would be noise (AC3.3).
- **`gh` CLI, not an HTTP client** — the poller/reactor posture: zero runtime
  dependencies, the operator's own auth, best-effort.
- **Separate module from `reactions.py`.** Both shell `gh`, but one posts a
  reaction from a *payload-derived* target and the other posts text from a
  *registry-derived* one; fusing them would couple two different trust stories
  for ~20 saved lines.

## Error handling

Every new failure mode degrades: a failed `set-option` warns and spawns anyway;
an unparseable `list-panes` reports "live" (status quo); every announcer failure
is a logged no-op. Dispatch outcome, dedup and retry semantics are unchanged.

## Testing strategy

- **Unit** (`cli/tests/test_announce.py`): `AnnounceConfig` parsing/defaults;
  `announcement_body` content assertions (contains the attach command; contains
  no cwd/session id); `announce()` argv construction via a fake runner; the
  no-op ladder (disabled, process runner, non-github provider, malformed
  owner/repo, missing `gh` warn-once); failure → `False` without raising.
- **Unit** (`cli/tests/test_tmux_runner.py`): `spawn` issues `set-option …
  remain-on-exit on` when enabled and not when disabled; a failing `set-option`
  still yields `ok`; `has_live_session` for live pane / dead pane / missing
  session / unparseable output; `deliver` on a dead pane returns
  `session_missing`.
- **Integration** (Gherkin-docstringed, `test_tmux_runner_integration.py` /
  `test_webhook_routing_integration.py` style): PR-close keeps the tmux session
  and emits `session.retained` by default and kills it when configured off; a
  delivery into a retained dead session respawns (issue-80 path intact); spawn
  announces once while a respawn stays quiet, process-mode spawns do not; a failing
  announcer never changes the dispatch outcome.
- **CLI** (`cli/tests/test_cli.py`): `sessions close --keep-tmux` / `--kill-tmux`
  behaviour, and `sessions attach` reaching a retained session of a *closed*
  work item.
