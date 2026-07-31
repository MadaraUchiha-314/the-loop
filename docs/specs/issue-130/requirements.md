---
type: requirements
phase: requirements-definition
workItem: issue-130
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
collaborators: [engineer, technical-writer]
overrides: {}
---

# Requirements: an index for `portable/`, and a ref you can click

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #130](https://github.com/MadaraUchiha-314/the-loop/issues/130) is about the
directory [issue-128](https://github.com/MadaraUchiha-314/the-loop/issues/128) created.
`<state.root>/portable/` is the half of the-loop's generated state that travels with the
work and is therefore **tracked in git** — one record per work item. Two complaints, both
about reading it:

1. *"currently portable folder is just a bunch of files"* — the directory names its
   contents by slug (`github-octo-repo-15.json`). To answer "what is the-loop tracking?"
   you open every file, because the directory listing carries no answer and the record
   names are a shape, not a list.
2. *"the `ref` in the portable file doesn't point to a URL"* — a record says
   `"ref": "github:octo/repo#15"`. That is a machine identity: it is what the daemon
   parses, what the slug is derived from, and what the legacy shim keys on. It is not
   something you can click, and every consumer of these files so far has been a human
   reading a diff in a pull request.

Both are navigability, not correctness. Nothing behaves differently as a result of this
work item; a directory that was write-only becomes readable.

## Analysis

### What the directory is, and what that permits

`portable/` is generated state with an unusual property: it is **tracked**. It is read in
two very different ways — by the daemon (`WorkItemStore`, one record at a time, by path)
and by a person (a pull-request diff, `ls`, `cat`). The daemon has never needed an index;
the person has never had one.

That asymmetry decides the shape of the answer:

- The index is **for the reader**. Nothing in the-loop may read it, or it becomes a second
  source of truth for what the directory already states — and a stale second source is
  worse than none, because the daemon would then act on it.
- It must therefore be **derived**, and derived *from the directory*, on every write.
  An index that accumulates entries drifts the moment a record is removed by hand, or by a
  version that did not maintain it.

This is the same reasoning `docs/specs/<id>/graph-state.json` already carries
([state on disk](/cli/state)): a cache, never an authority, so a stale copy degrades to a
recompute rather than to wrong behaviour.

### The cost this reintroduces, stated plainly

[decision-046](../../decisions/decision-046.md) split the state by portability, and one of
the results was that **two machines conflict only if they worked the same work item** —
the pre-issue-128 layout had a single shared `poll-state.json`, which guaranteed a
conflict. An index is one shared file again, written on every record write. Two machines
that touch *different* work items now collide on it.

That is a real regression of that property, and it is accepted here for one reason: the
index is derived, so the conflict is not a conflict about facts. Either side may be taken
and the next write repairs it. The requirements below make that resolution *true* (R1.5,
R1.6) rather than merely claimed — deterministic ordering so the diff is minimal, and a
full rebuild on every write so any accepted merge converges.

### Why `ref` gains a URL rather than becoming one

The obvious reading of the second complaint is "put a URL in the `ref` field". That is
rejected, and the reason is worth writing down once:

- `ref` is parsed (`WorkItemRef.parse`) into provider/owner/repo/number, and the **slug**
  — the record's own filename — is derived from it. A URL has no provider prefix, so
  `jira:` (reserved) could not be expressed, and reversing a URL to a ref requires knowing
  each provider's URL layout.
- Every record on disk today carries the ref form, as does the pre-issue-128 poll state
  the upgrade shim reads. Redefining the field would make an in-place format break out of
  a navigation aid.

So the ref stays the identity and a `url` field is **added** beside it. This is the
harness's usual shape: the machine's name for a thing and the human's link to it, both
present, neither pretending to be the other.

### A URL cannot always be derived

A work item whose provider is not `github`, or whose owner/repo are not the shape GitHub
accepts, gets **no URL** rather than a guessed one. Omission is honest; a link that 404s
is not.

### The host: corrected on review

The first version of this section said a ref carries no host, so a URL assumes
`github.com` and GitHub Enterprise is out of scope. The owner rejected that on
[PR #131](https://github.com/MadaraUchiha-314/the-loop/pull/131):

> Why is this out of scope? This should be in scope. When the poller is polling or the
> webhook is receiving, we can identify the host as well.

Correct, and checkable: a webhook payload carries `repository.html_url`; a polled item
carries its own (the poller already stores it as `WorkItem.url`). The host was not
unavailable, it was being **discarded** at the ingress one line before the ref was built.
"A ref carries no host" described the format as though it were a constraint — but the
format is ours.

It also matters beyond the link. A work item on `ghe.corp.example` and one on `github.com`
with the same owner/repo/number are *different work items*; sharing a registry entry, a
poll ledger and a file name between them is a collision. So the host belongs to the
**identity** — R5 — and the URL is then simply derived from it like everything else.

## Requirements

### Requirement 1 — an index of the portable directory

**User story:** As an operator (or a reviewer of a pull request that touches tracked
state), I want one file that lists every work-item record in `portable/`, so that I can
see what the-loop is tracking without opening each record.

#### Acceptance criteria (EARS)

1. WHEN a work-item record is written THEN the system SHALL write an index at
   `<state.root>/portable/index.json` listing every record in that directory.
2. WHEN a work-item record is removed THEN the system SHALL rewrite the index without it.
3. WHEN the last record in the directory is removed THEN the system SHALL remove the index
   too, so an empty `portable/` holds nothing.
4. The index SHALL be **derived from the directory** on each write — a scan, never an
   accumulated list — so that a record added, removed or edited by hand is reflected the
   next time anything is written.
5. Index entries SHALL be ordered deterministically (by `ref`), so that an unchanged
   directory produces a byte-identical file and a diff shows only what changed.
6. IF the index is absent, stale, corrupt or unwritable THEN no the-loop behaviour SHALL
   change: nothing reads it, a write failure SHALL be logged and swallowed rather than
   failing the record write it accompanies, and the next successful record write SHALL
   repair it.
7. The index SHALL NOT be a work-item record: reading the directory's records SHALL skip
   it, and it SHALL never be mistaken for one.

### Requirement 2 — every entry names the file, the work item and its URL

**User story:** As a reader of the index, I want each entry to tell me which file it
describes, which work item it is, where that work item lives, and what the record
contains, so that the index answers the question without a second lookup.

#### Acceptance criteria (EARS)

1. WHEN the index is written THEN each entry SHALL carry the record's `ref`, its `file`
   name relative to `portable/`, and the `sections` present in it (`control`, `poll`).
2. WHEN a work item's URL can be derived (R3) THEN the entry SHALL carry it as `url`.
3. WHEN a record is a **sealed** upgrade tombstone THEN its entry SHALL say so
   (`"sealed": true`) with no sections, so a record that looks empty is explained rather
   than surprising.
4. IF a file in the directory is not a readable record naming a work item THEN it SHALL be
   omitted from the index rather than described wrongly.

### Requirement 3 — a record carries a URL beside its ref

**User story:** As someone reading a work-item record (or its diff on GitHub), I want the
work item's URL in the file, so that I can navigate to the ticket the record is about.

#### Acceptance criteria (EARS)

1. WHEN a work-item record is written THEN it SHALL carry a `url` field beside `ref`,
   pointing at the work item's page.
2. The `ref` field SHALL keep its current form and meaning — the URL is added, never
   substituted — so that parsing, slug derivation and the pre-issue-128 shim are untouched.
3. IF a URL cannot be derived — the provider is not `github`, or the owner/repo are not
   the character shape GitHub accepts — THEN the field SHALL be omitted rather than
   guessed.
4. WHEN a record written by an earlier version (no `url`) is next written THEN it SHALL
   gain the field, so the directory converges without a migration.

### Requirement 4 — the index is a classified, documented generated path

**User story:** As a maintainer, I want the index to go through the same gate every other
generated file goes through, so that "does this travel?" is answered where the file is
invented rather than after someone copies the wrong thing.

#### Acceptance criteria (EARS)

1. WHEN the index path is added to `StateLayout` THEN it SHALL be declared in
   `GENERATED_PATHS` as **portable**, with its `holds`/`why`.
2. The index SHALL be documented in `docs/cli/state.md` — its shape, its lifecycle, what
   is lost if it is deleted, and how to resolve a conflict on it — with the same
   classification as the declaration, and SHALL appear in the `state.root` table in
   `docs/config/cli/index.md`.
3. The published `.gitignore` recipe SHALL continue to track it (it is portable), with no
   new pattern needed.
4. The existing parity tests SHALL cover it: a build SHALL go red if the declaration, the
   documentation and the recipe disagree about it.

### Requirement 5 — a ref names its host when it is not the default one

**User story:** As an operator running the-loop against GitHub Enterprise, I want my work
items identified and linked by the host they actually live on, so that the record is about
my work item rather than about a github.com URL that does not exist.

#### Acceptance criteria (EARS)

1. A work-item ref SHALL be `<provider>:[<host>/]<owner>/<repo>#<number>`, and the host
   SHALL be omitted when it is the provider's default (`github.com`), so every ref written
   before this change parses to the same work item and resolves to the same file name.
2. WHEN a webhook event is routed THEN the host SHALL be read from the event — the
   repository's `html_url`, falling back to the issue/PR URL — and never from
   configuration or assumption.
3. WHEN a polled work item is identified THEN its host SHALL be read from its own URL, and
   SHALL agree with the ref the router derives for the same item, because one keys the
   poll ledger and the other keys the routing.
4. IF a ref's path is neither `<owner>/<repo>` nor `<host>/<owner>/<repo>` — where a host
   is a dotted name, or one with an explicit port — THEN parsing SHALL fail, rather than
   yield a work item whose identity is a path fragment.
5. WHEN a URL is derived for a ref THEN it SHALL use the ref's host.
6. Two work items with the same owner, repo and number on different hosts SHALL be
   different work items, with different records.

## Security considerations

**Untrusted actors and inputs.** The refs the index is built from arrive from GitHub
webhook payloads and poller responses, which are attacker-influenced (anyone who can open
an issue or name a repository). The index and the `url` field are both **derived from
data already in the record**; neither introduces a new ingress.

**Trust boundaries.**

- *Directory → index.* A file in `portable/` may be anything (hand-written, corrupt, a
  stray). The index builder reads with the same tolerant reader the store already uses and
  omits what it cannot parse (R2.4) — a corrupt neighbour cannot fail a write.
- *Ref → URL.* Building a URL by interpolating a ref into a string is the one new
  operation. The parts are constrained twice over. At **parse** (R5.4) the path must be
  `[<host>/]<owner>/<repo>` — previously it split at the *first* `/` and let the rest be
  the "repo", so `github:octo/repo/../../evil#15` became a work item whose identity was a
  path fragment; it is now rejected outright. At **derivation** (R3.3) the host must be a
  bare hostname with an optional port, and owner and repo must match GitHub's own name
  shape (`[A-Za-z0-9._-]+`) — no `/`, so no path segment can be injected; no `@`, so no
  credentials can be smuggled. Anything else yields no URL. Fail closed: no link beats a
  misleading one.
- *Host → URL.* The host now comes from an attacker-influenceable field
  (`repository.html_url` on a webhook payload). It is extracted with a scheme-anchored
  regex that takes the authority only, and is then subject to the same shape check before
  it reaches a URL. A payload naming a host the operator does not use produces a record
  that links there — which is no more than the payload already claimed, and the receiver's
  signature verification is what bounds who can make that claim.

**Abuse cases.**

1. *A forged index merged into a tracked repository.* Inert by construction — nothing
   reads it (R1.6), so the worst outcome is a reader misled until the next write repairs
   it. Contrast the `control` section, which **is** an input and is bounded by the
   auto-execute label ([state on disk](/cli/state) § Security).
2. *A crafted repository name yielding a link to somewhere else.* Bounded by R3.3 above,
   and pinned by a negative test.
3. *Disclosure.* The index holds refs, URLs, file names and section names — all of it
   already present in the records beside it and on the ticket it describes. Nothing that
   was local-only becomes tracked.

**Fail-closed behaviour is unchanged.** A missing or unreadable record still reads as
"nothing recorded", and the daemon still declines to spawn on its own.

## Out of scope

- **Reading the index anywhere.** No command, hook or daemon path consumes it. Making it
  an input is what would make it dangerous, and it is the one property this design rests
  on.
- **A markdown index.** JSON matches the directory it indexes (*"everything here is JSON
  or JSONL, meant to be read with `jq`"*), and a second rendering of the same list is a
  second thing to keep in step. Reconsider if a rendered table on GitHub is what the
  operator actually wants.
- **Host-aware `gh` invocations.** `comments.py`, `reactions.py` and the poll provider
  call `gh api repos/<owner>/<repo>/…`, which resolves through the operator's own `gh`
  host configuration — fine for a single-host deployment, insufficient for a daemon
  spanning two. R5 is what makes the host *available* to that work; passing it to `gh`
  touches authentication and is a follow-up work item.
- **A read-fallback to the pre-R5 (hostless) file name.** An existing GitHub Enterprise
  deployment is re-identified by R5: the ledger re-baselines once and a session should be
  re-registered. The shim shape exists in this codebase (issue-106, issue-128) and is
  cheap to add — held back because GHE was documented as unsupported, so the population it
  would serve is speculative. Documented rather than silent.
- **A `reindex` command.** The index self-repairs on the next record write, and an active
  daemon writes on every poll cycle. A command would be a second way to produce a file
  that is already produced automatically.
