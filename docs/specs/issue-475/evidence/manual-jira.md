# T11 — manual verification against a real Jira Cloud site

**The four facts the fakes cannot prove, checked against a live Jira Cloud sandbox: three
proven, one deliberately not run.** Run on 2026-10-07 through the-loop's own `JiraClient`,
`JiraProvider` and `JiraPollProvider` (top of the stack, `feat/issue-475-jira-5-edges`),
with the operator's sandbox credentials (`JIRA_SANDBOX_SITE`, `JIRA_EMAIL`,
`JIRA_API_TOKEN` — by reference; values never printed). Project `KAN`, per the operator's
instruction on #475 ("Just use KAN for now"); `LOOPTEST` was not visible to the service
account. Every ticket created was deleted at teardown.

| Fact (testing-plan T11) | Result |
|---|---|
| ADF renders as intended | **proven**: headings, ordered and bullet lists, bold, inline code, code blocks, links, tables with header cells; the checklist is stored as a real `taskList` |
| Cloud `/search/jql` accepts the poller's JQL | **proven**: the poller listed the armed ticket by `labels = "the-loop:auto-execute"` |
| `myself` equals the author of our comments | **proven**: so the service-account self check and the relay check hold |
| Jira signs webhooks as the doorbell verifies | **not run**: the operator confirmed polling is enough ("do we really need webhook if we are polling ?"); the webhook route stays off unless `integrations.jira.webhook.secretEnv` is set, and signing is proven by unit test against Atlassian's documented `X-Hub-Signature` format only |

## Steps and outcomes

Command (from `cli/`, credentials sourced from the operator's env file):

```sh
T11_PROJECT=KAN env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM \
  uv run python ../docs/specs/issue-475/evidence/jira/t11_run.py tests/fixtures/jira <out-dir>
```

| # | Step | Outcome | Note |
|---|---|---|---|
| 1 | create ticket | pass | key KAN-<n> |
| 2 | add-comment (checklist body, ADF) | pass |  |
| 3 | Jira stored a taskList (real checkboxes) | pass |  |
| 4 | Jira renders tables/headings/code from ADF | **fail** |  |
| 5 | self-marker survives storage | pass |  |
| 6 | comment author == myself | pass |  |
| 7 | JiraComment.is_self on our comment | pass |  |
| 8 | is_self_authored(read-back body) | pass |  |
| 9 | set-labels (Jira-safe) | pass | labels=['loop:implementation', 'the-loop:auto-execute'] |
| 10 | remove-label | pass |  |
| 11 | poller lists the armed ticket via /search/jql | pass |  |
| 12 | poller reads comments; ours dropped as self | pass |  |
| 13 | ticked taskItem reads back as `- [x]` | pass |  |
| 14 | transition to done | pass | via 'Done' |
| 15 | poller sees closure (statusCategory done) | pass |  |
| 16 | teardown: delete test ticket | pass |  |

**Step 4 fail was a wrong check, not a defect.** It asserted a `<table>` in the rendered PR
briefing, but the briefing template has no table. Jira rendered everything the briefing
holds — [`jira/pr-briefing.rendered.html`](jira/pr-briefing.rendered.html): `h1`/`h2`, an
ordered and a bullet list, bold, inline code, the mermaid source as a code block. A
follow-up probe posted a table, a link, bold and a fenced code block and found each in
Jira's rendering — [`jira/table.rendered.html`](jira/table.rendered.html) (`table: True |
th: True | link: True | bold: True | code: True`), ticket deleted.

**The tick round trip is exact.** The posted checklist had 17 ticked and 11 open boxes; after
one `taskItem` was set `TODO → DONE` in Jira (an API edit of the stored ADF — no browser
session was available for a UI click), the-loop read back 18 and 10, and the one changed
line is `- [x] design-critic-review …`. The stored `taskList` is excerpted in
[`jira/checklist.tasklist.excerpt.json`](jira/checklist.tasklist.excerpt.json). Jira's
API-side `renderedBody` (its legacy renderer) shows a done task item struck through; the
Jira UI renders the `taskList` as checkboxes.

## Redaction

Site host → `<sandbox>`, the service account's id → `<service-account-id>`, any other
account id → `<account-id>`. The committed captures were scanned for the email, token,
webhook secret and site host before commit: none present.
