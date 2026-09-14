# Specs

Per-work-item **specs** are the historical record of how each change was made. Every
work item under the-loop is a chain of artifacts, produced and locked one phase at a
time (see the [spec workflow](/capabilities/spec-workflow)):

- **`brainstorm.md`** *(optional)* — a free-form scratchpad for a fuzzy idea.
- **`requirements.md`** (or **`bugfix.md`** for bugs) — user stories + EARS acceptance
  criteria and a security-considerations section.
- **`design.md`** — architecture, components, data models, security design, testing
  strategy (and UI/UX artifacts for user-facing work).
- **`tasks.md`** — the DAG of small, verifiable tasks.
- **`evidence/`** — the record each gate leaves: the review rounds, the security
  verdict, the docs touched, the pull requests. Work items before
  [issue-365](https://github.com/MadaraUchiha-314/the-loop/issues/365) carry an
  `execution-log.md` instead; it is history, and nothing reads it.

These are the *raw history*. The organized, current-behaviour view lives under
[capabilities](/capabilities/capabilities), which links back here for provenance.

**Browse every work item's spec in the sidebar** (each `issue-<n>` group), or use search.
The list is generated from the repository, so it always reflects what's on disk.
