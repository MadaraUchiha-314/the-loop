---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#405"
---

# Documentation: the clause reader stops at the phases; the close path waits for the endgame (issue-405)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/channels.md` | the typed-grammar bullet: the clause is read after a connector's signature is dropped and each word cleaned of markup and format characters; a non-name refuses by position; the four drop families and `read`; the grammar's input logged | issue-405 row added |
| `docs/capabilities/interactive-sessions.md` | a new bullet ahead of the close rules: a closure reaching a live session at its terminal node is held (`session.closing`), ended by the completion claim or `finishGraceSeconds`, cancelled by a reopen; `session.autoclosed merged` semantics | issue-405 row added |
| `docs/capabilities/webhook-triggers.md` | the autoclose bullet: `merged` from the recorded pull requests, the hold and where it is specified | issue-405 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/routing-options.md` | new `tmux.finishGraceSeconds` section after `tmux.harnessKillGraceSeconds` |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the `finishGraceSeconds` key, identical in both copies (parity test) |
| `commands/finish-tasks.md` | the endgame order: post the completion summary first and promptly, claim `the-loop graph complete <id>`, then close the ticket if still open; why (the hold, the merge's `Closes #N`) |
| `skills/the-loop/SKILL.md` | the merge-on-approval bullet: the merge races the endgame; summary then claim, at once, nothing between; a ticket the merge closed is expected |
| `cli/the_loop/eventlog.py` | the catalogue: `channel.dropped`'s four selection reasons and `read`; `session.autoclosed`'s `merged`/`waited_seconds`/`finished`; `session.closing`, `session.closing_cancelled` |
| `docs/reports/e2e-slack-test-2026-09-20-run-3.md` | **new** — the run-3 report (#404's deliverable), redacted, with a "Fixes applied after this run" section |
| `docs/reports/index.md` | the end-to-end Slack test series (three runs) indexed, as #404 asked |
| `docs/reports/followups/README.md`, `p1-execute-without-reads-past-the-phase-list.md`, `p2-close-path-races-the-endgame.md` | the run-3 table and the two per-item notes |
| `README.md` | no change: it names neither the typed grammar's internals nor the close path's timing |
