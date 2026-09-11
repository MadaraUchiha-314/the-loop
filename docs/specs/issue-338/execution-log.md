---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#338"
phase: needs-review
status: in-progress
---

# Execution Log: long agent output reaches Slack as a digest instead of a hard truncation

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): a rendering change inside the Slack channel, one additive enum key in both schema copies (an `autonomy.sensitivePaths` entry, as issue-325's `reactions` block was), no new call, grant, token, scope or state. Brainstorming skipped: the ticket's five numbered asks are the requirement. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — five requirements, five abuse cases |
| design | 2026-09-11 | | [`design.md`](design.md) — `channels/digest.py`, `fit` in the renderer, the key; [`decision-118`](../../decisions/decision-118.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, seven applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-338-lk8282` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T7, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — five abuse cases, five closed |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#345](https://github.com/MadaraUchiha-314/the-loop/pull/345) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-11 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–6, red first (`test_channels_digest.py` did not import against
  `3b7563c`; the three scenarios failed on the raw section text). `channels/digest.py`:
  `strip_comments` (a forward scan), `to_mrkdwn` (the line and inline rules, applied
  outside code fences and spans, broadcasts neutralised everywhere), `shorten_paths`,
  `condense` (the block parser, the ask, the numbered lists, the pointers, a two-pass
  budget — whole when it fits once drawn, else with the footer reserved — the
  sentence / clause / space cut), `truncate` (13.10.0's `_cap`), `fit` (the one entry
  point; the raw length is the threshold, the drawn length is re-checked so the one
  growing rule never posts over the cap). `channels/slack.py`: `long_messages` on the
  config (unknown → `digest` with a warning), `render_blocks(long_messages=)` routing
  the text and excerpt sections through `fit`, `post` building the plain-text fallback
  from the drawn section when the text was over the cap, `_cap` an alias of `truncate`
  for the verbose context lines. `commands/channels_cmd.py`: the `longMessages:` line.
  Both schema copies (one additive enum key, `maxChars` restated), the two config
  templates, the option page, the guide (*Reading it on a phone*, a *Limits* bullet),
  the command page, the capability doc, the README and the collaboration reference;
  decision-118.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 41
  unit (`test_channels_digest.py`), 3 scenarios (`test_channels_integration.py`).
  Existing assertions changed: two — `test_bus.py`'s cap pin now names
  `long_messages="truncate"` (and pins the digest beside it), and `test_channels.py`'s
  schema-default pin gained the new key.
- **Self-review:** three passes over the diff. Pass one (the code, adversarially)
  found that `to_mrkdwn` drew a `# comment` inside a shell fence as a heading and a
  `**` inside a code span as bold — now every drawing rule runs outside fences and
  spans (`_outside_code`); that a Slack link's site-absolute URL (`</docs/a/b/c|t>`)
  was shortened as a path — `<` joined the lookbehind; that a heading that *is* the
  question left an empty `**` line behind — an emptied block renders nothing; that the
  broadcast rewrite could grow a 2 900-character text past Slack's limit — `fit`
  re-measures the drawn text; that a Java / Node `at …(…)` line started a trace on
  any parenthesised indented line — a `file:line` location is now required; and that
  a test helper lived in the module — moved to the test. Pass two verified five design
  claims against the code: the threshold is the raw length; nothing but `slack.py`
  imports the digest (pinned by a test on import lines); the footer is the event's URL
  only; the pipeline's order and the ledger record are untouched (the scenario asserts
  no record); the lockfile refresh `uv run` made was incidental and is not in the
  change. Pass three read the docs against the code: the guide's and the design's
  before/after examples were the sketch, not the output — replaced with the real
  digest of the checklist at `maxChars: 700`; the design's budget prose said the
  footer was always reserved — now describes the two passes; the option page's
  `as before 13.11` became `13.10.0's behaviour`. Nothing else new.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-11 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket; read `channels/{slack,base,publishers,bus}.py`,
  `commands/channels_cmd.py`, `graph/hooks/{sideeffects,selection}.py`, the channel
  test suites, the guide, the option and command docs, the issue-337 spec and
  decisions 103, 111, 116, 117 at `3b7563c` (13.10.0). Established that every text
  section is cut by one function (`_cap`) in one place (`render_blocks`), that GitHub
  markdown reaches Slack unconverted (the markers literally — the issue-337 log's
  observation), and that the post's plain-text fallback is uncapped. Settled the three
  design questions in decision-118: a structural digest the channel computes rather
  than a model summary; one enum key (`longMessages: digest | truncate`) with
  `maxChars` as the threshold; mrkdwn rendering on every message, the digest only
  above the cap. Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_channels.py` green at `3b7563c` (101 passed).
- **Next:** task 1 (the digest module), red first.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Findings → disposition | Link |
|-------|-----------------------------|----------|---------|------------------------|------|
| 1 | self | the-loop (this session) | six new findings | code drawn as prose — every rule now runs outside fences and spans; a Slack link URL shortened as a path — `<` in the lookbehind; an emptied heading left `**` — renders nothing; the broadcast rewrite could grow past the cap — re-measured; an over-eager trace start — `file:line` required; a test helper in the module — moved | this log |
| 2 | self | the-loop (this session) | zero new findings | five design claims verified against the code (the raw threshold, the single importer, the footer's source, the untouched pipeline, the incidental lockfile) | this log |
| 3 | self | the-loop (this session) | zero new findings (converged) | the docs read against the code: two examples and two sentences corrected | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — | — |
| 4 | security | the-loop checklist | pass; no human sign-off at tier 3 | A1–A5 closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), five abuse cases closed
- **Human sign-off:** not required (tier 3 < `humanSignOffMinTier: 4`); the owner's PR approval is the gate

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1 | `test_a_long_text_is_digested_within_the_limit` (five limits, two fixtures), `test_render_blocks_digests_the_text_section`, `test_render_blocks_digests_the_excerpt_too`; `Scenario: A long agent comment reaches Slack as a digest that leads with the ask`; `Scenario: A notification's artifact excerpt is digested too` |
| R1.2 | `test_the_cut_falls_on_a_sentence_boundary`, `test_a_sentence_too_long_for_the_room_is_cut_at_a_clause_then_a_space` |
| R1.3 | `test_the_footer_names_the_link_or_the_ticket`, `test_the_footer_links_the_event_never_the_text`, `test_nothing_is_left_out_when_everything_fits_compactly` |
| R1.4 | `test_truncate_is_the_13_10_0_cut`, `test_render_blocks_truncate_keeps_the_old_cut`, `test_an_unknown_long_messages_value_resolves_to_digest`, `test_bus.py::test_render_blocks_caps_text_and_points_at_the_link` |
| R1.5 | `test_the_fallback_text_carries_the_digest`; the first scenario's fallback assertion |
| R2.1 | `test_the_first_question_leads`, `test_a_reply_instruction_leads_when_nothing_asks`, `test_without_an_ask_the_first_sentence_leads`, `test_a_question_in_a_heading_leads_and_leaves_no_empty_heading` |
| R2.2, R2.3 | `test_a_list_becomes_numbered_lines_with_its_boxes`, `test_the_authors_order_is_kept_after_the_ask` |
| R3.1 | `test_fences_tables_and_traces_become_pointers`, `test_code_is_drawn_as_written` |
| R3.2 | `test_absolute_paths_are_shortened_and_urls_untouched` |
| R3.3, R3.4 | `test_html_comments_never_reach_slack`, `test_to_mrkdwn_draws_markdown_as_slack_does`, `test_to_mrkdwn_is_idempotent_and_leaves_prose_alone`, `test_a_short_section_is_drawn_and_nothing_else` |
| R4.1 | `test_a_short_text_passes_through_untouched`; `Scenario: A short comment reaches Slack untouched` |
| R4.2 | `test_the_threshold_is_the_raw_length`, `test_a_text_that_grows_past_the_cap_when_drawn_is_digested`, `test_long_messages_is_parsed_and_defaults_to_digest`, `test_channels.py::test_config_defaults_match_the_schema`, `test_config_schema_parity.py` |
| R4.3 | `test_status_prints_the_long_messages_line` (both values) |
| R5.1 | `test_docs_parity.py` (`p3`–`p5` on `channels.slack.longMessages`); the docs table below |
| NFR faithful, linear | `test_every_digest_line_is_the_authors`, `test_a_pathological_comment_digests_in_linear_time`, `test_empty_and_odd_inputs_never_raise` |
| A1–A5 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | the rendering bullet (drawn as mrkdwn; above `maxChars`, per `longMessages`); a new *long text is digested* bullet (the digest's rules in EARS, `truncate`, the whole-text rule under the cap, the fallback text, the mrkdwn drawing and the broadcast rule, the status line); two design links | issue-338 row |
| [`standing-sessions.md`](../../capabilities/standing-sessions.md), [`control-plane.md`](../../capabilities/control-plane.md) | unchanged — a standing session's thread is rendered by the same channel and gains the same digest; the control plane is not touched | — |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/channels-options.md` | `slack.maxChars` restated as the threshold and the phone's lever; a new `slack.longMessages` section (type, default, what `digest` does and never does, `truncate`, the whole-text rule, the mrkdwn drawing); the example YAML |
| `docs/guide/slack.md` | a new *Reading it on a phone* section (the four rules, the checklist digest at `maxChars: 700`, the notification preview, `maxChars` as the lever, `longMessages: truncate`, the markers); a *Limits* bullet (structural, not a summary) |
| `docs/cli/commands/channels.md` | the `status` bullet names the `longMessages` line |
| `README.md` | the `channels poll` line says long text arrives as a digest |
| `skills/the-loop/reference/collaboration.md` | the channels paragraph names the digest |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | the `maxChars` comment and a `longMessages` line |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | `longMessages` (enum, default `digest`); `maxChars`'s description (byte-identical copies) |
| `docs/decisions/decision-118.md`, `decisions.md` | the decision and its index row |
| `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/automation.md` | unchanged — the operating model itself did not change (what Slack shows is the channel's rendering; the ledger is still the record) |
