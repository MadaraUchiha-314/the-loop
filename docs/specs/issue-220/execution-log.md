---
type: execution-log
workItem: issue-220
phase: needs-review
status: in-progress
---

# Execution Log: the-loop's JSON schemas ship with the plugin, not with your repo

> Append-only log for issue-220. Ticket:
> [#220](https://github.com/MadaraUchiha-314/the-loop/issues/220).

## How this session ran the loop

One cloud session, one pass, no human at the other end — the same posture as
issue-208/209/211/217, with the same two consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started by the ticket
   itself; there was nobody to tick the checklist. Phases assumed: the full spec chain,
   verification, self-review. `brainstorming` and the opt-in `design-critic-review` were
   not taken — the ticket states the problem and the answer in four bullets, and no second
   model was available to this session.
2. **The chain was authored before the code, but approved by nobody.** The artifacts are a
   proposal to ratify, not a locked chain; `status: draft` on all four says so.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-13 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-13 | | [`requirements.md`](requirements.md) — 5 requirements, 4 NFRs, 4 abuse cases. Risk tier **3**: the change is declarative, but it grants `/upgrade` the authority to delete files from operators' repositories |
| design | 2026-08-14 | | [`design.md`](design.md) — the manifest declares, the commands read, one string-handling fix in `scaffold()`, one parity test |
| test-planning | 2026-08-14 | | [`testing-plan.md`](testing-plan.md) — 5 rows in scope, 6 `n/a` with reasons, and a section naming what cannot be executed at all |
| tasks-breakdown | 2026-08-14 | | [`tasks.md`](tasks.md) — 9 tasks |
| implementation | 2026-08-14 | | Built. Tasks 1–8 complete |
| verification | 2026-08-14 | | Testing plan executed in full: 8 new tests green; whole suite 1895 passed + 1 skipped; lint, format, types, markdownlint (623 files) and config validation clean |
| needs-review | 2026-08-14 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-220-3vc1hg` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-13 — orientation

Read the ticket, `CLAUDE.md`, the harness config, the skill, and the issue-217 chain for
conventions. Mapped who actually touches a schema before designing anything, which turned
out to be the decisive fact:

- **No code copies the schemas.** `/the-loop:init` does, in prose — three bullets in
  `commands/init.md` and three `meta` entries in `.the-loop/manifest.yaml`. The Python CLI
  never loads a JSON Schema at runtime; it reads keys (`harness_config.READS`) and degrades
  to defaults. So the fix is declarative, and NFR1 ("no schema loading enters the runtime")
  costs nothing to hold.
- **issue-36 already built the machinery.** Templates went internal in exactly this shape:
  `manifest.templatesDir` declares the plugin-side home, `manifest.deprecated` drives
  `/upgrade`'s cleanup of the copies already out there. Reusing it means no new upgrade
  step and one mechanism for "internal to the plugin", not two.
- **This repository's `.the-loop/` is the plugin's shipped directory.** That is why the
  schemas stay put and `schemasDir` merely names where they already are — and why CI,
  `scripts/validate_config.py` and every existing test needed no change at all.

### 2026-08-14 — the one thing that was not declarative

Removing the copies costs an operator their editor validation, so the change gives back a
`# yaml-language-server: $schema=<published url>` line. That turned out to be the only part
with a real constraint: **the directive is honoured on the first line and nowhere else.**

`harness_config.scaffold()` — the issue-193 path that adopts a repository which never ran
`/init` — writes `_SCAFFOLD_HEADER + <the packaged default>`, which would have pushed the
modeline to line 7 and left a comment that looks like validation and isn't. `_with_header`
now puts the header *below* a leading modeline and degrades to today's concatenation when
there is none. It is the only production line this work item changes.

The URL tracks `main` rather than a released tag, argued in
[decision-080](../../decisions/decision-080.md): a pinned tag freezes the operator's editor
at whichever plugin version happened to run `/init`, which is the staleness this work item
exists to remove, moved one layer out.

### 2026-08-14 — spotted, not fixed

`rules/the-loop.mdc` (the Cursor always-applied rule) still keys off `.the-loop/config.yaml`
— the filename retired by issue-82's rename — so in a project initialized by any recent
version the rule finds nothing and never announces that the-loop is initialized. Unrelated
to schemas, and fixing it here would widen this diff into the Cursor packaging surface.
Flagged in the PR briefing for its own ticket.

## Documentation

| Doc | Change |
|-----|--------|
| [`commands/init.md`](../../../commands/init.md) | Schemas named alongside templates as internal; the two schema-copy bullets removed from step 3; steps 2 and 5 read the plugin's schema and validate locally |
| [`commands/upgrade-the-loop.md`](../../../commands/upgrade-the-loop.md) | Cleanup step names the three copies, bounds deletion to the manifest's exact paths, and reports a drifted copy instead of deleting it quietly; step 4 retitled "Migrate configs to the current schemas" |
| [`skills/the-loop/SKILL.md`](../../../skills/the-loop/SKILL.md) | New paragraph in §Configuration: the schemas are the plugin's, `manifest.schemasDir`, and the modeline is for the editor alone |
| [`reference/onboarding.md`](../../../skills/the-loop/reference/onboarding.md), [`reference/collaboration.md`](../../../skills/the-loop/reference/collaboration.md) | Schema defaults and collaborator validation resolve through the plugin |
| [`docs/config/index.md`](../../../docs/config/index.md) | New **Where the schemas live** section (the modeline, why it is a comment, why it is harmless offline) + the comparison table |
| [`docs/config/harness-config.md`](../../../docs/config/harness-config.md), [`docs/config/cli/index.md`](../../../docs/config/cli/index.md) | "Validated against" now names the plugin's schema; §Manifest documents `schemasDir` and `deprecated` |
| [`docs/guide/quickstart.md`](../../../docs/guide/quickstart.md), [`docs/guide/how-it-works.md`](../../../docs/guide/how-it-works.md) | What `/init` writes, and the new bullet putting schemas beside templates as plugin-internal |
| [`docs/reports/labels-and-dashboards.md`](../../reports/labels-and-dashboards.md) | Fixed a link to `.the-loop/config.schema.json`, a path retired by the issue-82 rename |
| [`skills/the-loop/templates/design.md`](../../../skills/the-loop/templates/design.md) | The example schema reference no longer implies a project-local path |

`README.md` is untouched **with reason**: it describes the loop's phases and the plugin's
installation, and says nothing about which files land in a project — the change makes no
sentence of it wrong.

## Capability docs

[`distribution.md`](../../capabilities/distribution.md) — updated in this PR: four new
current-behaviour clauses (schemas internal, validation reads the plugin's copy on disk,
upgrade removes the copies with the drift and escape rules, the modeline on every
scaffolded config) plus the issue-220 history row. No other capability's behaviour
changed; `cli.md` is untouched because the CLI's read surface is unchanged, which is
NFR1 stated as an absence.

## Verification results

In [`testing-plan.md`](testing-plan.md) § Verification results, with evidence in
[`evidence/verification.md`](evidence/verification.md).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new finding — the sweep for surviving references caught two stale paths the ticket never mentioned: `docs/reports/labels-and-dashboards.md` linking the pre-rename `.the-loop/config.schema.json`, and `rules/the-loop.mdc` keying off `.the-loop/config.yaml`. Fixed the first (a dead link inside this work item's own subject), flagged the second as out of scope | [labels-and-dashboards.md](../../reports/labels-and-dashboards.md) |
| 2 | self | the-loop (this session) | new finding — **`schemasDir: .the-loop` is plugin-relative but reads as project-relative**, and a project has a `.the-loop/` too. Resolving it the wrong way finds a directory that exists and lacks every file you came for — the worst kind of wrong, since it does not fail loudly. `templatesDir` has no such collision (`skills/the-loop/templates` cannot be mistaken for a project path). Added an explicit CAREFUL note above the key and on the key's own line | [`manifest.yaml`](../../../.the-loop/manifest.yaml) |
| 3 | self | the-loop (this session) | new finding — the configuration reference's comparison table carried the "both shipped with the plugin" note inside the *CLI* column, where it reads as a property of the CLI config alone. Split it into its own row that says it once per column. A fourth pass (requirement trace R1–R5 → mechanism → test; grep sweep for project-relative schema paths; read-through of `init.md` as the agent executes it) found nothing new — stopped per `reviews.stopOnNoNewFindings` | [`docs/config/index.md`](../../config/index.md) |
| 4 | critic | — | **not run.** `reviews.critics` is empty in this repo's harness config and no second harness was available to this session | |
| 5 | security | the-loop (this session) | mechanism-level review against the four abuse cases. One boundary genuinely moves: `/upgrade` may now delete files from an operator's repository. It is bounded by a closed list of three literal paths in `manifest.deprecated`, a refusal for any candidate resolving outside the project's `.the-loop/`, a diff-before-delete rule for a drifted copy, and a fail-closed **needs-user** for anything it cannot establish. The second new surface — a URL in a scaffolded config — is inert to the loop: `grep` confirms no code path reads the modeline, so a tampered one reaches nothing the loop does. Risk tier 3, so no named human security sign-off is mandated; the PR approval gate stands | [`requirements.md`](requirements.md) § Security considerations, [`evidence/verification.md`](evidence/verification.md) § T8 |
