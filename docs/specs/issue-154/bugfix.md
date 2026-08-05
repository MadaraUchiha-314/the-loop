---
type: bugfix
phase: requirements-definition
workItem: issue-154
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the tmux session name the-loop records and posts is not the name tmux gave the session

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

`TmuxRunner.target_for` mints a work item's tmux session name as
`loop-<WorkItemRef.slug>`, and that slug may contain a **dot** — it is built from
the work item's `[<host>/]<owner>/<repo>` path through
`re.sub(r"[^A-Za-z0-9._-]+", "-", raw)`, which deliberately keeps `.`. A repo
named `docs.github.com` or `foo.js`, or any work item on a GitHub Enterprise host
(`github:ghe.corp.example/octo/repo#15`), therefore yields a target like
`loop-github-octo-foo.js-15`.

**tmux does not accept that name.** `session_check_name()` rewrites `.` and `:` to
`_` before the session is created, so tmux hosts `loop-github-octo-foo_js-15`
while the-loop stores, logs and *posts on the ticket* `loop-github-octo-foo.js-15`.
The announcement comment (issue-86) is the visible symptom the issue reports: the
`tmux attach -t …` command it publishes names a session that does not exist.

The damage is not only cosmetic, because the dotted name is also what the-loop
hands back to tmux. In tmux's target grammar `.` separates window from pane, so a
dotted name is not merely "not found" — it is *parsed as a different target*:

```console
$ tmux new-session -d -s 'loop-a.b-15' && tmux ls -F '#{session_name}'
loop-a_b-15
$ tmux has-session -t 'loop-a.b-15'; echo "exit=$?"
can't find pane: b-15
exit=1
$ tmux attach -r -t 'loop-a.b-15'
can't find pane: b-15
$ tmux new-session -d -s 'loop-a.b-15'
duplicate session: loop-a_b-15
```

(tmux 3.4, reproduced while writing this spec.)

So for every work item whose slug contains a dot, the whole tmux lifecycle is
broken: the liveness probe reads the live session as **absent**, every delivery
reports `session_missing`, the dispatcher respawns, and `new-session` collides
with the very session it is replacing — the issue-146 failure mode, reached here
by a different route and reached *deterministically* rather than only under load.
issue-146's handling contains the damage (a live occupant is never killed; the
event is delivered into it), which is why this ships as a wrong-name bug rather
than as a crash-loop — but the work item never gets a session it can attach to,
and `the-loop sessions attach` fails for it too.

Tracked as [issue #154](https://github.com/MadaraUchiha-314/the-loop/issues/154).

## Steps to reproduce

1. Run `the-loop poll start` (or `gh-webhook start --route`) with
   `routing.runner: tmux` against a work item whose slug contains a dot — a repo
   with a dot in its name (`octo/foo.js`), or any work item on a non-default
   host (`github:ghe.corp.example/octo/repo#15`).
2. Trigger a first spawn (post a comment / apply the auto-execute label).
3. Read the announcement comment the-loop posts on the ticket: it names
   `loop-github-octo-foo.js-15` and tells the human to run
   `tmux attach -t loop-github-octo-foo.js-15`.
4. Run that command on the machine running the-loop → `can't find pane: js-15`.
   `tmux ls` shows the session is really called `loop-github-octo-foo_js-15`.
5. Post another comment. The delivery's liveness probe (`tmux has-session -t
   loop-github-octo-foo.js-15`) fails, the dispatcher respawns, and
   `tmux new-session` reports `duplicate session: loop-github-octo-foo_js-15`.
   The work item never gets a session the operator can reach.

## Expected vs actual

- **Expected:** the name the-loop records in the registry, logs, emits in the
  event log and posts on the ticket is **the name tmux actually gave the
  session**, so the published `tmux attach -t …` command works and every
  subsequent probe/paste/kill addresses the right session.
- **Actual:** the-loop mints a name tmux is guaranteed to rewrite, then keeps and
  publishes the pre-rewrite spelling. The attach command fails, the liveness
  probe reads a live session as absent, and the respawn collides with it.

## Root cause (confirmed by reading the code and by running tmux)

| # | Site | Defect |
|---|------|--------|
| C1 | `runner.py: target_for` | Returns `loop-<slug>` verbatim. Its docstring already knows `:`/`.` are tmux target syntax ("`-` separated (`:`/`.` are tmux target syntax)") — but only the **`/` → `-`** substitution happens, inside `WorkItemRef.slug`, which explicitly preserves `.`. Nothing ever applies tmux's own `session_check_name()` rewrite. |
| C2 | `registry.py: Session.tmux_target` | Stores whatever it is given and is the value every consumer uses (`announce`, `sessions attach`, `deliver`, `kill`, `terminate_harness`). A record written before this fix holds the pre-rewrite spelling, so upgrading alone would not heal an existing session. |
| C3 | `runner.py: _LOOP_TARGET_RE` | The guard authorising `terminate_harness` to signal pane pids admits `.`, i.e. it admits exactly the strings tmux re-parses as `session.window`. Nothing exploits it today (`has_session` fails first), but the guard's job is to make that unreachable by construction. |

## Requirements

> A bug's requirements are the correct behaviour plus proof it stays correct. The
> `(ACn)` tags are the stable identifiers `design.md`, `tasks.md` and the
> `Requirement:` lines on the integration tests all reference.

### Requirement 1 — the-loop only ever mints names tmux keeps verbatim

#### Acceptance criteria (EARS)

1. WHEN the-loop derives a tmux session name for a work item THEN the name SHALL
   contain no character tmux rewrites — no `.` and no `:` — so that the name
   tmux creates is byte-for-byte the name the-loop derived. (AC1)
2. WHEN a work item's slug contains no such character THEN its tmux session name
   SHALL be **unchanged** from today's, so no existing session, registry record
   or already-posted attach command is invalidated by this fix. (AC2)

### Requirement 2 — what the-loop records, publishes and re-addresses is the real session name

#### Acceptance criteria (EARS)

1. WHEN a session record is constructed or loaded from the registry THEN its
   `tmuxTarget` SHALL be normalised to the name tmux uses, so a record written
   **before** this fix addresses the session tmux actually created rather than a
   name that does not exist. (AC3)
2. WHEN the-loop announces a session on the work item THEN the `tmux attach -t
   <name>` command in that comment SHALL name a session tmux can find. (AC4)
3. WHEN the-loop probes, pastes into, terminates or kills a session THEN it
   SHALL address it by that same normalised name, so a dotted slug no longer
   produces a `session_missing` reading of a live session. (AC5)

### Requirement 3 — the pane-signalling guard cannot admit a re-parsed target

#### Acceptance criteria (EARS)

1. WHEN `terminate_harness` is asked to signal the processes inside a tmux
   target THEN it SHALL refuse any target containing `.` or `:` — the characters
   that make tmux read a session name as `session:window.pane` — so a corrupted
   or hand-edited `tmuxTarget` cannot aim a signal at another session's panes.
   (AC6)

### Requirement 4 — the fix is proved, and stays proved

#### Acceptance criteria (EARS)

1. Every acceptance criterion above SHALL be covered by a test that fails before
   the fix and passes after it (`tdd.mode: standard`). (AC7)
2. The stub tmux used by the integration tests SHALL model tmux's own name
   rewrite, so that a defect of this shape is expressible — and therefore
   catchable — at the integration level rather than only in unit tests. An
   integration test SHALL reproduce the reporter's scenario end to end: a work
   item whose slug contains a dot is spawned, and the name recorded and
   announced is the name the stub tmux created. (AC8)

## Security considerations

No new attack surface; one existing guard **narrowed**.

- **Every trust boundary is unchanged.** The name being fixed is derived
  end-to-end from data the-loop already trusts: the work-item ref (parsed and
  charset-restricted by `WorkItemRef.parse`/`slug`) and, for legacy records, the
  registry file the-loop itself wrote. No event payload, comment body or other
  untrusted input reaches the name, a tmux argv, or a spawn decision. The
  normalisation is a pure, total string function with no I/O.
- **The fix removes a target-injection *shape*, and adds none.** `.` and `:` are
  tmux's target grammar (`session:window.pane`), so a name carrying them is
  re-parsed by tmux into a target the-loop did not mean — demonstrated above,
  where `has-session -t loop-a.b-15` resolves to a *pane* lookup. Stripping them
  at the single point where names are minted, and again when a record is loaded,
  means every argv the-loop hands tmux names exactly one session. The
  `_LOOP_TARGET_RE` guard on `terminate_harness` (the only path that reaches OS
  processes) is tightened to match, so the ambiguous shape is rejected by
  construction rather than merely unreachable in practice.
- **`kill-session` is not newly reachable.** The set of names the-loop will kill
  is still exactly `target_for()` output plus normalised registry values; the
  issue-146 rule (only a definite dead-pane reading licenses a kill) is
  untouched. What changes is that those names now resolve to the session
  the-loop meant, which strictly reduces the chance of acting on the wrong one.
- **Abuse case considered — colliding on another work item's session.** Because
  the rewrite maps `.` onto `_`, two work items whose slugs differ *only* in a
  `.`/`_` position (`octo/foo.bar#15` and `octo/foo_bar#15`) map to one tmux
  name. This aliasing is tmux's, not the-loop's — tmux itself cannot host both
  (`new-session -s loop-a_b-15` against an existing `loop-a.b-15` answers
  `duplicate session`), so no naming scheme the-loop can choose makes both
  attachable under their natural names. The bounded consequence is documented in
  § Out of scope; it is **not** a new destruction path: the issue-146 pre-flight
  refuses to spawn over a live occupant, so the worst case is an event delivered
  into the aliased work item's session, which is visible on both tickets (each
  announcement names the shared target) rather than silent.
- **No new secrets, files, network calls, config surface, or dependencies.**

## Out of scope

- **Making the `.`/`_` alias injective.** Encoding the distinction back into the
  name (escaping `_`, or appending a hash of the pre-rewrite slug) would change
  the session name of *every* work item with an underscore, or make dotted names
  unreadable, to separate a pair of work items tmux cannot host simultaneously
  anyway. The minimalism ladder says no: the aliasing is recorded here and in
  `_clear_target`'s docstring — whose "an occupant is always this work item's own
  agent" reasoning is qualified accordingly — rather than papered over.
- **Changing `WorkItemRef.slug`.** The slug is also the registry **file name**,
  and it is deliberately backwards compatible (issue-130: "every ref string
  already on disk still parses to the same work item, and `slug` still resolves
  to the same file name"). Rewriting dots there would rename every registry file
  on GHE installs. The tmux name is a *rendering* of the slug for one consumer;
  that is where the rewrite belongs.
- **Renaming tmux sessions created before this fix.** Nothing is renamed: a
  session created under a dotted spelling was *already* named with underscores by
  tmux, so normalising the stored value is what makes the record correct. No
  `rename-session` call, and no migration file, is needed.
- **Re-announcing on the ticket.** A first-spawn-only announcement stays
  first-spawn-only (owner decision, PR #87). A work item already carrying a
  wrong attach command gets a correct one on its next *first* spawn; the
  operator's remedy in the meantime is `the-loop sessions list`, which now prints
  the real name.
- **The rest of tmux's `session_check_name` behaviour.** It also `vis`-escapes
  non-printable and non-ASCII bytes. `WorkItemRef.slug` already restricts the
  name to `[A-Za-z0-9._-]`, so `.`/`:` are the only reachable rewrites; guarding
  the unreachable ones would be untestable code.

## Open questions

None. The issue states the defect and the expected outcome ("the final tmux
session details posted on the gh issue or work item is wrong — fix this"); this
spec follows it, and resolves the one thing it leaves open — what to do about
records written before the fix — by normalising on load rather than by shipping a
migration.
