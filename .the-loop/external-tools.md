# External tools, skills, MCPs and plugins

> Free-form, user-owned registry. The-loop reads this file so the harness is aware of
> the tools it is allowed to freely use while delivering work items. Edit at will.

## MCP servers

- _e.g._ `github` — GitHub issues/PRs/Actions via MCP
- _e.g._ `jira` — Jira tickets via MCP

## CLIs

- _e.g._ `gh` — GitHub CLI

## Skills / plugins

- `the-loop` — this plugin
- `caveman` (<https://github.com/JuliusBrussee/caveman>) — output-token compression skill
  (drops narration filler, never touches code/commands/errors). the-loop expresses this
  natively via `tokenEconomy.outputVerbosity`; install caveman if you prefer the packaged
  skill. Its preservation rules must not compress the reviewer briefing or paper-trail
  comments (see `reference/token-economy.md`). (issue-37)
- `ponytail` (<https://github.com/DietrichGebert/ponytail>) — generation-minimalism decision
  ladder (YAGNI → reuse → stdlib → native → dep → one-liner). the-loop expresses this
  natively via `reference/minimalism.md` / `config.minimalism`; install ponytail if you
  prefer the packaged skill. (issue-37)
- _other installed plugins you want the-loop to leverage_

## Notes

Describe any access patterns, auth, or constraints the harness should know about.

**Token economy (issue-37):** caveman and ponytail above are **registered, not vendored** —
the-loop implements their techniques natively (`tokenEconomy` / `minimalism`) and does not
bundle a runtime (decision-005). Register-only means the harness may use them if installed;
the-loop does not depend on them.
