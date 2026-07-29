---
type: bugfix
phase: requirements-definition
workItem: issue-111
status: approved
approvedBy: []
severity: low
riskTier: 3
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the session registry reads its neighbours as sessions

> Phase 1 of 3 for a bug (requirements → design → tasks). Named `requirements.md`
> rather than `bugfix.md` because the shipped process graph's
> `requirements-definition` node `produces: [requirements.md]` (issue-109,
> `graph/pdlc.yaml`) — the runtime is the enforced source of truth, and a
> bug-shaped spec under that name is still gated. Human approval for this tier-3
> change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

issue-106 consolidated everything the CLI generates under one `state.root` and
put the **session-related** state together under `<root>/sessions/`
(`the_loop.state.StateLayout`): the registry files, the control records
(`sessions/control/`) — and the poll state, which moved from
`.the-loop/poll-state.json` to `.the-loop/sessions/poll-state.json`.

`SessionRegistry.list_sessions` predates that move and still assumes it owns the
whole directory: it globs `*.json` and hands **every** match to
`Session.from_dict`. The poll state is a `*.json` file in that directory and is
not a session record, so it raises `KeyError: 'workItem'`, which `_read` catches
and reports as a corrupt registry entry:

> WARNING the-loop.sessions skipping unreadable registry file
> `.the-loop/sessions/poll-state.json`: `'workItem'`

Reported as [issue #111](https://github.com/MadaraUchiha-314/the-loop/issues/111).

Nothing is lost — the poll state is skipped, not overwritten, and every real
session still lists — but the warning is emitted on **every** listing: once per
provider per poll cycle (`Poller._reconcile_closures` → `list_sessions`, issue-94)
and on every `the-loop sessions list`. That matters for two reasons:

1. It is the daemon's steady-state log line. An operator watching a long-running
   poller sees a corruption warning about a file that is perfectly healthy.
2. It **devalues the only signal for a genuinely corrupt session record**. That
   warning exists so a session file the-loop can no longer parse is visible
   rather than silently dropped; once it fires every cycle for a benign file, a
   real one is indistinguishable from the noise.

## Steps to reproduce

1. Run the daemon with the default layout (`state.root: .the-loop`) so the poll
   state resolves to `.the-loop/sessions/poll-state.json`.
2. Let one poll cycle complete, so the poller writes its state file.
3. Run `the-loop sessions list` (or wait for the next cycle).

**Observed:** `WARNING the-loop.sessions: skipping unreadable registry file
.the-loop/sessions/poll-state.json: 'workItem'`, repeated indefinitely.
**Expected:** the registry ignores files that are not its own and says nothing
about them; the warning is reserved for a file the registry itself wrote and can
no longer read.

Minimal reproduction against the library:

```python
registry = SessionRegistry(root)
registry.register(session)                       # writes github-octo-repo-15.json
(root / "poll-state.json").write_text('{"items": {}}')
registry.list_sessions()                         # -> 1 session, and one bogus warning
```

## Expected vs actual

- **Expected:** WHEN the registry lists sessions THEN it SHALL consider only the
  files **it wrote**, and SHALL be silent about anything else sharing the
  directory — the directory is shared session-related state by design
  (issue-106), not the registry's private space.
- **Actual:** every `*.json` in the directory is treated as a session record, so
  a sibling file that is not one is reported as a corrupt registry entry on every
  listing.

## Root cause (confirmed)

`cli/the_loop/sessions/registry.py:247-254`:

```python
for path in sorted(self.root.glob("*.json")):
    session = self._read(path)
```

with `_read` (`registry.py:184-189`) catching `(OSError, ValueError, KeyError)`
and logging `"skipping unreadable registry file %s: %s"`. `Session.from_dict`
indexes `data["workItem"]`, so a non-session JSON object raises `KeyError` and
lands in that handler — the warning is the correct handler reached with the wrong
input.

Two facts make this a *structural* defect rather than a one-file accident:

- **The directory is deliberately shared.** `state.py` documents
  `<root>/sessions/` as "the parent of every session-related file"; the poll
  state is there by design, `control/` is a sibling subdirectory, and the next
  piece of session-related state will land there too. Naming `poll-state.json` as
  a special case fixes today's symptom and leaves the next neighbour free to
  repeat the bug.
- **The registry already knows what its own files are called.** `_write` names
  every file `f"{item.slug}.json"`, and `WorkItemRef.slug` is
  `<provider>-<owner>-<repo>-<number>` sanitised to `[A-Za-z0-9._-]` — so a
  registry file's name **always** ends in `-<digits>`. The information needed to
  recognise its own files exists; `list_sessions` simply does not use it.

`find_by_work_item` is unaffected: it addresses a file by `_path_for(ref)` and can
never reach a neighbour, because a slug always ends in `-<number>`. Only the
directory scan is wrong. Interim `*.tmp` files from `_write`'s atomic replace are
already outside the `*.json` glob.

## Requirements

Acceptance criteria in EARS notation. The user story they serve:

> **As an** operator running the-loop's daemon, **I want** the session registry
> to be quiet about files it does not own, **so that** the one warning it does
> emit still means a session record went bad.

### R1 — Recognise the registry's own files

1. WHEN the registry lists sessions THEN it SHALL include exactly those files it
   wrote — files named `<slug>.json` where the slug is the one
   `WorkItemRef.slug` produces — and no others. (AC1)
2. WHEN a file in the registry directory is not named like a registry file THEN
   listing SHALL skip it **silently** (a debug-level line at most) and SHALL NOT
   log a warning. (AC2)
3. WHEN the poll state (`<root>/sessions/poll-state.json`, issue-106) is present
   in the registry directory THEN a listing SHALL neither warn about it nor read
   it, and SHALL still return every real session in the directory. (AC3)

### R2 — Keep the corruption signal

1. WHEN a file **is** named like a registry file but cannot be parsed as a
   session — unreadable, invalid JSON, or missing required fields — THEN listing
   SHALL skip it and SHALL log the existing warning, unchanged. (AC4)

### R3 — No change to lookup or write behaviour

1. WHEN a session is registered, found, paused, resumed, closed or touched THEN
   behaviour SHALL be byte-identical to before this change; the fix SHALL be
   confined to how the directory is scanned. (AC5)

### R4 — Regression coverage & documentation

1. The fix SHALL include a regression test that fails before it and passes after:
   a registry directory containing a real session **and** a `poll-state.json`
   lists the session and emits no warning. (AC6)
2. The affected capability docs SHALL record, in the same PR, that the sessions
   directory is shared and that the registry recognises only its own files. (AC7)

## Out of scope

- **Moving the poll state back out of `<root>/sessions/`.** Its location is the
  deliberate outcome of issue-106 (all session-related state in one directory an
  operator can inspect, back up or wipe), and moving it again would re-baseline
  every watched thread on upgrade — the exact hazard
  `resolve_poll_state_path` exists to avoid. The registry adapts to the shared
  directory; the layout does not change.
- **Cleaning up or migrating existing files.** Nothing on disk is touched; this
  changes only which files a listing reads.
- **Making `_read` tolerant of partial session records.** A registry-named file
  missing `workItem` is genuine corruption and must keep warning (AC4).
- **The control records under `sessions/control/`.** They are in a subdirectory,
  which the non-recursive glob never reaches; `ControlStore` addresses its files
  directly and has no directory scan.
- **Any change to `find_by_work_item`, `register`, `pause`, `resume`, `close` or
  `touch`** (AC5).

## Security considerations

**No new attack surface; the change strictly narrows what the registry reads.**

- **Trust boundary.** The boundary here is *what the daemon accepts as a routing
  record*. A session record decides where an event is dispatched (which cwd,
  which harness session id is resumed), so the registry directory is trusted
  local state. This change **tightens** that boundary: fewer files in the
  directory are considered, and only ones matching the shape the registry itself
  writes. Nothing that was rejected before is accepted now.
- **No widening of routing.** A file that is skipped is not routed to. The
  worst-case failure of a too-strict filter is a session that does not appear in
  a listing (fail-closed: no dispatch), never a session synthesised from a
  foreign file (fail-open). The filter is a *superset* check over what `_write`
  produces, so no file the registry wrote can be excluded — asserted by a test
  driven from `WorkItemRef.slug` itself rather than a hand-written name (AC1).
- **Untrusted input.** The filename check is a bounded, anchored regex over a
  filename (`re.fullmatch`, no backtracking risk, no user-supplied pattern), run
  before any file is opened. Skipping a file means *not* parsing it, so the
  change removes JSON parsing of one file rather than adding any.
- **Local-only.** No network, no subprocess, no credential, no new file, no new
  config key. Anyone who can write into the registry directory already has
  arbitrary local write access to the daemon's state and needs no such filename
  trick.
- **Log hygiene as a security property.** The warning being restored to a
  *meaningful* signal is itself the security-relevant outcome: a corrupt or
  tampered session record must remain visible in the log rather than buried under
  a per-cycle false positive (AC4 keeps it).
- **Abuse case covered by a test:** a file named to look like anything other than
  a registry file must never be read as a session record — and a
  registry-shaped file that fails to parse must still warn rather than be
  silently dropped.

## Open questions

None. The reported symptom, the root cause and the fix's shape are all confirmed
locally against the current code.
