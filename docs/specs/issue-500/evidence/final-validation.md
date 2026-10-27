---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#500"
---

# Final validation: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

> The `evidence` node's proof: each acceptance criterion of `bugfix.md`, mapped to how the
> executed `testing-plan.md` proved it. Summarised from the plan's Verification results.
> The full suite and `make check` are green: 6789 passed, with lint, format, type check
> and validate clean.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 — a repeated heading is given a text no existing `###` heading carries | T2 `test_a_gate_approved_twice_on_one_day_records_distinct_headings` (red on the pre-fix hook); T11 markdownlint finds 0 errors on an artifact recorded three times, and two MD024 errors on the pre-fix shape | [integration.md](integration.md), [markdownlint.md](markdownlint.md) |
| R1.2 — a first recording is written exactly as before | T2 full-match `<YYYY-MM-DD> — approved` on the first heading; the issue-247 scenarios unchanged in T12 | [integration.md](integration.md), [lint-and-typecheck.md](lint-and-typecheck.md) |
| R1.3 — N same-day recordings are distinct; the n-th carries `(n)` | T2 asserts `[base, base (2), base (3)]` | [integration.md](integration.md) |
| R2.1 — append-only, attribution and body as issue-247 left them | T2 byte-prefix assertions; the issue-247 tests pass in T12 | [lint-and-typecheck.md](lint-and-typecheck.md) |
| R2.2 — no existing heading is rewritten or renumbered | T2: each recording's output starts with the previous output, byte for byte | [integration.md](integration.md) |
| R3.1 — the regression test fails before the fix and passes after | T2 red, then green | [integration.md](integration.md) |
| R3.2 — the test asserts shape; one real linter run backs it | T11 | [markdownlint.md](markdownlint.md) |
| Security — no new attack surface | checklist plus the built-in `security-review`, no findings | [security-review.md](security-review.md) |
