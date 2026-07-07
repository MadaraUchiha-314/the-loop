# Capability: testing-and-contracts

> Integration-test coverage that is *queryable* (Gherkin scenario docstrings) and API
> contracts that are *declarative* (spec-first OpenAPI / GraphQL SDL).

## What it is

Two loop conventions that make correctness self-describing: every integration test
names the scenario it proves, and every API is authored contract-first with docs
generated from the contract.

## Current behaviour

- Every integration test SHALL carry a Gherkin-syntax docstring
  (`Feature:` / `Scenario:` / Given-When-Then) naming the scenario under test, with a
  `Requirement:` link when tied to a spec's `requirements.md`
  (`testing.gherkinDocstrings: required`, `testing.linkRequirements`).
- Integration tests SHALL be discovered via `testing.integrationTestGlobs`.
- `the-loop scenarios` SHALL extract and tabulate all covered scenarios
  (`--format table|markdown|json`) so a harness or reviewer can query coverage.
- RESTful API specs SHALL be authored in `specs/openapi/` (OpenAPI); GraphQL schemas
  SHALL be SDL-first under `specs/graphql/`; documentation SHALL be generated from
  those contracts, never hand-written (`config.apiSpecs`; not exercised in this repo —
  the-loop ships a CLI + docs, not an API).

## Design

[`reference/testing.md`](../../skills/the-loop/reference/testing.md) ·
[`docs/specs/issue-11/design.md`](../specs/issue-11/design.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-11 | Introduced Gherkin scenario docstrings, the `scenarios` command and contract-first API conventions | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
