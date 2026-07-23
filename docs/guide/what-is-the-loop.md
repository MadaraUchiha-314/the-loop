# What is the-loop?

**the-loop** is an opinionated product-development-lifecycle (PDLC) harness, shipped as
a plugin for [Claude Code](https://claude.com/claude-code) **and Cursor**. Once a plan
is approved, an agent harness delivers a work item end-to-end with minimal or no human
intervention, escalating to humans only when a decision is genuinely needed.

> **Status: v0 foundation.** This release establishes the plugin skeleton, the
> configuration contract, templates, commands, the operating skill, and the
> documentation/knowledge structure. Runtime automation (webhooks, remote execution, DAG
> orchestration, language-specific tooling) continues to land as follow-up work — see the
> [decision log](/decisions/decision-003).

## The loop, in one line

```text
(brainstorm) → requirements → design → tasks (each iterated until locked + human-reviewed)
  → implement (+self-check) → self/critic review → evidence → complete → learn
```

A work item is a chain of artifacts, each derived from the one before it and **iterated
with feedback until it is locked** before the loop advances. Optionally it starts with a
free-form `brainstorm.md` scratchpad (the root artifact); then it is specified with a
[Kiro-style](https://kiro.dev/docs/specs/) 3-phase spec (`requirements.md` →
`design.md` → `tasks.md`), each gated by a human review, then executed autonomously.
Each work item's phase is tracked on the ticket via labels:

```text
not-started → brainstorming (optional) → requirements-definition → design
  → tasks-breakdown → implementation → needs-review → complete
```

## Rules the loop enforces

- Every work item has a ticket. Its 3-phase spec is **reviewed and approved per phase
  before execution**.
- Collaborators are identified up-front; not every task needs every persona.
- Every human decision leaves a **paper trail** on the ticket or PR.
- Self-checks run tests at logical checkpoints; progress is logged for visibility.
- Configured self-reviews and critic reviews run **before** escalating to a human.
- The same tooling runs locally and in CI; logging is identical at dev-time and runtime.
- Integration tests document their scenario in **Gherkin** docstrings, queryable as a
  table via `the-loop scenarios`.
- APIs are **contract-first**: REST specs in `specs/openapi/` (OpenAPI), GraphQL SDL in
  `specs/graphql/`; docs are generated from the contracts, never hand-written.
- **Capability docs are the organized view of specs**: per-work-item specs are the
  historical record; living docs under [`developer/capabilities`](/capabilities/capabilities)
  are the single source of truth for each capability's *current* behaviour, updated in
  the same PR as the work item.
- **UI/UX design is a first-class artifact**: for user-facing work the design phase
  tracks Figma links and/or self-contained HTML+CSS+JS prototypes, iterated-until-locked
  with the designer.
- All commits follow **Conventional Commits**.
- PRs are written **for the reviewer**: a condensed, prioritized summary, **mermaid**
  diagrams, and documented low-level decisions — and the loop educates the user on those
  decisions (mandatory, not optional).

Next: [install the plugin](/guide/installation) or jump straight to the
[quickstart](/guide/quickstart).
