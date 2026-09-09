# Security review — issue-331

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change routes one already-validated string — the GitHub host the issue-311 resolver
answers from the operator's own CLI config or `gh`'s own `$GH_HOST` — into the poll
source's `RepoSpec` for entries that named no host. Nothing new is read, granted, stored
or reached: the listing for such an entry already went to that host through `gh`'s own
resolution; the fix makes the source's scope name, its ownership test and its log
description say the same. The bug being fixed withheld a closure; it never granted one.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | The resolved default host is not the shape of a host and reaches a `--repo` argument | `github_host` skips a malformed candidate with a warning (issue-311, unchanged); `RepoSpec.parse` applies `is_github_host` to an inherited host exactly as to a written one and refuses with a `ValueError` naming the entry and the default, so a bad default fails the source at plan time (pre-flight exits 1; a reload keeps the previous plan) | `test_repospec_refuses_a_malformed_default_host` ×4 (`ghe`, a URL, a path, whitespace) |
| A2 | An enterprise source claims a github.com repository with the same `OWNER/REPO` — undoing issue-311 R5.3 | `owns()` is unchanged; it still compares the ref's host to the spec's. Only the spec's host changed, from `""`-meaning-github.com to the resolved one, so a github.com ref is refused by a source bound to an enterprise host and vice versa | `test_a_bare_repo_inherits_the_default_host_and_owns_its_refs` (negative half); `test_provider_owns_by_host_too` (issue-311, unchanged) |
| A3 | A github.com deployment changes behaviour | the resolver answers `github.com`, which `RepoSpec.parse` keeps unwritten; every argv, scope name and `describe()` string for github.com is byte-identical | `test_a_github_com_default_leaves_the_spec_unwritten`; `test_a_github_com_read_is_byte_identical`, `test_build_provider_constructs_github` (issue-311/-63, unchanged); the 187 pre-existing `test_poller.py` tests unchanged and green |
| A4 | A poll source is made to read a GitHub the operator did not configure | by construction: the inherited host comes from `integrations.github.host`, an enterprise `github.api.baseUrl` or `$GH_HOST` — the operator's own config and `gh`'s own override, the same inputs `gh` already honoured for the listing. The daemon passes no `repo_root`, so no checkout's remote is consulted. No new input exists to abuse | `test_the_daemon_binds_sources_to_the_resolved_host` (the three sources and their precedence; `none` → unwritten) |

## Checklist

- [x] AuthN/AuthZ unchanged: `gh` still authenticates per host and sends only the credential it holds for the host in `--repo`; no gate, grant or actor rule is touched (A4).
- [x] Provenance: the inherited host is operator-configured or `gh`'s own environment, never read from a payload, a comment or a ref (A4).
- [x] Input validation: one grammar (`is_github_host`) for a host wherever it enters — a written entry, an inherited default, a ref, the resolver's candidates (A1).
- [x] Secrets: none involved; the host is a public name and already appeared in every listing argv.
- [x] Fail closed, restated: a malformed default fails the source before `gh` is spawned; `owns()` still refuses a mismatched host; no host anywhere means github.com, unwritten (A1, A2, A3).
- [x] Disclosure: `describe()` now prints the host in the poller's log line — a name the same log already printed inside every `gh` argv at debug level.
- [x] Evidence redaction: every host, ref and path in the tests and evidence is a fixture (`ghe.corp.example`, `ghe.example.com`, `other.corp.example`, `octo/repo`).

## Outcome

**Pass.** Four abuse cases, four closed by a test or by construction as recorded. No
finding needs a security-relevant decision; no human sign-off at tier 3.
