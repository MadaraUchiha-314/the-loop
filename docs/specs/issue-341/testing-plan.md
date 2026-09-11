---
type: testing-plan
phase: test-planning
workItem: "issue-341"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the kickoff prefix, the declared set, and the refusal that answers

> Derived from `requirements.md` and `design.md`, before `tasks.md`. Authored at
> `test-planning`; the results section is filled at `verification`.
>
> **This file is executable content.** Commands below are what the agent runs; credentials
> appear by reference only.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `channels/repos.py`: the declared set from `kickoff.repo` + poll sources, dedup by key, declared string preserved, a malformed entry skipped, a non-`github` source ignored, an unreadable `polling` section contributing nothing. `channels/kickoff.py`: the grammar (bare / `owner/repo` / `host/owner/repo`, case, a four-segment path, `../`, `$(id)`, `a;b`, `https://…`, a prefix on line two); every row of the resolution table; stripping (first line replaced, later lines kept, a blank first line kept for `issue_title` to skip, nothing left refused as `empty-message`); `refusal_text` (the four wordings, the cap at twelve, the empty-set wording, no token / no other config value). `SlackChannelConfig.kickoff_enabled` without `kickoff.repo` | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py` |
| T2 | Integration (scenario) | yes | through `process_kickoff` and the socket handler: a prefixed kickoff opens the issue in a **polled** repository with the prefix stripped from title and body and `kickoff.labels` applied; an ambiguous prefix is refused in the member's own thread with the candidates and creates nothing; a prefix-less message with `kickoff.repo` behaves exactly as 13.11.1; a prefix-less message with no `kickoff.repo` is refused with the ask-for-a-prefix reply | `uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "kickoff"` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API route or payload changes | | |
| T4 | End-to-end | n/a — the poller arming a created issue is `test_poller.py`'s subject and is unchanged; T2 proves the create call this work item composes | | |
| T5 | UI / visual | n/a — the only surface is a Slack message, asserted as text in T1/T2 | | |
| T6 | Snapshot | n/a — assertions on dataclasses, call arguments and message text | | |
| T7 | Performance / load | n/a — resolution is one regex and a set build per message, both in-process | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A7 (`requirements.md` § Security considerations): an unlisted member gets no reply and no disclosure; an undeclared qualified prefix is never absorbed by the fallback; metacharacters never leave the text; a foreign host matches nothing; the refusal carries no token or other config value; a broken `polling` section widens nothing; no grant means no read | `uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py -k "unauthorized or undeclared or metachar or host or leak or malformed or grant"` |
| T9 | Accessibility | n/a — no UI of the-loop's own | | |
| T10 | Migration / upgrade | yes | a 13.11.1 config parses unchanged (no schema key added or removed); both schema copies identical; docs parity (P3/P4/P5); the event catalog knows every reason emitted; the existing channels, commands, buttons and digest suites green | `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_channels_commands.py cli/tests/test_channels_buttons.py cli/tests/test_channels_integration.py` |
| T11 | Manual exploratory | n/a — no Slack workspace is reachable from this session; the reviewer's walk-through is the PR briefing's "what to check" | | |
| T12 | Lint / format / typecheck / config validation / full suite | yes | the repository's own gates, as pre-commit and CI run them | `make check` |
| T13 | Security review (gate) | yes | the-loop checklist against A1–A7, recorded as evidence; tier 3 needs no human sign-off (`humanSignOffMinTier: 4`) | `evidence/security-review.md` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1 | `test_the_declared_set_is_kickoff_repo_and_every_poll_source`, `test_a_declared_entry_keeps_the_operators_own_slug`, `test_the_set_is_deduplicated_by_key`, `test_a_malformed_declared_entry_is_skipped` |
| T1 | R1.2, R1.4 | `test_the_prefix_grammar_accepts_three_shapes`, `test_the_prefix_is_case_insensitive`, `test_prose_is_not_a_prefix` |
| T1 | R1.1, R1.3 | `test_a_bare_prefix_resolves_and_is_stripped`, `test_a_qualified_prefix_resolves`, `test_stripping_keeps_the_following_lines`, `test_a_prefix_alone_is_refused_as_an_empty_message` |
| T1 | R2.2, R2.3, R2.4 | `test_an_undeclared_qualified_prefix_is_refused`, `test_an_ambiguous_bare_prefix_is_refused`, `test_an_unmatched_bare_prefix_falls_back` |
| T1 | R2.5 | `test_refusal_text_names_the_candidates`, `test_the_candidate_list_is_capped`, `test_refusal_text_with_no_declared_repositories` |
| T1 | R5.1 | `test_status_names_the_fallback_and_how_many_a_prefix_may_pick`, `test_status_says_when_there_is_no_fallback`, `test_status_says_kickoff_is_off_without_the_grant` |
| T1 | R3.1, R3.2, R3.3 | `test_no_prefix_uses_the_fallback`, `test_no_prefix_and_no_fallback_is_no_target`, `test_kickoff_is_enabled_without_a_repo` |
| T2 | R1.1, R1.3, R1.5 | `Scenario: A prefixed kickoff opens its issue in the repository the message named` |
| T2 | R2.3, R2.5 | `Scenario: An ambiguous kickoff prefix is refused in the thread and creates nothing` |
| T2 | R3.1, R3.4 | `Scenario: A kickoff with no prefix still opens in the configured fallback repository` |
| T2 | R3.2, R3.3 | `Scenario: With no fallback repository a kickoff is asked for a prefix, not dropped in silence` |
| T8 | A1, R2.6 | `test_an_unlisted_member_is_told_nothing` |
| T8 | A2 | `test_an_undeclared_qualified_prefix_never_falls_back` |
| T8 | A3 | `test_metacharacters_never_parse_as_a_prefix`, `test_only_a_declared_slug_reaches_the_writer` |
| T8 | A4 | `test_a_foreign_host_matches_nothing` |
| T8 | A5 | `test_the_refusal_carries_no_token_or_other_config` |
| T8 | A6 | `test_a_malformed_polling_section_widens_nothing` |
| T8 | A7 | `test_without_the_grant_nothing_is_read_or_answered` |
| T10 | R3.4, R4.2, R5.1 | `test_config_schema_parity.py`, `test_docs_parity.py`, `test_eventlog.py` |

## Verification environment

The repository checkout, `uv run --project cli`, no network. Slack is the existing
`FakeSlackClient` (`cli/tests/test_channels.py`, `test_channels_integration.py`); the
ledger is the injected `create_issue` / `post_comment` callables `process_kickoff`
already accepts. No credential is read: the bot token is a `monkeypatch.setenv` fixture
value and never appears in evidence.

## Evidence to capture

- `evidence/verification.md` — the commands of T1, T2, T8, T10, T12 with their pass/fail
  output (counts, not full logs), and the red-first note for the new suites.
- `evidence/security-review.md` — A1–A7, each with the test that closes it.
- Redaction: no tokens, no member ids beyond the `U…` fixtures, no repository names
  beyond the fixtures and the reporter's public list.

## Activities checklist

- [ ] Red first: `test_channels_kickoff.py` fails to import against `cd1ae94`.
- [ ] T1 unit suite green.
- [ ] T2 scenarios green, each with a Gherkin docstring (`testing.gherkinDocstrings: required`).
- [ ] T8 abuse cases green, one per A1–A7.
- [ ] T10 migration suites green, including both schema copies.
- [ ] T12 `make check` green.
- [ ] T13 security review recorded.

## Verification results

> Filled at the `verification` node.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
