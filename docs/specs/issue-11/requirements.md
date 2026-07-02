---
type: requirements
phase: requirements-definition
workItem: issue-11
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
collaborators: [architect, engineer]
overrides: {}
---

# Requirements: Integration tests and OpenAPI specs

> **Source of truth:** GitHub [issue #11](https://github.com/MadaraUchiha-314/the-loop/issues/11)
> is the canonical requirements input for this work item. This file distills it into
> reviewable, testable requirements. Design and the task DAG live in `design.md` and
> `tasks.md`.

## Introduction

the-loop should make integration-test coverage *queryable* by a coding-agent harness and
make API contracts *declarative* (spec-first). This work item codifies both as loop
conventions, driven by config, with a CLI command that extracts and tabulates the tested
scenarios.

## Requirements

### R1 — Gherkin scenario docstrings on integration tests

**User story:** As a harness (or reviewer), I want every integration test to state its
scenario in a structured docstring, so that coverage is self-describing and traceable.
1. Every integration test SHALL have the scenario being tested listed in Gherkin-like
   syntax (`Feature:` / `Scenario:` / `Given`-`When`-`Then`) as a docstring (or the
   language's nearest comment equivalent).
2. IF a test is linked to a `requirements.md` THEN the docstring SHALL include a
   `Requirement:` link to that `requirements.md` (with a section anchor where possible).
3. The convention SHALL be language-agnostic (Python docstrings, JS/TS block comments,
   Go comments) and SHALL be driven by `config.testing`.

### R2 — Queryable, tabular scenario view

**User story:** As a coding-agent harness (Claude/Cursor), I want to query all the
scenarios being tested, so that I can present a tabular view without running the suite.
1. The `the-loop` CLI SHALL provide a `scenarios` command that scans the configured
   integration-test globs (`testing.integrationTestGlobs`, with built-in defaults) and
   extracts every Gherkin scenario.
2. WHEN invoked THEN it SHALL present a tabular view (Feature, Scenario, Requirement,
   file:line) as an aligned table, a Markdown table, or JSON (`--format`).
3. The command SHALL keep the CLI's zero-runtime-dependency guarantee (stdlib only;
   PyYAML remains optional for config defaults).

### R3 — RESTful API specs in OpenAPI

1. All API specs for RESTful APIs SHALL be authored in the `specs/openapi/` folder in
   the OpenAPI spec format (`apiSpecs.rest`, default `openapi-3.1`).
2. Documentation SHALL be automatically generatable from the OpenAPI specs
   (`apiSpecs.rest.generateDocs` / `docsTool`); generated docs are never hand-written.

### R4 — GraphQL best practice

1. the-loop SHALL define the GraphQL equivalent of R3 (the issue's TODO): an SDL-first,
   checked-in schema under `specs/graphql/` with generated documentation and a CI
   breaking-change check (`apiSpecs.graphql`). Recorded in `decision-014`.

## Non-functional requirements

- New config keys validate against `.the-loop/config.schema.json`.
- CLI quality gates stay green: ruff, pyright, pytest, markdownlint.

## Out of scope (this work item)

- Enforcing the docstring convention mechanically in the test runner (review-enforced
  for now).
- Wiring OpenAPI/SDL lint & docs-generation pipelines into the-loop's own CI (the-loop
  has no HTTP API yet).
