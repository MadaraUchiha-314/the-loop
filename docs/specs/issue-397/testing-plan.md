---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#397"
status: approved
approvedBy: ["the-loop"]     # locked with design.md; tier 2
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: minor Slack polish — room-declaration confirmation, ephemeral help, connector signature

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Planned at `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `wants_public_help`: the token, its case, its position, the first-line-only rule with the connector's signature (R2.1, R3.1, R3.2) | `cd cli && uv run pytest tests/test_channels_verbs.py` |
| T2 | Integration (scenario, Gherkin-docstringed) | yes | dispatcher: a new declaration calls the opener once, a repeat and a removal do not, a raising opener leaves the declaration and 🎉 intact (R1.1–R1.4); CLI: a declaration opens through the bus only with a `channels` section and reports a failed open (R1.1, R1.3); mentions: `help public` is a visible reply with no ephemeral, plain `help` + signature line stays ephemeral, nothing recorded or delivered (R2.1, R2.2, R2.4, R3.2) | `cd cli && uv run pytest tests/test_workchannels_integration.py tests/test_workchannels_cli.py tests/test_channels_mentions_integration.py` |
| T3 | Contract (OpenAPI) | n/a — no control-plane API change | | |
| T4 | End-to-end (live) | no — the change reuses the room-open and reply paths issue-393's live run exercised; nothing new talks to Slack | | |
| T5 | UI / visual | n/a — no rendered artifact changes | | |
| T6 | Snapshot | n/a — the one text change (`help_text`) is asserted directly in T2 | | |
| T7 | Performance / load | n/a — one open per new declaration, off the per-message path | | |
| T8 | Security / abuse case | yes | the unauthorized-actor drop already covers `help public` (unchanged branch, pinned by issue-389's `test_channels_mentions_security.py`); the signature-line case is T1/T2 | with T1/T2 |
| T9 | Accessibility | n/a | | |
| T10 | Migration / upgrade | n/a — no key, state or schema change | | |
| T11 | Manual exploratory | no — deferred to the next live Slack run, where O1/O4 are observed for free | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.1, R3.1, R3.2 | `help public`, `HELP PUBLIC please`, `help me public` (no), a non-help verb (no), `help\n*Sent using* @Claude` (no), `help public\n*Sent using* @Claude` (yes), `help\npublic` (no) |
| T2 | R1.1, R1.2, R1.4 | a declaration from the ticket calls the opener once with the work item; re-declaring and removing call it no more |
| T2 | R1.3 | an opener that raises: declaration recorded, 🎉 reaction, no error |
| T2 | R1.1, R1.3 | CLI: bus open called once with the config, a failed `PostResult` becomes an `err` line, declaration stands; no `channels` section ⇒ no open |
| T2 | R2.1, R2.4 | `@bot help public` in a thread → one `chat.postMessage` in that thread carrying the grammar and the words `help public`, no ephemeral, nothing recorded/delivered |
| T2 | R2.2, R3.2 | `@bot help` + signature line → ephemeral only |
| T8 | abuse 1 | unauthorized member's `help` variants dropped (existing test) |

## Results (verification)

Recorded in [`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command | Outcome | Artifact |
|---|---|---|---|
| T1 + T2 (touched files) | `cd cli && uv run pytest -q tests/test_workchannels_integration.py tests/test_channels_mentions_integration.py tests/test_channels_verbs.py tests/test_workchannels_cli.py` | pass — 73 passed | `evidence/automated-tests.md` |
| full suite | `cd cli && uv run pytest -q` | pass — 4282 passed, 1 skipped | `evidence/automated-tests.md` |
| lint / format / typecheck | `uv run ruff check cli hooks && uv run ruff format --check cli hooks && uv run pyright cli` | pass | `evidence/automated-tests.md` |
| T8 | `cd cli && uv run pytest -q tests/test_channels_mentions_security.py` | pass (in the full suite) | `evidence/automated-tests.md` |
