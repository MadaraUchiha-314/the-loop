---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#416"
---

# Security review: multi-modal messages are forwarded to the session, never parsed by the loop

> The `security-review` node's proof. Risk tier **3** — the change fetches untrusted
> content from Slack and GitHub to disk with a credential; it touches no sensitive path.
> See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist, against `requirements.md` § Security considerations
  and `design.md` § Security design, verified against the diff.
- **Outcome:** pass — one finding, fixed before the gate (F1 below); no residual risk
  accepted.
- **Findings:** F1 — a file name reaches a `gate.feedback` / `control.command` record
  with control keywords **kept** (those records keep keywords by design, decision-103).
  Disposition: **accepted as designed, and bounded** — the name is the authorized
  uploader's own, on the same footing as the words they typed in the same message; a
  stranger's file never reaches a record (abuse case 6), and a `work-item.reply` mirror
  defangs the whole text, file names included, as before. Recorded here rather than
  changed, because defanging a name on an unmarked record would alter what the person
  attached.
- **Human sign-off:** n/a (risk tier below 4).

## The one-sentence summary

This change hands a credential to a download for the first time, and the whole argument
is that the download cannot be pointed anywhere the credential does not belong, cannot
read more than the cap, and cannot put anything on the machine except opaque bytes under
one declared directory.

## Abuse cases, and the disposition of each

| # | Abuse case (from `requirements.md`) | Disposition |
|---|---|---|
| 1 | A Slack file object's `url_private*` or `vtt` names a host that is not Slack's | **Mitigated.** `fetch_url` checks the host against the allow-list before any request; the bot token is a parameter of that one function and travels nowhere else. `test_a_file_url_off_slacks_host_is_not_fetched_and_gets_no_token`: zero requests made. |
| 2 | A redirect leaves the allowed set | **Mitigated.** The opener never follows a redirect; each `Location` is re-checked and a hop outside stops with the credential unsent. `test_a_redirect_off_host_is_refused_with_the_credential_unsent`: one request, the first, and none to the attacker's host. |
| 3 | A file over the cap | **Mitigated.** The declared size is a pre-check; the streamed read stops at `max_bytes + 1` and over means nothing saved. `test_a_file_over_the_cap_is_not_saved`. |
| 4 | A hostile file name | **Mitigated.** `safe_name` keeps the last path segment, removes `..`, separators, control characters and a leading dot, caps the length; the saved name is `<source id>-<safe name>` inside the slug's directory. `test_a_hostile_name_stays_inside_the_directory`. |
| 5 | Instruction-shaped content in a file, a transcript or a name | **Mitigated.** Bytes are written and never opened, executed or parsed; a transcript and a name are rendered only inside the section whose frame says UNTRUSTED; the ledger's `scrub` / `strip_html_comments` / `neutralise_broadcasts` / `defang_control_keywords` run on the record text as on any reply. `test_the_section_names_kind_path_link_reason_and_frames_everything_as_untrusted`; the record assertions in the integration scenarios. |
| 6 | An unauthorized member's file | **Mitigated.** `process_reply` drops `unauthorized-actor` before `fetch_attachments` is reached. `test_a_strangers_file_is_never_fetched`: no request, nothing on disk, nothing recorded. |

## Fail-closed behaviour

- No token → every file `no-token`, named and linked, nothing fetched.
- Off-host, over the cap, transfer failure, past ten files → a fixed reason on the
  file; nothing saved for it.
- A fetch that raises anything else is caught at the channel (`fetch_attachments`
  returns reasons, never raises) and at the dispatcher (`_attachments_section` logs and
  returns the empty string): **no failure here can stop the delivery of the words the
  file came with.**
- The `files:read` scope missing → the download is refused by Slack and recorded as
  `transfer-failed` on the file; `channels status --probe` names the gap.

## Trust boundaries

| Boundary | Crosses | Control |
|---|---|---|
| Slack file metadata → the fetch | a URL, a name, a size | host allow-list before any request; name sanitised; size a hint, the stream the check |
| the bot token → Slack | one bearer header | only to `files.slack.com` / `*.slack.com`, re-checked per redirect hop |
| the GitHub token → GitHub | one bearer header | only to `github.com`, `*.github.com`, `*.githubusercontent.com` and the configured enterprise host, re-checked per hop |
| the network → disk | ≤ 25 MiB of opaque bytes per file, ≤ 10 per message | under `<state.root>/local/attachments/<slug>/`, classified local, never opened by the-loop |
| the fetched file → the session | a path and, for audio, Slack's transcript | inside the UNTRUSTED-framed section; the session's own tool reads the file |
| the fetched file → the ticket | name, type, size, permalink or asset URL, quoted transcript | never a path, never a private download URL, never a token |

## New attack surface

**One new outbound call with a credential attached**, written as described above and
covered by the abuse-case tests. No new endpoint, no new command, no new config key, no
new dependency (`urllib` only), no new file that holds a secret. The Slack scope added
is read-only.

## What a reviewer should check hardest

1. `fetch_url`'s host check and redirect walk — that no path through it sends
   `Authorization` to a host outside `allowed_hosts`.
2. `record_lines` — that nothing it renders can carry a local path or `url_private`.
3. That `fetch_attachments` is called only after `unauthorized-actor` in `process_reply`
   (it is: after `bot.react(reply, "received")`, which sits after the last refusal).
