# Security review — issue-329

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds one **section** to the portable work-item record (`ended`), written by
the dispatcher's one close path from a provider's `closed` event or the provider's own
state answer, and read by the two attention surfaces to demote the item. The stamp is a
fact about visibility, never authority: it arms nothing, spawns nothing, deletes nothing
local, and gates no control command. The one act it sits beside — the existing cleanup
on closure — is reached only through the existing named-and-authorized actor check,
which now also sees GitHub's `closed_by` on a polled closure. The widened reconciliation
asks the provider about more items; it never acts on doubt.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A `closed` webhook for an issue the-loop never tracked fills `portable/` with stamps | `Dispatcher._tracks` — a session record of any status, or a portable record with any section — gates `_record_closure`; an untracked ref writes nothing | `test_routing.py::test_a_close_for_an_untracked_ref_creates_no_record` (no `portable/` directory is even created) |
| A2 | A login outside `authorizedUsers` closes a ticket on a polling deployment and the item's checkout is destroyed | the polled event's `sender` is judged by the unchanged `_cleanup_after_close`: unauthorized → `cleanup.deferred / unauthorized-actor`, session closed, checkout kept | `test_poller_integration.py::test_a_polled_closure_by_an_unlisted_closer_is_deferred` (`stranger` named in the deferral) |
| A3 | A closure GitHub cannot attribute releases resources | no `closed_by` → no `sender` → `cleanup.deferred / no-actor`, exactly as before | `test_poller.py::test_provider_closure_event_names_the_closer_as_sender` (no `sender` without an actor); `test_poller_integration.py::test_a_paused_sessions_closed_item_is_detected_and_stamped` (`actor: ""`) |
| A4 | A forged or stale `ended` on a tracked repository hides an open item | the next listing that carries the item clears the stamp before anything reads it (`work_item.reopened`); the stamp arms nothing while it stands | `test_poller.py::test_a_listed_item_clears_its_ended_stamp` |
| A5 | An unauthorized `reopened` event clears a stamp | the router's actor guard drops every non-`closed` `issues` / `pull_request` event from an unlisted actor before the dispatcher (unchanged, `test_router_still_guards_non_close_issue_events`); the poller's listing rule is the fallback | `test_routing.py::test_router_still_guards_non_close_issue_events` (existing); `test_a_reopen_clears_the_ended_stamp` (authorized path) |
| A6 | A malformed stamp (not a mapping) hides an item, or crashes a surface | `ControlStore.ended` and `endedOf` return `null` for anything but a mapping (with a string `state` on the dashboard); `attention.py` counts only mappings — the item shows | `test_control.py::test_a_malformed_ended_reads_as_not_ended`; `test_core_attention.py::test_an_ended_item_asks_for_no_attention` (second half); `model.test.ts › treats a record without the field, or with a malformed one, as open` |

## Checklist

- [x] AuthN/AuthZ unchanged: the cleanup gate (`_cleanup_after_close`) is untouched; the router's guard on non-close events is untouched; the stamp is not consulted by any control, spawn or gate path (A2, A3, A5).
- [x] Provenance: the stamp's `actor` is the webhook's `sender` or GitHub's `closed_by` — provider-recorded, never comment text; the stamp itself is written only from a `closed` event or the provider's state answer, never from a comment (A1).
- [x] Input validation: `state`, `kind`, `reason`, `source` are fixed vocabularies chosen by the dispatcher; `actor` is a login string; the reader tolerates any shape by ignoring non-mappings (A6).
- [x] Secrets: nothing new is stored; `work_item.ended` / `work_item.reopened` carry a ref, the fixed vocabularies, a login and a delivery id.
- [x] Fail closed, restated: no stamp means 13.6.0 behaviour; reconciliation never runs on a failed, interrupted or degraded listing (existing tests unchanged and green); an unanswerable closure leaves the item; a stamp beside a live session on this machine does not stop the poller from asking (`test_a_live_session_beside_a_stamp_is_still_reconciled`).
- [x] Disclosure: `docs/cli/state.md` § Security updated — the record now also discloses `closed` / `merged` and its reason, which the ticket already shows.
- [x] Evidence redaction: every login, ref and path in the tests and evidence is a fixture (`octocat`, `stranger`, `octo/repo`, `/tmp/pytest-…`).

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
