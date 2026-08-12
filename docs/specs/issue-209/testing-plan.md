---
type: testing-plan
phase: test-planning
workItem: issue-209
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: `GET /api/v1/sessions/transcript`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md),
> before [`tasks.md`](tasks.md). Authored at `test-planning`, completed at
> `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `get_transcript`: derivation (per-character munge, `CLAUDE_CONFIG_DIR` honoured), fallback scan, tail windows (default / explicit / 0 = whole file / longer than the file), malformed-line wrapping, closed-session and PR-endpoint resolution, every refusal (no session, cursor, bad id, missing file) | `uv run pytest -q cli/tests/test_core_sessions.py` |
| T2 | Integration (scenario) | yes | The route as served: 200 with entries/`totalLines`/`truncated` for a real registration + fixture JSONL; tail honoured; 404 no-session / cursor / missing-file; 400 malformed ref; 422 negative tail; closed session still served | `uv run pytest -q cli/tests/test_transcript_integration.py` |
| T3 | Contract (OpenAPI) | yes | The authored contract gains exactly `/api/v1/sessions/transcript` (`sessionTranscript`) and still equals the served schema (R3.1) | `uv run pytest -q cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — a live daemon + a real Claude session writing a real JSONL is T11's manual walk; every seam (registry, path, file, route) is covered in-process against a real-format fixture | | |
| T5 | UI / visual | n/a — the panel, tabs and caption shipped in issue-207; this fills the panel's body with rows using existing tokens, no layout change | | |
| T6 | Snapshot | n/a — no serialized artifact is produced | | |
| T7 | Performance / load | n/a beyond NFR3, which T1 proves structurally (bounded deque; the whole file is read only on explicit `tail: 0`) — no latency budget is at stake on a loopback admin plane | | |
| T8 | Security / abuse case | yes | One negative per § Security design mechanism: traversal id (`../`), `..` inside an id, a symlink inside the projects root pointing outside it, crafted `cwd` — all indistinguishable 404s, nothing outside the root ever opened | `uv run pytest -q cli/tests/test_transcript_integration.py cli/tests/test_core_sessions.py` |
| T9 | Accessibility | n/a in new work — rows reuse the trace panel's existing list semantics; no new interactive control is added | | |
| T10 | Migration / upgrade | n/a — no config key, schema or stored format changes; against an older service the UI's 404 fallback *is* the pre-change behaviour (R4.2) | | |
| T11 | Manual exploratory | yes | Against a live service with a spawned session: the panel shows real turns, the caption path matches the served `path`, a Cursor/absent session falls back with the reason | a human, a workstation with the daemon + a session |
| T12 | Docs parity | yes | Capability docs updated in-PR; no new event type, so the observability catalog is untouched | `uv run pytest -q cli/tests/test_docs_parity.py` |
| T13 | Schema validation | n/a — no schema is touched (NFR2) | | |
| T14 | Lint / format / types | yes | Repo gates, CI parity | `make lint format-check typecheck` |
| T15 | UI unit | yes | `transcriptTurns` projection (text/tool_use/tool_result/malformed/unknown shapes); `transcriptPath` per-character munge; the panel renders rows on success and the reason + event trail on 404; demo transport answers from the fixture | `bun run test` in `ui/` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | entries parsed per line; a non-JSON line comes back as `{"malformed": …}` in place |
| T1 | R1.2 | derived path honours `CLAUDE_CONFIG_DIR`; per-character munge; fallback scan finds a differently-munged directory |
| T1 | R1.3, abuse 4 | default tail 200; explicit tail; `tail: 0` = whole file; tail ≥ file = untruncated |
| T1 | R1.4 | a closed session's transcript resolves |
| T1 | R2.2–R2.5 | each refusal is a `LookupError` with its stated guidance |
| T2 | R1.1–R1.3, R3.1 | `Scenario: the trace of a registered session is served with its tail` |
| T2 | R1.4 | `Scenario: a closed session's transcript is still served` |
| T2 | R2.3 | `Scenario: a work item with no session has no transcript to serve` |
| T2 | R2.4 | `Scenario: a Cursor session's transcript location is not guessed at` |
| T2 | R2.5 | `Scenario: a session that has not written a transcript yet is a 404 naming the path` |
| T2/T8 | R2.1, R2.2, abuse 1 | `Scenario: a crafted session id cannot walk the read outside the projects root` (+ symlink variant) |
| T3 | R3.1 | contract parity over the new path |
| T15 | R4.1–R4.4 | live panel rows; 404 fallback keeps the event trail; stale copy gone; munge parity |
| T11 | all | the full loop, by hand |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none for T1–T3, T8, T12, T14 — `TestClient` drives the
  app in-process; the projects tree is a `tmp_path` fixture reached via
  `CLAUDE_CONFIG_DIR`. T15 needs bun. T11 needs a workstation with the daemon and a
  spawned Claude Code session (a human's).
- **Fixtures & data:** JSONL fixtures written inline per test, in the real Claude
  Code line format (type/message/content blocks) so the same fixture drives the UI
  projection tests.
- **Credentials:** none.

## Evidence to capture

`evidence/verification.md`: per-activity command + outcome, full suite tail,
lint/type output, UI test + build output. No screenshots — the UI change fills an
existing panel and T15 asserts the behaviour; T11 is deferred to the reviewer's
workstation and said so honestly.

## Activities checklist (ticked at `verification`, with results)

- [x] T1 unit suite green — 1872 passed, 1 skipped (baseline 1849, +23 new); see
      [`evidence/verification.md`](evidence/verification.md)
- [x] T2 integration scenarios green, Gherkin docstrings present
      (`test_transcript_integration.py`, 8 scenarios)
- [x] T3 contract parity green (`/api/v1/sessions/transcript` in both contract and
      served schema)
- [x] T8 negative tests green (traversal, symlink escape, crafted registration —
      indistinguishable 404s)
- [x] T12 docs parity green
- [x] T14 lint / format / typecheck / markdownlint clean
- [x] T15 UI suite green — 55 passed (baseline 52), incl. projection, munge-parity
      and live-panel tests; `bun run lint`, `typecheck` and `build` clean
- [ ] T11 manual walk — deferred to a human with a workstation; the one activity
      this plan cannot run itself (steps in
      [`evidence/verification.md`](evidence/verification.md))

## Verification results

Executed 2026-08-12 by the implementing session. Everything but T11 ran and passed;
full command output in [`evidence/verification.md`](evidence/verification.md). The
same honesty note as issue-208 on TDD: tests were written alongside the
implementation in one pass, red→green observed per-assertion while iterating rather
than as a committed red state.
