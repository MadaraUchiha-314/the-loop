---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#416"
status: in-review            # draft | in-review | approved — tier 3: a human approves the PR
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 3                  # fetches untrusted content from Slack and GitHub to disk with a credential; touches no sensitive path
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: multi-modal messages are forwarded to the session, never parsed by the loop

> Phase 1 of 4 (requirements → design → testing plan → tasks). Source:
> [issue-416](https://github.com/MadaraUchiha-314/the-loop/issues/416).

## Introduction

A person answers the-loop from Slack with a screenshot, or records a voice note on their
phone, or drops an image into a GitHub comment. Today none of that reaches the session,
and the two channels fail differently:

- **Slack reads `text` and nothing else.** Every construction of an inbound message —
  the Socket Mode handler, the three poll readers, the thread snapshot `record-context`
  makes — takes `text`, `user`, `ts`, `thread_ts` and the bot flags, and ignores the
  message's `files`. A message that is *only* an image arrives with an empty `text`; the
  pipeline mirrors an empty quote onto the ticket and then `reply_session` refuses it
  ("the reply text is empty"), so the ✅ never comes and the person is left guessing. A
  message with text *and* an image delivers the text and silently drops the image. The
  Slack app the manifest describes has no `files:read` scope, so even a reader that
  wanted the file could not fetch it.
- **GitHub carries the link and nothing behind it.** An uploaded image becomes
  `![shot](https://github.com/user-attachments/assets/<uuid>)` in the comment body, and
  the body travels to the session inside `$payload_excerpt` verbatim. For a public
  repository the session can fetch that URL itself. For a private one it cannot — the
  asset needs a GitHub credential the session does not hold — and nothing tells it so.

The issue asks the right question first: **is any parsing required at all?** The
investigation behind this work item (recorded in `design.md` § What was found) answers
it: **no**. The harness that hosts a session — Claude Code in a tmux pane, the only kind
that can receive a relayed turn today — reads an image or a PDF from a local path with
its own file-reading tool. And Slack transcribes a voice clip **itself**: the file object
carries a `transcription` block (a preview of the text) and a `vtt` captions URL holding
the whole transcript, both produced by Slack before the-loop ever sees the message. So
the loop's whole job is to **fetch the bytes and the transcript Slack already made, put
them where the session can read them, and say so in the delivered message** — and the
owner's constraint that the loop does *no* speech-to-text and *no* image parsing is not
a limitation to work around; it is the design.

### Scope

In scope: what the Slack channel and the GitHub relay do with a message that carries a
file, on the path into a running session and onto the ledger record; the Slack app scope
that makes fetching possible; the place on disk the fetched files live.

Out of scope, and deliberately: any interpretation of the content — no speech-to-text,
no OCR, no image description, no model call of any kind on the file (the owner's
constraint, and decision-135); any new config key; attachments on the way *out* (the
session posting an image to Slack); sessions the-loop cannot reach (Cursor has no
interactive session kind in the-loop; a relayed turn already never reaches it).

## Requirements

### Requirement 1 — a Slack message's files reach the session

**User story:** As a person answering the-loop from Slack, I want the screenshot I
attached to reach the session the way my words do, so that I can show it what I mean
instead of describing it.

#### Acceptance criteria (EARS)

1. WHEN an inbound Slack message carries one or more `files` — on the Socket Mode path
   (`message`, `app_mention`) or any of the three poll reads — THEN the channel SHALL
   carry those file objects on the normalized message beside its `text`.
2. WHEN a message that the pipeline would deliver as `work-item.reply` carries files
   THEN the channel SHALL fetch each file's bytes with the bot token, save it under
   `<state.root>/local/attachments/<work-item slug>/`, and the text delivered into the
   session SHALL end with an **Attachments** section naming, per file: its kind
   (`image`, `audio`, `video`, `pdf`, `file`), its name, its media type and size, the
   local path, and the Slack permalink.
3. WHEN a message carries files and an empty `text` THEN it SHALL be delivered — the
   Attachments section is the text — and SHALL NOT be dropped as an empty reply.
4. WHEN the delivered Attachments section names an image or a PDF THEN it SHALL tell the
   session to read the file with its own file-reading tool, and SHALL NOT describe the
   file's content: the loop never looks inside.
5. WHEN a file cannot be fetched — no bot token, the `files:read` scope missing, a
   transfer error, a size over the cap, a URL off Slack's file host — THEN the section
   SHALL still name the file with its permalink and a fixed-words reason it was not
   fetched, and the message SHALL be delivered regardless.
6. WHEN a message carries more than ten files THEN the first ten SHALL be fetched and
   the rest named with a reason, so one message cannot fill the disk.
7. WHEN the message's classification is `gate.feedback` or `control.command` — the
   ledger's ingress, not the channel, delivers those — THEN the files SHALL be fetched
   and named on the **record** exactly as in Requirement 3 below, so the session that
   later receives the relayed comment sees the same link and transcript a reply would
   carry; nothing is pasted into the pane by the channel for those kinds, as today.

### Requirement 2 — a Slack voice note reaches the session as Slack's own transcript

**User story:** As a person on my phone, I want to answer the-loop with a voice note,
so that a question does not wait until I am at a keyboard.

#### Acceptance criteria (EARS)

1. WHEN a fetched Slack file is an audio clip AND its `transcription.status` is
   `complete` THEN the Attachments section SHALL carry the transcript **verbatim**, taken
   from the file's `vtt` captions (cue timings and numbering stripped, text joined) when
   that URL can be fetched, else from `transcription.preview.content`.
2. WHEN the transcript is still `processing` when the message arrives THEN the channel
   SHALL re-read the file (`files.info`) a bounded number of times over a few seconds
   before giving up, so a clip that Slack is still transcribing is not delivered as
   silent; WHEN it is still not complete THEN the section SHALL say so and name the
   saved audio path, and the message SHALL be delivered regardless.
3. The loop SHALL NOT run any speech-to-text of its own, call any model on the audio, or
   summarise the transcript: the text delivered is what Slack produced, attributed to
   Slack, marked untrusted.
4. WHEN a clip has no transcription block or its status is `failed` THEN the section
   SHALL say Slack produced no transcript and name the saved path.

### Requirement 3 — the ledger record names what was attached

**User story:** As someone reading the ticket later, I want to see that a screenshot or a
voice note was part of the conversation, so that the GitHub record stays the whole story.

#### Acceptance criteria (EARS)

1. WHEN a Slack message with files is recorded on the ledger — as a `work-item.reply`
   mirror, a `gate.feedback` or a `control.command` record — THEN the record's body
   SHALL carry one line per file: 📎, the file's name, its media type and size, and its
   **Slack permalink**; and for an audio clip with a transcript, the transcript quoted
   beneath it.
2. The record SHALL NOT carry a local path, a `url_private` download URL, or any token.
3. WHEN a `record-context` snapshot includes a message with files THEN each such message
   line SHALL name its files (📎 name, permalink) after the message's text, so a thread
   whose decisive turn was a screenshot is not recorded as a blank line.
4. WHEN a Slack kickoff (a top-level message that becomes an issue) carries files THEN
   the issue body SHALL end with the same 📎 lines, so the file is linked from the
   ticket; the files are not fetched at kickoff (there is no session to read them yet).

### Requirement 4 — a GitHub attachment reaches the session whether or not it can fetch it

**User story:** As a person commenting on a private repository with a screenshot, I want
the session to see it, so that "look at this" works on GitHub as it does in Slack.

#### Acceptance criteria (EARS)

1. WHEN a forwarded GitHub event's comment, review, issue or pull-request body contains
   one or more attachment URLs — `https://github.com/user-attachments/assets/…`,
   `https://github.com/<owner>/<repo>/assets/…`, `https://user-images.githubusercontent.com/…`,
   `https://private-user-images.githubusercontent.com/…`, and the same shapes on the
   configured GitHub Enterprise host — THEN the prompt delivered into the session SHALL
   end with an **Attachments** section naming each URL, and for each one fetched, its
   kind, media type, size and local path under `<state.root>/local/attachments/<slug>/`.
2. WHEN the daemon holds a GitHub token (the first set variable of
   `integrations.github.api.tokenEnv`, default `GH_TOKEN` then `GITHUB_TOKEN`) THEN the
   fetch SHALL send it as a bearer credential, so a private repository's asset can be
   read; WHEN it holds none THEN the fetch SHALL be anonymous, which serves a public
   repository's asset and fails for a private one.
3. WHEN a fetch fails THEN the section SHALL name the URL with a fixed-words reason and
   say the session may try the URL itself; the event SHALL be delivered regardless.
4. WHEN the same asset URL is seen again for the same work item — a lifecycle event
   re-carrying an issue body, a re-delivered comment — THEN the saved file SHALL be
   reused and SHALL NOT be fetched twice.
5. The `$payload_excerpt` contract (decision-086) SHALL be unchanged: the section is
   appended after the rendered prompt, outside the excerpt, and a custom
   `routing.promptTemplate` that never heard of attachments still gets it.

### Requirement 5 — the Slack app can read files, and says when it cannot

**User story:** As an operator upgrading an existing app, I want to be told the scope I
am missing, so that a silently unfetched screenshot is not my first clue.

#### Acceptance criteria (EARS)

1. The shipped app manifest SHALL declare the `files:read` bot scope, with the reason
   beside it, and the Slack guide's copy of the manifest SHALL match.
2. WHEN `the-loop channels status --probe` measures the bot's granted scopes AND
   `files:read` is absent THEN the findings SHALL carry one sentence naming the scope
   and its consequence — files are named and linked, never fetched — and the remedy
   (re-import the manifest, reinstall).
3. WHEN the scopes cannot be read THEN there SHALL be no finding, exactly as for the
   mention scope: measured, never guessed.

### Requirement 6 — the fetched files have a declared, machine-local home

**User story:** As an operator who tracks `portable/` in git, I want fetched files to
land where nothing tracks them, so that a screenshot never ends up in a commit.

#### Acceptance criteria (EARS)

1. Fetched files SHALL live under `<state.root>/local/attachments/<work-item slug>/`,
   declared in `StateLayout` and classified **local** in `GENERATED_PATHS` and on the
   state page, so the portability tests and the `.gitignore` recipe cover them.
2. A saved file's name SHALL be derived from the source's own id (Slack's file id, the
   asset URL's last path segment) plus a sanitised copy of the original name: no path
   separators, no control characters, no leading dot, capped in length.
3. The loop SHALL remove nothing it fetched: retention is the operator's, and the state
   page SHALL say so.

## Non-functional requirements

- **No new dependency and no new config key.** The fetch is stdlib `urllib`; the Slack
  file metadata comes from the message the SDK already delivers and from `files.info`
  on the client the-loop already builds. Caps are constants.
- **Bounded cost.** One message fetches at most ten files, each at most 25 MiB, each
  with a 30 s timeout; a transcript wait is at most three re-reads two seconds apart.
- **Best-effort by contract.** Nothing in this work item can make a message
  undeliverable that was deliverable before: every failure lands in the section as a
  reason and the message goes on.
- **Idempotent on disk.** A file that already exists at its derived path is reused.

## Security considerations

> Threat-model-lite, captured with the requirements.

- **Actors & trust.** The person attaching a file is an authorized user or a
  collaborator — the pipeline's existing allow-list runs before any file is looked at
  (a stranger's message is dropped before its files are read). The **file itself is
  untrusted**: an image can carry text shaped like an instruction, a transcript is
  Slack's model reading whatever was said, a GitHub asset can be anything an account with
  write access uploaded. The file's **metadata** (`name`, `mimetype`, `url_private`,
  `permalink`, `vtt`) is Slack's, but Slack passes through the uploader's name and — in
  principle — a crafted URL is a URL the-loop would send a bearer token to.
- **Trust boundaries & data.** Two credentials cross into new code: the Slack bot token
  (sent to fetch `url_private_download` and `vtt`) and the GitHub token (sent to fetch an
  asset). Bytes from the network cross onto disk under the state root, and a path to
  them crosses into a session's prompt. Nothing crosses in the other direction: no token
  reaches a record, a prompt or a file name.
- **Abuse cases (EARS):**
  1. WHEN a Slack file object's `url_private`, `url_private_download` or `vtt` names a
     host that is not Slack's file host THEN the channel SHALL NOT fetch it and SHALL
     NOT send the bot token anywhere, recording "off-host" as the reason.
  2. WHEN a fetch is redirected to a host outside the allowed set for that credential
     THEN the loop SHALL NOT follow it with the credential attached and SHALL record the
     file as not fetched.
  3. WHEN a file's declared or actual size exceeds the cap THEN the loop SHALL stop
     reading at the cap, save nothing, and record the reason — a declared size is a
     hint, the streamed byte count is the check.
  4. WHEN a file's name contains a path separator, `..`, a control character or a leading
     dot THEN the saved name SHALL be sanitised so the file lands inside the work item's
     attachment directory and nowhere else.
  5. WHEN the fetched content, a transcript or a file name contains text shaped like an
     instruction THEN it SHALL reach the session only inside the section the frame marks
     UNTRUSTED, and the loop SHALL act on none of it — the bytes are written, never
     opened, executed or parsed.
  6. WHEN an unauthorized member sends a file THEN no fetch SHALL occur: the allow-list
     check precedes the file read, as it precedes everything else.
- **Fail closed.** No token → no fetch, said so. Unknown host → no fetch. Over cap → no
  file. Scope missing → a finding in `status --probe` and a reason in every section. A
  fetch that raises never stops the delivery of the words that came with it.

## Out of scope

- Speech-to-text, OCR, image captioning or any model call on an attachment (owner's
  constraint; decision-135).
- Attachments the session sends *out* (posting an image to Slack or GitHub).
- Cursor sessions: the-loop has no interactive Cursor session kind, so no relayed turn
  reaches one today; this work item changes nothing about that.
- Retention or garbage collection of fetched files.
- A new config key for the cap, the directory or the wait; constants, revisited if a
  deployment needs otherwise.

## Open questions

None outstanding. The one judgement call — fetch on the daemon or hand the session the
URL and let it fetch — is settled in `design.md` § What was found: the session holds no
Slack token and, on a private repository, no GitHub one, so the daemon is the only
party that can.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
