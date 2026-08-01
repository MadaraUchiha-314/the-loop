# Decision 047: the portable directory carries a derived index, and derived means nothing may read it

- **Status:** proposed
- **Date:** 2026-07-31
- **Deciders:** @MadaraUchiha-314 (issue #130)
- **Work item:** issue-130
- **Spec:** `docs/specs/issue-130/`
- **Builds on:** [decision-046](decision-046.md) — which created `<state.root>/portable/`,
  the tracked half of the-loop's generated state, and with it the reader this decision is
  about.

## Context

[Issue #130](https://github.com/MadaraUchiha-314/the-loop/issues/130): *"currently
portable folder is just a bunch of files"*.

It is, and that is a consequence of the previous decision rather than an oversight in it.
`portable/` is the only generated state the-loop **tracks in git**, which makes it the
only generated state a *person* reads — in a pull-request diff, in a terminal, months
later. The daemon never needed a listing: it addresses records by path, one at a time. A
reader has no such luxury, and the file names are slugs, so answering "which work items is
this daemon tracking?" means opening every file.

The same issue asks for the records' `ref` to be navigable. `"github:octo/repo#15"` is a
machine identity — parsed into provider/owner/repo/number, and the source of the record's
own filename — and it is the only thing in the file that names what the record is *about*.

An index is easy to add and easy to get wrong. The failure mode is not the file; it is
what starts depending on it.

## Decision

**`portable/` carries `index.json`: one entry per record, derived from the directory on
every write, and read by nothing in the-loop.** Records carry a `url` beside `ref`, derived
by the same rule.

Four properties, each of which is the mitigation for a specific way this goes wrong:

1. **Derived, not maintained.** Every write and every removal rebuilds the entries by
   scanning the directory. An incrementally-maintained list would be faster and would
   drift — from a record removed by hand, from a version that kept no index, from a crash
   between two writes. Rebuilding makes drift unrepresentable: the directory *is* the
   index, and the file is a rendering of it.
2. **Read by nothing.** No command, hook or daemon path consumes it. This is what keeps a
   stale index cosmetic rather than behavioural, and what makes a **forged** one inert —
   the file is tracked, so on a repository that accepts pull requests it is proposable by
   strangers. Compare the `control` section, which *is* an input and needs the
   auto-execute label to bound it.
3. **Best-effort to write.** An `OSError` while writing or removing the index is logged
   and swallowed. The record beside it states that an authorized user armed a work item;
   the index is a convenience. Failing an arming write because a convenience could not be
   written would be a silent disarm — the exact failure decision-046 exists to prevent.
4. **Deterministic.** Entries ordered by `ref`, so an unchanged directory produces a
   byte-identical file, and a diff shows only what changed.

**The `url` is added, not substituted.** `ref` keeps its form and meaning. The URL is
derived only for `github` refs whose owner and repo are GitHub's own name shape, and
omitted otherwise: a ref carries no host, and `WorkItemRef.parse` splits the path at the
first slash, so an unchecked interpolation can produce a link to something other than the
work item it claims. No link beats a misleading one.

## Consequences

**Positive.**

- `portable/` answers what it holds without being opened file by file, and each answer
  carries a link to the ticket it is about.
- A pull request that touches tracked state now has a readable summary of what changed in
  it, in the diff, beside the records.
- The index is a generated path like any other, so it went through the
  `GENERATED_PATHS` gate: classified (portable — left behind, it would describe a
  directory that is not there), documented, and pinned by the parity tests.

**Negative / accepted costs.**

- **One shared file returns.** decision-046's split gave two machines a conflict *only*
  when they worked the same work item; both now write `index.json` whatever they touched.
  This is the price, and it is bounded by property 1: the conflict is not about facts.
  Take either side, or delete the file — the next write rebuilds it. The documentation
  says exactly that.
- **A write does slightly more I/O**: one small read per record in the directory, plus one
  atomic write. The directory holds one file per *actively tracked* work item, and this
  path already writes a file.
- **A second thing describing the same facts.** Mitigated by 1 and 2 rather than by
  discipline: the only way to consume the index is to read it, and nothing does.

## Alternatives considered

| Option | Why not |
|---|---|
| A command (`the-loop portable list`) instead of a file | Does not help the reader the issue is about — someone looking at a directory in a pull request, on a machine that may not have the CLI. The file *is* the interface. |
| Incrementally maintained index (append/remove entries) | Faster, and able to drift from the directory it claims to describe. Since the index is only ever read by people, a wrong index is worse than a slow one. |
| Make the index authoritative (the daemon reads it) | Turns a convenience into a second source of truth, and a tracked, externally-proposable file into an input. Both are exactly what property 2 refuses. |
| `ref` becomes a URL | An in-place format break for a navigation aid: the slug derives from the ref, the pre-issue-128 shim keys on it, and a URL has no provider prefix (`jira:` is reserved) and cannot be parsed back without knowing each provider's layout. |
| Guess a URL for any ref | A ref carries no host and no provider-specific layout. A link that 404s, or that points at a different repository because a name contained a slash, is worse than an absent field. |
| A markdown index (clickable on GitHub) | JSON matches the directory it indexes and the tooling the state docs assume (`jq`). A second rendering is a second thing to keep in step — reconsiderable if a rendered table is what the operator actually wants. |
