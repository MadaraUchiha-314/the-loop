# Evidence: the budget experiment (rejected approach, kept as the record)

Work item: issue-165. This measurement is **not** a passing check — it is the record of an
approach that was tried and rejected, kept because it is the evidence *for* rejecting it.

## What happened

This work item first shipped per-artifact word budgets. The owner rejected them in review
on PR #168 — *"we don't know the scope of each work item, so how can we put budgets on
requirements.md or design.md?"* — and they are gone from the schema, the configs, the
templates and the test.

Three of the eight budgets had to be renegotiated before the change could merge, which is
the argument in miniature:

| Budget | What the measurement showed |
|---|---|
| `tasks: 200` | Unreachable from its own empty template — 274 words of guidance prose. Raised to 400. |
| `requirements: 500` · `design: 900` | The actual artifacts ran 682 and 1017. Both cut. |
| `prBriefing: 400` | The PR briefing ran ~530 carrying only the education the R10 gate requires. Recorded as a deliberate overrun. |

A number renegotiated by every artifact that meets it is not a policy. See
[decision-061](../../../decisions/decision-061.md) §D2.

## The run

`prose_words()` no longer exists — it was removed with the budgets. The figures below are
the run from before that removal, at commit `b74f0fd`.

```console
$ prose_words() from cli/tests/test_writing_parity.py, applied to what this PR ships

artifact                                       words  budget  status
docs/specs/issue-165/brainstorm.md               659       0  unbudgeted by design
docs/specs/issue-165/requirements.md             453     500  ok
docs/specs/issue-165/design.md                   886     900  ok
docs/specs/issue-165/testing-plan.md             133     400  ok
docs/specs/issue-165/tasks.md                    264     400  ok
docs/specs/issue-165/execution-log.md            577       0  unbudgeted by design
docs/decisions/decision-061.md                   236     400  ok
docs/decisions/decision-062.md                   389     400  ok
docs/capabilities/writing-style.md               344     700  ok
skills/writing/SKILL.md                          544     600  ok

Shipped templates (P6 — the scaffold must fit the budget it declares):
template                                       words  budget  status
skills/the-loop/templates/bugfix.md              114     500  ok
skills/the-loop/templates/capability.md           85     700  ok
skills/the-loop/templates/decision.md             69     400  ok
skills/the-loop/templates/design.md              286     900  ok
skills/the-loop/templates/pr-briefing.md         102     400  ok
skills/the-loop/templates/requirements.md        143     500  ok
skills/the-loop/templates/tasks.md               274     400  ok
skills/the-loop/templates/testing-plan.md        126     400  ok
```
