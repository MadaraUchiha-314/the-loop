# Decision 007: Enforce Conventional Commits

- **Status:** superseded by [decision-008](decision-008.md) (the enforcement
  *mechanism* changed from a custom validator to commitizen; the *rule* still stands)
- **Date:** 2026-06-30
- **Deciders:** @MadaraUchiha-314 (via issue #1 update, §2.9.3)
- **Work item:** issue-1

## Context

Issue #1 added the rule that all commits must be semantic commits following
Conventional Commits v1.0.0 (https://www.conventionalcommits.org/en/v1.0.0/).

## Decision

- Add `hooks.commitConvention` to the config (enum `conventional-commits` | `none`,
  default `conventional-commits`).
- Enforce it locally with a `commit-msg` pre-commit hook backed by
  `scripts/check_commit_msg.py` — a zero-dependency validator of
  `<type>[optional scope][!]: <description>` (types: feat, fix, docs, style, refactor,
  perf, test, build, ci, chore, revert). Merge/revert/fixup/squash messages are exempt.
- Document the rule in the skill and `reference/tooling.md`.

## Consequences

- Commit history becomes machine-readable (enables changelog/versioning later).
- Enforcement is local (commit-msg). CI deliberately does NOT lint the whole PR's
  historical commits, because commits made before this rule (earlier in PR #2) are not
  conventional and would fail; the rule applies going forward.
- New commits in this repo use Conventional Commits from this point on.

## Alternatives considered

- `commitlint` (Node) via a remote pre-commit repo — rejected here: the sandbox proxy
  blocks remote hook repos; a tiny local Python validator keeps zero deps and matches
  the local==CI approach.
