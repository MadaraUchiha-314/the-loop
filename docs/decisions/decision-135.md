<!-- Written per the `the-loop:writing` skill. -->

# Decision 135: a file a person attaches is fetched and forwarded, never interpreted — the harness reads the image, Slack supplies the transcript

- **Status:** proposed
- **Date:** 2026-09-21
- **Work item:** [issue-416](https://github.com/MadaraUchiha-314/the-loop/issues/416)
- **Deciders:** MadaraUchiha-314 (owner, on the ticket: "I don't want ANY complicated
  STT or image parsing in the loop"); the-loop (design)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it),
  [decision-086](decision-086.md) (the excerpt is a field allow-list; nothing acts on
  prompt text), [decision-133](decision-133.md) (a record delivered with a preset frame
  names its text as untrusted data)

## Context

A screenshot in a Slack thread, a voice note from a phone, an image dropped into a
GitHub comment: none of them reached the session. The Slack channel read a message's
`text` and nothing else — a message that was only an image was refused as empty — and
the app the manifest describes could not fetch a file. A GitHub comment carried the
asset's URL verbatim, which a session can open on a public repository and not on a
private one. The ticket asked first whether any parsing is required at all, and drew
the line at speech-to-text and image parsing inside the loop.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The loop fetches; it never interprets.** A file is downloaded as opaque bytes to `<state.root>/local/attachments/<slug>/`, and the session is handed the **path** with a fixed line: kind, name, type, size, link. No OCR, no captioning, no model call on a file, anywhere. | The harness that hosts a session — Claude Code in a tmux pane, the only kind the-loop hosts interactively — reads an image or a PDF from a path with its own tool. Anything the loop added would be a second, worse reader in front of a better one. |
| D2 | **A voice note is forwarded as Slack's own transcript, verbatim and attributed.** The clip's `transcription` block and its `vtt` captions are Slack's; the-loop strips cue timings from the captions and nothing more, and re-reads a still-`processing` transcript a bounded number of times. | Slack already transcribes every audio clip before the-loop sees the message. Forwarding that text meets the owner's constraint exactly — there is no speech-to-text in the loop because there is none to add — and the section says whose transcript it is. |
| D3 | **The daemon fetches, not the session.** The Slack bot token and the daemon's GitHub token are sent by one function that checks the destination host against an allow-list before every request and again on every redirect hop, reads one byte past a 25 MiB cap, and refuses anything else. | The session holds no Slack token and, on a private repository, no GitHub one; the daemon holds both. Handing a credential to a fetch is the one new trust boundary, so the fetch is written to be safe to hand one to. |
| D4 | **Two renderings, two readers.** The pane gets kinds and local paths under a frame that names everything UNTRUSTED; the ticket gets 📎 names, types, the Slack permalink or the asset URL, and the transcript quoted — never a path, never a private download URL. | The ledger stays the whole story without carrying a path that means nothing off this machine (decision-103); the pane gets what the session can act on, framed the way every delivered record already is (decision-133). |
| D5 | **Best-effort by contract.** Every failure — no token, off-host, over the cap, a transfer error, past ten files — is a line naming the file and a fixed reason, and the words the file came with are delivered regardless. | Nothing in this change may make a message undeliverable that was deliverable before. A file the loop could not fetch is still named and linked, and a GitHub URL is offered for the session to try itself. |
| D6 | **The section rides outside the excerpt and outside the template.** On the GitHub path it is appended after the rendered prompt, so `$payload_excerpt` keeps decision-086's contract and a custom `routing.promptTemplate` carries it unchanged. | The excerpt is a field allow-list with a per-field cap; a screenshot's URL may fall past the cap in a long body, and the section — built from the full body — still names it. |
| D7 | **Constants, not configuration; no retention.** Ten files per message, 25 MiB per file, 30 s per request, three transcript re-reads; the fetched files accumulate under `local/` until the operator deletes them. | A config key is a promise to document, migrate and onboard for a knob nobody has asked to turn. A sweeper is a later work item if disk becomes a problem; the state page says so. |

## Consequences

**Good.** "Look at this" works from a phone: a screenshot in Slack reaches the session
as a file it can open, a voice note reaches it as text, and a GitHub screenshot on a
private repository reaches it at all. The ticket keeps a link to every file that shaped
a conversation. Nothing in the loop reads a file, so there is nothing to get wrong about
what an image shows.

**Costs.** A network call sits on the delivery path, bounded by the caps. Slack's
transcript is imperfect and is forwarded as it is; the section says so. Files accumulate
on disk. An existing app must be re-installed for `files:read` before a file is fetched
rather than only named; `channels status --probe` names the gap.

**What it does not change.** The excerpt contract, the process graph, any config key,
the Cursor adapter (which has no interactive session for a turn to reach), and the
recording acts: a `record-context` snapshot names files as links, and a decision is the
text typed.

## Alternatives considered

- **Hand the session the URL and let it fetch.** Rejected: the session holds no Slack
  token and, on a private repository, no GitHub one. The URL is still named, so a
  session on a public repository can try it itself.
- **Transcribe in the loop** (a speech-to-text dependency, or a model call). Rejected by
  the owner, and unnecessary: Slack's transcript exists before the message is delivered.
- **Describe images in the loop** (a vision model call, an OCR pass). Rejected by the
  owner, and worse than the harness's own reading.
- **Attach the bytes to the ledger record.** Impossible on GitHub's API (no upload
  endpoint for comment assets) and unwanted: the permalink is the record.
- **A config block for the caps and the directory.** Deferred: constants until somebody
  needs to turn one.
