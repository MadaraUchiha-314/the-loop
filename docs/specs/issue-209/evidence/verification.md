# Verification evidence — issue-209 (`GET /api/v1/sessions/transcript`)

Executed 2026-08-12 by the implementing session, per
[`../testing-plan.md`](../testing-plan.md). Every activity but T11 ran; T11 needs a
human, a workstation, tmux and a spawned Claude Code session (steps at the end).

## T1 / T8 — unit suite, security negatives

```console
$ uv run pytest -q cli/tests/test_core_sessions.py
...................................                                      [100%]
35 passed in 0.14s
```

15 new tests in the `-- transcript (issue-209)` section: tail windows (default /
explicit / `0` = whole file / beyond the file), per-character munge +
`CLAUDE_CONFIG_DIR` + home-default derivation, fallback directory scan,
malformed-line wrapping (non-JSON, non-object JSON, blank lines skipped), closed
session, PR endpoint (dispatched and not-yet-dispatched), and every refusal — no
session, cursor, crafted ids (`../../secret`, `..`, `a/b`, `a\b`, empty), symlink
escape, missing file naming the derived path, negative tail, malformed ref.

## T2 / T8 — integration scenarios (the route as served)

```console
$ uv run pytest -q cli/tests/test_transcript_integration.py
........                                                                 [100%]
8 passed in 1.29s
```

8 Gherkin-documented scenarios: served tail (real Claude Code line format), closed
session, no-session / cursor / missing-file 404s, traversal and symlink negatives
(the outside file's content asserted absent from the response), 400 malformed ref,
422 negative tail.

## T3 — contract parity

```console
$ uv run pytest -q cli/tests/test_api_contract_parity.py
.                                                                        [100%]
1 passed in 1.98s
```

`/api/v1/sessions/transcript` (`sessionTranscript`) present in both the authored
contract and the served schema.

## T12 / T14 — docs parity, lint, format, types, schema validation, full suite

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
194 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
uv run --project cli python -m pytest -q cli
1872 passed, 1 skipped in 70.82s (0:01:10)
```

Baseline before this work item: 1849 passed (issue-208's evidence); +23 new, none
removed. The one skip is pre-existing.

## T15 — UI suite and build

```console
$ cd ui && bun run lint && bun run typecheck && bun run test && bun run build
$ oxlint --type-aware
$ tsc --noEmit
 Test Files  4 passed (4)
      Tests  55 passed (55)
✓ built in 925ms
```

Baseline 52 tests; +3 (`transcriptTurns` projection: text/tool_use rows, string
content + tool-result labelling, malformed/unknown-shape degradation) and the
end-to-end trace test rewritten from "says it cannot read turns" to "renders the
turns, the tool invocations, the malformed row and the path caption" against the
demo transport.

## Derivation ground truth

The per-character munge was verified against a real Claude Code installation on
this machine before it was coded:

```console
$ ls ~/.claude/projects/
-home-user-the-loop
```

for a session whose cwd is `/home/user/the-loop` — one dash per munged character;
the run-collapsing variant the UI previously displayed is corrected to match
(R4.4).

## T11 — manual walk (deferred to a human)

1. On a workstation with the daemon: `the-loop sessions start` a work item (or let
   a webhook spawn one) and let the agent do a little work.
2. Open the dashboard, navigate to the work item: the **Trace · turns & tool
   calls** panel should render real turns, and the caption path should equal the
   `path` field of `GET /api/v1/sessions/transcript?ref=<ref>` on the service's
   machine.
3. `the-loop sessions close` the item and reload: the transcript should still be
   served (R1.4).
4. Register a `cursor` session for a scratch item: the panel should say the
   location is undocumented and fall back to the event trail.
