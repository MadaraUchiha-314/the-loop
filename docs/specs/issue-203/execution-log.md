---
type: execution-log
workItem: issue-203
phase: needs-review
status: in-progress
---

# Execution Log: an inline `url` for the Slack integration

> Append-only log for issue-203. Ticket:
> [#203](https://github.com/MadaraUchiha-314/the-loop/issues/203).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-10 | @MadaraUchiha-314 (out of band) | The owner filed the ticket and dispatched a cloud session **at it**, so no checklist was posted and none was waited on — the same provenance as issue-201, recorded here rather than implied. Phases selected: the full spec chain, verification, review. `design-critic-review` (opt-in) not selected. |
| requirements-definition | 2026-08-10 | | [`requirements.md`](requirements.md) locked — three requirements: the URL may be configured inline, a resolution failure names every remedy, and the existing deployment is untouched. Risk tier **4** (`autonomy.inferFromChange`: the change edits `.the-loop/cli-config.schema.json`, matching `sensitivePaths: **/*schema*`), so the gate is `human-approves-pr` and a **named human security sign-off** is required. |
| design | 2026-08-10 | | [`design.md`](design.md) locked — one optional schema property, one keyword-defaulted constructor argument, one changed line in the shared `_url()`. |
| test-planning | 2026-08-10 | | [`testing-plan.md`](testing-plan.md) locked — 4 rows in scope, 7 `n/a` with reasons. Reviewed together with the design, one gate for the pair. |
| tasks-breakdown | 2026-08-10 | | [`tasks.md`](tasks.md) locked — 7 tasks, two independent roots. |
| implementation | 2026-08-10 | | Tests red first, then the resolver, the providers, the schema, the docs and the paper trail. |
| verification | 2026-08-10 | | Every in-scope row executed; evidence committed under [`evidence/`](evidence/). |
| needs-review | 2026-08-10 | | Self-review converged; awaiting the human gate and the security sign-off on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-203-uqjv14` | the whole work item | open |

## Progress entries

### 2026-08-10 — the inline url

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown →
  implementation → verification
- **Did:** Added `integrations.slack.url` as an optional schema property and threaded it
  through the one place that builds a Slack provider (`resolve()`) into the one place that
  resolves a URL (`_SlackBase._url()`), with config taking precedence over the environment
  and a blank value collapsing to absent. The failure message now names both remedies. The
  three companion surfaces the change makes wrong — the options page, the scaffolded
  config template, the capability doc — moved with it, and the reasoning is
  [decision-075](../../decisions/decision-075.md).
- **Checkpoint/tests:** the precedence tests were written first and run red (6 failing,
  including the schema-validation abuse case) before any source change; the three
  integration scenarios were verified red against the pre-change resolver by stashing
  the two implementation files (2 of 3 failed — the third is the
  unchanged-behaviour guard, correctly green both ways). Full suite green afterwards.
- **Next:** the reviewer briefing on the PR, then the human approval + security sign-off.

## Verification results

> Recorded in [`testing-plan.md`](testing-plan.md) § Verification results, against the
> matrix rows that planned them.

## Design critic review

> Not selected. `design-critic-review` is opt-in (issue-188) and this work item did not
> tick it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — the first cut let a blank `url:` win over a working env var, because `str(section.get("url", ""))` treats `""` as a value. Collapsed to `or ""` at the resolver and pinned it as abuse case 2: a config edit that looks like a comment must not disable delivery | [`base.py`](../../../cli/the_loop/graph/integrations/base.py) |
| 2 | self | the-loop (this session) | new findings — the precedence tests originally constructed providers directly, which would have proved `_url()` right while leaving the wiring (the half that was actually missing) unverified. Rewritten to go through `resolve()`, parametrised over both transports | [`test_graph_integrations.py`](../../../cli/tests/test_graph_integrations.py) |
| 3 | self | the-loop (this session) | zero (converged) | — |
| 4 | critic | — | unavailable — `reviews.critics` is empty in this project's config | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |
| 5 | security | built-in security-review skill | no findings at HIGH or MEDIUM; one named risk accepted with a stated mitigation — see the gate below | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the built-in **security-review skill** — what
  `security.review.mechanism: auto` selects when it is available. Full record:
  [`evidence/security-review.md`](evidence/security-review.md).
- **Outcome:** **pass, no findings at HIGH or MEDIUM — with one accepted risk stated
  rather than discovered.** The review's one non-obvious question was whether an untrusted
  repository could set the new key: the CLI config *is* cwd-resolvable, but it already
  carries `integrations.github.cli.binary` (a program the daemon executes) and
  `api.baseUrl` (where a GitHub token is sent), so a webhook URL widens nothing against an
  attacker who already controls that file. The change adds the first key in a the-loop config that may hold a
  credential *by value*. It is bounded three ways: to Slack's incoming-webhook URL alone
  (post rights to one channel — `github.api.tokenEnv` and `webhooks.ghWebhook.secretEnv`
  stay env-only); to an operator's explicit act, since nothing writes the key on their
  behalf and `urlEnv` remains the default; and to a documented cost, stated in the schema
  description, the config template and a `::: danger` block in the options page. No
  untrusted input can reach the key — it is read by the daemon from a local file, and no
  webhook payload, ticket comment or poll response influences it. The value is never
  logged and never appears in the error, which names sources only. The three abuse cases
  (non-string, blank, leakage) each have a negative test.
- **Human sign-off:** **required and pending** — risk tier 4 meets
  `security.review.humanSignOffMinTier: 4`. Requested from @MadaraUchiha-314 in the PR
  briefing; this work item is not complete until it is recorded here.

## Final validation evidence

| Requirement | Proved by |
|---|---|
| R1 — the URL may be configured inline | `test_an_inline_url_is_used`, `test_an_inline_url_wins_over_the_environment` (both transports) and the end-to-end `Scenario: a notification is delivered to the URL configured inline`, which asserts the request target rather than the resolver's return value |
| R2 — a resolution failure names every remedy | `test_the_failure_names_both_remedies_and_not_the_url` — both sources named, no URL echoed — and `Scenario: an unresolvable webhook url fails closed without wedging the graph`, which pins the best-effort contract at the same time |
| R3 — the existing deployment keeps working untouched | `test_without_an_inline_url_the_environment_is_read`, `test_a_custom_url_env_is_still_honoured`, `test_a_provider_built_the_old_way_still_works`, the unchanged config `version`, and the whole suite green (1796 passed, 1 skipped) |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`cli.md`](../../capabilities/cli.md) | A new rule under the CLI-config behaviours: two sources for the Slack webhook URL, config first, both transports resolving through one method, a failure naming both remedies — and the explicit statement that the carve-out is Slack's alone | `issue-203` row added at the top of § History |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/cli/integrations-options.md`](../../config/cli/integrations-options.md) | New `### slack.url` section — type, default, precedence, the example, the danger block, the failure mode it removes, and the exact error text. `slack.urlEnv`'s note changed from "a variable name, never the URL" (now false) to what it actually is: the default source, and the one to keep where the file is shared |
| [`skills/the-loop/templates/cli-config.yaml`](../../../skills/the-loop/templates/cli-config.yaml) | A commented-out `url:` in the scaffolded config, with its cost written beside it — the choice is visible without being invited |
| `README.md`, the skill and its `reference/` docs | Unchanged, and deliberately: none of them describes how the Slack integration is configured. The configuration reference is the surface a reader meets for this, and it moved |
