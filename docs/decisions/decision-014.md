# Decision 014: Gherkin scenario docstrings on integration tests + contract-first API specs

- **Status:** accepted
- **Date:** 2026-07-02
- **Deciders:** @MadaraUchiha-314 (issue author intent)
- **Work item:** issue-11

## Context

Issue #11 asks for two conventions the loop should enforce:

1. Integration tests should be self-describing — a coding-agent harness (Claude,
   Cursor, …) should be able to query *all scenarios being tested* and present a tabular
   view, and tests tied to a `requirements.md` should link back to it.
2. API contracts should be authored declaratively — RESTful specs in `specs/openapi/`
   in the OpenAPI format, with documentation generated from them. The GraphQL
   equivalent was left as a TODO to figure out.

## Decision

- **Gherkin docstrings, extracted by text — not a BDD framework.** Every integration
  test carries a Gherkin-syntax docstring (`Feature:`/`Scenario:`/Given-When-Then,
  optional `Requirement:` link). A new stdlib-only CLI command, `the-loop scenarios`
  (`--format table|markdown|json`), extracts them by scanning configured globs
  (`testing.integrationTestGlobs`) and stripping comment markers, so the same
  convention works across Python docstrings, JS/TS block comments and Go comments
  without adopting cucumber/behave/pytest-bdd or binding tests to step definitions.
- **REST: OpenAPI 3.1 under `specs/openapi/`**, spec-first; docs generated (default
  tool `redocly`, free-form), never hand-written (`apiSpecs.rest`).
- **GraphQL best practice: SDL-first under `specs/graphql/`** — the checked-in SDL
  (snapshotted when code-generated) is the reviewable contract; mandatory
  type/field descriptions; docs generated (default tool `spectaql`, free-form); a
  breaking-change check against the previous snapshot in CI (`apiSpecs.graphql`).
  This resolves the issue's GraphQL TODO.
- Conventions are codified in `skills/the-loop/reference/testing.md` and driven by two
  new config sections, `testing` and `apiSpecs` (schema-validated).

## Consequences

- Positive: scenario coverage is queryable without executing tests; requirements ↔ test
  traceability is explicit; API changes are reviewed as contract diffs; docs can never
  drift from the contract (they're generated); zero new runtime dependencies.
- Negative: the docstring convention is enforced by review/convention, not by a parser
  wired into the test runner; a free-text Gherkin block can drift from what the test
  actually does (mitigated by the review loop reading both together).

## Alternatives considered

- **A BDD framework (cucumber/behave/pytest-bdd)** — real executable Gherkin, but binds
  every language's tests to step-definition machinery and violates minimalism for what
  is fundamentally a documentation/traceability need.
- **Code-first API specs (generate OpenAPI from handlers/annotations)** — keeps spec
  and code in one place, but makes the contract an artifact of the implementation;
  design-phase review of API changes needs the contract to be the source of truth.
- **GraphQL code-first only (no checked-in SDL)** — introspection always exists, but
  without a checked-in SDL snapshot there is no reviewable diff and no CI
  breaking-change gate.
