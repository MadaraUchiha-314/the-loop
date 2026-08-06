# Scenario coverage added by issue-163

`the-loop scenarios --format markdown`, filtered to this work item's rows.

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 54 | testing is planned and verified as nodes of the PDLC | the test-planning node will not pass without a locked plan | docs/specs/issue-163/requirements.md#R1 | cli/tests/test_graph_verification_integration.py:87 |
| 55 | testing is planned and verified as nodes of the PDLC | a locked plan carrying the gated sections clears the planning node | docs/specs/issue-163/requirements.md#R1.2 | cli/tests/test_graph_verification_integration.py:110 |
| 56 | testing is planned and verified as nodes of the PDLC | the results heading must be authored holding something | docs/specs/issue-163/requirements.md#R1.2 | cli/tests/test_graph_verification_integration.py:123 |
| 57 | testing is planned and verified as nodes of the PDLC | an activity that was planned but not executed keeps the gate shut | docs/specs/issue-163/requirements.md#R3.3 | cli/tests/test_graph_verification_integration.py:140 |
| 58 | testing is planned and verified as nodes of the PDLC | an executed plan with recorded results clears the verification node | docs/specs/issue-163/requirements.md#R3.2 | cli/tests/test_graph_verification_integration.py:155 |
| 59 | testing is planned and verified as nodes of the PDLC | the implementation node routes to verification on a pass | docs/specs/issue-163/requirements.md#R3.1 | cli/tests/test_graph_verification_integration.py:169 |
| 60 | testing is planned and verified as nodes of the PDLC | the template an agent authors from can pass its own gate | docs/specs/issue-163/requirements.md#R1.4 | cli/tests/test_graph_verification_integration.py:192 |
