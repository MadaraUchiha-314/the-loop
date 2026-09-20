---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#397"
status: approved             # draft | in-review | approved
approvedBy: ["the-loop"]     # tier-2 polish: autonomous-complete per the skill's risk tiers; the acceptance is the ticket's own, copied verbatim
collaborators: [engineer]
overrides: {}
riskTier: 2                  # three small behaviour changes on the Slack surface; no sensitive path, no grant, scope, schema or state change
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: minor Slack polish — room-declaration confirmation, ephemeral help, connector signature

> Phase 1 of 4 (requirements → design → testing plan → tasks). A tier-2 work item:
> the four files are short and locked together, and the loop completes on its own
> after the review loop. Source:
> [`docs/reports/followups/minor-observations-o1-o4-o5.md`](../../reports/followups/minor-observations-o1-o4-o5.md),
> filed as [issue-397](https://github.com/MadaraUchiha-314/the-loop/issues/397).

## Introduction

Three observations from the 2026-09-19 e2e Slack test that issue-393 left alone. Each
is a few lines; together they make the room a touch more conversational and the
grammar reachable by a caller that is not a person at a keyboard.

| Obs. | Today | Consequence |
|---|---|---|
| **O1** | `add-channel` is acknowledged on the ticket (🎉); the **room** hears nothing until the item's first update | The person who declared the room from the ticket gets no confirmation where they will be working |
| **O4** | `help` answers with `chat.postEphemeral` | Invisible to any integration acting on a person's behalf (the MCP connector the test drove) |
| **O5** | A connector signs every message with a second line, "*Sent using* @Claude" | None today: the grammar reads the first token of the first line. Recorded so the property stays pinned |

## Requirements

### R1 — a room hears about its declaration (O1)

**User story:** As an authorized user declaring a room from the ticket or the
terminal, I want the room itself to say it is now the work item's conversation, so
that I know the declaration took without waiting for the item to start.

#### Acceptance criteria (EARS)

1. WHEN a *new* declaration of a room is recorded (`the-loop add-channel`, from a
   ticket comment or the CLI) THEN the system SHALL open the work item's
   conversation in that room at once — the same idempotent open the spawn path
   makes — so the room's "every update about … is posted in this channel" message
   appears at the declaration, not at the first update.
2. IF the room is already the work item's conversation (re-declaring it, or a
   declaration made after the item started there) THEN nothing SHALL be posted.
3. IF the confirmation cannot be posted (no token, a workspace down, an opener that
   raises) THEN the declaration SHALL stand and be acknowledged exactly as before;
   the failure is a log line (and, from the CLI, an `err` message), never an error.
4. `remove-channel` and an `already-declared` outcome SHALL open nothing.

### R2 — `help` can reach a non-human caller (O4)

**User story:** As an integration (or a person watching a thread) I want a visible
form of `help`, so that the grammar is readable by whoever reads the thread and not
only by the member who typed it.

#### Acceptance criteria (EARS)

1. WHEN a member mentions the bot with `help public` THEN the system SHALL post the
   grammar as an **ordinary message** in the thread (or room, top-level) the member
   asked in, and SHALL post no ephemeral.
2. WHEN a member mentions the bot with plain `help` THEN the answer SHALL stay
   ephemeral, as issue-389 R3.2 specifies.
3. The ephemeral `help` text SHALL name `help public` so the visible form is
   discoverable.
4. Neither form SHALL record anything on the ledger or deliver anything to a
   session.
5. The slash command's `/the-loop help` SHALL stay ephemeral: its answer travels
   through Slack's `response_url`, a per-invoker receipt by Slack's own contract;
   this is documented, not changed.

### R3 — the connector signature stays harmless (O5)

**User story:** As an operator driving the-loop through a connector that signs its
messages, I want the signature never to change what my first line meant.

#### Acceptance criteria (EARS)

1. WHEN a verb is followed by a second line THEN the system SHALL read the verb, and
   any word that modifies it (`public`), from the **first line only**.
2. A test SHALL pin that a message reading `help` + newline + `*Sent using* @Claude`
   is plain, ephemeral `help`, and that `help public` + the same line is the visible
   form.

## Non-functional requirements

- **No new call on the hot path.** R1 adds one bus open per *new* declaration — a rare,
  human-initiated event; nothing changes per message.
- **Observability.** The existing `channel.thread_opened` / `channel.open_failed`
  events record the confirmation and its failure; no new event type.

## Security considerations

- **Actors & trust:** the declaring user is already inside the trust boundary (the
  named-and-allowlisted check every control command passes); `help` is answered to
  authorized users and collaborators as before. Slack message text stays untrusted
  data: `public` is matched as one lower-cased token and never echoed.
- **New attack surface:** none. R1 posts a message the-loop already posts, in a room
  an authorized user declared, with no text from the comment. R2 posts the fixed
  `help_text` as a visible message where the member asked; it discloses only what the
  ephemeral already disclosed to the same member — the grammar and this channel's
  grant list, nothing about other work items. `help public` in a room the member may
  not speak in is refused above this branch by the unchanged speaker check.
- **Abuse cases:** (1) an unauthorized member types `help public` → dropped by the
  existing authorization, no post; (2) a connector's signature line carries `public`
  → not read (R3.1). Both pinned by tests.
- **Secrets / data:** none touched; nothing new is logged.

## Out of scope

- A slash-command `in_channel` answer (R2.5): the observation was the mention path,
  and the responder seam is shared by every slash answer.
- Any change to the room message's wording (issue-393's voice work owns it).
