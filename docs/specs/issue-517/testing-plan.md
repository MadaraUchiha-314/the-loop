---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#517"
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

# Testing plan: hand a conversation to the-loop from any surface, at any stage

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Each task's
> `_Test:_` names a row below. **This file is executable content**: it names commands an
> agent will run. No credential appears here.

## Test matrix

Most of the proof is pytest at three levels: unit tests for the parser and hook,
scenario tests through the runtime and dispatcher, and abuse-case negatives. A
recorded dry run of the skill is the one manual activity. It covers the part no fake
can reach: the interview and a real issue.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `core/handoff.py` (parse, render, `STAGE_ENTRY`, `find_record`, part splitting); `import-handoff` hook demotion; `JiraClient.create_issue` fields; `declared_skips` `requiresHandoff` rule; checklist unticking | `make test` |
| T2 | Integration (scenario) | yes | runtime walk per R6 table row, start to the first approval gate; no-handoff walk unchanged; dispatcher arming reads the record and checks out the spec branch; `the-loop handoff import`/`note`; `ticket create --issue-type --parent` through the API route | `make test` |
| T3 | Contract | yes | the CLI API route `POST /work-items/tickets` and the MCP tool accept the two new optional fields; existing contract tests stay green | `make test` |
| T4 | End-to-end | n/a | no environment runs a real poller against a real repo in CI; T11 covers the real-issue path by hand | |
| T5 | UI / visual | n/a | no rendered UI changes beyond one checklist line, which T6 covers as text | |
| T6 | Snapshot | yes | the checklist body with a handoff (earlier rows unticked, handoff line) and the rendered handoff record; byte-stable text | `make test` |
| T7 | Performance / load | n/a | one extra comment listing per arming of a fresh item; no hot path changes | |
| T8 | Security / abuse case | yes | one negative test per abuse case 1–7 in `design.md` §Security design, plus path/branch-name validation | `make test` |
| T9 | Accessibility | n/a | no new visual surface | |
| T10 | Migration / upgrade | yes | a `work-item-state.json` with none of the new keys loads, walks and archives unchanged; the graph compiles with the new node and edges; `make validate` passes | `make test`, `make validate` |
| T11 | Manual exploratory | yes | the handoff skill in Claude Code on a scratch issue: interview, confirmation, issue, record, draft PR; then the poller picks it up at the right step | procedure below |
| T12 | Static checks | yes | lint, format, types, markdown lint over the new skill and docs | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R5.1, R5.5 | parse/render round trip; unknown version → None; unknown key → None |
| T1 | R6 table | `STAGE_ENTRY` returns each row's starting step, with and without `testing-plan.md` |
| T1 | R5.2 | a body over 65,536 characters splits into parts, none truncated, rejoined byte-equal |
| T1 | R7.3, R7.5 | demotion un-skips the producing node and later skips only; no file verifies → `brainstorming` un-skipped |
| T1 | R3.4 | `create_issue(issue_type="Story", parent_key="PROJ-1")` sends `issuetype` and `parent` |
| T1 | R7.1 | `requiresHandoff` node skipped with `via: no-handoff` when state has no handoff |
| T2 | R6.1, R6.3, R6.4 | `Scenario: a requirements-settled handoff walks to requirements-approval` |
| T2 | R6 table | `Scenario: a brainstorm-settled handoff walks to brainstorm-approval` |
| T2 | R6 table | `Scenario: an exploring handoff walks to brainstorming` |
| T2 | R6 table | `Scenario: a design-settled handoff with a testing plan walks to design-approval` |
| T2 | R6 table | `Scenario: a design-settled handoff without a testing plan walks to test-planning` |
| T2 | R7.1 | `Scenario: an item with no handoff walks exactly as before` |
| T2 | R7.3 | `Scenario: a requirements.md missing Security considerations demotes to requirements-definition` |
| T2 | R6.5 | `Scenario: a brainstorm carried under requirements-settled is locked as approved by the handoff` |
| T2 | R6.2 | `Scenario: arming a handed-off item checks out its spec branch` |
| T2 | R5.4 | `Scenario: handoff note points the record at the committed files and PR` |
| T2 | R7.4 | `Scenario: an imported spec-chain artifact URL is recorded and rendered in graph context` |
| T2 | R3.4, R3.5 | `Scenario: a Jira copy is created with issue type, parent and the mirror label` |
| T3 | R3.4 | route and MCP tool accept `issueType` and `parent`; omitted → today's request |
| T6 | R6.4 | checklist snapshot for a requirements-settled handoff |
| T6 | R5.1 | record snapshot for each carrier (`branch`, `ticket`, `artifact`) |
| T8 | Abuse 1 | `Scenario: a handoff record from an unauthorized user is ignored` |
| T8 | Abuse 2 | `Scenario: a handoff record entering implementation is rejected` |
| T8 | Abuse 3, 6 | `Scenario: a record posted or edited after the walk started changes nothing` |
| T8 | Abuse 4 | `Scenario: a carried file whose hash does not match is refused` |
| T8 | Abuse 5 | an artifact body with agent-directed text is written verbatim and changes no state |
| T8 | Abuse 7 | `Scenario: arming a Jira mirror is refused` |
| T8 | Security design | a part comment by another author is ignored; a branch outside `the-loop/` or failing `check-ref-format` is refused; an artifact name outside the closed set is refused |
| T10 | Compatibility NFR | legacy state fixture loads and archives; `make validate` |
| T11 | R1, R2, R4, R5, R8 | manual procedure below |

## Verification environment

- **Repositories:** this repo only. T11 uses a scratch issue in this repository,
  closed afterwards, and a branch under `the-loop/` deleted afterwards.
- **Services / containers:** none for T1–T10. Tests use the existing GitHub and Jira
  fakes (`cli/tests/jirafakes.py` and the dispatcher fixtures).
- **Fixtures & data:** new fixtures under `cli/tests/fixtures/handoff/`: one record per
  carrier, artifacts for each R6 row, a malformed `requirements.md`, and a legacy state
  file.
- **Credentials:** by reference only. T11 uses the operator's existing `gh`
  authentication and the daemon's configured GitHub token (`cli-config.yaml` variable
  name). No Jira credentials: T11 does not create a Jira copy, and T2 covers that path
  with the fake.
- **Bring-up:** `make install-dev` · **Tear-down:** none (T11: close the scratch issue,
  delete the branch).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

**T11 procedure.**

1. In a checkout, discuss a small fake feature with Claude, then run
   `/the-loop:handoff`.
2. Pick *requirements settled* and *queue it*, and confirm.
3. Check that the issue, record and draft PR exist and every link resolves.
4. Post `the-loop start`, then confirm the checklist shows earlier phases unticked and
   the handoff line.
5. Reply `the-loop execute`.
6. Confirm `the-loop check` shows *skipped by handoff* and the pointer reaches
   `requirements-approval` after `import-handoff`.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T3, T6, T8, T10 | pytest summary, plus the list of new test ids per row | `tests.md` |
| T2, T8 | scenario table from `the-loop scenarios --format markdown` | `scenarios.md` |
| T10 | `make validate` output | `tests.md` |
| T11 | redacted transcript of the interview and confirmation; links to the scratch issue, record and PR; `the-loop check` output | `manual-handoff.md` |
| T12 | `make check` summary | `tests.md` |

## Verification activities

- [ ] T1, T2, T3, T6, T8, T10 — `make test`
- [ ] T10 — `make validate`
- [ ] T12 — `make check`
- [ ] T2/T8 scenario table — `uv run the-loop scenarios --format markdown`
- [ ] T11 — manual handoff procedure above

## Verification results

*Not yet executed.*

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.

### 2026-10-21 — approved

**@MadaraUchiha-314** wrote:

approved
