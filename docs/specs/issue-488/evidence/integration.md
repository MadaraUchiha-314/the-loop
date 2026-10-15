# T2 · integration scenarios — issue-488

**Outcome: pass.** All 22 tests in the two files pass. Together they cover the six
doorbell scenarios, the quiz-gate e2e scenarios, and the existing e2e walks with their
updated node traces.

## Commands

```sh
cd cli && env -u THE_LOOP_CLI_CONFIG uv run python -m pytest -q tests/test_quiz_integration.py tests/test_pdlc_e2e_integration.py
uv run the-loop scenarios --root . --glob 'cli/tests/test_quiz_integration.py' --glob 'cli/tests/test_pdlc_e2e_integration.py' --format markdown
```

`THE_LOOP_CLI_CONFIG` is unset because this machine's operator config, and the running
daemon it names, otherwise leaks into the suite. Without the unset, 21 tests about the
poll command, poll status, instances, lifecycle and critics fail on an unchanged `main`
checkout too, so they are not this change's.

## Run

```text
22 passed in 0.48s
```

## Scenarios (as `the-loop scenarios` renders them)

The issue-488 rows are the six in `test_quiz_integration.py`, plus "review is not
requested until the code quiz is ticked" and the three `quiz-gates` rows. Unticking the
`explainer` row is exercised by the existing `trivial-tier` scenario: its trace now
records `spec-explainer~`, `spec-quiz~`, `code-explainer~` and `code-quiz~`. No separate
`explainer-off` scenario was added, which narrows the testing plan's T4 wording.

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | a tick alone answers a quiz gate, and nothing else. | a ticked box re-evaluates the waiting gate without delivering a prompt | docs/specs/issue-488/requirements.md#R2.6 | cli/tests/test_quiz_integration.py:54 |
| 2 | a tick alone answers a quiz gate, and nothing else. | a quiz tick on a work item with no waiting gate spawns nothing | docs/specs/issue-488/design.md#C5 | cli/tests/test_quiz_integration.py:72 |
| 3 | a tick alone answers a quiz gate, and nothing else. | a tick the gate could not judge is retried on the next poll | docs/specs/issue-488/design.md#Error handling | cli/tests/test_quiz_integration.py:93 |
| 4 | a tick alone answers a quiz gate, and nothing else. | a tick by an authorized user advances the spec quiz | docs/specs/issue-488/requirements.md#R2.6, R3.8 | cli/tests/test_quiz_integration.py:126 |
| 5 | a tick alone answers a quiz gate, and nothing else. | only the-loop's own ticked quiz comment rings | docs/specs/issue-488/requirements.md abuse case 6 | cli/tests/test_quiz_integration.py:140 |
| 6 | a tick alone answers a quiz gate, and nothing else. | a work item with no live session has no gate to ring | docs/specs/issue-488/design.md#C5 | cli/tests/test_quiz_integration.py:154 |
| 7 | PDLC process conformance, end to end | a tier-3 work item flows ticket → complete with no interventions | docs/specs/issue-217/requirements.md#R1, #R2.3 | cli/tests/test_pdlc_e2e_integration.py:64 |
| 8 | PDLC process conformance, end to end | review is not requested until the code quiz is ticked | docs/specs/issue-488/requirements.md#R3.6, #R3.7 | cli/tests/test_pdlc_e2e_integration.py:75 |
| 9 | PDLC process conformance, end to end | a trivial-tier item completes with declared skips recorded as skips | docs/specs/issue-217/requirements.md#R2.3 | cli/tests/test_pdlc_e2e_integration.py:89 |
| 10 | PDLC process conformance, end to end | a tick by an unauthorized user is refused | docs/specs/issue-488/requirements.md#R2.5 (abuse cases 1, 4) | cli/tests/test_pdlc_e2e_integration.py:105 |
| 11 | PDLC process conformance, end to end | a changed spec sends the spec quiz back to the explainer | docs/specs/issue-488/requirements.md#R5.6 | cli/tests/test_pdlc_e2e_integration.py:110 |
| 12 | PDLC process conformance, end to end | a tick by an authorized user advances the spec quiz | docs/specs/issue-488/requirements.md#R2.6 | cli/tests/test_pdlc_e2e_integration.py:115 |
| 13 | PDLC process conformance, end to end | the agent escalates via the ask seam and the operator's reply resumes it | docs/specs/issue-217/requirements.md#R2.3 | cli/tests/test_pdlc_e2e_integration.py:128 |
| 14 | PDLC process conformance, end to end | a malformed artifact fails the phase gate rather than silently advancing | docs/specs/issue-217/requirements.md#R2.3, issue-281 AC 1.1 | cli/tests/test_pdlc_e2e_integration.py:142 |
| 15 | PDLC process conformance, end to end | a changes-requested verdict loops the run back to the design phase | docs/specs/issue-217/requirements.md#R2.3 | cli/tests/test_pdlc_e2e_integration.py:156 |
| 16 | PDLC process conformance, end to end | gh unreachable — events still emitted, side effects reported degraded | docs/specs/issue-217/requirements.md#R3.3 | cli/tests/test_pdlc_e2e_integration.py:171 |
| 17 | PDLC process conformance, end to end | marked and unauthorized comments are never classified as human input | docs/specs/issue-217/requirements.md#R2.3, security consideration 2 | cli/tests/test_pdlc_e2e_integration.py:185 |
| 18 | PDLC process conformance, end to end | scenario directories and named tests stay in lockstep | docs/specs/issue-217/requirements.md#R2.1, #R2.2 | cli/tests/test_pdlc_e2e_integration.py:201 |
| 19 | PDLC process conformance, end to end | every committed fixture set is well-formed | docs/specs/issue-217/requirements.md#R2.2 | cli/tests/test_pdlc_e2e_integration.py:212 |
| 20 | PDLC process conformance, end to end | a scenario directory without scenario.yaml is refused, not skipped | docs/specs/issue-217/requirements.md#R2.2 | cli/tests/test_pdlc_e2e_integration.py:224 |
| 21 | PDLC process conformance, end to end | an unknown step kind fails the scenario naming file and field | docs/specs/issue-217/requirements.md#R2.2, security consideration 1 | cli/tests/test_pdlc_e2e_integration.py:236 |
| 22 | PDLC process conformance, end to end | a step naming an absent fixture file is refused at load time | docs/specs/issue-217/requirements.md#R2.2 | cli/tests/test_pdlc_e2e_integration.py:252 |
| 23 | PDLC process conformance, end to end | the ordered-subsequence matcher names the first missing event | docs/specs/issue-217/requirements.md#R1.3, #R1.4 | cli/tests/test_pdlc_e2e_integration.py:269 |
| 24 | PDLC process conformance, end to end | a walk that diverges from the expected trace fails, naming the divergence | docs/specs/issue-217/requirements.md#R1.3, #R1.4 | cli/tests/test_pdlc_e2e_integration.py:288 |
| 25 | PDLC process conformance, end to end | the hermeticity tripwire — an unmodelled operation raises | docs/specs/issue-217/requirements.md#R3.1, security consideration 3 | cli/tests/test_pdlc_e2e_integration.py:316 |
