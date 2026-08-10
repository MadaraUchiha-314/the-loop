# Evidence — the end-to-end scenarios (issue-203)

Row T2 of [`../testing-plan.md`](../testing-plan.md). What the unit tests cannot show:
that a value written in a config file is the URL the `notify` hook's HTTP request actually
carries. `urllib.request.urlopen` is patched in-process and the recorded request target is
asserted — the-loop does not test Slack, it tests where it points.

## Run

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_slack_url_integration.py -v
collected 3 items

cli/tests/test_graph_slack_url_integration.py ...                        [100%]

============================== 3 passed in 0.03s ===============================
```

## Scenarios, as the harness sees them

`the-loop scenarios` reads the Gherkin docstrings out of the integration tests, so these
rows are generated from the tests themselves rather than restated here:

| # | Feature | Scenario | Requirement | Location |
|---|---------|----------|-------------|----------|
| 84 | Slack notifications are configurable inside the-loop's own config | a notification is delivered to the URL configured inline | `docs/specs/issue-203/requirements.md#R1` | `cli/tests/test_graph_slack_url_integration.py:75` |
| 85 | Slack notifications are configurable inside the-loop's own config | a configuration with no inline url still reads the environment | `docs/specs/issue-203/requirements.md#R3` | `cli/tests/test_graph_slack_url_integration.py:95` |
| 86 | Slack notifications are configurable inside the-loop's own config | an unresolvable webhook url fails closed without wedging the graph | `docs/specs/issue-203/requirements.md#R2` | `cli/tests/test_graph_slack_url_integration.py:113` |

Scenario 84 sets **both** sources and asserts the request went to the configured one —
precedence proved by the delivered request, not by the resolver's return value.

## Red before green

With the two implementation files stashed and the tests left in place:

```console
$ git stash push cli/the_loop/graph/integrations/base.py \
                 cli/the_loop/graph/integrations/slack.py
$ uv run --project cli python -m pytest -q cli/tests/test_graph_slack_url_integration.py
WARNING  the-loop.graph:sideeffects.py:187 notification not delivered:
         slack has no webhook url — set THE_LOOP_SLACK_WEBHOOK_URL
FAILED …::test_a_notification_is_delivered_to_the_url_configured_inline
FAILED …::test_with_neither_source_nothing_is_posted_and_the_graph_continues
2 failed, 1 passed in 0.06s
```

Two of three fail without the change; the third —
`test_a_configuration_with_no_inline_url_still_reads_the_environment` — is the
regression guard for R3 and is correctly green on both sides. The captured warning is also
the old error message, which is what row T2 of the second failure is about: it named one
remedy where two exist.
