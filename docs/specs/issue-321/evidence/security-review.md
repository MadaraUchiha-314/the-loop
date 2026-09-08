# Security review — issue-321

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change sits on one trust boundary — the classification that decides whether a
message on a channel becomes a gate answer — and moves nothing across it. Who may speak
(`routing.authorizedUsers`, checked before classification), what a channel's message
may become (`channels.slack.publish`, checked after), and who judges an unmarked record
(the ledger's ingress: the marker check, `authorizedUsers`, `classify-feedback`'s filter,
`comments_from`'s narrow-only envelope attribution) are all unchanged. What changed is
the *reader* the pipeline uses to see the gate (now the dispatcher's own coupling, with
its start requirement and ownership check intact) and what the pipeline does when that
reader cannot answer: within the grant, hand the reply to the ingress; outside it, the
marked mirror as before.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A channel granted only `work-item.reply` carries "approved" while the pipeline cannot read the gate | the fallback is bounded by the grant: without `gate.feedback` the reply is the marked mirror with direct delivery, and the gate never reads a marked comment | `test_channels.py::test_an_unreadable_gate_without_the_grant_is_a_marked_reply_as_before`; `test_bus_integration.py::test_a_reply_for_a_work_item_with_no_session_record_is_left_to_the_ledger` (second half) |
| A2 | An unlisted member replies "approved" while the pipeline cannot read the gate | `unauthorized-actor` before classification; the graph is not even read | `test_channels.py::test_an_unlisted_member_is_dropped_before_the_gate_is_even_read` |
| A3 | A control keyword arrives while the pipeline cannot read the gate | keyword → gate → reply is unchanged; a keyword is `control.command` with that grant and `unpublishable-event` without — never a gate answer, and the graph is not read | `test_channels.py::test_a_control_keyword_outranks_an_unreadable_gate` |
| A4 | A reply deferred to the ledger reaches the session twice | the pipeline delivers nothing for `gate.feedback`; the record is unmarked so the ingress delivers it once, with its own graph consult first | `test_channels.py::test_an_unreadable_gate_defers_to_the_ledger_when_the_channel_may_answer_gates` (`deliveries == []`); `test_bus_integration.py` both scenarios |
| A5 | The pipeline's coupling drives the graph it should only read | the reader calls `context()` only; `on_event` / `on_spawn` / `on_pr_event` / `on_cleanup` are never reached; no sinks; the state file is byte-identical after a classification over real state | `test_channels.py::test_the_pipelines_read_moves_nothing`; `test_bus_integration.py::test_an_approval_from_slack_reaches_the_gate_under_the_default_control_policy` (`graph-state.json` unchanged) |

## Checklist

- [x] AuthN/AuthZ unchanged: `process_reply` still drops a bot, an empty allow-list and an unlisted member before any classification; the reader is handed the allow-list only so its construction equals the dispatcher's (`test_the_pipeline_reads_the_graph_through_the_dispatchers_own_coupling`).
- [x] The grant still bounds what a message may become (A1); the fallback changes which reader judges a reply the pipeline could not, never whether a reply-only channel can answer a gate.
- [x] The reader keeps `_guarded`'s gates — the start requirement, the checkout-ownership proof, the spec-dir containment — because it is the dispatcher's construction; a looser reader was refused in decision-109.
- [x] No text decides the gate: the read is over the-loop's own registry and `graph-state.json`; the reply's text reaches only `parse_command` (as before) and the record.
- [x] Secrets and text: `channel.reply_received` gains one enum field (`gate`); `test_the_reply_event_says_what_the_gate_read_returned` asserts the reply text is absent from the log; `test_event_payloads_never_carry_tokens_or_text` still holds.
- [x] Fail closed, restated: "cannot tell" is judged by the ingress or stays a marked reply — never a record no reader accepts. A read fault is `None`, not `False` (`test_a_graph_fault_is_cannot_tell`).
- [x] Evidence redaction: every token in the tests and the evidence is a fixture string; the checkouts are temp directories.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
