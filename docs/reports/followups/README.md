# Follow-up tickets from the e2e Slack test

These are the items from
[`docs/reports/e2e-slack-test-2026-09-19.md`](../e2e-slack-test-2026-09-19.md)
that the issue-393 PR did **not** fix — captured here as ready-to-file GitHub
issues (a title line and a body). Everything else from the report — B1, B2, B3,
B4, B6, B8, B9, B10, **B11**, F1, F2, F3, and observations O2/O3/O8 — was fixed in
that PR.

| File | Item(s) | Kind |
|------|---------|------|
| [`b5-read-mode-hot-reload.md`](b5-read-mode-hot-reload.md) | B5 | bug — filed as [#395](https://github.com/MadaraUchiha-314/the-loop/issues/395), fixed |
| [`b7-graph-status-stale-node.md`](b7-graph-status-stale-node.md) | B7, O6 | bug — filed as [#396](https://github.com/MadaraUchiha-314/the-loop/issues/396), fixed |
| [`o7-phantom-prompt-text.md`](o7-phantom-prompt-text.md) | O7 | investigation — **hazard fixed** (clear input line before delivery) |
| [`o9-merge-on-approval-knob.md`](o9-merge-on-approval-knob.md) | O9 | enhancement — **fixed** (`routing.mergeOnApproval` + stated consequence) |
| [`minor-observations-o1-o4-o5.md`](minor-observations-o1-o4-o5.md) | O1, O4, O5 | polish — filed as [#397](https://github.com/MadaraUchiha-314/the-loop/issues/397) |

The 2026-09-20 re-run
([`docs/reports/e2e-slack-test-2026-09-20.md`](../e2e-slack-test-2026-09-20.md))
validated the issue-393 fixes live and added its own findings — **all fixed on
branch `fix/n1-selection-grammar-refusal-reason`:**

| File | Item(s) | Kind | Status |
|------|---------|------|--------|
| [`n1-execute-without-refused-live.md`](n1-execute-without-refused-live.md) | N1 (F1 regression) | bug | **fixed** — distinct drop reasons + refusal mirrored to the ticket |
| [`n2-room-policy-rules-not-suppressing.md`](n2-room-policy-rules-not-suppressing.md) | N2 | bug | **fixed** — gate-collapse for progress + nodeless mirror, operator-docs by text, endgame-collapse |
| [`n3-critic-and-summary-and-docs.md`](n3-critic-and-summary-and-docs.md) | B9 remainder, `--summary`/`--default` adoption, mention-less connectors | bug / enhancement / docs | **fixed** — timeout surfacing, skill guidance, channels doc |

The 2026-09-20 **run 3**
([`docs/reports/e2e-slack-test-2026-09-20-run-3.md`](../e2e-slack-test-2026-09-20-run-3.md))
validated the PR #402 fixes on 19.8.3 and recorded two findings — filed together as
[#405](https://github.com/MadaraUchiha-314/the-loop/issues/405), **fixed**:

| File | Item(s) | Kind | Status |
|------|---------|------|--------|
| [`p1-execute-without-reads-past-the-phase-list.md`](p1-execute-without-reads-past-the-phase-list.md) | P1 (N1/F1 regression) | bug | **fixed** — signature and markup stripped, refusal by position, distinct drop reasons, `read` on the record |
| [`p2-close-path-races-the-endgame.md`](p2-close-path-races-the-endgame.md) | P2 | bug | **fixed** — a closure at the terminal node is held for `finishGraceSeconds` or the completion claim; `merged` from the state file |

Each file's first `#` heading is the suggested issue title; the rest is the body.
Quotes are drawn verbatim from the report, with the internal deployment kept in
the report's placeholder form (`<host>`, `<test-repo>` …).
