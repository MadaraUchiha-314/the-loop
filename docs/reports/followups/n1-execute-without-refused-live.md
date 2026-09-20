# bug: `execute without <phase>` is refused live for names the checklist offers (F1 regression)

From [`docs/reports/e2e-slack-test-2026-09-20.md`](../e2e-slack-test-2026-09-20.md) (N1),
the live validation run of the issue-393 fixes on the-loop 19.7.0.

## Seen

In a declared room, mention-addressed `execute without capability-docs` and
`execute without design-critic-review` — both rows of the live phase checklist, one
ticked and one optional — were each refused: ⚠️ reaction,
`channel.dropped reason=unskippable-phase`, and the explanation posted only as an
ephemeral, which a connector (and anyone reading later) cannot see. A plain
`execute` then worked.

## What the repro rules out

On the daemon's own host, with the daemon's installed 19.7.0 and the live config,
every component passes in isolation:

- `_selection_checklist` reads the live checklist (3,926 chars) through the same
  integration the gate uses;
- `selection_rows` parses all 17 rows, `rows.always` empty;
- `without_clause` extracts the item — the connector's appended "*Sent using*"
  second line does not interfere;
- `apply_without` composes with an **empty refusal** for both names;
- `strip_mention` + `parse_command` on the exact inbound text: a bare
  `execute …` after mention-strip parses to **no** control command in isolation,
  yet the live listener clearly reached the grammar (the drop reason is the
  grammar's) — the inbound normalization differs from what the components see in
  isolation. That gap is where the bug lives.

## Impact

F1's typed fallback — the only phase-shaping gesture a connector or phone-first
operator has, since they cannot tick Block Kit checkboxes — does not work at all.
Fail-closed (nothing was wrongly frozen), but the person gets a ⚠️ and no visible
reason.

## Root cause (found on the 2026-09-20 follow-up)

The refusal came from `_selection_grammar` hitting the **checklist-unreadable**
branch (`_selection_checklist` returned `""`), not from `apply_without` rejecting
the phase name — the names were valid, as the isolation repro confirms. This
happens transiently: a `list-comments` read of the ticket right after the item
starts can miss the just-posted checklist. The bug was that this transient,
retriable failure was recorded and reacted to **identically** to a genuine
rejected-phase-name error — both dropped as `unskippable-phase` with the `error`
reaction — so the operator was told their phase name was rejected when it was not.

## Fix (branch `fix/n1-selection-grammar-refusal-reason`)

`_selection_grammar` now returns the drop **reason** alongside the refusal, and
the caller records it: a checklist that could not be read drops as
`checklist-unreadable` (transient, retriable), while a name the checklist does
not offer stays `unskippable-phase` (permanent user error). The ephemeral text
already told the two apart ("Could not read the phase checklist…" vs "`x` is not
a phase…"); now the event log does too, which is the only trail on a deployment
whose process log goes to `/dev/null`.

## Remaining (not in this fix)

1. Mirror the refusal onto the ticket the way the B2 fix does for
   `control.rejected` — the ephemeral is invisible to any integration.
2. The deeper connector problem (N3): the Slack MCP connector cannot produce a
   real mention, so the room must be reached with raw `<@BOT_ID>` markup or
   declared `--listen all`. Not a the-loop bug.
