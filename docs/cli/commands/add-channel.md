# `add-channel`

Give one work item a room of its own.

```bash
the-loop add-channel slack@#tmp-issue-375 --work-item github:OWNER/REPO#375
the-loop add-channel slack@C0TMP375 --work-item github:OWNER/REPO#375
the-loop add-channel slack://C0TMP375 --work-item github:OWNER/REPO#375 --no-comment
```

## What it does

`channels.slack.channel` is the operator's **one** channel: every work item this
deployment touches gets a thread in it, and anyone who wants to follow one work item
has to follow all of them. That is the wrong shape for the work item people spin a
channel up for — the migration with six stakeholders, the incident with a `#tmp-…`
room ([issue-375](https://github.com/MadaraUchiha-314/the-loop/issues/375)).

This declares a **collaboration channel** on one work item. Two things follow, and
only these two:

1. **The conversation lives there.** The work item's thread root is opened in the
   declared channel instead of the central one, so every update the-loop posts about
   it lands in the room the people are in. If its conversation had already started
   elsewhere, the next update opens a root in the new room and leaves a pointer in
   the old thread.
2. **Every message there is about that work item.** A top-level message in the room
   is a reply *on the work item* — not a new issue — and so is a message in a thread
   the-loop did not open. A dedicated room has one subject.

**It grants nobody anything.** Who may speak is still `channels.slack`'s principals
allow-list; who may direct the loop is still `routing.authorizedUsers`; who may be
input on one work item is still the
[collaborator roster](/cli/commands/add-collaborator). A channel is a place, not a
person — so the order of "declare the room" and "invite the people" never matters.

Three effects, in this order:

1. **Resolves a name to an id, then writes the declaration** into the work item's
   portable record (`<state.root>/portable/<slug>.json`, `collaborationChannels`
   section), with who declared it, when, and through which surface. The record
   stores the **id** — what the ingress routes on — and keeps the name beside it
   for display.
2. **Posts the same keyword** — `the-loop add-channel slack@C0TMP375` — back on the
   work item, carrying the loop-prevention marker, so the thread reads identically
   whether the declaration came from the terminal or from a comment. Best-effort: a
   failing `gh` is reported and the declaration stands.
3. **Records `control.command`** with the work item, the channel, the actor and the
   effect (`declared` / `already-declared`), plus the channel it replaced if any.

## The grammar

`<type>@<target>`, and `<type>://<target>` for the same thing; what is stored and
printed is always the first form.

| Type | Target | Notes |
|------|--------|-------|
| `slack` | the channel's **name** (`#tmp-issue-375`, or bare) or its conversation id (`C…` public, `G…` private, `D…` a DM) | A name is resolved to an id **when you declare it**, and the id is what is stored — so a later rename changes nothing. Resolving needs the app's `channels:read` / `groups:read` scopes and the bot to be able to see the channel; a name that resolves to neither is refused rather than stored. An id needs no scope and no lookup. |

A type the-loop has no adapter for is refused at declaration time rather than stored
and silently ignored. Adding one later — Jira, WhatsApp — is a row in the type table
plus an adapter, not a new grammar.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `TYPE@TARGET …` | required | One or more channels, e.g. `slack@C0TMP375`. |
| `--work-item` | required | The work item the channel is declared on, e.g. `github:OWNER/REPO#375`. |
| `--listen` | `mentions` | What the room hears: `mentions` (only messages carrying `@the-loop`) or `all` (every message, as a room did before [issue-389](https://github.com/MadaraUchiha-314/the-loop/issues/389)). Recorded on the declaration; a re-declaration replaces it. |
| `--portable-dir` | `<state.root>/portable` | Where the declarations live. |
| `--comment` / `--no-comment` | on | Post the keyword back to the work item. |

## Exit codes

| Code | When |
|------|------|
| `0` | at least one channel was newly declared |
| `1` | nothing changed — every channel named was already declared |
| `2` | a malformed ref, an unknown type, a name that resolves to no channel this bot can see, a work-item ref that will not parse, or a channel another work item holds: **nothing** was written and nothing posted |

## Notes

- **All or nothing.** Every ref is validated **and resolved** before any of them is
  written, so a second channel the bot cannot see leaves the first unapplied.
- **One channel per type per work item.** Declaring a second Slack channel *moves*
  the conversation rather than adding one; the output names what it replaced.
- **One work item per channel.** A channel another work item declares is refused —
  attributing a room's messages must not be a guess. Undeclare it there first.
- A declaration is **scoped to the work item's active life**: cleared when the item
  closes, and `the-loop sessions reset` forgets it. `the-loop cleanup` keeps it, as
  it keeps the control record.
- **Poll mode reads less than Socket Mode.** `conversations.history` returns
  top-level messages, so a reply inside a thread the-loop did not open is seen only
  under `channels.slack.read.mode: socket`. The room is baselined on first sight, so
  declaring a channel never replays its backlog.
- The same declaration can be made from the ticket, by an authorized user commenting
  `the-loop add-channel slack@C0TMP375`. The keyword is configurable at
  `routing.control.keywords.add-channel`; setting it to `""` disables the word.
- Runs **in-process**, not through the control-plane service — deliberately, like
  [`ask`](/cli/commands/ask) and
  [`add-collaborator`](/cli/commands/add-collaborator).
- Authorization on this path is shell access to the machine running the-loop. The
  stricter test — a named login in `routing.authorizedUsers` — is the comment path's,
  because that is where an untrusted author can reach.
