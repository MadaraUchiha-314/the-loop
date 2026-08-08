# Evidence — walkthrough (issue-179)

The ticket's scenario, end to end, against the **shipped** `pdlc-work-item-loop` in a
temporary repository. The GitHub integration is faked in-process (an object serving
`list-comments` and recording `add-comment`); nothing touches the network and no
credentials are involved.

## The operator's half: `the-loop graph skip`

```console
$ the-loop graph --repo <tmp> skip issue-9 \
    --node spec-chain --node review-chain --node phase-selection \
    --reason "docs-only change: no spec chain, no review chain" --actor "@MadaraUchiha-314"
declared: brainstorming will be skipped
declared: requirements-definition will be skipped
declared: requirements-approval will be skipped
declared: design will be skipped
declared: test-planning will be skipped
declared: design-approval will be skipped
declared: tasks-breakdown will be skipped
declared: self-review will be skipped
declared: critic-review will be skipped
declared: security-review will be skipped
declared: evidence will be skipped
declared: capability-docs will be skipped
declared: reviewer-briefing will be skipped
rejected: phase-selection — not a skippable node or shipped skip set
  note: these are declarations, not verdicts — `the-loop check` reports each node as
  'skipped by declaration', and the never-skippable gates still run.
```

Thirteen phases from two tokens — and the one token the vocabulary refuses is
`phase-selection` (R1.2). `the-loop check` on that repository still reports
`UNMET (at phase-selection) · waiting for an authorized user to choose the phases and
reply the-loop execute`: the declarations are recorded, and the loop still will not walk
a single phase until a human answers the gate.

## The usual half: the selection gate

```text
== 1. the loop starts: the gate posts its checklist and waits ==
🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. **Untick anything this
work item does not need — right here on this comment — then reply `the-loop execute`.**
The tick state at that moment is frozen and becomes the graph this item walks.

- [x] brainstorming
- [x] requirements-definition
...
selectable rows: 16

== 2. an authorized human unticks everything a doc fix does not need ==
gate: pass → pointer now at: implementation
declared skips: 13 · provenance: {'via': 'selection', 'token': 'design', 'by': '@owner',
                                  'reason': '', 'at': '2026-08-08T17:19:43+00:00'}

== 3. `the-loop check`: skipped by declaration, never a pass ==
  PASS   phase-selection
  SKIP   brainstorming            skipped by declaration — via selection, token 'brainstorming', by @owner
  SKIP   requirements-definition  skipped by declaration — via selection, token 'requirements-definition', by @owner
  SKIP   requirements-approval    skipped by declaration — via selection, token 'requirements-approval', by @owner
  SKIP   design                   skipped by declaration — via selection, token 'design', by @owner
  SKIP   test-planning            skipped by declaration — via selection, token 'test-planning', by @owner
  SKIP   design-approval          skipped by declaration — via selection, token 'design-approval', by @owner
  SKIP   tasks-breakdown          skipped by declaration — via selection, token 'tasks-breakdown', by @owner

== 4. verification: the plan was declared away, so the gate moves ==
  empty log  → block · required section is empty: Verification results (docs/specs/issue-9/execution-log.md)
  filled log → pass

== 5. the tamper case: a forged declaration on the gate itself ==
  honoured? False
  surfaced as invalid: ['phase-selection']
```

## What each step proves

| Step | Requirement | What it shows |
|---|---|---|
| 1 | R1.1, R1.7 | The checklist offers **16** selectable phases — every node of the loop but `phase-selection` and the terminals — and the loop waits, having walked none of them |
| 2 | R1.8 | One authorized reply records thirteen declarations with provenance (`via`, `token`, `by`, `at`) and the pointer lands on the first phase that survived, `implementation` |
| 3 | R1.8 | Every declared node reports **`SKIP` — skipped by declaration, by whom**, never `pass`. The omissions are the record |
| 4 | R2.2 | With `test-planning` declared away and no `testing-plan.md`, `verification` blocks on the *execution log's* empty `Verification results`, and passes once it holds something. Skipping the plan removed the document, not the verifying |
| 5 | R1.2 | A hand-written declaration on `phase-selection` is not honoured and is surfaced as invalid — the invariant holds against a tampered state file, not merely against the CLI |

*(The run emits `could not sync loop:<phase>: … 403 Forbidden` lines for the phase-label
calls, which reach a real GitHub endpoint with no credentials in this environment. They
are best-effort by design — label sync never gates a node — and are elided above.)*
