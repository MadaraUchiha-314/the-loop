---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Integration scenarios (T2)

The four Gherkin scenarios pass. They drive a real `GatewayClient` attached to a real
`Dispatcher`'s channel store, a real gateway app in-process, and signed Slack HTTP
events. All four fail on `origin/main` code (see [unit.md](unit.md)).

## `uv run python -m pytest -q tests/test_gateway_rooms_integration.py`

```text
4 passed
tests/test_gateway_rooms_integration.py::test_a_collaborators_top_level_message_in_a_declared_room_reaches_the_work_item
tests/test_gateway_rooms_integration.py::test_messages_held_before_the_room_was_published_are_routed_when_it_is
tests/test_gateway_rooms_integration.py::test_clearing_the_declaration_retracts_the_room
tests/test_gateway_rooms_integration.py::test_a_gateway_that_lost_its_store_gets_the_rooms_back_on_re_registration
```

## `uv run the-loop scenarios --glob 'cli/tests/test_gateway_rooms_integration.py' --format markdown`

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | a work item's collaboration channel routes every collaborator's message to it | a collaborator's top-level message in a declared room reaches the work item | docs/specs/issue-505/requirements.md#requirement-2 (R2.2), R1.1, R1.2, | cli/tests/test_gateway_rooms_integration.py:132 |
| 2 | a work item's collaboration channel routes every collaborator's message to it | messages held before the room was published are routed when it is | docs/specs/issue-505/requirements.md#requirement-3 (R3.1) | cli/tests/test_gateway_rooms_integration.py:160 |
| 3 | a work item's collaboration channel routes every collaborator's message to it | clearing the declaration retracts the room | docs/specs/issue-505/requirements.md#requirement-4 (R4.1), R4.3 | cli/tests/test_gateway_rooms_integration.py:185 |
| 4 | a work item's collaboration channel routes every collaborator's message to it | a gateway that lost its store gets the rooms back on re-registration | docs/specs/issue-505/requirements.md#requirement-1 (R1.4) | cli/tests/test_gateway_rooms_integration.py:210 |

The first scenario is the ticket's reproduction. A collaborator who is registered by no
instance posts a top-level mention in the declared room. The gateway records
`subject.routed … by: "claim"` onto `loop-github-o-r-14` instead of
`to: unassigned, by: hold`.
