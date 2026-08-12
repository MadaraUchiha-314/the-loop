# Verification evidence — issue-208

> Captured 2026-08-12, in the cloud session that implemented the work item.
> Each section is one activity of [`testing-plan.md`](../testing-plan.md)'s checklist,
> with the command run and the tail of its output.

## T1/T2/T8 — unit + integration suites (full run)

```bash
uv run pytest cli/tests -q
```

```text
1849 passed, 1 skipped in 79.65s (0:01:19)
```

Baseline before this work item: 1819 passed, 1 skipped — the 30 new tests are the
ask/reply unit tests (`test_core_sessions.py`, `test_comments.py`,
`test_core_attention.py`) and the Gherkin-documented scenarios in
`test_ask_reply_integration.py`.

## T3 — contract parity

Covered by the full run above (`test_api_contract_parity.py` passes with
`/api/v1/sessions/reply` / `replySession` present in both the authored contract and the
served schema).

## T12 — docs parity

Covered by the full run above (`test_docs_parity.py`), plus
`test_every_emitted_event_type_is_documented` in `test_eventlog.py`, which pins both new
event types to entries in `EVENT_TYPES`.

## T14 — lint / format / types / schema validation

```bash
make lint format-check typecheck validate
```

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
193 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
```

## T15 — UI unit tests and build

```bash
cd ui && bun run test && bun run lint && bun run typecheck && bun run build
```

```text
Test Files  4 passed (4)
     Tests  52 passed (52)
$ oxlint --type-aware        (clean)
$ tsc --noEmit               (clean)
dist/assets/index-DNVg-1pt.js   243.04 kB │ gzip: 76.04 kB
✓ built in 1.23s
```

The suite includes the new send-flow test (type a reply → POST → the card closes on
refresh) and the two inbox-dedupe tests over the `awaiting-input` attention kind.

## T11 — manual walk (deferred)

Not run: it needs a workstation with tmux, `gh` and a spawned session, which this cloud
session is not. The activity is left unticked in the plan, honestly, and is the one
thing for a reviewer to exercise before merge:

1. `the-loop ask --work-item <ref> --question 'ping?'` from inside a spawned session —
   the marked comment appears on the ticket, `the-loop events --type 'session.awaiting*'`
   shows the event, the dashboard card lights up.
2. Reply from the dashboard (or
   `curl -X POST …/api/v1/sessions/reply -d '{"ref":"…","text":"pong"}'`) — the text
   lands in the pane, the card closes, the marked delivery report appears on the ticket
   and is **not** forwarded back into the session on the next poll cycle.
