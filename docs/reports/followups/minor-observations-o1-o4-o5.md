# Minor Slack polish: room-declaration confirmation, ephemeral help, connector signature

**Kind:** polish · **Source:** e2e Slack test 2026-09-19 (O1, O4, O5) · **Not fixed in issue-393**

Three small observations from the e2e test, grouped because each is a few lines of
work. Split into separate issues if any is picked up on its own.

## O1 — declaring a room is silent until the item starts

`add-channel` was accepted on the ticket (🎉) but the **room** heard nothing until
`the-loop start`, when the "Every update about … is posted in this channel"
message appeared. A person who declared the room from the ticket gets no
confirmation in the room itself that it is now the conversation.

*Suggestion:* post the room-opened confirmation when the room is **declared**, not
only on the first update — or a one-line "this room is now #<id>'s conversation;
updates start when it does."

## O4 — the `help` answer is ephemeral

`help` replies ephemerally, so it is invisible to any integration acting on a
person's behalf (including the MCP connector the test drove). Fine for a human at
a keyboard; worth knowing, and worth a non-ephemeral option for automated callers.

## O5 — the Slack connector appends "*Sent using* @Claude"

The connector adds a "*Sent using* @Claude" second line to every message. the-loop's
keyword parser reads the **first line only**, so this never interfered — recorded
for completeness. **Likely no action needed**; keep only if the parser ever grows
to read beyond the first line.

## Acceptance

- O1: a room gets a confirmation when it is declared, not only when the item starts.
- O4: `help` can reach a non-human caller (a non-ephemeral form, or documented).
- O5: no action unless the keyword parser starts reading past the first line.
