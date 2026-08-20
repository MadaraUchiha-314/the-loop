# Evidence: the Gherkin scenarios this work item adds (issue-277)

`the-loop scenarios --glob 'tests/test_standing*_integration.py' --format markdown`,
run from `cli/` (the root the command resolves to in this repository). Re-run after the
owner's ruling ([decision-100](../../../decisions/decision-100.md)) added `create`/`delete`.

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | standing sessions | a Slack thread reply reaches a standing session and no ticket | docs/specs/issue-277/requirements.md R4.1, R4.2, R4.3 | tests/test_standing_channels_integration.py:146 |
| 2 | standing sessions | an unauthorized Slack member never reaches a standing session | docs/specs/issue-277/requirements.md R4.4 | tests/test_standing_channels_integration.py:203 |
| 3 | standing sessions | a stopped standing session is resumed, not restarted from nothing | docs/specs/issue-277/requirements.md R2.3, R2.4, R2.6, R2.7 | tests/test_standing_integration.py:140 |
| 4 | standing sessions | a live tmux session the-loop cannot account for is never spawned over | docs/specs/issue-277/requirements.md R2.9 | tests/test_standing_integration.py:203 |
| 5 | standing sessions | a standing session is told what it is not | docs/specs/issue-277/requirements.md R5.1, R5.2 | tests/test_standing_integration.py:278 |
| 6 | standing sessions | the-loop start, stop and status carry the standing sessions | docs/specs/issue-277/requirements.md R2.1, R2.2, R2.5, R2.8 | tests/test_standing_integration.py:344 |
| 7 | standing sessions | a standing session is created through the API, with no config entry | docs/specs/issue-277/requirements.md R6.1, R6.7 | tests/test_standing_integration.py:542 |
| 8 | standing sessions | a created standing session is deleted and does not come back | docs/specs/issue-277/requirements.md R6.4 | tests/test_standing_integration.py:631 |
| 9 | standing sessions | the-loop restart does not destroy the sessions the API created | docs/specs/issue-277/requirements.md R6.6 | tests/test_standing_integration.py:676 |
| 10 | standing sessions | the two session namespaces cannot address each other | docs/specs/issue-277/requirements.md R3.1, R3.2 | tests/test_standing_security_integration.py:32 |
| 11 | standing sessions | a message into a stopped standing session refuses instead of spawning one | docs/specs/issue-277/requirements.md R3.4 | tests/test_standing_security_integration.py:84 |
