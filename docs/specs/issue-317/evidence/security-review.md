# Security review — issue-317

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change moves one existing action — posting the work item's Slack root and binding it
(issue-312) — from the first event to the dispatcher's spawn path, behind an injected
opener that reads the CLI config per call. Nothing new is posted, granted, authorized or
read: the root is `render_root(ref, url)` as before, the opener is handed the router's
ref alone, and a binding stays **attribution** while the member allow-list stays
**authority**. The only new surface is the spawn path calling into the channel layer, and
that call is contained twice (the bus's per-channel catch, the dispatcher's own).

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | An unauthorized user comments the start keyword, hoping to open a thread | `_apply_control` refuses the command before `_on_unmatched`; the opener sits on `_spawn_for`, which a refused start never reaches | `test_control_integration.py::test_an_unauthorized_start_opens_no_thread` |
| A2 | A start on an unarmed work item (no auto-execute label) | `_spawn_refusal` → `spawn-policy`; nothing is enqueued, so nothing opens — and, as before (PR #107), nothing is recorded | `test_control_integration.py::test_a_refused_start_opens_no_thread`; `test_channels_integration.py::test_a_refused_start_opens_no_thread_scenario` |
| A3 | The channel raises, times out or returns no `ts` at start time | `bus.open_conversation` turns it into a failed `PostResult` + `channel.open_failed`; `_open_conversations` contains anything that still escapes; the spawn proceeds and nothing is bound | `test_channels_integration.py::test_a_channel_outage_never_fails_the_spawn`; `test_control_integration.py::test_a_raising_opener_never_fails_the_spawn`; `test_channels.py::test_a_failed_open_binds_nothing` |
| A4 | Text, a URL or Block Kit markup in the spawning comment reaching the root | The opener receives `work_item.ref` — the router's extraction — and `render_root` has no text input (issue-312 A2 stands) | `test_control_integration.py::test_the_opener_is_handed_the_ref_alone`; `test_channels.py::test_the_root_is_built_from_the_ref_alone` (unchanged) |
| A5 | The channel state file is corrupt or hand-edited | `ChannelState.load` resolves to empty (unchanged); the start opens a fresh root and binds it | `test_channels.py::test_a_corrupt_state_file_still_opens_on_start` |

## Checklist

- [x] AuthN/AuthZ unchanged: the open runs only after `_spawn_refusal` (arming, actor authorization, the collaborator no-spawn rule, spawn policy) and the adapter check; the member allow-list is still checked per reply; no new grant.
- [x] No shell, no subprocess: the open is the Slack SDK client and the issue-312 lock; the opener reads a config mapping.
- [x] Secrets: the token is read at call time inside the channel (`_client`) and never written — `test_token_never_lands_in_the_state_file` stands; `channel.open_failed` and `channel.thread_opened` carry ids and an error string, never a token (`test_open_posts_the_root_alone_and_binds_with_origin_start`, `test_a_failing_open_is_a_result_and_an_event_never_an_exception` assert the payloads).
- [x] Fail closed: no `channels` section → the opener returns before loading anything; no channel id / no token → `ChannelError` before any call (`test_open_fails_closed_like_post`); a root that fails to post binds nothing.
- [x] Least privilege: the same scopes (`chat:write`); no new API call — the root and the best-effort permalink moved earlier, not added.
- [x] A dispatcher without an opener behaves as at 13.1.1 (`test_a_dispatcher_without_an_opener_opens_nothing`).
- [x] Evidence redaction: no real workspace ids, hostnames or tokens in the committed evidence (`C123`, `xoxb-test`, `octo/repo` are fixtures).

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
