---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#362"
---

# Self-review: a DM is a channel like any other

> The `self-review` node's proof, per `reference/reviewing.md`. Reviewed the staged diff
> against the spec chain, adversarially — "what would make CI reject this, and what would
> make a reader of this code in six months get it wrong?"

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (`claude`) | 4 new findings | all 4 fixed in the same pass — see below | this file |
| 2 | self (`claude`) | zero new findings (converged) | — | this file |
| — | critic | **unavailable** — no critic is configured in this repository's `.the-loop/cli-config.yaml`, so no round could run; it does **not** count toward `reviews.criticReviewCount` | — | — |

## Round 1 findings

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | **Two files were staged that are not this change**: `uv.lock` (a `the-loopy-one` version line and a resolver marker, drifted from running `uv run`) and `.the-loop/portable/github-octo-repo-15.json` (a fixture the test suite rewrites with a current timestamp). Committing either would put unrelated churn in the diff and, in the lock file's case, a dependency-resolution change nobody reviewed | Both reverted with `git restore`. `uv.lock` drifted a second time after a later `uv run` and was reverted again; the final diff carries neither |
| 2 | **`channels_cmd.py`'s module docstring was now wrong**: it summarises the five actions and said `status` shows "what is configured, with token *presence* only" — true before `--probe`, which makes two API calls | Docstring updated to name `--probe` and its two calls |
| 3 | **`--probe` was reachable but undocumented.** `docs/cli/commands/channels.md` is the command's page; its `status` description and its Flags table are what an operator reads, and neither knew about the flag, the `channel kind:` line or the reconcile cadence. The docs-parity test does not catch this — it checks *config schema* leaves, not CLI flags, so nothing would have failed | Both the description and the Flags table updated, with a link to the guide's new section. Recorded in `evidence/documentation.md` |
| 4 | **Stray apostrophe in `report_subscription`'s docstring** (`:func:\`subscription_findings\`', so …`) | Fixed |

Two earlier defects — the overloaded `scopes=None` and the unguarded reconcile call —
were found by **tests during implementation**, not by this review, and are recorded in
[`verification.md`](verification.md) § What the tests found with the design updates they
caused.

## What round 2 checked and accepted

- **The finding could nag an operator who has already fixed their app.** A `D…` channel
  keeps its `[!]` line without `--probe`, because without a probe there are no scopes to
  check. Accepted deliberately, and it is the fail-loud choice: the line ends by naming
  `--probe`, which resolves it to silence in one command. The alternative — staying quiet
  about the one configuration a default installation certainly cannot serve — is the bug
  this work item exists to close.
- **`kind_summary` calls an unrecognised id "not a Slack conversation id".** Correct, not
  merely defensive: the guide tells operators to copy the id, and `conversations.history`
  takes ids, so `#general` in the config is a real misconfiguration worth naming.
- **The in-page anchor `#slackreadintervalseconds` in `channels-options.md` is spelled
  differently from the repo's hyphenated *cross-page* anchors** (`#slack-read-mode`).
  Left as the un-hyphenated form: MD051 validates in-page fragments and rejects the
  hyphenated spelling, and it implements the same slugger VitePress uses. The
  cross-page links elsewhere are unvalidated and likely already wrong — out of scope
  here, and not something to make worse by matching them.
- **`min(1.0, interval)` spins the wait loop at the override's rate.** Only reachable
  through `catch_up_override`, which is a test seam (the shape `watcher.start_watcher`
  already set); the configured floor is 60s, so production ticks at 1s exactly as before.
- **`_granted_scopes` accepts a `Mapping` response or an object with `.headers`.** Both
  shapes are exercised (`FakeResponse` and a bare `dict`), and anything else yields
  `None` → no finding. No path turns an SDK surprise into a wrong warning.
