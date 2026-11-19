---
type: evidence
workItem: issue-543
---

# Dogfood: `graph pr-spec` on PR #546

> Testing-plan row T11, run at commit `08fba802` on 2026-11-19 from the repository root.
> Paths are shown relative to the checkout.

## Outcome: partial, and why

issue-543 is delivered by **one** pull request, #546. By R1.2 a single-PR work item needs
no PR spec. So the verb records `required: false, reason: single-pr`, no PR spec is
written, and the gate cannot go stale here. The planned half of T11 that writes a PR spec
under `docs/specs/issue-543/pr-546/` and shows a stale report cannot run on this work item
without breaking its own rule. T2's second scenario shows that behaviour end to end
instead ([integration.md](integration.md)).

## 1. The verb

The running daemon predates the new route and answers it with a bare `404`, so the verb
ran in-process (`THE_LOOP_SERVICE_LOCAL=1`):

```text
$ the-loop graph pr-spec issue-543 --pr 546 --checkout . --json
{
  "workItem": "issue-543",
  "pullRequest": "github:madarauchiha-314/the-loop#546",
  "recorded": true,
  "record": {
    "version": 1,
    "pullRequest": "github:madarauchiha-314/the-loop#546",
    "required": false,
    "reason": "single-pr",
    "chainDigest": "sha256:bb1ae417d8e735e997027b83f5cfe6df6dd386a0fcb6fde46725021dc30aa510",
    ...
  },
  "recordPath": "docs/specs/issue-543/pr-loops/pr-546/pr-spec.json",
  "findings": []
}
```

The record is committed at
[`pr-loops/pr-546/pr-spec.json`](../pr-loops/pr-546/pr-spec.json).

## 2. The gate, before and after a local chain edit

`pr-spec-current` was evaluated on this checkout at both placements. Then `design.md` was
edited locally, evaluated again, and the edit discarded:

```text
--- before
outer implementation pass {'prSpec': 'not-required'}
inner #546 pass {'prSpec': 'not-required'}
--- after local design.md edit
outer implementation pass {'prSpec': 'not-required'}
inner #546 pass {'prSpec': 'not-required'}
```

A single-PR work item is unaffected by a chain change, as R1.2 and the "single-repository
unaffected" NFR require.

## 3. What dogfooding found

- **Refs that differ only in case.** The ref derived from the checkout's remote is
  lowercase (`madarauchiha-314`), while the daemon's keeps the ticket's case
  (`MadaraUchiha-314`). The hook would have refused the record. Fixed test-first in
  `6001c40c`: refs now compare case-insensitively.
- **A stale service.** A daemon older than the route answers `graph pr-spec` with a bare
  `404` whose detail is empty. `the-loop restart` on a build with this change picks the
  route up. The verb now routes like the harness's GitHub verbs. Because this old service
  sends an empty detail, it is still reported as a bare `404` here.
