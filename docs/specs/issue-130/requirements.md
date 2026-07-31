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

A ref carries no host. `github:octo/repo#15` is `github.com` by assumption, and the-loop
has no GitHub Enterprise support for the ref syntax to inherit (`workspace.defaultHost`
exists for *checkouts*, and is not reachable from a store that is handed a directory). A
work item whose provider is not `github`, or whose owner/repo are not the shape GitHub
accepts, therefore gets **no URL** rather than a guessed one. Omission is honest; a link
that 404s is not.

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
  operation. `WorkItemRef.parse` accepts any non-`#` text as the path, and splits it at
  the *first* `/`, so `repo` may contain further slashes or `..` — enough to make a
  derived URL point somewhere other than the work item it claims. The URL is therefore
  emitted only when owner and repo match GitHub's own name shape
  (`[A-Za-z0-9._-]+`), and omitted otherwise (R3.3). Fail closed: no link beats a
  misleading one.

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
- **GitHub Enterprise hosts.** The ref syntax has no host, and inventing one here would
  put a config-shaped decision inside a store. See Analysis.
- **A `reindex` command.** The index self-repairs on the next record write, and an active
  daemon writes on every poll cycle. A command would be a second way to produce a file
  that is already produced automatically.
