# Evidence: the API contract and the scenario table (issue-239)

Testing-plan row **T4**. `apiSpecs` makes the OpenAPI document the authored source of
truth and the docs generated from it, so what is verified here is that the served surface
and the checked-in contract agree.

## The served schema matches the authored contract

```text
..                                                                       [100%]
2 passed in 0.58s
```

## The contract describes the stream

```yaml
operationId: streamEvents
parameters:
- workItem
- transcript
- Last-Event-ID
responses:
  '200':
  - text/event-stream
  '400': (no body)
  '404': (no body)
  '503': (no body)
  '422':
  - application/json
```

`text/event-stream` alone on the 200. The first attempt at this offered **both** that and
`application/json`, because FastAPI infers a JSON response from the return annotation and
merges it with a declared one — so the published contract described a media type the route
never sends. `response_class=StreamingResponse` on the decorator is what makes the inferred
half agree with the declared half. Caught by reading this evidence file, not by a test:
the parity test compares paths, methods and operation ids, and both documents were equally
wrong.

## The config schema validates, and the packaged copy is the authored one

```text
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
........                                                                 [100%]
8 passed in 0.04s
```

`test_docs_parity` P4 is the one that matters for this work item: every leaf of the config
schema must be documented, so `service.stream`'s three keys could not have been added
without the reference section that describes them.

## The Gherkin scenarios this work item added

`the-loop scenarios` renders every integration test's Gherkin docstring as a queryable
table (`testing.gherkinDocstrings`). All 13 of this work item's scenarios are registered,
each naming the requirement it proves:

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 254 | the control plane learns without asking | an event is appended while a subscriber is connected | docs/specs/issue-239/requirements.md R1.1, R1.2 | cli/tests/test_stream_integration.py:171 |
| 255 | a subscriber sees only what it asked for | two work items are active and the subscriber filters to one | docs/specs/issue-239/requirements.md R1.3 | cli/tests/test_stream_integration.py:200 |
| 256 | the stream cannot feed itself | the control plane refreshes while streaming | docs/specs/issue-239/design.md §Trade-offs | cli/tests/test_stream_integration.py:225 |
| 257 | a dropped connection loses nothing | a subscriber reconnects quoting the last frame it saw | docs/specs/issue-239/requirements.md R1.5 | cli/tests/test_stream_integration.py:259 |
| 258 | an idle connection is not reaped, and can be told from a dead one | nothing happens on a connected stream | docs/specs/issue-239/requirements.md R1.4 | cli/tests/test_stream_integration.py:291 |
| 259 | watching a work item does not slow down working one | every allowed stream connection is open and idle | docs/specs/issue-239/requirements.md R5.1 | cli/tests/test_stream_integration.py:332 |
| 260 | an open dashboard cannot starve the service | more connections are opened than the configuration allows | docs/specs/issue-239/requirements.md R5.2 (abuse case 1) | cli/tests/test_stream_integration.py:357 |
| 261 | a closed tab frees its capacity | the only allowed connection is opened and closed | docs/specs/issue-239/requirements.md R5.4 | cli/tests/test_stream_integration.py:380 |
| 262 | a bad cursor is a caller error, not a silent full replay | Last-Event-ID is not a byte offset | docs/specs/issue-239/requirements.md R1.5 (abuse case 3) | cli/tests/test_stream_integration.py:410 |
| 263 | an unparseable filter never widens to "everything" | the workItem parameter is not a work-item ref | docs/specs/issue-239/requirements.md R1.3 (abuse case 3) | cli/tests/test_stream_integration.py:427 |
| 264 | replay cannot be used to read unbounded history | a client resumes from an offset far behind the end of the log | docs/specs/issue-239/requirements.md R1.5 (abuse case 4) | cli/tests/test_stream_integration.py:447 |
| 265 | a deployment can narrow itself to REST-only | service.stream.enabled is false | docs/specs/issue-239/requirements.md R1.1, R4.1 | cli/tests/test_stream_integration.py:469 |
| 266 | the event log answers "who was watching, and what was refused?" | a connection is opened, a second refused, and the first closed | docs/specs/issue-239/requirements.md §Non-functional (observability) | cli/tests/test_stream_integration.py:491 |

A note on the command, since the next person will hit it: `--root .` resolved to a
completely different repository on this machine, and `--root "$(pwd)"` was needed. Not
this work item's defect, and not investigated here.
