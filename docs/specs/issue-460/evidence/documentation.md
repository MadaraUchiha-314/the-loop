---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#460"
---

# Documentation: an orphan tag blocks every release

## Capability docs

**[`docs/capabilities/release-publishing.md`](../../../capabilities/release-publishing.md)**
gains:

- two requirements: the run builds on `main`'s tip, and the commit and tag are pushed
  atomically, with the PR-time test named;
- a design link to this spec;
- a history row for issue-460 that records 19.22.0 as tagged but never published.

## Documentation

- **`release.yml`**: the comments on the two changed steps explain why each one is
  there.
- **`CHANGELOG.md`**: gains the 19.22.0 entry that the orphan bump commit carried.
- **`README.md`** and the skill docs say nothing about release mechanics, so they are
  unchanged.
