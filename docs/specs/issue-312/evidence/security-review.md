# Security review — issue-312

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds a root message the-loop posts (built from a ref and a URL derived from
it), a sibling lock file, a per-work-item record in the local channel state, one
best-effort permalink call, and a read-only listing command. Nothing here grants,
authorizes, or reads anything a member typed: a binding stays **attribution**, the member
allow-list stays **authority**.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A member posts a top-level message shaped like the-loop's root, hoping it becomes a work item's thread | Only two call sites bind: `_open_thread` (a post the-loop itself made) and `process_kickoff` (behind the `work-item.create` grant, a configured repo and the member allow-list). A look-alike without the grant is never read; with it, it is a kickoff candidate judged like any other | `test_channels.py::test_a_members_root_shaped_message_binds_nothing` |
| A2 | Text in an event or a member's message reaches the root (a planted link, Block Kit markup, a foreign ref) | `render_root(work_item, url)` takes the bound ref and a URL derived from it through `WorkItemRef`; it has no text input | `test_channels.py::test_the_root_is_built_from_the_ref_alone` |
| A3 | Slack's permalink call fails or returns nothing | `try/except Exception` around `chat.getPermalink`; the binding is written with `permalink: ""` and the event is still delivered | `test_channels.py::test_a_failed_permalink_still_binds_the_thread` |
| A4 | The state file is corrupt or hand-edited | `ChannelState.load` resolves to empty (unchanged); the next event opens a fresh root and binds it; a record without a `thread` is ignored on load | `test_channels.py::test_a_corrupt_state_file_opens_a_fresh_thread` |
| A5 | The platform has no `flock` | `ChannelState.locked` yields unlocked after one debug line — today's behaviour, never a refusal to deliver | `test_channels.py::test_without_flock_the_lock_degrades_to_today` |

## Checklist

- [x] AuthN/AuthZ unchanged: the member allow-list (`routing.authorizedUsers` `slack` ids) is checked per reply after the bot drop, exactly as before; no new grant.
- [x] No shell, no subprocess: the lock is `os.open` + `flock`; Slack calls go through the SDK client.
- [x] Secrets: the token is read at call time and never written — `test_token_never_lands_in_the_state_file` stands; `channels threads` prints ids and a permalink, never a token or message text (`test_channels_threads_lists_and_filters_conversations` asserts the dummy token is absent).
- [x] Event log payloads carry ids only: `test_thread_opened_is_emitted_with_ids_only`.
- [x] Fail closed: every existing refusal (no channel id, no token, disabled or malformed section) is reached before any new code runs; a root that fails to post binds nothing; a reply that fails never opens a second thread.
- [x] Least privilege: the same scopes (`chat:write`, `channels:history`); `chat.getPermalink` needs none beyond them.
- [x] Evidence redaction: no real workspace ids, hostnames or tokens in the committed evidence (`C123`, `xoxb-test` are fixtures).

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
