---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#488"
status: approved             # draft | in-review | approved — locked with design.md at design-approval
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the explainer, the spec quiz and the code quiz

> Derived from the approved [`requirements.md`](requirements.md) and the draft
> [`design.md`](design.md), and reviewed with the design at `design-approval`. **This file
> is executable content**: it names commands an agent will run. No credential is needed
> except the one already in the environment, which is named by reference only.

**The proof in one line.** The parts that decide something are the row parser, the two
hooks, the poller's tick detection, the webhook rewrite and the dispatcher's
no-spawn rule. Unit and integration tests prove those against a fake GitHub. A headless
browser proves the page and its quiz engine. One live run on a sandbox issue proves that
GitHub's GraphQL really names the person who ticked. That last fact is the whole design's
premise, and no fake can establish it.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | Row parser (absent → on, unticked → off). Skip-set declaration and provenance. `quiz-attested` branches (C4). Spec digest. `post-quiz-attestation` idempotency, PR fan-out, view-command rendering. Poller `quizSeen` keying. Webhook `edited` rewrite. Dispatcher drop without a gate. `comment_edits` response mapping | `make test` (`cd cli && uv run python -m pytest -q`) |
| T2 | Integration (scenario) | yes | The tick reaching the gate end-to-end through poller → dispatcher → GraphLink → hook, with a fake GitHub. Selection → skips. Stale digest → back-edge. Gherkin docstrings, in `cli/tests/test_quiz_integration.py` (matches the `testing.integrationTestGlobs` entry) | `make test` |
| T3 | Contract (OpenAPI) | n/a — no REST route, MCP tool or API schema is added. The new verb surface is zero, and `test_api_contract_parity.py` still runs under T1 and must stay green | | |
| T4 | End-to-end (graph walk) | yes | The shipped `pdlc-work-item-loop` walks the four new nodes in order on the happy path, and skips all four when the row is unticked. Uses the existing e2e scenario runner (`cli/tests/test_pdlc_e2e/`) with updated `happy-path` and `trivial-tier` traces plus one new `explainer-off` scenario | `make test` |
| T5 | UI / visual | yes | `templates/explainer.html` (the shipped template, filled with the fixture quiz): tabs, quiz reveal-after-select, progress line, light and dark mode, 375 px width with no horizontal scroll, no network request, no script error | headless Chromium via Playwright: `node docs/specs/issue-488/evidence/ui/check.mjs` |
| T6 | Snapshot | yes | The rendered checklist body with the `explainer` row (pinned like the existing layout tests), the confirmation comment in both directions, and the quiz comment body (ticket link form and HTML view-command form) | `make test` |
| T7 | Performance / load | n/a — one string check per already-fetched comment, and one GraphQL query per detected tick. No loop or I/O is added to the steady-state poll cycle beyond that | | |
| T8 | Security / abuse case | yes | One negative test per abuse case (design §Security design): unauthorized editor, unknown editor and query error, `<script>` text in quiz data rendered as text, artifact or unmarked text ignored, forged comment ignored. Redaction is a manual grep (T11) | `make test`. The `textContent` case runs under T5 |
| T9 | Accessibility | yes | Tabs are keyboard-operable (arrow keys, Home, End). Options are native radios. The verdict is in words, not colour alone. An automated axe-core pass on the template with zero serious or critical violations | Playwright script (T5) with `axe-core` injected from `node_modules` |
| T10 | Migration / upgrade | yes | A work item that is already past `design-approval` when the new graph ships keeps walking: its frozen graph has no quiz nodes, so the runtime must not route it into them. Covered by loading a pre-change frozen graph fixture | `make test` |
| T11 | Manual exploratory | yes | **Live GraphQL attribution** on a sandbox issue in this repository. The-loop posts a quiz comment, the owner ticks it, and `comment_edits` returns the owner's login as the newest editor. Plus the redaction grep of any committed explainer HTML | procedure in Verification activities |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–1.5, 1.7 | row rendered ticked; absent → on; unticked → 4 skips with token `explainer`; confirmation line both ways; Slack token list and `without` |
| T1 | R2.4–2.7, R3.6–3.8, R3.10 | `quiz-attested`: ticked + authorized → pass with `attestedBy`; unticked → wait; typed fallback; PR fan-out and ticket fallback |
| T1 | R5.4, R5.6 | view commands rendered from owner, repo, branch and path only; digest stable for identical bytes and changed by one byte |
| T2 | R2.6 | `Scenario: a tick by an authorized user advances the spec quiz` |
| T2 | R2.5, abuse 1 | `Scenario: a tick by an unauthorized user is refused` |
| T2 | R1.3 | `Scenario: an unticked explainer row skips all four nodes` |
| T2 | R5.6 | `Scenario: a changed spec sends the spec quiz back to the explainer` |
| T2 | R3.7–3.8 | `Scenario: review is not requested until the code quiz is ticked` |
| T2 | design C5 | `Scenario: a quiz tick on a work item with no waiting gate spawns nothing` |
| T4 | R1.2, R1.6, R2.1, R3.1, R3.6 | e2e traces: happy path through the four nodes; `explainer-off`; contribution loop unaffected |
| T5 | R3.3, R4.1, R6.6, NFR a11y | template renders the four tabs; feedback count 0 before selection and 1 after |
| T6 | R1.1, R1.5, R2.4, R3.6, R5.4 | checklist, confirmation and quiz comment bodies pinned |
| T8 | abuse 1, 2, 3, 4, 6 | `test_quiz_attested_refuses_unauthorized_editor`, `test_quiz_attested_fails_closed_without_editor`, `test_explainer_template_renders_text_not_markup`, `test_quiz_attested_ignores_unmarked_and_artifact_text`, `test_quiz_attested_ignores_forged_comment` |
| T9 | NFR a11y | axe pass, plus keyboard walk across the tabs |
| T10 | R1.6 (no regression) | `test_frozen_graph_without_quiz_nodes_keeps_walking` |
| T11 | R2.6, abuse 2, abuse 5 | live attribution, and the redaction grep |

R6.1–6.5 and R6.7 are quiz-*content* rules that the agent follows while writing. No
automated test can judge "a genuine misunderstanding". They are proved by review: the
reference states them as a checklist, and the self-review and critic-review rounds
check the first real explainer this feature produces, its own (see Evidence plan).

## Verification environment

- **Repositories:** this repository only, at the PR #489 head.
- **Services / containers:** none for T1–T10. The tests use the fake GitHub integration
  and the in-process dispatcher the suite already provides. For T11, the operator's
  running the-loop daemon on this machine (`the-loop sessions list` shows it).
- **Fixtures & data:**
  - recorded GraphQL `userContentEdits` responses (authorized, unauthorized, null
    editor, empty history, error) under `cli/tests/fixtures/github/comment_edits/`;
  - a pre-change frozen graph for T10;
  - the filled explainer template fixture with a `<script>` string in one option.
- **Credentials:** by reference only. T11 uses the daemon's existing GitHub token
  (`integrations.github.api.tokenEnv`, default `GH_TOKEN`), held by the service. No new
  scope is needed.
- **Bring-up:** `make install-dev`. For T5 and T9: `npm i --prefix
  docs/specs/issue-488/evidence/ui playwright@1 axe-core@4`, then point
  `executablePath` at the system Chromium. **Tear-down:** delete the T11 sandbox issue's
  comments, and close the sandbox issue.
- **If bring-up fails:** record it under Verification results, leave the dependent rows
  unticked, and escalate on PR #489.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T4, T6, T8, T10 | pytest summary (counts, duration) and the names of the new tests | `unit.md` |
| T2 | `the-loop scenarios --glob 'cli/tests/test_quiz_integration.py' --format markdown` plus the run output | `integration.md` |
| T5 | screenshots of each tab in light and dark mode, an answered quiz (one right, one wrong) and the 375 px view; a GIF of the answer-select-feedback flow; the check script's console output | `ui/*.png`, `ui/quiz-flow.gif`, `ui/check.md`, `ui/check.mjs` |
| T9 | axe-core results (violations by impact) | `ui/a11y.md` |
| T11 | the GraphQL response for the live tick (login only, no token, internal host redacted), the quiz comment URL, and the redaction grep output | `live-attribution.md` |
| R6 content rules | the self/critic review rows that judge this work item's own explainer and quizzes against R6.1–6.7 | `self-review.md`, `critic-review.md` (written at those nodes) |

## Verification activities

- [ ] T1, T4, T6, T8, T10: `make test`, all green, new tests named in `unit.md`
- [ ] T2: `make test`, then `the-loop scenarios --glob 'cli/tests/test_quiz_integration.py' --format markdown` captured into `integration.md`
- [ ] T3 parity: `test_api_contract_parity.py` green within `make test` (no new route)
- [ ] T5: `node docs/specs/issue-488/evidence/ui/check.mjs skills/the-loop/templates/explainer.html` reports 0 feedback before select, 0 network requests, 0 page errors, no overflow at 375 px; screenshots and GIF committed
- [ ] T9: the same script's axe pass reports 0 serious or critical violations; keyboard tab walk recorded
- [ ] T11: live attribution on a sandbox issue. Post a quiz comment with `the-loop comment`, the owner ticks it, and `comment_edits` returns the owner's login as the newest editor
- [ ] T11: `grep -nEi 'gh[pousr]_[A-Za-z0-9]{20,}|token|cookie|@[a-z0-9.-]+\.(internal|corp|local)'` over any committed explainer HTML returns nothing
- [ ] Lint parity: `make lint` and `make typecheck` green (pre-commit = CI)

## Verification results

*Not yet executed.*

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

**Not executed:** none yet.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.

### 2026-10-15 — approved

**@MadaraUchiha-314** wrote:

approved
