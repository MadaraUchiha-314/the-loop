# bug: `execute without <phase>` refuses every argument — the clause reads past the phase list

From [`docs/reports/e2e-slack-test-2026-09-20-run-3.md`](../e2e-slack-test-2026-09-20-run-3.md)
(P1), the live validation run of the PR #402 fixes on the-loop 19.8.3.

## Seen

`execute without capability-docs` and `execute without 14` — a name the live checklist
offers and the numeric form the refusal itself suggests — were both refused with the
identical text: *"that name is not a phase this checklist offers … 14. `capability-docs`
…"*. `channel.dropped reason=unskippable-phase`. 0 for 4 across runs 2–3.

## Root cause

`without_clause` read **everything to the end of the line** after `without` as phase
names, and `apply_without` refuses the reply on the first item that is not an offered
phase. A word that is not token-shaped is named *"that name"* — which is what the
operator saw for both a valid name and a valid number, so the list carried more than the
phase, and the extra was not a word. The live message did not end where the operator's
list ended: a connector signature (`*Sent using* @Claude`, issue-397 O5) or markup on
the command's line. Every other reader (`execute`, `start`, `approved`, `help`) matches a
keyword or the first token only, so nothing else was affected; the run-2 isolation repro
put the signature on a second line, which `[^\n]*` never reaches.

## Fixed (issue-405)

- `verbs.strip_signature` drops a connector signature wherever it sits; `without_clause`
  runs it first and cleans each item of Slack markup (`*5*` → `5`) and invisible format
  characters.
- A word that is still not a name refuses the reply **by position** ("word 2 after
  `without` reads as markup, a mention or prose"), never echoed.
- `apply_without` returns the refusal's family — `unknown-phase` | `unskippable-phase` |
  `empty-clause` — and the pipeline records it; `checklist-unreadable` stays the fourth.
- The exact text handed to the grammar and the items it read are logged at `info`, and
  the `channel.dropped` record carries `read` (a non-token item as its length only).
