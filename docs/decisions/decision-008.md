# Decision 008: Use commitizen for Conventional Commits (not a custom validator)

- **Status:** accepted (supersedes the mechanism in [decision-007](decision-007.md))
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 review)
- **Work item:** issue-1

## Context

decision-007 enforced Conventional Commits with a bespoke `scripts/check_commit_msg.py`
validator (chosen originally because the sandbox proxy blocks remote pre-commit hook
repos). On PR #2 review the maintainer asked: "why are we not using commitizen or
something? We should prefer well written and popular libraries instead of custom code."

## Decision

- Replace the custom validator with **[commitizen](https://commitizen-tools.github.io/commitizen/)**,
  the de-facto Conventional Commits tool for the Python ecosystem (fits the-loop's
  Python-first stack: uv, ruff, pyright, pytest).
- Keep the local/system pre-commit approach that decision-006 established: the commit-msg
  hook runs `cz check --allow-abort --commit-msg-file` against the installed `cz`
  binary, so the sandbox proxy's block on remote hook repos does not apply and local ==
  CI still holds.
- Configure commitizen in `.cz.toml`; add it to the CLI `dev` extra and the CI install
  list. Delete `scripts/check_commit_msg.py`.

## Consequences

- Less code to maintain; the convention (types, `!` breaking-change, scopes) is defined
  and updated by a maintained library instead of a hand-rolled regex.
- Unlocks commitizen's adjacent features for free later: `cz commit` (guided messages)
  and `cz bump` (semver bump + changelog from commit history).
- Same enforcement boundary as before: validation is local (commit-msg); CI does not
  re-lint historical commits (earlier PR #2 commits predate the rule).

## Alternatives considered

- **commitlint** (Node) — the most popular tool overall, but adds a Node/JS dev
  dependency and config to a Python-first project; commitizen is the better ecosystem
  fit.
- **Keep the custom validator** — rejected per the maintainer's "prefer popular
  libraries over custom code" principle (see `learning-004`).

## General principle (recorded as learning-004)

Prefer well-maintained, popular libraries over bespoke code unless there is a concrete
reason (a hard constraint the library can't meet). The original sandbox-proxy constraint
did **not** actually require custom code — a system-installed library invoked from a
local hook satisfies it.
