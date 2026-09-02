# Security review — issue-315

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so the autonomous review suffices.

## Threat model recap

No new trust boundary is crossed. The poller reads the same `gh` answers and writes the
same local files; what changes is how a failure in one repository is contained, how one
condition is classified, and what the heartbeat carries.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | `gh`'s stderr reaches the heartbeat and the terminal | Same operator-local file class as `events.jsonl`, which already carried the text verbatim; rendered as plain text by `status`, never interpreted, never posted to a ticket or channel | `test_poll_status.py::test_a_degraded_scope_is_named_beneath_the_last_cycle` (printed verbatim, nothing else done with it) |
| A2 | A skipped repository hides its pull requests | The quarantine withholds `gh issue list` only; `gh pr list` runs every cycle for a quarantined repository | `test_poller.py::test_disabled_issues_is_permanent_and_still_lists_pull_requests`, `test_poller_integration.py::test_one_repository_with_issues_disabled_does_not_blind_the_others` |
| A3 | A transient failure is misread as permanent and parks a repository | Only `gh`'s own "has disabled issues" classifies; a 502 is retried next cycle; a quarantined repository is re-probed every 60 cycles, on reload and on restart, and named by `status` meanwhile | `test_poller.py::test_only_ghs_own_message_classifies_as_permanent`, `…::test_a_quarantined_repository_is_reprobed_every_sixty_cycles` |
| A4 | A partial listing closes sessions in the repository that failed | `_reconcile_closures` is handed the degraded scopes and skips their sessions before asking the provider anything | `test_poller.py::test_reconciliation_skips_a_degraded_scope_and_keeps_the_rest`, `…::test_a_skipped_scope_is_not_reconciled_either` |

## Checklist

- [x] Input validation: no new input is parsed; `gh`'s message is substring-matched for one classification and otherwise carried as opaque text.
- [x] No shell: every `gh` spawn is the existing argv list; no new spawn.
- [x] Secrets: nothing new is read, logged or written; the heartbeat carries `gh`'s error text, as the event log already did.
- [x] Fail closed: under doubt a scope is neither reconciled nor quarantined; a reworded `gh` message degrades the classification to transient, never to silence.
- [x] No new attack surface on the ingress: the webhook path is untouched; the poller's authorization guards are untouched.
- [x] Evidence redaction: fixture repositories (`octo/repo`, `octo/repo-m`) and the ticket's anonymised `gh` message only.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required (tier 3).
