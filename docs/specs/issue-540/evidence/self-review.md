---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#540"
---

# Self-review: prompts in Markdown files, application strings in one JSON catalog

> Policy (`the-loop critic policy`): `selfReviewCount: 2`, `stopOnNoNewFindings: true`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | claude/claude-opus-5-5 (author session) | new findings | **F1** Moving `CONTROL_REFUSAL_REMEDIES` to JSON dropped the per-code rationale comments (issue-344 hook semantics), because JSON holds no comments → fixed: a code-side legend above the `strings.section` call says what each code means. **F2** R1.1 said "every prompt" while the design deliberately leaves five kinds of agent-facing text inline → fixed: requirements § Out of scope lists them with reasons, and follow-up #542 covers the two that should still move. Checked, no finding: the schema's `promptTemplate`/`spawnTemplate` descriptions ("falls back to a built-in default") are still true, so the sensitive schema file is untouched. A helper named `_text` collided with an existing `cimonitor._text` (caught by tests during implementation; renamed `_prose`), and a slot called `name` clashed with the helpers' own parameter → all four helpers are positional-only. | this file |
| 2 | claude/claude-opus-5-5 (author session) | zero (converged) | Re-read the diff against R1–R3 and the abuse cases. Every `prompts.render`/`strings.t` call passes a literal name or key, or a key built from a code validated against a fixed set first (`prnotice` decline codes go through `DECLINE_REASONS.get`; Slack/quiz titles go through `.get` on a dict built from the catalog). No request data reaches a name or key. Substitution is single-pass, and the render grid fed `{x}`/`$x` values: 66,174 old-vs-new renders are identical. The directive still renders above the labelled payload excerpt, and `apply_directive`'s fail-safe and tests are unchanged. A missing prompt file raises at import of the module that loads it, so a broken install fails at daemon start, not mid-session. Locale changes after import do not reach the module-level dictionaries; this is documented in the capability doc. No new findings. | this file |
