---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#243"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a forwarded event carries the instruction, not GitHub's metadata

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner's direct instruction to complete #243 in a cloud session (see *Deviations from the standard gates*). Full process; `brainstorming` skipped — the issue names the change; `design-critic-review` not selected (`reviews.critics` is empty). |
| requirements-definition | 2026-08-16 | pending — PR | `requirements.md`. Six requirements; the ticket's second question is R6 (answer it, do not act on it). |
| design | 2026-08-16 | pending — PR | Field allow-list per container, in a new `webhook/excerpt.py`. Carries the pros/cons analysis the ticket asked for. |
| test-planning | 2026-08-16 | pending — PR | 16 rows, 8 in scope; every `n/a` carries a reason. |
| tasks-breakdown | 2026-08-16 |  | 10 tasks; three independent red roots plus an independent baseline measurement. |
| implementation | 2026-08-16 |  | TDD: the red run captured and committed before the distiller existed. |
| verification | 2026-08-16 |  | Every planned activity ran; two spec numbers and one design rule corrected after execution. |
| needs-review | 2026-08-16 | pending — PR | Three self rounds, no critic configured, security checklist passed. |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| *pending* | The whole work item — the spec chain and the change. | — |

## Progress entries

### 2026-08-16 — read the render path, measured it, wrote the spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** traced what a session actually receives —
  `Dispatcher._render_prompt` (`cli/the_loop/webhook/dispatcher.py:2491`) →
  `payload_excerpt` (`:443`) → `_PAYLOAD_EXCERPT_KEYS` (`:73`) — and measured it against a
  realistic `issue_comment` webhook rather than estimating: a 61-character instruction
  arrives inside a 4,014-character excerpt that **hits the 4,000-char cap** and is chopped
  mid-string inside `issue.user.gists_url`, so the delivered JSON does not even parse.
  Confirmed the poll ingress synthesises lean payloads already
  (`poller/github.py:_item_payload`), so this is a webhook-shaped problem distilled at a
  seam both ingresses share.
- **Checkpoint/tests:** baseline suite green before any edit.
- **Next:** capture the baseline as evidence, then the red tests.
- **Blockers:** none.

### 2026-08-16 — red, then green

- **Phase:** implementation
- **Did:** wrote the units first and made the red *meaningful* rather than an
  `ImportError` — the excerpt moved into `webhook/excerpt.py` carrying the pre-change
  behaviour verbatim, so the run failed on assertions about behaviour (21 failed, 6 passed,
  [`evidence/red.md`](evidence/red.md)). Then the allow-list: two tables, a per-field text
  cap, a top-level `actor` for lifecycle events, and one line in
  `Dispatcher._render_prompt`.
- **Checkpoint/tests:** 28 passed in the new unit file, 4 in the new integration file,
  2156 across the repository; `ruff`, `ruff format`, `pyright`, `markdownlint` and
  `validate_config` all clean.
- **Corrected:** two claims the specs made before the code existed. The distilled excerpt
  is 203 characters, not the ~238 the design estimated. And the design said *every*
  container would carry an `author`; the first red run showed why it must not — GitHub's
  `issue.user` is whoever **opened** the item, not who acted, so a lifecycle event carries
  a top-level `actor` (from `router.event_actor`, the same definition authorization uses)
  and its container carries no author at all.
- **Next:** capability doc, decision record, the config reference, reviews.
- **Blockers:** none.

### 2026-08-16 — docs, self-review, security review

- **Phase:** verification → needs-review
- **Did:** capability doc (per-event table, truncation rule, unknown-shape rule),
  [decision-086](../../decisions/decision-086.md), and the placeholder contract in
  `routing-options.md`. Ran the self-review rounds and the security review recorded below,
  and posted the ticket's second question — the constant per-event text — as an analysis
  with four costed options for the owner to decide.
- **Checkpoint/tests:** full suite and the whole lint set re-run after the doc edits.
- **Next:** the human PR gate (risk tier 3 → `human-approves-pr`).
- **Blockers:** none.

## Deviations from the standard gates

Two, both stated rather than quietly taken — the same two [issue-246](../issue-246/execution-log.md)
recorded, for the same reason:

1. **`phase-selection` was not posted as a checklist and waited on.** This session was
   started by the owner directly against issue #243, in a cloud checkout with no poller
   and no daemon, so there is no ingress that could deliver the reply to such a post. The
   instruction is treated as the declaration (`the-loop execute`, default phase set,
   `brainstorming` skipped). The gate the risk tier actually turns on —
   `human-approves-pr` — is **not** bypassed.
2. **The four spec artifacts are marked `approved` in one PR** rather than approved one at
   a time, for the same reason. The reviewer approves the chain and the code together.

## Verification results

> This work item has a `testing-plan.md`, so the `verification` node records its results
> there, against the matrix rows it planned. This section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> Only when this work item selected the opt-in `design-critic-review` phase (issue-188).
> Not selected: `reviews.critics` is empty in `.the-loop/harness-config.yaml`, so no
> different model is configured to read the locked design.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop session | new findings — read the distiller for dead weight and for what the tables *imply*. `_TEXT_FIELDS` carried a `"text"` entry no container can reach (removed, per the minimalism ladder), and the fit loop was checked for termination: the budget strictly halves toward zero, the `budget > 0` guard ends it, and the hard chop that remains is unreachable while any free text is left to give | this PR |
| 2 | self | the-loop session | new findings — traced the *consumers* rather than the diff. Nothing outside the dispatcher imported `payload_excerpt` or `_PAYLOAD_EXCERPT_KEYS`, so the re-export is for external callers only; `test_interaction.py`'s placeholder-ordering assertions still bind the templates; and the change is strictly more robust at the entry — `event_excerpt(None)` renders `{}` where the old subset raised `TypeError` | this PR |
| 3 | self | the-loop session | new findings — asked what the excerpt stopped saying, not just what it stopped carrying. A **labelled issue's body no longer reaches the spawn prompt**. That is a real context reduction rather than metadata pruning, so it is now deliberate: pinned by `test_a_lifecycle_event_carries_the_title_but_not_the_body`, and stated in `design.md` § Trade-offs, decision-086 § Consequences and the capability doc | this PR |
| 4 | critic | — | **unavailable** — `reviews.critics: []`, so no different model is configured. Does **not** count toward `reviews.criticReviewCount` (`reference/reviewing.md`) | — |
| 5 | security | checklist (`reference/security.md`) | pass — see § Security review | this PR |

Rounds 1–3 each found something new, so the loop did not stop early; a fourth self round
was not run (`reviews.selfReviewCount` is 3, and the three covered distinct surfaces — the
code's own weight, its consumers, and what the change costs a reader downstream).

## Security review (gate)

- **Mechanism:** the-loop's checklist (`security.review.mechanism: auto` prefers the
  built-in `security-review` skill; it is not available in this session, so the checklist
  was applied and is recorded here rather than claimed as a skill run).
- **Scope:** this change **narrows** an untrusted ingress. It is still reviewed as a
  security change, because it edits the exact seam where attacker-controlled text becomes
  text an agent acts on.

  | Question | Verdict |
  |---|---|
  | Does any gate lose an input it used to read? | No. Authorization, the self-comment marker, control parsing, reaction targeting, head-ref resolution and workspace preparation all read `RoutedEvent.payload`, which is untouched. `test_the_gates_read_the_payload_not_the_excerpt` asserts each one on an event whose excerpt no longer shows its inputs. |
  | Can a comment body forge a field of the excerpt? | No. `json.dumps` escaping contains it, and the test asserts the forged text stays inside `body` while `html_url` and `author` keep their real values. Fewer sibling fields now exist to imitate. |
  | Can a body crowd out the-loop's own rules? | No. Free text is capped **per field** at 3,500 characters, and the whole-excerpt limit is enforced by shortening prose rather than cutting the document — the old cut removed the comment's URL and left unparseable JSON, which was the worse failure. |
  | Does any string reach an argv, a path or a ref? | No. The excerpt is rendered into a prompt; nothing opens, joins or executes a carried value. `path` and `line` are JSON values, as they were before. |
  | Is any new field carried that was not carried before? | No. The set is a strict subset of what the old excerpt copied — `check_run.output` included, which the old code carried inside the whole `check_run` object. |
  | New credential, config key or network path? | None. No config key was added (`test_docs_parity.py` would fail on an undocumented one), and the function performs no I/O. |
  | Attack surface removed | The `sender`/`user` objects (login-derived URLs, ×18 per object), the whole `issue` object on every comment event — its title **and** body — and every `api.github.com` URL. Asserted negatively, so a future field addition cannot bring them back silently. |
  | Residual | An author login is still attacker-influenced text in the prompt (a login can be `x", "body": "…`), bounded to a GitHub-legal login and JSON-escaped; pinned by `test_abuse_a_login_shaped_like_an_instruction_is_still_only_a_string`. Unchanged from before, where the same login appeared 18 times inside URLs. |

- **Human sign-off:** n/a. Risk tier 3 (`autonomy.defaultTier`; no `sensitivePaths` glob
  matches — no schema, no `.the-loop/` config, no workflow file), below
  `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

| Criterion | Met by |
|---|---|
| **R1.1, R1.2** a comment is body + address + author, with no `issue`, `sender` or API URL | `test_a_conversation_comment_carries_its_body_url_and_author_only`, `test_a_conversation_comment_drops_the_issue_the_sender_and_every_api_url` |
| **R1.3** an inline comment's anchor precedes its body | `test_an_inline_review_comment_puts_its_anchor_before_its_body` — asserts both the fields and their order in the rendered text |
| **R1.4, R1.5** a review carries state/body/URL/author, as a bare login | `test_a_review_carries_its_state_body_url_and_author`, `test_the_author_is_a_login_string_never_a_user_object` |
| **R2.1, R2.2** lifecycle events keep what they are about, plus the label | `test_a_labeled_issue_carries_the_entity_and_the_label_that_is_the_event`, `test_a_merged_pull_request_says_that_it_merged` |
| **R2.3, R2.4** CI events keep identity, status, conclusion and the failure message | `test_a_failed_check_run_carries_the_failure_message_it_came_with`, `test_a_workflow_run_carries_its_branch_and_conclusion`, `test_a_check_suite_carries_what_a_suite_actually_has` |
| **R2.5** `status` reads the payload root | `test_a_status_event_reads_the_fields_that_sit_at_the_payload_root` |
| **R2.6, R2.7** an unruled event distils; an unrecognised payload renders `{}` | `test_an_event_with_no_rule_distils_whatever_containers_it_carries`, `test_a_payload_with_nothing_recognisable_renders_an_empty_object` |
| **R3.1–R3.3** the cap takes prose, never the address | `test_a_capped_body_keeps_the_json_parseable_and_the_url_intact`, `test_a_capped_inline_comment_keeps_its_anchor`, `test_a_check_runs_summary_is_capped_like_any_other_free_text` |
| **R4.1, R4.2** both ingresses render the same comment through one function | `test_the_poller_and_the_webhook_render_the_same_comment_identically`, `test_a_polled_review_and_inline_comment_distil_like_their_webhook_twins` |
| **R5.1** the gates read the payload, not the excerpt | `test_the_gates_read_the_payload_not_the_excerpt`; and end to end, `test_a_delivered_prompt_carries_the_instruction_and_not_the_metadata` |
| **R5.2** the placeholder contract is unchanged | `test_interaction.py`'s existing ordering assertions, plus the `UNTRUSTED` assertion in the delivery test — both untouched and green |
| **R6.1, R6.2** the second question is answered, not decided | `design.md` § The constant text (four options, costed, with a recommendation), decision-086 §7, and the analysis posted on the ticket |
| **Non-functional (cost)** | Measured, not asserted: excerpt 4,014 → 203 chars, prompt 6,676 → 2,865, and the excerpt parses ([`evidence/baseline.md`](evidence/baseline.md), [`evidence/after.md`](evidence/after.md)) |

**Not claimed:** that this was observed against real GitHub. No `gh` binary and no
credentials exist in this environment, so the payloads are hand-built from GitHub's
documented shapes and the tmux boundary is the suite's existing fake. What that leaves
untested is named in [`testing-plan.md`](testing-plan.md) § Residual risk.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | New behaviour block under *Current behaviour*: the per-event table of what the excerpt carries, the no-`sender`/no-`issue`/no-API-URL rule, the title-but-not-body rule for lifecycle events, the per-field truncation guarantee, the unruled-event and unrecognised-payload rules, and the statement that the gates read the full payload | issue-243 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/cli/routing-options.md`](../../config/cli/routing-options.md) | `promptTemplate` gains the placeholder table an operator needs to write a custom template, and a paragraph stating that `$payload_excerpt` is no longer the raw payload — what it carries, how it truncates, and that the full payload is still what the gates judge by |
| [`docs/decisions/decision-086.md`](../../decisions/decision-086.md) (new) + the decision index | Why an allow-list rather than a deny-list, why the renderer fails safe, and why the ticket's second question is escalated with costed options rather than answered |

`README.md`, the operating-model skill and its `reference/` docs were checked and needed
no change: none of them describes what a rendered prompt contains. Verified by grepping
all three for `payload_excerpt`, `payload excerpt` and `excerpt` — the only hits outside
`docs/specs/` were the two shipped prompt templates (whose UNTRUSTED framing is unchanged
on purpose, R5.2), the capability doc and the config page above.
