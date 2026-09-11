---
type: testing-plan
phase: test-planning
workItem: "issue-338"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the Slack digest — the ask first, choices numbered, pointers, cut at a sentence

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `to_mrkdwn` (each rule, idempotence, plain prose is the identity); `strip_comments` (closed, unclosed, foreign); `condense` (the ask leads, the reply-instruction fallback, no ask → the first sentence, lists numbered with ☑ / ☐, fences / tables / traces as pointers with counts, paths shortened and URLs untouched, the sentence / clause / whitespace cut, the footer with and without a URL, the budget honoured, the faithfulness property, empty / whitespace / unicode inputs); `fit` (short untouched, `truncate` is the 13.10.0 output, the raw length is the threshold); the config (`long_messages` parse, unknown → default with a warning, schema default parity); `render_blocks` (the section is the digest, the excerpt too, the fallback text matches, the marker never reaches Slack, `truncate` keeps the old cut); `channels status` (the line per value) | `uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py cli/tests/test_channels.py::test_config_defaults_match_the_schema` |
| T2 | Integration (scenario) | yes | through `publish_comment` → the bus → the channel with a fake Slack client: a long agent comment arrives as the digest (the ask first, no fence, within `maxChars`, the link, the ledger untouched); a short comment passes through untouched; a notification's artifact excerpt is digested | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "digest or untouched or excerpt"` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route changes | | |
| T4 | End-to-end | n/a — no Slack workspace is reachable; T2 exercises every module up to the SDK boundary | | |
| T5 | UI / visual | n/a — Slack draws Block Kit; the section text is asserted in T1/T2 and the before/after is in `design.md` | | |
| T6 | Snapshot | n/a — assertions on strings and block dictionaries, the faithfulness property instead of a golden file | | |
| T7 | Performance / load | yes | a 64 KB comment of unclosed `**`, `<!--`, `[` and fence openers digests within a generous wall-clock bound (the linearity claim of the design, abuse case A1) | `uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py -k pathological` |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A5 (`requirements.md` § Security considerations) | `uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py -k "pathological or broadcast or footer_links or foreign_comment or reads_the_digest"` |
| T9 | Accessibility | n/a — no UI of the-loop's own | | |
| T10 | Migration / upgrade | yes | a 13.10.0 config parses unchanged and gains `digest`; both schema copies identical; docs parity on the new heading; the existing channel suites green | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_configschema.py cli/tests/test_channels.py cli/tests/test_channels_buttons.py cli/tests/test_channels_integration.py cli/tests/test_bus.py cli/tests/test_channels_commands.py` |
| T11 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A5, recorded as evidence; tier 3 needs no human sign-off | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3 | `test_a_long_text_is_digested_within_the_limit`, `test_the_cut_falls_on_a_sentence_boundary`, `test_a_sentence_too_long_for_the_room_is_cut_at_a_clause_then_a_space`, `test_the_footer_names_the_link_or_the_ticket` |
| T1 | R1.4 | `test_truncate_is_the_13_10_0_cut`, `test_an_unknown_long_messages_value_resolves_to_digest` |
| T1 | R1.5 | `test_the_fallback_text_carries_the_digest` |
| T1 | R2.1 | `test_the_first_question_leads`, `test_a_reply_instruction_leads_when_nothing_asks`, `test_without_an_ask_the_first_sentence_leads` |
| T1 | R2.2, R2.3 | `test_a_list_becomes_numbered_lines_with_its_boxes`, `test_the_authors_order_is_kept_after_the_ask` |
| T1 | R3.1 | `test_fences_tables_and_traces_become_pointers` |
| T1 | R3.2 | `test_absolute_paths_are_shortened_and_urls_untouched` |
| T1 | R3.3, R3.4 | `test_html_comments_never_reach_slack`, `test_to_mrkdwn_draws_markdown_as_slack_does`, `test_to_mrkdwn_is_idempotent_and_leaves_prose_alone` |
| T1 | R4.1, R4.2 | `test_a_short_text_passes_through_untouched`, `test_the_threshold_is_the_raw_length`, `test_config_defaults_match_the_schema` |
| T1 | R4.3 | `test_status_prints_the_long_messages_line` |
| T1 | NFR faithful | `test_every_digest_line_is_the_authors` |
| T2 | R1.1, R2.1, R3.1, R1.3 | `Scenario: A long agent comment reaches Slack as a digest that leads with the ask` |
| T2 | R4.1 | `Scenario: A short comment reaches Slack untouched` |
| T2 | R1.1 (excerpt) | `Scenario: A notification's artifact excerpt is digested too` |
| T7, T8 | A1 | `test_a_pathological_comment_digests_in_linear_time` |
| T8 | A2 | `test_a_slack_broadcast_in_a_comment_is_neutralised` |
| T8 | A3 | `test_the_footer_links_the_event_never_the_text` |
| T8 | A4 | `test_nothing_but_the_renderer_reads_the_digest` (the pipeline modules import no digest symbol) |
| T8 | A5 | `test_a_foreign_html_comment_is_removed_too` |
| T10 | R4.2, R5.1 | schema parity, docs parity, config validation, the existing suites |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The Slack SDK is faked at its injection point
  (`client_factory` / `build_client`); the ledger writer (`post_comment`) is faked as
  the existing suites fake it; no tmux, no `gh`.
- **Fixtures & data:** temp directories per test; fixture texts inside the test module
  (a checklist shaped like the phase-selection hook's, a traceback, a table, a long
  paragraph).
- **Credentials:** none. `THE_LOOP_SLACK_BOT_TOKEN` is set to a dummy value by name
  where a channel is built.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T7, T8, T10, T12 | command, counts, duration, raw tail of the output; red → green per task | `verification.md` |
| T13 | the abuse-case table with verdicts and the tests that close each | `security-review.md` |

## Verification activities

- [x] T1 — the unit selection above
- [x] T2 — the scenario selection above
- [x] T7 — the pathological-input test
- [x] T8 — the abuse-case selection above
- [x] T10 — the parity and existing-suite selection above
- [x] T12 — `make check`
- [x] T13 — `evidence/security-review.md`

## Verification results

> Filled at `verification` (2026-09-11, head of `claude/github-issue-338-lk8282`).

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py cli/tests/test_channels.py::test_config_defaults_match_the_schema` | pass — 42 passed | [`evidence/verification.md`](evidence/verification.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "digest or untouched or excerpt"` | pass — 4 passed (the three issue-338 scenarios plus an issue-337 scenario the selection also matches) | [`evidence/verification.md`](evidence/verification.md) |
| T7 | `… test_channels_digest.py -k pathological` | pass — a 64 KB crafted comment, three digests plus the drawing plus the cut, in 0.05 s against a 5 s bound | [`evidence/verification.md`](evidence/verification.md) |
| T8 | `… test_channels_digest.py -k "pathological or broadcast or footer_links or foreign_comment or reads_the_digest"` | pass — 4 passed, A1–A5 each closed by a named test (A5 shares `foreign_comment` with `html_comments_never_reach_slack`) | [`evidence/verification.md`](evidence/verification.md), [`evidence/security-review.md`](evidence/security-review.md) |
| T10 | schema parity, docs parity, config validation, the channel, bus and command suites | pass — 303 passed; both schema copies identical; `channels.slack.longMessages` documented with type and default; a 13.10.0 config parses unchanged | [`evidence/verification.md`](evidence/verification.md) |
| T12 | `make check` | pass — ruff, ruff format, markdownlint, pyright, `validate_config`, the full suite | [`evidence/verification.md`](evidence/verification.md) |
| T13 | the-loop checklist | pass — five abuse cases, five closed; no human sign-off at tier 3 | [`evidence/security-review.md`](evidence/security-review.md) |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
