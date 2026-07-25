---
type: execution-log
workItem: "issue-93"
phase: needs-review
status: in-progress
---

# Execution Log: an event on a PR routes to the PR's linked issue first

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-93/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #93: a PR event must resolve the linked GH issue first and reuse that issue's existing tmux session. |
| design | 2026-07-25 |  | One shared seam (`webhook/router.py: extract_work_items`) + one provider enrichment (`poller/github.py`: `closingIssuesReferences` in the existing `gh pr list`). Ordering linked-issues-before-PR is the whole mechanism. |
| tasks-breakdown | 2026-07-25 |  | 12-task DAG |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-93-uy0xtc` |
| needs-review | 2026-07-25 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-25 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Traced both ingress paths end to end (`Router.route` →
  `Dispatcher.handle` / `_on_unmatched`, and `Poller._process_item` →
  `GitHubPollProvider.refs` → `extract_work_items`). Confirmed **three**
  cooperating defects rather than the one in the title:
  1. GitHub delivers a PR **conversation comment** as `issue_comment` with a
     `pull_request` key on the `issue` object; `extract_work_items` treated it as
     a plain issue event, so it resolved to the PR's number alone — with the
     auto-execute label on the PR that is an unmatched labelled event, i.e. a
     spawn.
  2. PR→issue linkage was heuristic-only (head branch + a bare `Closes #N`), so
     GitHub's own Development-panel linkage, `OWNER/REPO#N`, `GH-N` and issue
     URLs were all invisible.
  3. `_on_unmatched` spawns for `work_items[0]`, and the PR number was first —
     so even a *resolved* linkage still keyed a new session to the PR.
  Drafted the 3-phase spec; the design settles on reordering at extraction
  (rather than teaching the dispatcher a second notion of "the ticket") because
  the poller's own `has_session` check calls `provider.refs`, not the dispatcher.
- **Next:** implement T1–T12.
- **Blockers:** none. Human approval of the spec + code happens at the PR
  (tier-3, `human-approves-pr`).

### 2026-07-25 — implemented (T1–T12)

- **Phase:** implementation → needs-review
- **Did:**
  - `webhook/router.py`: `_pr_entity()` (a `pull_request*` event, **or** an
    `issues`/`issue_comment` event whose `issue` carries `pull_request`);
    `linked_issue_numbers()` resolving `closingIssuesReferences` → head branch →
    body keywords, deduplicated, never the entity itself; a widened
    `_CLOSING_KEYWORD_RE` (`#N`, `OWNER/REPO#N`, `GH-N`, issue URL, `Fixes:` )
    with a **cross-repo qualifier guard**; `extract_work_items` emitting linked
    issues **before** the PR's own number.
  - `poller/github.py`: `closingIssuesReferences` appended to the existing
    `gh pr list --json` field list (no extra API call), a latched one-time
    downgrade + warning when the installed `gh` rejects the field (any other
    `gh` failure still propagates), `GhItem.linked_issues`,
    `WorkItem.raw["linkedIssues"]`, and injection into the synthesised
    webhook-shaped payload so the router keeps one code path.
  - Tests: 8 router unit cases, 4 provider/`gh`-client cases, and one integration
    test per ingress path (`test_webhook_routing_integration.py`,
    `test_poller_integration.py`) with Gherkin docstrings + requirement links.
- **Evidence:** both integration regressions **fail before** the change
  (`git stash` of the two source files → 2 failed) and pass after; full gate
  green from the repo root: `ruff check` + `markdownlint` (209 files), `ruff
  format --check`, `pyright` (0 errors), `pytest` **332 passed**,
  `validate_config`.
- **Docs:** `docs/capabilities/webhook-triggers.md` and
  `interactive-sessions.md` (current behaviour + history rows),
  `skills/the-loop/reference/automation.md`, new
  `docs/decisions/decision-036.md`.
- **Next:** PR + reviewer briefing; await human approval (tier 3).
- **Blockers:** none.

## Reviews

| Round | Type | Findings | Resolution |
|-------|------|----------|------------|
| 1 | self | `GH-` alternative reachable only if the `#` alternative fails first; confirmed by the parametrised test. Cross-repo references must be dropped, not renumbered — added the qualifier guard + tests. | resolved in the implementation |
| 2 | self | Ordering change must not alter PR-close cleanup: `_is_pr_close` closes *all* matched sessions and the issue ref was already present for `pull_request` events — unchanged. | no change needed |
| 3 | self | The `_no_link_field` latch is per-`GhClient`, so a hot reload rebuilds it and pays one failed call again; self-healing and cheaper than global state. Downgrade is gated on the error naming the field so an auth/network fault still surfaces. | accepted as designed |

## Security review

Per `security.review` (tier 3 → no named human sign-off required;
`humanSignOffMinTier: 4`). No new attack surface: the change only decides *which
work-item ref* an already-authorized event resolves to. All newly-read payload
fields are parsed into **integers**, formatted into a `WorkItemRef` whose slug is
already regex-sanitised before it reaches a filesystem path or tmux target. The
self-reply marker guard and the `routing.authorizedUsers` guard still run before
dispatch, unchanged and in the same order. No new subprocess, network call or
file; the `gh` invocation is the existing one with one more `--json` field, run
as an argv list (no shell). One **narrowing**: a closing reference naming another
repository is now dropped instead of being read as this repository's issue
number. Degradation on an old `gh` falls back to today's conventions with a
warning — never wider routing, never a failed cycle.
