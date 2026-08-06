---
type: testing-plan
phase: test-planning
workItem: ""
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- writing: budget=400 skill=the-loop:writing —
     prose words only — front matter, headings, tables, code,
     mermaid and EARS criteria are free. Advisory, never a gate: over budget is a
     review comment. Cut before you justify. See the `the-loop:writing` skill. -->

# Testing plan: <work item title>

> Derived from the approved `requirements.md`/`bugfix.md` and `design.md`, **before**
> `tasks.md` — each task's `_Test:_` names a row of the matrix below. Authored at the
> `test-planning` node and **completed at the `verification` node**: the same file is
> written once as a plan and once as a record, so intent and outcome sit in one diff.
> See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Credentials appear **by reference only** (env var name, secret-store key),
> never by value.

## Test matrix

> One row per candidate testing type. A type that does not apply is marked `n/a`
> **with a reason** — an unexplained blank is not a decision. Nothing here is mandatory
> in itself; the matrix is **work-item dependent**, and most work items use a handful of
> rows. Add types the catalogue does not list (chaos, load-soak, i18n, data-migration
> dry-run…) as extra rows.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | <units under test> | `<command>` |
| T2 | Integration (scenario) | yes | <behaviour>, Gherkin-documented | `<command>` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — <reason> | | |
| T4 | End-to-end | n/a — <reason> | | |
| T5 | UI / visual | n/a — <reason> | | |
| T6 | Snapshot | n/a — <reason> | | |
| T7 | Performance / load | n/a — <reason> | | |
| T8 | Security / abuse case | yes | negative test per trust boundary in `design.md` §Security design | `<command>` |
| T9 | Accessibility | n/a — <reason> | | |
| T10 | Migration / upgrade | n/a — <reason> | | |
| T11 | Manual exploratory | n/a — <reason> | | |

## Scenarios & requirement trace

> Which requirement each row proves, and — for integration rows — the Gherkin
> `Scenario:` titles the tests will carry (`testing.gherkinDocstrings`). Do not paste the
> scenario table here: `the-loop scenarios --format markdown` renders it for the reviewer
> briefing.

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R<n> | <case> |
| T2 | R<n> | `Scenario: <one-line behaviour>` |

## Verification environment

> What the verification needs in order to run. the-loop **facilitates** verification; it
> does not own your environment — name the project's own commands here rather than
> expecting the loop to model the setup. Where an operator document already describes
> this, link the doc registered in `customInstructions.docs` instead of restating it.

- **Repositories:** <this repo only | also `<org>/<repo>` at `<ref>`, checked out to `<path>`>
- **Services / containers:** <what must be running, and the command that starts it>
- **Fixtures & data:** <seed data, recorded cassettes, sample files>
- **Credentials:** **by reference only** — `<ENV_VAR_NAME>` / `<secret-store key>`.
  Never write a secret value into this file.
- **Bring-up:** `<command>` · **Tear-down:** `<command>`
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that
  never came up.

## Evidence plan

> What will be captured, and where. Evidence is committed under
> `<specDir>/<id>/evidence/`; a link to a CI run that expires or to a local path is not
> evidence.
>
> **Redact before committing.** Captured output and screenshots routinely contain tokens,
> cookies, personal data and internal hostnames, and this directory is as public as the
> repository. If a capture cannot be redacted, do not commit it — say so in the results
> row instead. A secret that reaches a commit is rotated, not merely edited out.

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1 | test summary (counts, duration) | `unit.txt` |
| T2 | scenario table + run output | `integration.txt` |
| T5 | screenshots of each verified state; an animated capture (GIF) when the behaviour is a **flow** rather than a state | `ui/<state>.png`, `ui/<flow>.gif` |

## Verification activities

> The checklist the `verification` node gates on (`checkmarks: complete`). One line per
> thing that will actually be executed. Tick a line **only** when it has been run and its
> evidence recorded below. An activity that cannot be executed is **not** ticked: record
> why under Verification results and either replan this matrix (with the reason) or
> escalate.

- [ ] T1 — `<command>`
- [ ] T2 — `<command>`
- [ ] T8 — `<command>`

## Verification results

> Authored empty at `test-planning` (as `_Not yet executed._`) and filled at
> `verification`. One row per executed activity: the exact command or procedure, the
> outcome, and a link to the committed evidence.

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** <activity — why, and what was done about it (replanned / escalated)>

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
