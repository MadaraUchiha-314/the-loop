---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#500"
status: draft                # draft | in-review | approved
approvedBy: []
severity: low                # low | medium | high | critical
collaborators: [engineer]    # a simple bug usually needs only the engineer
overrides: {}
---

# Bugfix spec: record-feedback appends duplicate sibling headings when a gate is approved twice on one day

> Phase 1 of 3 for a bug (bugfix → design → tasks). The author declared
> `requirements-approval` skipped at phase selection, so this spec is reviewed on the
> pull request rather than at a gate.

## Summary

When one gate records feedback into the same artifact twice on the same day,
`record-feedback` writes the same `### <date> — <outcome>` heading twice under
`## Review comments`. markdownlint's **MD024** (`siblings_only: true` in this repository)
rejects the second one, so the gate's own output breaks `make lint` on an artifact the
session is not supposed to edit. Ticket:
[#500](https://github.com/MadaraUchiha-314/the-loop/issues/500).

Observed on issue-496: the requirements were re-gated after an amendment
(`the-loop graph force … --to requirements-definition`) and approved again the same day.
`docs/specs/issue-496/requirements.md` now carries two `### 2026-10-18 — approved`
headings. It passes lint today only because a `markdownlint-disable-next-line MD024`
comment was added by hand above the second one — a per-incident workaround, not a fix.

## Steps to reproduce

1. Walk a work item to a gate that records into an artifact (`requirements-approval`,
   `design-approval`).
2. Approve it; `record-feedback` appends `### <today> — approved`.
3. Send the item back through the gate the same day (a forced re-gate, or
   `changes-requested` followed by approval) and approve again.
4. The artifact now holds two identical `###` headings under `## Review comments`;
   `make lint` → `MD024/no-duplicate-heading`.

## Expected vs actual

- **Expected:** every review block the hook appends has a heading no sibling already
  carries, so recording a review is never a lint event.
- **Actual:** the heading is built only from `date.today()` and the outcome, so any two
  same-outcome reviews on one day collide.

## Root cause (confirmed)

`cli/the_loop/graph/hooks/feedback.py`, `record_feedback`:

```python
entry = [f"\n### {date.today().isoformat()} — {outcome}\n"]
```

The heading text has a resolution of one day and one outcome. The hook never looks at the
headings already in the file, so nothing stops it repeating one. It is the same class of
defect as issue-247 (MD036): machine-written markdown assembled without asking what the
linter will make of it.

## Requirements

### Requirement 1 — a recorded review never repeats a sibling heading

#### Acceptance criteria (EARS)

1. WHEN `record-feedback` appends a review block AND the artifact already contains a
   `###` heading with the same text THEN the hook SHALL give the new heading a text no
   existing `###` heading in the artifact carries.
2. WHEN no heading with that text exists THEN the hook SHALL write the heading exactly as
   today (`### <YYYY-MM-DD> — <outcome>`), so first-time recordings and every artifact
   already on disk are unchanged.
3. WHEN the same gate records N same-outcome reviews on one day THEN the N headings SHALL
   be pairwise distinct, and each repeat SHALL say which recording of that heading it is
   (the n-th carries `(n)`).

### Requirement 2 — the rest of the record is untouched

1. The fix SHALL keep the block append-only, under the artifact's own
   `## Review comments` section, with the attribution and body exactly as issue-247 left
   them.
2. The fix SHALL NOT rewrite or renumber any heading already in the artifact.

### Requirement 3 — proven, and kept proven

1. The fix SHALL include a regression test that fails before it and passes after it:
   two approvals recorded into one artifact on one day produce distinct `###` headings.
2. As with issue-247, the test SHALL assert the emitted shape (no duplicate `###`
   heading texts) rather than shell out to the linter; one verification-time run of the
   real linter over a twice-recorded artifact is the evidence that the shape is right.

## Security considerations

- The bug is not security-relevant: it produces a lint failure, not an exposure.
- **No new attack surface.** The fix reads the artifact the hook already reads and
  changes only the text of the heading the hook itself writes. The heading's inputs stay
  the date and the classifier's outcome (a closed set, `OUTCOMES`) plus a number the hook
  computes; no comment text, author or other untrusted input reaches the heading. Who may
  approve, what is classified and what is recorded are all unchanged.

## Out of scope

- Removing the hand-added `markdownlint-disable-next-line MD024` comment from
  `docs/specs/issue-496/requirements.md`. That artifact is approved and locked; the
  comment is harmless and documents the incident. Requirement 2.2 also forbids the hook
  from touching existing headings.
- A reviewer's own comment body that fails lint (issue-247 decided the harness never
  rewrites a human's words).

## Open questions

None.
