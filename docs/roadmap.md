# the-loop roadmap (internal)

> **Internal project doc — not shipped in the skill.** This is the-loop's *own*
> development roadmap: what is built in v0, what is deferred, and the open questions
> carried from the founding issue (#1). The published plugin (commands/skills/hooks)
> describes only capabilities that exist; forward-looking work lives here so it does not
> leak into the user-facing artifact. Deferral rationale: `docs/decisions/decision-003.md`.

## Deferred automation (planned, not yet built)

- ~~**Webhook → harness routing.**~~ Shipped (issue #15, `decision-016`): the
  `gh-webhook` receiver routes verified events through the session registry
  (`the-loop sessions`) and resumes the matched Claude/Cursor session via its official
  CLI. Spec: `docs/specs/issue-15/`.
- **The dream — remote auto-trigger.** An authorized user creates a work item (GH issue /
  Jira) → the-loop is automatically triggered in a remote workspace (e.g. Codespaces) and
  delivers it end-to-end, notifying humans only when a decision is required.
- **Project-wide DAG orchestration.** Given a full work-breakdown, orchestrate the whole
  DAG of work items via depends-on / blocked-by relationships.
- ~~**Cursor packaging.**~~ Shipped (issue #12, `decision-015`): `.cursor-plugin/`
  manifests reuse the same skills/commands; the SessionStart hook is a Cursor rule.

These map to the deferred tasks (14–23) in `docs/specs/issue-1/tasks.md`.

## Open questions carried from issue #1

- Validate that "all scripts from root" scales for large monorepos.
- Confirm browser-logging via the chrome-devtools MCP and document setup.
- Decide the predictability mechanism (Claude hooks vs custom code/scripts), including how
  to hard-enforce mandatory user-education (R10.4).
- ~~Find the Cursor equivalent of marketplace distribution.~~ Answered: Cursor ≥ 2.5
  plugins (`.cursor-plugin/plugin.json` + `marketplace.json`, installable from a GitHub
  repo). See `docs/decisions/decision-015.md`.
- Confirm GitHub's `depends-on` / `blocked-by` equivalents for DAG orchestration.
- Finalize Go tooling defaults (left as "??" in the issue).

## Meta

- Feedback about the-loop itself is filed as GitHub issues on the the-loop repository.
- the-loop uses the-loop to develop and improve itself; each prescribed practice is
  applied to this repo first (see `learnings/learning-005.md`).
