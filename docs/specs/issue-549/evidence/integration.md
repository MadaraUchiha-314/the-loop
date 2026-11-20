# Integration scenarios (T2)

Run on 2026-11-20 at `93ba24e5`, from `cli/`, with the same three variables unset:

```text
uv run python -m pytest -q tests/test_channels_integration.py tests/test_channels_declared_integration.py tests/test_channels_outbox_integration.py tests/test_bus_integration.py tests/test_gateway_slack_integration.py
111 passed in 2.89s
```

This work item's scenarios, from
`uv run the-loop scenarios --root "$PWD" --glob 'cli/tests/test_*_integration.py' --format markdown`,
filtered to issue-549. All 12 titles in `testing-plan.md`'s trace are present.

| # | Feature | Scenario | Requirement | Location |
| 90 | bookkeeping stays out of Slack | a session-started notice reaches GitHub and not Slack | docs/specs/issue-549/requirements.md R10.1, R10.2 | cli/tests/test_bus_integration.py:821 |
| 100 | every Slack message is a short form, and in a room its long form | a long comment in a declared room posts a short message and its long form in the thread | docs/specs/issue-549/requirements.md R4.1, R2.1, R2.2, R2.6, R2.7, | cli/tests/test_channels_declared_integration.py:795 |
| 101 | every Slack message is a short form, and in a room its long form | the central channel gets the short form only | docs/specs/issue-549/requirements.md R4.2, R3.2 | cli/tests/test_channels_declared_integration.py:833 |
| 102 | every Slack message is a short form, and in a room its long form | the-loop comment with a summary posts the summary to Slack and the whole text to GitHub | docs/specs/issue-549/requirements.md R3.1, R3.2, R3.8, R4.1 | cli/tests/test_channels_declared_integration.py:865 |
| 103 | progress within a phase edits one message | a progress edit in the central channel edits one message | docs/specs/issue-549/requirements.md R6.1 | cli/tests/test_channels_declared_integration.py:919 |
| 104 | progress within a phase edits one message | a progress edit with fewer parts deletes the surplus | docs/specs/issue-549/requirements.md R6.1, R6.2 | cli/tests/test_channels_declared_integration.py:951 |
| 105 | approve from Slack at every human gate | a gate opened under a lowercased ref posts its buttons in the work item's own thread | docs/specs/issue-549/requirements.md R11.1, R11.2 | cli/tests/test_channels_declared_integration.py:1091 |
| 106 | approve from Slack at every human gate | a press in a declared room approves the gate | docs/specs/issue-549/requirements.md R11.4 | cli/tests/test_channels_declared_integration.py:1136 |
| 107 | approve from Slack at every human gate | a channel that cannot receive a press shows how to approve on GitHub | docs/specs/issue-549/requirements.md R11.5 | cli/tests/test_channels_declared_integration.py:1199 |
| 108 | approve from Slack at every human gate | a gate answered on GitHub edits its Slack message to show the outcome | docs/specs/issue-549/requirements.md R11.6 | cli/tests/test_channels_declared_integration.py:1382 |
| 150 | — | A long agent comment reaches the central channel as its short form | docs/specs/issue-549/requirements.md R1.1, R2.7, R3.4, R4.2 | cli/tests/test_channels_integration.py:1846 |
| 151 | — | A short comment reaches Slack untouched | docs/specs/issue-549/requirements.md R2.7, R3.5 | cli/tests/test_channels_integration.py:1893 |
| 152 | — | A notification's artifact is not digested onto the message | docs/specs/issue-549/requirements.md R1.1, R3.5, R4.2 | cli/tests/test_channels_integration.py:1922 |
| 186 | a retried delivery never posts twice | an outbox replay after a partial delivery posts only the missing parts | docs/specs/issue-549/requirements.md §Non-functional requirements | cli/tests/test_channels_outbox_integration.py:217 |
| 345 | one Slack app serves every instance through the gateway | the gateway proxy forwards reactions.remove and chat.delete | docs/specs/issue-549/requirements.md#requirement-6 (R6.2), R8 | cli/tests/test_gateway_slack_integration.py:468 |
| 402 | graph verbs name the work item as its ticket does | a verb with no --ref takes owner and repo from the registration | docs/specs/issue-549/requirements.md R11.2 | cli/tests/test_graph_refs_integration.py:227 |
