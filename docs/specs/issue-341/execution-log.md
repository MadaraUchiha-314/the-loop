---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#341"
phase: needs-review
status: in-progress
---

# Execution Log: a Slack kickoff names its own repository, resolved against the repositories the-loop already polls

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): a first-line prefix resolved against a set the operator already declared, a refusal path, and one precondition dropped. No schema key, no grant, no scope, no state. Brainstorming skipped: the ticket carries the ask, the current code and the reasoning to revisit. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — five requirements, seven abuse cases |
| design | 2026-09-11 | | [`design.md`](design.md) — `channels/repos.py`, `channels/kickoff.py`, the pipeline order; [`decision-120`](../../decisions/decision-120.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — nine tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-341-k4mghj` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — seven abuse cases, seven closed |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#PRNUM](https://github.com/MadaraUchiha-314/the-loop/pull/PRNUM) | tasks 1–10: the whole work item | open |

## Progress entries

### 2026-09-11 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–10, red first (`test_channels_kickoff.py` did not collect against
  `cd1ae94`). New `channels/repos.py` — `DeclaredRepo`, `parse_repo_path`,
  `declared_repositories`, `repository_keys` — with `commands.py` delegating to it and
  `_configured_repositories` deleted, so kickoff and the slash command bound themselves
  by one list. New `channels/kickoff.py` — `PREFIX_RE`, `KickoffTarget`,
  `resolve_target`, `refusal_text` — six outcomes, no I/O, nothing of the member's text
  ever becoming a repository. `channels/inbound.py`: the target check moved **below** the
  allow-list and became a resolve-or-refuse step (the `error` reaction plus a reply in
  the member's own thread), with the resolved slug and the stripped text on the event.
  `channels/slack.py`: `kickoff_enabled` needs the grant and a channel, not a target.
  `commands/channels_cmd.py`: the `kickoff:` status line names the fallback (or its
  absence) and the size of the declared set. Four drop reasons in `eventlog.py`. Both
  schema copies (three descriptions, no key), the guide, the channels and polling option
  pages, the capability doc and its history row, the collaboration reference, and
  `decision-120`.
- **Checkpoint/tests:** `make check` — 3418 passed, 1 skipped; see
  `evidence/verification.md`. New tests: 47 unit (`test_channels_kickoff.py`), 5
  scenarios (`test_channels_integration.py`). Existing assertions changed: one —
  `test_bus.py::test_kickoff_needs_the_grant_and_a_repo`, which pinned the precondition
  R3.3 removes.
- **Self-review:** three passes over the diff. Pass one found the `empty-message` gap —
  a message that is only a prefix (`devbox:`) would have opened an issue titled *Work
  item from a channel*, because the emptiness check runs before the strip; it became a
  sixth outcome, refused with the others, and the spec chain was corrected to match. It
  also found `text.splitlines()` computed twice and `_matches` untyped. Pass two verified
  three design claims against the code: what reaches `comments.create_issue` is always a
  **declared** string; the refusal path sits strictly below the allow-list; the fallback
  is `kickoff.repo` verbatim, not its normalized entry, so a prefix-less message is
  byte-for-byte 13.11.1. Pass three read the docs against the code and found the options
  table missing the empty-message row, and that `channels status` would have printed an
  empty repository with `(labels: …)` under the new precondition — both fixed. Two test
  hygiene observations outside scope: the suite writes `.the-loop/portable/*.json` into
  the working repository (removed from this branch, not committed), and `uv run`
  rewrites `uv.lock` because the 13.11.1 bump did not include it.
- **Next:** the owner's review.
- **Blockers:** none.

## Design critic review

> Not selected for this work item (`reviews.critics: []` — no external critic is
> configured, so the three self-review passes above are the review).

### 2026-09-11 — spec chain written

- **Phase:** phase-selection → requirements-definition → design → test-planning → tasks-breakdown
- **Did:** read the ticket against `channels/inbound.py`, `channels/slack.py` and
  `channels/commands.py`; found that the closed set the ticket asks to resolve against
  is the set `may_target` already bounds a slash command to (decision-116 D4), so the
  design reuses that builder rather than adding a second list or a config key. Wrote the
  spec chain and `decision-120`.
- **Open judgement recorded:** what an unmatched **bare** prefix means when a fallback
  exists. The ticket asks both for "rejected, not guessed" and for existing installs to
  behave identically, and `fix: …` satisfies the prefix grammar. Resolved as D3 of
  decision-120: a bare word that matches nothing is not treated as a prefix; a
  **qualified** one (`owner/repo:`) that matches nothing is refused.
