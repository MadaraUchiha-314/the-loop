---
type: brainstorm
phase: brainstorming
workItem: issue-389
status: draft                # no gate approves a brainstorm (issue-281); it converges on the thread
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Brainstorm: a room that talks to the-loop only when it is addressed

> Phase 0, the root artifact for
> [issue #389](https://github.com/MadaraUchiha-314/the-loop/issues/389): a multi-party
> collaboration experience when a Slack channel is dedicated to a work item. Nothing here
> is a commitment; the direction converges on the ticket.

## Problem / opportunity

A dedicated room today is a firehose in both directions. Since
[issue-375](https://github.com/MadaraUchiha-314/the-loop/issues/375) and
[issue-378](https://github.com/MadaraUchiha-314/the-loop/issues/378) an authorized user
can declare `the-loop add-channel slack@#tmp-issue-389`, and from then on **every message
an authorized member types in that room is a message on the work item**: mirrored onto
the ticket as a marked comment and typed into the session's pane. That was the right
first step (a room never opens a second issue, and nothing said there is lost), and it
is the wrong steady state for a room with six people in it. Most of what they say is to
each other. The agent is interrupted by all of it, the ticket fills with it, and anyone
not on `routing.authorizedUsers` is dropped in silence, so the stakeholders the room
exists for cannot address the-loop at all.

The ticket names the two acts people actually want from the loop in a room, and neither
exists today:

| People want to say | What the-loop offers today |
|---|---|
| "this thread is context for the work" | nothing; the thread is either firehosed in message by message (authorized members) or invisible (everyone else) |
| "we decided X" (product, design, tech) | nothing outside a phase gate; a decision typed mid-flight is one more `work-item.reply` and lands nowhere a later reader looks |
| address the-loop at all | `/the-loop`, which has no thread and reads as an operator command, not a conversation |

The opportunity is a third shape of conversation. The central channel's threads
(the-loop opened them, so every reply is addressed to it) and the operator's DM stay as
they are. A **room** listens only when it is addressed, and what it is asked for is a
small set of acts each with a durable record.

## Context & constraints

Five things fix the shape of every option below.

1. **Through the ledger, never around it**
   ([decision-103](../../decisions/decision-103.md)). Whatever a mention becomes is a
   ledger record first: an event type from the one catalog (`channels/events.py`),
   granted per channel in `channels.slack.publish`, recorded on the ticket with an
   envelope naming the person, and only then delivered. A new act is a new catalog row,
   not a new path.
2. **No model in the channel** ([decision-118](../../decisions/decision-118.md)). The
   pipeline classifies by grammar: control keyword → open gate → reply. The session is
   the only model in the system. So an act a room asks for is either a fixed grammar
   the channel parses, or free text handed to a session that may not be running.
3. **A session is not always there.** An armed work item parks at `phase-selection`
   with no session ([issue-358](https://github.com/MadaraUchiha-314/the-loop/issues/358));
   a machine can be lost ([issue-363](https://github.com/MadaraUchiha-314/the-loop/issues/363));
   the window is cleared at every phase boundary (`reference/context.md`). A pane
   delivery is ephemeral; the ledger record is the copy that survives, and a file under
   `docs/specs/<id>/` is the copy the next session reads.
4. **Who may speak is decided once, and narrowly.** `routing.authorizedUsers` (GitHub
   login plus Slack id) may command, answer gates and reply. A work-item collaborator
   ([issue-307](https://github.com/MadaraUchiha-314/the-loop/issues/307)) is a GitHub
   login granted *input* on one item, with no Slack id. A room has people who are
   neither, and the security posture is that an unlisted member is dropped in silence
   and never told what exists ([issue-341](https://github.com/MadaraUchiha-314/the-loop/issues/341)).
5. **What Slack can deliver over the connection the-loop already holds.** Socket Mode
   with interactivity on, both transports reading `message.channels` / `message.groups`
   whose text carries a mention as `<@U0BOT>` (the bot's own id is already read via
   `auth.test`). Available with a manifest change: the `app_mention` event
   (`app_mentions:read`), **message shortcuts** (the ⋯ menu on any message, a
   `message_action` payload carrying the message, its channel, its `thread_ts` and a
   `trigger_id`), **modals** (`views.open` on that trigger, `view_submission` back),
   reaction events (`reactions:read`), and `chat.getPermalink`. Thread history is
   already read with `conversations.replies`. Verify each against Slack's docs at
   requirements time; they move.

Two existing shapes are the nearest prior art and are reused rather than reinvented:
a button is exactly the typed keyword ([decision-117](../../decisions/decision-117.md)),
so a shortcut can be exactly the typed mention; and the phase gates already append a
human's feedback into the artifact it concerns (`record-feedback`), so a decision has a
place to be folded into.

Adjacent, and out of scope here: the noise in the *other* direction (every subscribed
event as a top-level message in the room) is a rendering question for the room, not an
addressing one, and Slack's "Agents & AI Apps" split-pane surface is a different
conversation shape from a shared room.

## Ideas & options

Five questions, each with its options. The lean per question is in the working
hypothesis.

### Q1. When does a room reach the-loop?

- **Option 1A: every message** (today). *Struck by the ticket.*
- **Option 1B: only when addressed.** A message enters the pipeline only if its text
  mentions the bot (`<@U0BOT>`); everything else is dropped as `not-addressed`, silently
  and with no reaction, because the message was not for the-loop. Works on both
  transports with no new scope, since the mention is in the text either way.
  *Cost:* a reply under one of the-loop's own room messages (an approval request, a
  question) would also need the mention unless exempted. Lean: exempt it. A thread
  the-loop started is addressed to it by construction, which is the same rule the
  central channel already lives by.
- **Option 1C: a per-room switch** (`the-loop add-channel slack@#room --listen
  mentions|all`). *Deferred:* a knob for a case nobody has asked for yet. If a room ever
  wants the firehose back, this is one flag on the existing declaration.
- **Option 1D: the `app_mention` event instead of text matching.** *Struck:* Slack
  delivers the same message twice (`message.*` and `app_mention`), costs a scope, and
  buys nothing the text does not already say.

### Q2. What can a mention ask for?

- **Option 2A: a small fixed grammar after the mention, with a fallthrough.**
  `@the-loop context` (in a thread: this thread; top-level: this message);
  `@the-loop decision <text>`; `@the-loop <control keyword>` (`start`, `execute`, …,
  the keywords a thread already accepts); and **anything else is a reply** to the
  session, exactly today's `work-item.reply`, so `@the-loop what is blocking you?`
  still reaches the agent. No model, works in poll mode, no manifest change.
  *Cost:* a vocabulary to learn, mitigated by an ephemeral `help` reply on an
  unrecognised verb.
- **Option 2B: message shortcuts and a modal.** *Add as context* and *Record a decision*
  in the ⋯ menu of any message. The context shortcut acts at once; the decision shortcut
  opens a modal (kind: product / design / tech; a one-line summary pre-filled from the
  message; rationale; the thread as the discussion link). Each is **exactly the typed
  mention** entering the same pipeline, so it adds no authority. Socket-only, like the
  buttons, and `channels status` says so.
  *Cost:* manifest change (`features.shortcuts`), two new interactive payload types in
  the listener, the modal round-trip, a `trigger_id` that expires in three seconds.
- **Option 2C: free text only, the session decides.** The mention is delivered whole
  and the agent works out whether it was context, a decision or a question. *Struck as
  the only path:* the record then depends on an agent that may not be running, and the
  no-model rule in the channel was chosen deliberately. It survives as 2A's
  fallthrough.
- **Option 2D: reactions as verbs** (📌 for context). *Deferred for context, struck for
  decisions:* a reaction carries the member's id, so it can be authorized, but a
  decision recorded by emoji has no text and no rationale, and a pin nobody sees is a
  weak act. Revisit for context only if the grammar proves too much typing.

### Q3. What is "context", and where does it live?

- **What is captured.** The thread the mention sits in, as a **snapshot**: every
  message so far, author resolved through the directory (`<@U…>` drawn as a name),
  time, the permalink, and who asked. A second `context` on the same thread appends
  only what is new. Following a thread after the snapshot ("subscribe") is a different
  act and is not proposed.
- **Option 3A: a ledger record only.** A `context.added` row in the catalog, recorded
  as a marked, quoted, scrubbed comment on the ticket (broadcasts neutralised, markers
  defanged, the same scrub a reply mirror gets), delivered into the session when one
  is running. *Cost:* a session spawned later must read the ticket to find it. The
  skill already says the ticket is read at the start of a work item, and the gates
  re-read the thread.
- **Option 3B: the record plus a file the session keeps.** Same record; the
  operating-model rule then says a session that receives or reads a `context.added`
  record references it from the current phase's artifact (a `## Context` list of
  permalinks and one-line gists, not a copy), the same delta/state split capability
  docs use. *Lean.* The ticket comment is the copy; the artifact is the organised view.
- **Option 3C: the channel writes the file itself.** *Struck:* the daemon never writes
  into a repository's spec tree on a channel's behalf; that is the session's job and
  keeps the "through the ledger" rule literal.
- **A cap, not a digest.** GitHub's comment limit and the reader's patience both argue
  for a ceiling on the snapshot (messages and characters) with the permalink for the
  rest, decided at requirements time. No model summarises.

### Q4. What is a decision, and where does it live?

- **Option 4A: a `decision.recorded` row, attributed to the person.** Kind, text,
  rationale when given, the thread permalink, the room, who and when. Recorded on the
  ticket **unmarked** and enveloped, like `gate.feedback`, so the ledger's ingress
  reads it as *that person's* comment: it forwards it into a running session as their
  input (and never mirrors it back to Slack, the cross-channel loop rule), and a gate
  that later reads the thread sees a human's decision rather than the bot's echo.
  *Cost:* the envelope must carry the type, and a gate's classifier must read that
  type before it reads the words, so decision text never passes for an approval.
- **Where it lands in the repository.** The session folds every `decision.recorded`
  it receives or reads into `docs/specs/<id>/decisions.md` (a per-work-item log, one
  row each: kind, decision, who, link), and promotes one to
  `docs/decisions/decision-<nnn>.md` only when it is a durable project decision, which
  is the judgement the design phase already makes. The conflict log stays what it is
  (the agent's own assumptions).
- **Who may record one.** Lean: the same people who may answer a gate, since a decision
  binds the work the way an approval does. A later refinement could map kinds to roles
  (`product` → `product-manager`, …) from `collaborators.yaml`, but nothing today
  reads roles at the channel, and that is YAGNI until a room disputes a decision.
- **Text is required.** With no model to summarise a thread, `@the-loop decision` with
  nothing after it is refused with the grammar shown, ephemerally.

### Q5. Who may address the-loop in a room?

- **Option 5A: `routing.authorizedUsers` only** (today). *Cost:* the room's stakeholders
  mention the-loop and get silence, which reads as broken, not as safe.
- **Option 5B: two tiers.** Context and replies are *input*, which is what a work-item
  collaborator is already defined to give; decisions and control keywords need an
  authorized user. To make 5B real, the collaborator roster (issue-307) has to carry a
  Slack id beside the GitHub login, as `routing.authorizedUsers` entries do since
  issue-309. *Lean.*
- **Option 5C: anyone in the room.** The room is the work item's by declaration, so
  membership is the allow-list. *Struck:* Slack membership is not an identity the-loop
  can name on the ledger, and a record must name a person (decision-103).
- **Unlisted mention.** Silence stays the rule for a stranger. Whether a room member who
  is *not* on any roster should get an ephemeral "ask an authorized user to add you" is
  an open question: it is friendlier, and it reveals that a roster exists.

## Sketches & notes

The room's inbound path with the new gate and the two new acts, everything after the
mention gate being the pipeline that exists:

```mermaid
sequenceDiagram
  participant M as room member
  participant L as Slack listener / poll read
  participant P as inbound pipeline
  participant G as GitHub (ledger)
  participant S as session (if any)
  M->>L: "@the-loop context" in a thread
  L->>P: message, room → work item (issue-375)
  P->>P: addressed? (text carries <@bot>) else drop not-addressed
  P->>P: authorize (tier per act) · classify: keyword → verb → gate → reply
  P->>P: grant: context.added in channels.slack.publish?
  P->>L: conversations.replies → snapshot, names resolved
  P->>G: record: marked, quoted, scrubbed comment + envelope
  P->>S: deliver (best-effort; refusal recorded)
  P->>M: 👀 → ✅ and a one-line reply with the record's link
```

The grammar, as it would read in `docs/guide/slack.md`:

| In a room, type | It becomes | Grant | Needs |
|---|---|---|---|
| `@the-loop context` (in a thread) | `context.added`, the thread snapshotted onto the ticket | `context.added` | poll or socket |
| `@the-loop decision <text>` | `decision.recorded`, unmarked, attributed to you | `decision.recorded` | poll or socket |
| `@the-loop <keyword>` | `control.command`, as in a thread today | `control.command` | poll or socket |
| `@the-loop <anything else>` | `work-item.reply`, delivered to the session | `work-item.reply` | poll or socket |
| ⋯ → *Add as context* / *Record a decision* | exactly the typed mention above | the same | socket |

What this touches, as a rough inventory: `channels/events.py` (two rows),
`channels/inbound.py` (the mention gate on the room path, two verb handlers, the tier
check), `channels/slack.py` (the shortcut and `view_submission` branches, the modal,
the snapshot renderer, the confirmation reply), `channels/github.py` (two record
shapes), the app manifest (`features.shortcuts`), the CLI config schema (`publish`
grants), `channels status`, `docs/guide/slack.md`, `docs/capabilities/channels.md`, and
the operating-model skill (the fold-in rule for context and decisions, the
`decisions.md` file).

## Open questions

Raised on the ticket for the paper trail; the owner's answers converge this brainstorm.

1. **Does the mention gate exempt the-loop's own threads in a room?** A reply under
   the-loop's approval request or question would otherwise need `@the-loop` to count.
   Lean: exempt them; a thread the-loop opened is addressed to it.
2. **Mode 1 stays as it is?** The central channel's threads and the operator's DM keep
   listening to every reply, because there the thread is the-loop's own. The ticket
   hints at retiring mode 1 later; this work item would leave it untouched.
3. **Who may add context, and who may record a decision?** Lean: input (context,
   replies) for authorized users and the work item's collaborators once the roster
   carries Slack ids; decisions and keywords for authorized users only.
4. **Is a verbatim thread snapshot on the ticket acceptable?** It copies other people's
   words, some from people on no roster, onto a ticket that may be public. The
   alternative is a record of permalink plus the asker's own words only, which makes
   the context useless to a session that cannot read Slack.
5. **Where does a decision live in the repository?** Lean: `docs/specs/<id>/decisions.md`
   folded in by the session, with promotion to `docs/decisions/decision-<nnn>.md` left
   to the design phase's judgement.
6. **Grammar first and shortcuts second, or both in this work item?** The grammar is the
   floor (works in poll mode, no manifest change); the shortcuts and modal are the
   "user friendly" bar the ticket sets. Lean: both, sequenced within one work item, the
   shortcut being exactly the typed mention.
7. **Unrecognised or unauthorized mention: silence or an ephemeral nudge?** Silence is
   today's posture for strangers. A room member on no roster is a different case.

## Leaning / working hypothesis

- **A room listens only when addressed.** The mention gate sits on the issue-375 room
  path, before authorization; `not-addressed` is a silent drop. Threads the-loop
  opened, the central channel and the DM are unchanged.
- **Two new acts, two catalog rows.** `context.added` (marked, quoted snapshot of the
  thread, delivered) and `decision.recorded` (unmarked, attributed, enveloped). Both
  recorded on the ticket, both grantable in `publish`, both subscribable so every
  channel hears a decision. Everything else after a mention is a keyword or a reply,
  as today.
- **A shortcut is exactly the typed mention.** Decision-117's pattern, socket-only,
  with a modal for the decision's fields and `channels status` naming the steps.
- **The session keeps the organised view.** `docs/specs/<id>/decisions.md` for
  decisions; a `## Context` list in the phase artifact for context. The ledger record
  is the copy; the file is the view.
- **Two tiers of speaker.** Input for collaborators and authorized users, acts that bind
  for authorized users only. Collaborators gain a Slack id.

## Hand-off → requirements

If the owner confirms the lean, `requirements.md` asserts:

- **R-gate:** in a declared room, a message reaches the pipeline only when it mentions
  the bot or replies under a message the-loop posted; every other message is
  `not-addressed`, dropped with no record and no reaction. Central channel and DM
  behaviour unchanged, pinned by tests.
- **R-context:** `@the-loop context` snapshots the thread onto the ticket as a marked,
  scrubbed, capped record naming the asker, with the permalink; idempotent per thread;
  delivered best-effort; refusals recorded and reacted ⚠️.
- **R-decision:** `@the-loop decision <text>` records an unmarked, enveloped, attributed
  comment typed `decision.recorded`, with kind and rationale when given; refused with
  the grammar when the text is empty; never classified as a gate answer.
- **R-shortcuts:** *Add as context* and *Record a decision* message shortcuts, socket
  only, each entering the pipeline as the equivalent typed mention; a modal for the
  decision; the outcome written back to the member ephemerally.
- **R-speakers:** the tier per act; collaborators carry an optional Slack id; every
  refusal below the allow-list.
- **R-fold-in:** the operating-model rule for `decisions.md` and the context list, and
  the guide's table of gestures.
- **Security considerations:** a mention from a stranger; a crafted `message_action`
  payload; a thread carrying secrets or a broadcast; decision text carrying an approval
  keyword; injection through snapshotted content (delivered as data, never as
  instructions, as the event prompt already says); the roster growing a second id.

Left behind, as the record of what was considered: listening to every message, the
`app_mention` event, reactions as decisions, the channel writing spec files, room
membership as an allow-list, a model summarising a thread.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
