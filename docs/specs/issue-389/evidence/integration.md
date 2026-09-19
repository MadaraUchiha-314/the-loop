---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Integration scenarios (T2): the listener, the pipeline and the CLI forms end to end

> Row T2 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. Every Slack call goes
> through the fake client (`client_factory`), every ledger write through the fake writer
> (`post_comment`), every session delivery through the injected `deliver`. Run at the
> PR's head on 2026-09-19.

## Command

```bash
cd cli && uv run python -m pytest -q tests/test_channels_mentions_integration.py tests/test_channels_shortcuts_integration.py tests/test_collaborators_cli.py tests/test_workchannels_cli.py tests/test_channels_records_integration.py
```

## Outcome

**69 passed** in 0.75 s.

## Scenario table

`the-loop scenarios --root . --glob 'cli/tests/test_channels_mentions_integration.py' --glob 'cli/tests/test_channels_shortcuts_integration.py' --glob 'cli/tests/test_channels_records_integration.py' --format markdown`
(the requirement column is filled where the docstring names one; each file's
module docstring names its requirement for the rest):

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | a Slack conversation reaches the-loop only when addressed | a message without the mention leaves no trace | R1 | `cli/tests/test_channels_mentions_integration.py:160` |
| 2 | a Slack conversation reaches the-loop only when addressed | a mention in a mentions room is input | R1 | `…mentions_integration.py:180` |
| 3 | a Slack conversation reaches the-loop only when addressed | a mention under the-loop's own question is input and a plain reply there is not | R1 | `…mentions_integration.py:203` |
| 4 | a Slack conversation reaches the-loop only when addressed | a mention with a keyword composes the configured keyword | R3 | `…mentions_integration.py:241` |
| 5 | a Slack conversation reaches the-loop only when addressed | a mentioned top-level message in the central channel is a kickoff | R1 | `…mentions_integration.py:259` |
| 6 | a Slack conversation reaches the-loop only when addressed | a redelivered mention is processed once | R1 | `…mentions_integration.py:294` |
| 7 | a Slack conversation reaches the-loop only when addressed | a DM hears a plain message | R1 | `…mentions_integration.py:314` |
| 8 | a Slack conversation reaches the-loop only when addressed | an all room hears a plain message | R2 | `…mentions_integration.py:338` |
| 9 | a Slack conversation reaches the-loop only when addressed | poll mode reads no mention-gated conversation and moves no cursor | R1 | `…mentions_integration.py:363` |
| 10 | a Slack conversation reaches the-loop only when addressed | help answers ephemerally and records nothing | R3 | `…mentions_integration.py:397` |
| 11 | a Slack conversation reaches the-loop only when addressed | record-context snapshots a thread onto the ticket and into the session | R4 | `…mentions_integration.py:434` |
| 12 | a Slack conversation reaches the-loop only when addressed | record-context on a top-level message records its thread, never the mention | R4 | `…mentions_integration.py:475` |
| 13 | a Slack conversation reaches the-loop only when addressed | a second record-context records only what is new | R4 | `…mentions_integration.py:501` |
| 14 | a Slack conversation reaches the-loop only when addressed | record-decision lands as a marked record and a decision frame | R5 | `…mentions_integration.py:573` |
| 15 | a Slack conversation reaches the-loop only when addressed | a collaborator may add context but not a decision | R7 | `…mentions_integration.py:627` |
| 16 | a Slack conversation reaches the-loop only when addressed | a roster on one work item widens nothing on another | R7 | `…mentions_integration.py:693` |
| 17 | a message shortcut is exactly the typed mention | the context shortcut is the typed mention | R6 | `cli/tests/test_channels_shortcuts_integration.py:124` |
| 18 | a message shortcut is exactly the typed mention | the decision shortcut opens the modal and the submission is the typed mention | R6 | `…shortcuts_integration.py:163` |
| 19 | a message shortcut is exactly the typed mention | a shortcut acts once per trigger | R6 | `…shortcuts_integration.py:219` |
| 20 | a message shortcut is exactly the typed mention | the listener routes app_mention, message_action and view_submission | R1, R6 | `…shortcuts_integration.py:277` |
| 21 | a message shortcut is exactly the typed mention | Slack's own payload shapes drive the three handlers | R1, R6 | `…shortcuts_integration.py:342` |
| 22 | a session finds the records it has not folded | channels records lists the enveloped records of a work item | R4.7, R5.6 | `cli/tests/test_channels_records_integration.py:5` |

The CLI forms `add-collaborator --slack` and `add-channel --listen` are covered by
`test_collaborators_cli.py` and `test_workchannels_cli.py` in the same run (R2.1, R7.1).

## Fixtures

The three payload shapes the plan's environment names are checked in under
`cli/tests/fixtures/slack/` — `app_mention.json`, `message_action.json`,
`view_submission.json` — with team, app, trigger and token values replaced by
placeholders; scenarios 20 and 21 read them.
