---
type: requirements
phase: requirements-definition
workItem: issue-128
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
collaborators: [engineer, technical-writer]
overrides: {}
---

# Requirements: portable state — what travels with the work, what belongs to the machine

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #128](https://github.com/MadaraUchiha-314/the-loop/issues/128) asks how to carry
the state of the issues/PRs the-loop is tracking from one machine to another, and asks it
as four questions. The answers, established by reading every writer under `state.root`
and recorded here so nobody has to read them again:

1. **Which files should not be git-ignored?** One directory:
   `<state.root>/portable/` — one record per work item. Nothing else.
   *(Originally two paths under `sessions/`; the [PR #129
   review](https://github.com/MadaraUchiha-314/the-loop/pull/129#issuecomment-5139488802)
   asked for the layout to be consolidated, which is R6 below.)*
2. **Is the poll state alone enough?** No. It remembers which comments have already been
   seen, so a second machine does not re-forward a thread's whole history — but it holds
   no record of which work items an authorized user actually *armed*. Carrying it alone
   gives you a quiet daemon that has forgotten what it was supposed to be running. Both
   halves now sit in one file per work item, so carrying one and not the other is no
   longer a mistake it is possible to make.
3. **Should the session registry come too?** **No**, and the distinction is the whole
   answer. A control record is a statement about a *work item* ("an authorized user asked
   for this to be running") and is true on any machine. A session record is a **handle to
   a process on one machine** — a harness conversation id, an absolute `cwd`, a tmux
   target. Copied elsewhere it is not merely useless:
   `SessionRegistry.find_by_work_item` counts it as live, so the duplicate guard refuses
   to spawn the session the second machine actually needs, and every event routed to that
   work item is delivered to a conversation that does not exist there. It now lives in its
   own directory (`<state.root>/local/`) so the boundary is a path, not a rule.
4. **Is any of this documented?** No. `state.root` is documented as a *config option*
   (which paths default from it) and the sentence that follows it — *"All of it is
   git-ignored runtime state"* — is the only thing the docs say about the files
   themselves. Their structure, their lifecycle and which of them mean anything off this
   machine are documented nowhere. This work item is mostly that page.

## Analysis

### The split that decides everything

Everything under `state.root` is one of two kinds of thing, and the portability question
has a different answer for each:

- **Facts about the world.** What GitHub already told us and what an authorized human
  asked for: which comments have been seen, which items are armed. These are true
  regardless of which laptop is running the daemon. They are *slow* to rebuild (a fresh
  `poll-state.json` re-baselines every watched thread) and *impossible* to rebuild
  faithfully (nothing on GitHub records that a `stop` was honoured).
- **Handles to this machine.** A harness session id, a working directory, a tmux target,
  a pid, an append-only local log. These name things that exist only where they were
  created. They are cheap to rebuild — the daemon rebuilds them by spawning — and
  actively harmful when moved.

That is why "make the state portable" is not answered by tracking the directory: half of
it is not state *about* anything, it is a set of local handles.

### Every generated path, classified

Written as the layout that shipped (R6); the pre-issue-128 paths each row replaced are in
the last column.

| Path (default) | Written by | Holds | Travels? | Was |
|---|---|---|---|---|
| `<root>/local/<slug>.json` | `sessions/registry.py` | `harnessSessionId`, `cwd`, `runner`, `tmuxTarget`, `status`, `recentDeliveries` | **No** — handles to one machine; a copy wedges the duplicate-session guard | `<root>/sessions/<slug>.json` |
| `<root>/portable/<slug>.json` § `control` | `control.py` | last `start`/`stop`/`pause`/`resume`, `actor`, `source`, `requestedAt` | **Yes** — a statement about the work item | `<root>/sessions/control/<slug>.json` |
| `<root>/portable/<slug>.json` § `poll` | `poller/poller.py` | `seenComments`, `commentAttempts`, `spawn`, `lastPolledAt` | **Yes** — GitHub-side facts (the attempt ledgers are local bookkeeping, and self-heal) | one shared `<root>/sessions/poll-state.json` |
| `<root>/logs/events.jsonl` | `eventlog.py` | append-only decision trail | **No** — a per-machine audit record; two machines appending to one tracked file conflict on every line | unchanged |
| `<root>/gh-webhook.pid` | `commands/gh_webhook.py` | receiver pid | **No** — meaningless off the host | unchanged |
| `routing.workspace.root/…` | `workspace.py` | per-work-item git checkouts | **No** — regenerable, and not under `state.root` | unchanged |
| `docs/specs/<id>/graph-state.json` | `graph/state.py` | which node a work item is on | **Already tracked**, by design (issue-109) — the precedent this work item follows | unchanged |

The last row is the point: the-loop already made exactly this call once. Graph state is
checked in *because* it must survive a machine change, a session change and a multi-day
human review — and it is a cache, never an authority, so a stale copy degrades to a
recompute rather than to a wrong answer. The same reasoning picks the portable half above.

### Why each store exists

The consolidation question deserves the direct answer, recorded here because it is the
part a reader will want first: **`poll-state.json` is not the only store that has to be
persisted.** Three reasons, none of which it covers.

1. **Restart survival.** A session record maps a work item to a harness conversation id,
   its `cwd` and its tmux target. Held in memory, a daemon restart forgets it, and the
   next comment on an item starts a *new* conversation with no memory of the work in
   flight — and the duplicate-session guard goes with it.
2. **They are the IPC between the CLI and the daemon.** `the-loop sessions
   list|attach|start|stop|pause|resume` runs in a different process and reads both stores
   straight off disk (`commands/sessions_cmd.py`). Without files there is no channel:
   `attach` could not find the tmux session, `stop` could not tell the daemon anything.
3. **Neither is derivable from GitHub.** A conversation id exists nowhere upstream, and
   nothing upstream records that a `stop` was *honoured* — which is the whole point of
   decision-040's arming/starting split. Control also has to exist **before** a session
   does (`pause`/`stop` must land on an item that has not spawned), so it cannot simply
   be a field on a session record.

What *was* redundant is the **grouping**: three stores shaped by who writes them. R6
regroups them by what they are.

### Why the classification needs a home in code

The paths are declared once, in `the_loop.state.StateLayout` (issue-106). Their
portability is declared nowhere, so the next generated file will be added with no prompt
to ask which kind it is — and a wrong answer is either lost state or a `cwd` from
someone's laptop committed to a public repository. Issue-121 hit the same shape with the
harness-config read surface and solved it by declaring the surface as data and pinning it
with a test. This does that.

## Requirements

### Requirement 1 — the state is documented

**User story:** As an operator, I want one page that says what the-loop writes, where,
and what is in it, so that I can back it up, move it or wipe it without reading the
source.

#### Acceptance criteria (EARS)

1. WHEN the CLI documentation is read THEN it SHALL contain a page describing every
   generated path: what writes it, what it holds field by field, when it is created and
   pruned, and what is lost if it is deleted.
2. WHEN that page is read THEN each path SHALL carry an explicit **portable / local**
   classification and the reason for it.
3. WHEN that page is read THEN it SHALL answer the four questions of issue #128
   directly, including why the session registry is the one file that must **not** be
   carried.
4. WHEN the page is read THEN it SHALL be reachable from the CLI sidebar, from
   [Concepts](/cli/concepts) and from the `state.root` option, AND the claim *"All of it
   is git-ignored runtime state"* SHALL no longer appear.

### Requirement 2 — the recipe is copyable, and dogfooded

**User story:** As an operator, I want a `.gitignore` block I can paste, so that carrying
state is a decision I make once rather than a per-file judgement call.

#### Acceptance criteria (EARS)

1. WHEN the state page is read THEN it SHALL give a complete `.gitignore` block that
   ignores every local path and leaves the portable directory tracked, including the
   `*.tmp` files the atomic writer creates.
2. WHEN this repository's `.gitignore` is read THEN it SHALL be that block, applied to
   this repository's own `state.root` — the-loop tracks its own portable state.
3. WHEN the page is read THEN it SHALL state the hand-off procedure (commit on the
   machine that is stopping, pull on the machine that is starting) and SHALL say that
   the daemon never commits state itself.
4. IF an operator's `state.root` is outside a repository (`~/.the-loop`) THEN the page
   SHALL say so and SHALL describe the alternative (copy `portable/`, or point
   `state.root` at a tracked directory).

### Requirement 3 — the classification cannot drift

**User story:** As a maintainer, I want a red build when a new generated path is added
without saying whether it travels, so that the answer stays true after the next feature.

#### Acceptance criteria (EARS)

1. WHEN `the_loop.state` is imported THEN it SHALL expose a declaration of every
   generated path: its name, how it derives from the root, whether it is portable, and
   why.
2. WHEN the test suite runs THEN it SHALL assert that every path `StateLayout` produces
   appears in that declaration, naming the missing one when it does not.
3. WHEN the test suite runs THEN it SHALL assert that every declared path is documented
   on the state page with a matching portability classification.
4. WHEN the test suite runs THEN it SHALL assert that this repository's `.gitignore`
   contains the documented block verbatim, so the page and the repository cannot
   disagree.
5. WHEN `docs/` is absent (a source distribution) THEN the documentation assertions SHALL
   skip rather than fail, matching `test_docs_parity.py`.

### Requirement 4 — the reasoning is recorded as a decision

**User story:** As a maintainer, I want the portable/local split written as a decision, so
that "why isn't the session registry checked in?" is answered by a link.

#### Acceptance criteria (EARS)

1. WHEN `docs/decisions/` is read THEN it SHALL contain a record stating the split —
   facts about the world travel, handles to a machine do not — SHALL name what is
   portable and what is local, and SHALL record that the directory layout follows that
   classification rather than the writers.
2. WHEN that record is read THEN it SHALL state the consequences accepted: no automatic
   commit, one writer at a time, and JSON merge conflicts resolved by hand.
3. WHEN that record is read THEN it SHALL be listed in `docs/decisions/decisions.md`, AND
   `docs/capabilities/cli.md` SHALL describe the behaviour and carry a history row for
   this work item.

### Requirement 5 — no behavioural change

**User story:** As an operator, I want this to be documentation, a declaration and a
`.gitignore`, so that upgrading changes nothing about how my daemon behaves.

#### Acceptance criteria (EARS)

1. WHEN the CLI runs after this change THEN what each store *records* SHALL be unchanged
   field for field — only where it is written changes (R6), and the upgrade path (R7)
   keeps reads working across the move.
2. WHEN the full test suite runs THEN it SHALL pass. *(Superseded in part by R6: the
   reorganisation is a behaviour change, so tests that assert the old paths are updated
   deliberately. No test's **intent** is weakened to accommodate it.)*

### Requirement 6 — the layout follows the classification

**User story:** As an operator, I want the files grouped by whether they travel rather
than by which component wrote them, so that carrying state is a directory, not a puzzle.

> Added after the [PR #129 review](https://github.com/MadaraUchiha-314/the-loop/pull/129#issuecomment-5139488802):
> *"Do we need so many different files and folders? Can we consolidate the structures?"*
> The stores are not redundant (see [Why each store exists](#why-each-store-exists)), but
> the grouping was. The owner's call was to do the reorganisation in this work item.

#### Acceptance criteria (EARS)

1. WHEN the CLI generates state THEN the portable half SHALL be one record per work item
   at `<state.root>/portable/<slug>.json`, carrying a `control` section and a `poll`
   section, AND the machine-local session record SHALL be `<state.root>/local/<slug>.json`.
2. WHEN either section is written THEN the write SHALL replace **only** that section
   (read-modify-write) so a poll cycle cannot erase a control command recorded a moment
   earlier by the other ingress, AND the write SHALL remain atomic.
3. WHEN a record is left with neither section THEN it SHALL be removed, so `portable/`
   lists only work items the-loop knows something about.
4. WHEN the `.gitignore` recipe is written THEN it SHALL need no negation patterns.
5. WHEN two machines poll the same sources THEN they SHALL contend only on work items
   they both worked — the single shared `poll-state.json` SHALL be gone.

### Requirement 7 — upgrading loses nothing

**User story:** As an existing operator, I want to upgrade without re-forwarding threads
or losing what I armed, so that the reorganisation costs me nothing.

#### Acceptance criteria (EARS)

1. WHEN a work item's new record has no `control`/`poll` section THEN the-loop SHALL read
   the pre-issue-128 location (`<root>/sessions/control/<slug>.json`,
   `<root>/sessions/poll-state.json`) and, for the poll section, the pre-issue-106
   `.the-loop/poll-state.json`.
2. WHEN a section adopted that way is next written THEN it SHALL be written to the new
   layout, AND the old file SHALL be left untouched — a read shim, never a destructive
   move.
3. IF a record exists in **both** layouts THEN the new one SHALL win, so a `stop` recorded
   today is not overridden by a stale `start` in the old tree.
   3a. WHEN a section is deliberately removed (a work item ended) THEN it SHALL be
   tombstoned so the old tree cannot resurrect it, durably enough to survive a daemon
   restart, AND the tombstone SHALL be per **section**: a record written by the poller
   SHALL NOT stop a pre-issue-128 control record from being adopted.
4. WHEN a CLI config still declares `polling.stateFile` THEN the CLI SHALL refuse to run,
   naming `state.root` as the replacement, AND `the-loop migrate-config` SHALL remove the
   key and bump the schema version.

## Non-functional requirements

- **Reversible.** Un-ignoring a path only makes git *able* to see it. An operator who
  wants nothing tracked deletes the two negation lines; nothing else depends on them.
- **Honest about cost.** The page states the two real costs of tracking state — a working
  tree that goes dirty while the daemon runs, and hand-resolved JSON conflicts if two
  machines run at once — rather than presenting the recipe as free.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item changes what
> leaves a machine, so it is a security question even though it ships no code path.

- **Actors & trust.** The asset is the operator's machine and the repository the state is
  tracked in. Untrusted actors: anyone who can read a public repository (disclosure), and
  anyone who can open a pull request against the repository the state lives in
  (tampering).
- **Disclosure — what the two portable files contain.** Control records hold a work-item
  ref, one of four fixed keywords, a GitHub login, a timestamp and an optional note; poll
  state holds work-item refs, comment ids and timestamps. All of it is already visible on
  the public ticket the record is about. **This is a second, independent reason the
  session registry is excluded**: `cwd` is an absolute path from the operator's
  filesystem (username, directory layout) and `harnessSessionId` is a resume handle to a
  conversation. Neither belongs in a repository, whoever can read it.
- **Tampering — a tracked control record is an input.** `ControlStore.start_requested`
  gates autonomous spawning, so a forged `start` record merged into a repository the
  daemon later pulls is an attempt to arm a work item without commenting on it. Three
  things bound it, and the page SHALL state all three: the record only ever *arms* — the
  auto-execute **label** (repository write access) is still required and
  `spawnOnUnmatched` still governs; a `.the-loop/sessions/` diff in a pull request is a
  reviewable, obvious event, and is called out as one; and the recommendation is that
  state be tracked in a repository the operator alone can push to.
- **Abuse cases (EARS).**
  1. WHEN a pull request modifies a tracked control record THEN the reviewer SHALL treat
     it as a configuration change, per the documented review rule (the same stance
     `reviews.critics[]` already carries as executable config).
  2. WHEN state is tracked in a repository that accepts third-party pull requests THEN
     the documentation SHALL warn that arming records are then proposable by strangers,
     AND SHALL state that the label gate is what keeps that insufficient.
- **Fail closed.** Unchanged. A missing or unreadable control record reads as "nothing
  recorded" and the daemon declines to spawn; a missing poll state re-baselines rather
  than re-forwarding blind.
- **Risk tier: 3** (`autonomy.defaultTier`). Documentation, a declaration with no
  behaviour, a test and a `.gitignore`. `security.review.humanSignOffMinTier` is 4, so no
  named human security sign-off is required; the PR review is the tier-3 gate.
