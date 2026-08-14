# Learning 004: Prefer popular, well-maintained libraries over custom code

- **Date:** 2026-07-01
- **Source:** user-feedback
- **Work item:** issue-1

## What happened

the-loop's commit-message check was implemented as a custom
`scripts/check_commit_msg.py` regex validator. The maintainer asked on PR #2: "why are
we not using commitizen or something? We should prefer well written and popular libraries
instead of custom code." The custom code had been justified by the sandbox proxy blocking
remote pre-commit hook repos — but that constraint only blocked *remote hook repos*, not
using a popular library installed as a system tool and invoked from a local hook.

## Learning

Reach for a well-maintained, popular library before writing bespoke code. When a
constraint seems to force custom code, check whether it truly does — often the constraint
only rules out one integration path, not the library itself. Custom code is a
maintenance and correctness liability (a hand-rolled Conventional Commits regex will
drift from the spec; a maintained tool won't).

## Action

- Replaced the custom validator with **commitizen** (`cz check`) as a local/system
  commit-msg hook, keeping local == CI (`decision-008`, superseding the mechanism in
  `decision-007`).
- Going forward, default to established libraries; only write custom code when no
  suitable library exists or a hard requirement genuinely rules them all out — and record
  that reason in a decision.
