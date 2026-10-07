---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Final validation: Jira as a first-class work-item source and update channel

> **Every requirement R1–R9 and the issue's five umbrella acceptance criteria are met.**
> Every claim below comes from the executed verification (`testing-plan.md` § Verification
> results, [`verification.md`](verification.md)). T1–T10 ran offline against
> `FakeJiraClient`. T11 ran against a live Jira Cloud sandbox in replanned form
> ([`manual-jira.md`](manual-jira.md)). After every review fix, the full gate passed
> (6004+ tests), along with the security review ([`security-review.md`](security-review.md)).

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| **R1** A `jira:` ref parses, round-trips, rejects bad grammar, and leaves GitHub refs unchanged | `test_jira_refs.py`; the existing GitHub ref tests pass unmodified (only four placeholder refs were swapped) | T1 · [unit.md](unit.md#t1) |
| **R2** Spec ids come from the provider and never collide (`jira-proj-n` vs `issue-n`, including key `ISSUE`); a moved key is refused | `test_issue_project_key_never_collides_with_github`, `test_moved_jira_key_refuses_second_spec_folder` | T1 |
| **R3** The daemon comments on, labels, reads and transitions a Jira ticket with env-named credentials; Cloud, scoped and Data Center; contract suite; config 0.12.0 and migration; decision record | contract suite (T3); `test_jira_api.py` (T2); migration and schema tests, including every migrated stub validating (T8); [decision-142](../../../decisions/decision-142.md); **live**: comment, labels and a transition to Done on the sandbox (T11) | T2, T3, T8, T11 |
| **R4** Jira as ledger (events on the ticket, one `loop:` label) and as a mirror channel (`jira@KEY-n`); Jira-safe labels; ADF and wiki bodies; a self-marker that survives storage | `test_jira_channels.py`, golden bodies (T4, T10); **live**: ADF rendered by Jira (headings, lists, code, tables, links, taskList), the self-marker survived, and `the-loop:auto-execute` was set and removed (T11) | T4, T10, T11 |
| **R5** Poll ingress: JQL per project and label, comments, closure on statusCategory Done, back-off keeps the cursor, control comments work | `test_jira_poller.py` (T5), ingress scenarios (T6); **live**: `/search/jql` found the armed ticket, closure was seen after Done, and a tick in Jira read back as `- [x]` (T11) | T5, T6, T11 |
| **R6** Webhook ingress: signed doorbell, re-fetch, events mapped; poll and webhook deliver a comment once | `test_jira_webhook.py`, *Scenario: the same Jira comment by webhook and by poll is delivered once*; control comments execute once (M1/R2-2 tests). A live signed delivery was **not run**, by the operator's choice, because polling covers delivery | T5, T6 |
| **R7** Jira identities on the allow-list; unlisted or missing authors are refused; matched by id | `test_jira_authz.py`, `test_missing_actor_is_unauthorized_on_jira`, `test_jira_comment_from_unlisted_author_is_ignored` | T5, T7 |
| **R8** PR linkage by Jira key (branch and title only, registered ref, mapped repository); ticket, comment, ask and pr verbs on Jira refs; `work-on` on the `jira:` ref; `/init` Jira onboarding | `test_jira_linkage.py`, `test_jira_verbs.py`, *Scenario: a PR naming a registered Jira key routes to the Jira work item*, *Scenario: finish-tasks transitions the Jira ticket to Done*; C3 tests (a same-repository PR is the item's own delivery); skill and command text reviewed | T6, T7 |
| **R9** Decision record, capability docs, config reference and skill text updated | [documentation.md](documentation.md) | review |
| **Security considerations**, abuse cases 1–10 | 41 negative tests pass, including three added in review: relay marker, checklist planting, mirrored snapshot; security review passed, with named sign-off requested (tier 4) | T7 · [security-review.md](security-review.md) |
| **NFR** No regression on GitHub | full suite plus pre-commit (T9); the self-review checked GitHub byte-identity; L1 restored byte-identity for bodies that quote the marker | T9 |
| **NFR** Rate limits | 10 projects at a 60 s interval is about 10 JQL calls plus one comment read per armed issue per minute, within Jira Cloud's per-user limits (arithmetic, T15) | testing-plan T15 |

### The issue's umbrella criteria

- [x] A `jira:` work-item ref parses and round-trips, and spec ids don't collide with GitHub ids (R1, R2).
- [x] The daemon can comment on, label and transition a Jira ticket with a token from the configured env vars (R3, shown live in T11).
- [x] `channels.ledger: jira` records the paper trail on the ticket, and Jira can be a subscriber channel (R4).
- [x] A comment on an armed Jira ticket from an authorized user resumes the work item's session, through the poller and through the webhook (R5, R6; the webhook is unit- and scenario-tested, not live).
- [x] Docs under `docs/capabilities/` are updated, and a decision record covers the SDK choice (R9, decision-142).

## Known gaps carried forward (proposed follow-ups)

- GitHub variant of checklist planting: anyone can type the hidden phase-selection marker on GitHub.
- Jira ticket descriptions turn markers into gate markers whoever wrote them.
- A Slack kickoff with `channels.ledger: jira` still opens a GitHub issue; `ticket show` on Jira returns empty `attachments`/`author`.
- Commands routed through the daemon resolve relative paths in the daemon's working directory; `the-loop critic run` through the service cannot finish a real round (HTTP 120 s vs critic 900 s).
- 21 tests fail on `main` too when a daemon-spawned session's `THE_LOOP_*` env vars leak into the test run.
