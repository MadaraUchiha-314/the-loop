# Scenarios: issue-517 handoff

`uv run the-loop scenarios --root . --format markdown` over the issue-517 test files. All 17 scenario titles that `testing-plan.md` names are present.

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | the handoff verb | handoff post renders the record and its parts and posts them in order | docs/specs/issue-517/requirements.md R5.1, R5.2 | cli/tests/test_handoff_cmd.py:159 |
| 2 | the handoff verb | handoff show prints the record frozen in state | docs/specs/issue-517/requirements.md R5.4 | cli/tests/test_handoff_cmd.py:242 |
| 3 | the handoff verb | handoff import materializes the files the ticket carries | docs/specs/issue-517/requirements.md R7.2 | cli/tests/test_handoff_cmd.py:273 |
| 4 | the handoff verb | handoff import refuses a file whose bytes do not match the record | docs/specs/issue-517/requirements.md R7.2, R7.5 | cli/tests/test_handoff_cmd.py:299 |
| 5 | the handoff verb | handoff import refuses the files when a part comment is missing | docs/specs/issue-517/requirements.md R5.2, R7.2 | cli/tests/test_handoff_cmd.py:323 |
| 6 | the handoff verb | handoff import --from-dir takes the spec-chain artifact's files | docs/specs/issue-517/requirements.md R7.2, R7.5 | cli/tests/test_handoff_cmd.py:395 |
| 7 | the handoff verb | handoff note points the record at the committed files and PR | docs/specs/issue-517/requirements.md R5.4 | cli/tests/test_handoff_cmd.py:499 |
| 8 | the handoff verb | handoff note supersedes a record it cannot edit | docs/specs/issue-517/requirements.md R5.4 | cli/tests/test_handoff_cmd.py:537 |
| 9 | the poller starts a handed-off item at the right step | arming a handed-off item checks out its spec branch | docs/specs/issue-517/requirements.md R6.1, R6.2 | cli/tests/test_handoff_pickup.py:219 |
| 10 | only an authorized user or the-loop can hand off | a handoff record from an unauthorized user is ignored | docs/specs/issue-517/requirements.md abuse case 1 | cli/tests/test_handoff_pickup.py:252 |
| 11 | only an authorized user or the-loop can hand off | an outsider pastes the-loop's self-authorship marker | docs/specs/issue-517/requirements.md abuse case 1 | cli/tests/test_handoff_pickup.py:277 |
| 12 | a record cannot move a walk that has begun | a record posted or edited after the walk started changes nothing | docs/specs/issue-517/requirements.md abuse cases 3, 6 | cli/tests/test_handoff_pickup.py:296 |
| 13 | the pick-up fails closed | the comments cannot be listed at arming | docs/specs/issue-517/design.md §Error handling | cli/tests/test_handoff_pickup.py:316 |
| 14 | the Jira copy never runs the loop | arming a Jira mirror is refused | docs/specs/issue-517/requirements.md R3.5, abuse case 7 | cli/tests/test_handoff_pickup.py:365 |
| 15 | the runtime records where a handed-off walk begins | a fresh work item starts with a handoff | docs/specs/issue-517/requirements.md R6.1 | cli/tests/test_handoff_pickup.py:435 |
| 16 | a record cannot move a walk that has begun | a record posted or edited after the walk started changes nothing | docs/specs/issue-517/requirements.md abuse cases 3, 6 | cli/tests/test_handoff_pickup.py:456 |
| 17 | items with no handoff behave exactly as today | the prompt of an item with no handoff | docs/specs/issue-517/requirements.md compatibility NFR | cli/tests/test_handoff_pickup.py:584 |
| 18 | the session is told where its walk was handed in | a handed-off item's prompt | docs/specs/issue-517/requirements.md R6.1 | cli/tests/test_handoff_pickup.py:597 |
| 19 | a handed-off spec-chain artifact keeps its URL | an imported spec-chain artifact URL is recorded and rendered in graph context | docs/specs/issue-517/requirements.md R7.4 | cli/tests/test_handoff_pickup.py:618 |
| 20 | the handoff record | a branch-carried record renders and parses back unchanged | docs/specs/issue-517/requirements.md R5.1 | cli/tests/test_handoff_record.py:116 |
| 21 | the handoff record | a ticket-carried record carries each file in a details block | docs/specs/issue-517/requirements.md R5.1, R5.2 | cli/tests/test_handoff_record.py:133 |
| 22 | the handoff record | an artifact-carried record pins the spec-chain artifact's hash | docs/specs/issue-517/requirements.md R5.1 | cli/tests/test_handoff_record.py:152 |
| 23 | the handoff record | the rendered record is byte-stable for each carrier | docs/specs/issue-517/testing-plan.md T6 (R5.1) | cli/tests/test_handoff_record.py:203 |
| 24 | the poller starts at the right step | each stage enters its row's starting step | docs/specs/issue-517/requirements.md R6 table | cli/tests/test_handoff_record.py:282 |
| 25 | the handoff record | a record of a version the reader does not know is ignored | docs/specs/issue-517/requirements.md R5.5 | cli/tests/test_handoff_record.py:320 |
| 26 | the handoff record | a record with a key the reader does not know is rejected | docs/specs/issue-517/requirements.md R5.5 | cli/tests/test_handoff_record.py:336 |
| 27 | handoff abuse cases | a handoff record entering implementation is rejected | docs/specs/issue-517/requirements.md §Security, abuse case 2 | cli/tests/test_handoff_record.py:352 |
| 28 | handoff abuse cases | an artifact name outside the closed set is refused | docs/specs/issue-517/design.md §Security design | cli/tests/test_handoff_record.py:382 |
| 29 | handoff abuse cases | a branch outside the-loop/ or failing check-ref-format is refused | docs/specs/issue-517/design.md §Security design | cli/tests/test_handoff_record.py:439 |
| 30 | the handoff record | a body over 65,536 characters continues in part comments | docs/specs/issue-517/requirements.md R5.2 | cli/tests/test_handoff_record.py:556 |
| 31 | handoff abuse cases | a handoff record from an unauthorized user is ignored | docs/specs/issue-517/requirements.md §Security, abuse case 1 | cli/tests/test_handoff_record.py:644 |
| 32 | handoff abuse cases | a part comment by another author is ignored | docs/specs/issue-517/design.md §Security design | cli/tests/test_handoff_record.py:729 |
| 33 | phase selection for a handed-off item | the checklist for a requirements-settled handoff | R6.4 (T6) | cli/tests/test_handoff_selection.py:151 |
| 34 | phase selection for a handed-off item | an item with no handoff walks exactly as before | R7.1, compatibility NFR | cli/tests/test_handoff_selection.py:233 |
| 35 | a handed-off item starts at the right step | an exploring handoff walks to brainstorming | R6 table, R6.4 | cli/tests/test_handoff_selection.py:328 |
| 36 | a handed-off item starts at the right step | a brainstorm-settled handoff walks to brainstorm-approval | R6 table, R6.3, R6.4 | cli/tests/test_handoff_selection.py:343 |
| 37 | a handed-off item starts at the right step | a requirements-settled handoff walks to requirements-approval | R6.1, R6.3, R6.4 | cli/tests/test_handoff_selection.py:361 |
| 38 | a handed-off item starts at the right step | a design-settled handoff with a testing plan walks to design-approval | R6 table | cli/tests/test_handoff_selection.py:384 |
| 39 | a handed-off item starts at the right step | a design-settled handoff without a testing plan walks to test-planning | R6 table | cli/tests/test_handoff_selection.py:401 |
| 40 | a handed-off item starts at the right step | check reports the phases before the starting step as skipped by handoff | R6.3 | cli/tests/test_handoff_selection.py:417 |
| 41 | a handed-off item starts at the right step | an item with no handoff walks exactly as before | R7.1, compatibility NFR | cli/tests/test_handoff_selection.py:438 |
| 42 | import-handoff stays out of every other item's walk | a work item with no handoff | R7.1 | cli/tests/test_handoff_state.py:97 |
| 43 | compatibility | a work-item-state.json with none of the new keys | compatibility NFR (testing-plan T10) | cli/tests/test_handoff_state.py:200 |
| 44 | the import-handoff node | the shipped graph places it after phase selection | R7.1 | cli/tests/test_import_handoff.py:135 |
| 45 | the import-handoff node | an item with no handoff walks exactly as before | R7.1 | cli/tests/test_import_handoff.py:162 |
| 46 | import-handoff demotes a carried artifact that fails its shape check | a requirements.md missing Security considerations demotes to requirements-definition | R7.3 | cli/tests/test_import_handoff.py:248 |
| 47 | approvals carried in the chat | a brainstorm carried under requirements-settled is locked as approved by the handoff | R6.5, R8.3 | cli/tests/test_import_handoff.py:286 |
| 48 | a carried file is pinned by its sha256 (abuse case 4) | a carried file whose hash does not match is refused | R7.3, security design (abuse case 4) | cli/tests/test_import_handoff.py:321 |
| 49 | a carried body is data (abuse case 5) | an artifact body with agent-directed text is written verbatim and changes no state | security design (abuse case 5) | cli/tests/test_import_handoff.py:347 |
| 50 | conversation handoff | a Jira copy is created with issue type, parent and the mirror label | docs/specs/issue-517/requirements.md R3.4, R3.5 | cli/tests/test_jira_verbs.py:200 |
| 51 | Jira as a work-item source | an authorized Jira comment resumes the work item's session | docs/specs/issue-475/requirements.md#R5.3 | cli/tests/test_jira_integration.py:216 |
| 52 | Jira as a work-item source | the same Jira comment by webhook and by poll is delivered once | docs/specs/issue-475/requirements.md#R6.4 | cli/tests/test_jira_integration.py:250 |
| 53 | Jira as a work-item source | a Jira control comment seen by both ingresses is executed once | docs/specs/issue-475/requirements.md#R6.4 | cli/tests/test_jira_integration.py:294 |
| 54 | Jira as a work-item source | a Jira phase-selection checklist ticked in place is read at execute | docs/specs/issue-475/requirements.md#R5.5 | cli/tests/test_jira_integration.py:371 |
| 55 | Jira as a work-item source | an unlisted Jira user's execute leaves the gate waiting | docs/specs/issue-475/requirements.md#R7.2 | cli/tests/test_jira_integration.py:409 |
| 56 | Jira as a work-item source | a gate answer given on Slack advances a Jira work item's gate | docs/specs/issue-475/design.md#c8--ingress-poll-provider-webhook-doorbell-allow-list | cli/tests/test_jira_integration.py:438 |
| 57 | Jira as a work-item source | arming a Jira ticket is a label; starting it is a person | docs/specs/issue-475/design.md#security-design (abuse case 5) | cli/tests/test_jira_integration.py:491 |
| 58 | Jira as a work-item source | a Jira work item's session runs in its origin repository's worktree | docs/specs/issue-475/requirements.md#R5.4 | cli/tests/test_jira_integration.py:546 |
| 59 | Jira as a work-item source | a Jira `the-loop start` whose spawn failed is retried | docs/specs/issue-475/requirements.md#R6.4 | cli/tests/test_jira_integration.py:592 |
| 60 | Jira as a work-item source | a live Jira session outlives its project's mapping | docs/specs/issue-475/requirements.md#R5.4 | cli/tests/test_jira_integration.py:625 |
| 61 | Jira as a work-item source | a Jira comment reaches the session as untrusted data | docs/specs/issue-475/design.md#security-design (abuse case 10) | cli/tests/test_jira_integration.py:657 |
| 62 | Jira as a work-item source | a PR naming a registered Jira key routes to the Jira work item | docs/specs/issue-475/requirements.md#R8.1 | cli/tests/test_jira_integration.py:684 |
| 63 | Jira as a work-item source | finish-tasks transitions the Jira ticket to Done | docs/specs/issue-475/requirements.md#R3.7 | cli/tests/test_jira_integration.py:764 |
| 64 | conversation handoff | a Jira copy is created with issue type, parent and the mirror label | docs/specs/issue-517/requirements.md R3.4, R3.5 | cli/tests/test_jira_integration.py:797 |
| 65 | Jira as a work-item source | the-loop comment on a Jira ref is recorded on the Jira ticket | docs/specs/issue-475/requirements.md#R8.2 | cli/tests/test_jira_integration.py:840 |
| 66 | Jira as a work-item source | the delivered prompt names Jira and the origin repository | docs/specs/issue-475/requirements.md#R5.3 | cli/tests/test_jira_integration.py:875 |
