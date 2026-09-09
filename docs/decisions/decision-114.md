# Decision 114: a poll source's bare `OWNER/REPO` inherits the resolved GitHub host when the source is built, not when a ref is compared

- **Status:** proposed
- **Date:** 2026-09-09
- **Work item:** [issue-331](https://github.com/MadaraUchiha-314/the-loop/issues/331)
- **Deciders:** the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** decision-104 (one resolver for a host no event supplied; poll sources accept `[HOST/]OWNER/REPO` and own by host)

## Context

Issue-311 gave every `gh` call and every minted ref a host, and taught the poll source's
`owns()` to compare hosts so an enterprise source does not claim its github.com twin. It
left one value undecided: a `repos` entry written as bare `OWNER/REPO` parsed to
`RepoSpec(host="")`, documented as github.com. The listing for that entry, however, went
wherever `gh` resolved — `$GH_HOST` on an enterprise deployment — and the refs it minted
carried that host. `owns()` then refused every one of them, and closure reconciliation
silently did nothing (issue-331).

The ticket names two fixes: resolve an empty spec host inside `owns()` through the
resolver, or have the source inherit the resolved host at `from_source()` time.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The host is decided once, where the source is built.** `RepoSpec.parse` / `parse_repos` take a `default_host`; `from_source` / `build_provider` carry it; the daemon resolves it with `ghhost.github_host` from the same CLI config it reads `polling` from, at pre-flight, at the first plan and on every hot reload. | Every consumer of `RepoSpec.host` — the `--repo` argument, the scope name, `owns()`, `describe()` — then agrees by construction, with none of them learning about the resolver. Resolving inside `owns()` alone would fix the reported symptom and leave the listing still going wherever `gh` points: a source configured through `integrations.github.host` with no `$GH_HOST` would poll github.com while owning enterprise refs — the same asymmetry, mirrored. |
| D2 | **An inherited host passes the same normalisation and grammar as a written one.** `github.com` stays unwritten; anything that is not a host is refused with a `ValueError` at build time. | One grammar (`is_github_host`) for a host wherever it enters; a github.com deployment's argvs are byte-identical; a malformed default fails the source before it can reach `gh`. |
| D3 | **A written host wins over the default.** | A source may list repositories on two GitHubs; the explicit form issue-311 introduced keeps its meaning. |
| D4 | **`describe()` spells the host.** | The startup and reload log lines are where an operator sees which GitHub a source was bound to — the paper trail for a fix whose failure mode was silence. |

## Consequences

**Good.** A bare entry means one GitHub everywhere in the poller; the issue-311
workaround (host-pinning every entry) becomes optional; a source configured through
`integrations.github.host` alone now polls that host instead of github.com.

**Costs, accepted.** `from_source` grows a keyword; a provider without hosts ignores it.
The daemon reads the whole CLI config where it read the `polling` block — the same file,
the same lenient read.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Resolve an empty spec host inside `owns()` | Fixes the comparison and not the listing; leaves `_scope` / `scope_of` and `describe()` naming github.com for a repository read elsewhere |
| Fall back in `owns()` to "any host" when the spec has none | Undoes issue-311 R5.3: an enterprise source would claim its github.com twin |
| Document the workaround and require `HOST/OWNER/REPO` on enterprise | A silent no-op for every operator who does not read that line; the resolver already exists to answer exactly this question |
