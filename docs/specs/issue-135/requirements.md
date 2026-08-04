---
type: requirements
phase: requirements-definition
workItem: issue-135
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
collaborators: [engineer]
overrides: {}
---

# Requirements: change the default session-control comment keywords

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #135](https://github.com/MadaraUchiha-314/the-loop/issues/135) asks for the
**default** values of the four execution-control keywords (issue-106,
`webhooks.ghWebhook.routing.control.keywords`) to change shape:

| Command | Current default | Requested default |
|---------|------------------|--------------------|
| start   | `the-loop:start-execution`  | `the-loop start`  |
| stop    | `the-loop:stop-execution`   | `the-loop stop`   |
| pause   | `the-loop:pause-execution`  | `the-loop pause`  |
| resume  | `the-loop:resume-execution` | `the-loop resume` |

This is a **value** change only — the vocabulary (four commands), the matching
semantics (whole-token, case-insensitive), the trust boundary (authorized actor,
comment-only, ambiguity refused), and the config surface
(`routing.control.keywords`, override-one-keep-the-rest) established by issue-106
are unchanged. `autonomy.sensitivePaths` flags this tier 3+ because it edits
`.the-loop/cli-config.schema.json`; the change itself is cosmetic, not a widening
of the trigger boundary.

## Requirements

### Requirement 1 — the shipped defaults read `the-loop <verb>`

**User story:** As an operator running the-loop's default configuration, I want
the control keywords to read as a short command (`the-loop start`) rather than a
colon-joined identifier (`the-loop:start-execution`), so that the comment I type
matches how the CLI itself names the action (`the-loop sessions start`).

#### Acceptance criteria

1. **1.1** `cli/the_loop/control.py`'s `DEFAULT_KEYWORDS` SHALL default to
   `the-loop start`, `the-loop stop`, `the-loop pause`, `the-loop resume` for
   `start`/`stop`/`pause`/`resume` respectively.
2. **1.2** The shipped `.the-loop/cli-config.yaml`, the onboarding template
   (`skills/the-loop/templates/cli-config.yaml`) and
   `.the-loop/cli-config.schema.json`'s `keywords.*.default` SHALL carry the same
   four values, so a fresh install and the schema's own documentation agree with
   the code.
3. **1.3** Whole-token, case-insensitive matching (`control.parse_command`)
   SHALL continue to work unmodified against the new defaults — the boundary
   regex already excludes `\w`, `-` and `:` on each side, and a space is outside
   that set, so `the-loop start` matches `the-loop start.`, a line on its own,
   inside `**bold**`, and is rejected when glued to another word character
   (`xthe-loop start`, `the-loop startx`) exactly as the old format was. No
   change to the parser itself is required or made (verified by the updated unit
   tests in Requirement 3).
4. **1.4** An operator's own **explicit** `keywords` override in their
   `cli-config.yaml` SHALL be read verbatim, unaffected by this change — only the
   *default* moves; nothing here alters `ControlConfig.from_mapping`'s override
   behaviour.

### Requirement 2 — every reference to the defaults stays consistent

**User story:** As a reader of the-loop's docs, I want every place that quotes
the default keywords — the CLI README, the getting-started walkthrough, the
config reference, the capability doc, the upgrade command's guidance — to show
the same value the code ships, so following the docs literally works.

#### Acceptance criteria

1. **2.1** `docs/config/cli/routing-options.md`, `docs/capabilities/webhook-triggers.md`,
   `docs/cli/concepts.md`, `docs/cli/getting-started.md`,
   `docs/cli/commands/sessions.md`, `cli/README.md`,
   `skills/the-loop/reference/automation.md` and `commands/upgrade-the-loop.md`
   SHALL quote the new defaults wherever they currently quote the old ones.
2. **2.2** Historical, locked artifacts — prior specs (`docs/specs/issue-106/`,
   `docs/specs/issue-117/`, `docs/specs/issue-119/`), prior decisions
   (`docs/decisions/decision-040.md`) and `CHANGELOG.md` entries already
   published — SHALL NOT be rewritten: they are the record of what the defaults
   *were* at the time of those work items, not living documentation
   (`SKILL.md` § reference, don't duplicate).
3. **2.3** `docs/capabilities/webhook-triggers.md`'s history table SHALL gain a
   row for issue-135. `CHANGELOG.md` is generated at release time from
   Conventional Commit messages (`update_changelog_on_bump: false`, `.cz.toml`)
   and is never hand-edited, so the implementing commit SHALL carry a
   `BREAKING CHANGE:` footer: an operator relying on the *default* keyword
   (never configured `keywords` explicitly) sees their comment stop matching
   until they either adopt the new phrase or pin the old one explicitly.

### Requirement 3 — tests assert the new defaults, not the old ones

**User story:** As a maintainer, I want the test suite to encode the new
defaults as the contract, so a future change to them is caught the same way this
one would have been.

#### Acceptance criteria

1. **3.1** `cli/tests/test_control.py`'s default-keyword assertions and every
   literal keyword string used in its `parse_command` boundary/case/ambiguity
   cases SHALL use the new defaults; the boundary-violation cases SHALL keep
   covering the same two edges (a word character glued directly before/after the
   keyword; punctuation directly after still matching) in the new, two-word
   shape.
2. **3.2** `cli/tests/test_control_integration.py` and `cli/tests/test_poller.py`
   SHALL update their local `START_KEYWORD`/`STOP_KEYWORD`/`PAUSE_KEYWORD`/
   `RESUME_KEYWORD` constants to the new defaults; no other line in those files
   SHALL need to change, since every scenario references the constant rather
   than a hardcoded literal.
3. **3.3** The full CLI test suite (`pytest`) and lint (`ruff`) SHALL pass
   unchanged in every other respect.

## Security considerations

- **No new trust boundary.** This changes a string value, not the parser, the
  authorization gate, or the ambiguity rule established and reviewed under
  issue-106/decision-040. The control surface is still comments-only, still
  gated by `authorizedUsers` evaluated upstream, still refuses on two different
  keywords in one body.
- **Slightly higher chance of accidental self-match.** The old
  `the-loop:start-execution` was unlikely to appear in ordinary prose; the new
  `the-loop start` is a plausible fragment of an ordinary sentence (*"let
  the-loop start once CI is green"*). Because the control path only ever runs
  for an **authorized** actor's comment, the worst case is an authorized user
  accidentally triggering a command against their own work item — a
  self-inflicted, low-severity outcome, not a new attacker capability. Anyone
  who wants the old, less prose-prone shape keeps it by setting `keywords`
  explicitly (Requirement 1.4) — the schema documents this.
- **`additionalProperties: false` unaffected.** The schema edit is a `default`
  value on existing string properties; no new key, no relaxed validation.
