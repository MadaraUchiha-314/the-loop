---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#416"
---

# Self-review: multi-modal messages are forwarded to the session, never parsed by the loop

> The `self-review` node's proof, per `reference/reviewing.md`. Critic rounds: no
> critic is configured on this machine (`critics[]` is empty in the checked-in CLI
> config and no critic CLI is installed), so the critic rounds are recorded
> **unavailable** and do not count toward the operator's `criticReviewCount`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) | new findings | 4 found, 3 fixed, 1 accepted as designed — below |
| 2 | self (this session) | zero (converged) | re-read the whole diff against the requirements and the abuse cases; no new finding |
| critic 1–3 | — | **unavailable** | no critic configured on this machine |

## Round 1 findings

**F1 — two new event-log types were emitted but not catalogued.** `process_reply`
emits `channel.attachments` and the dispatcher `dispatch.attachments`;
`test_eventlog.py::…must_not_drift_apart` fails the build for any emitted type absent
from `EVENT_TYPES`, and the first full `make check` would have gone red on it. **Fixed**:
both are in the catalog with descriptions that say what the record carries — and, on
purpose, what it does not (no file name, no URL, no path), so the event log stays free of
the one thing this change puts on disk.

**F2 — a file name reaches an unmarked record with control keywords kept.** A
`gate.feedback` / `control.command` record keeps keywords by design (decision-103), and
the 📎 line carries the uploader's file name verbatim. **Accepted as designed, and
bounded**: the name is the authorized uploader's own, on exactly the footing of the words
they typed in the same message; a stranger's file never reaches a record (abuse case 6),
and the `work-item.reply` mirror defangs the whole text, names included, as it always
did. Recorded in `security-review.md` rather than changed — defanging a name on an
unmarked record would alter what the person attached.

**F3 — the module built `Attachment` values through untyped dicts.** `Attachment(**base)`
with a `dict` of mixed `str | int` values type-checked as 79 pyright errors, which
`make typecheck` refuses. **Fixed** by building one `Attachment` and deriving the rest
with `dataclasses.replace`, which is also the honest shape: every variant of a file is
the same value with one field changed.

**F4 — the spec chain had two markdownlint findings** (a code span with a leading space
in `design.md`; asterisk emphasis in `tasks.md` where the repo's rule is underscores).
**Fixed**; the first `make check` caught them and the second is the one recorded.

## Round 2 — the re-read

Read every requirement against what shipped, and every abuse case against the code as
written. Three things I looked at twice and left:

- **`fetch_attachments` sits after `bot.react(reply, "received")`**, which is after the
  last refusal in `process_reply` — so a stranger, an unpublishable event, an
  unauthorized act and a standing session's recording act are all dropped before a file
  is read. That ordering is the whole of abuse case 6, and the integration scenario
  pins it.
- **The pane text for `context.added` and `decision.recorded` is untouched.** `pane_text`
  is used only when `kind == "reply"`; a snapshot names files itself and a decision is
  the text typed. The design said so; the code does so.
- **The GitHub section is built from the full body, not the excerpt**, so a URL the
  per-field cap cuts is still named — and it is appended after `apply_directive`, so a
  custom template gets it. `test_a_prompt_without_attachments_is_unchanged` pins the
  other half: an ordinary event renders byte-identically.

Not changed, on reflection:

- **Cursor.** The adapter has no interactive session, so no relayed turn reaches it
  today, with or without a file. Named in the requirements' scope and the decision; not
  this work item's to change.
- **A Slack `files_info` re-read on the poll path.** The poll readers hand no client to
  the fetch, so a still-processing transcript on a poll-read message is delivered
  without one. The poll interval is measured in seconds to a minute; by the next read
  the message is already past the cursor. Accepted: the section says the transcript was
  not ready and names the saved clip.

## Requirement trace

| Requirement | Where it landed | Proved by |
|---|---|---|
| R1 — a Slack message's files reach the session | `InboundReply.files`; the four readers; `process_reply` → `fetch_attachments` → `render_section` | T2 image, file-only, poll-read, cannot-be-fetched scenarios; T1 caps |
| R2 — a voice note as Slack's transcript | `slack_attachments` → `_wait_for_transcript` → `_slack_transcript`; `vtt_to_text` | T1 captions, preview fallback, processing re-read, no-transcript; T2 voice-note and files.info scenarios |
| R3 — the record names what was attached | `record_lines`; `snapshot_thread` 📎; `process_kickoff` → `unfetched` | T1 record lines (no path); T2 image, gate answer, snapshot, kickoff scenarios |
| R4 — a GitHub attachment reaches the session | `Dispatcher._attachments_section`, `_github_token`; `github_attachment_urls`, `github_attachments` | T2 GitHub screenshot, private asset, reuse, unchanged-prompt scenarios; T1 URL shapes, token, reuse |
| R5 — the scope, measured | the manifest; `attachment_findings`; `probe_subscription` | T2 manifest and finding scenarios; the four touched probe suites |
| R6 — a declared, machine-local home | `StateLayout.attachments_dir`; `GENERATED_PATHS`; `docs/cli/state.md` | T10 `test_state_portability.py` |
| Security — abuse cases 1–6 | `fetch_url`, `safe_name`, the frame, the refusal order | T8 selection |

## Unresolved

None. The operator's first-use check (T11) is written down in `verification.md` and is
theirs to run; it needs a workspace this environment does not have.
