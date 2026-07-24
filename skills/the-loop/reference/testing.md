# Testing & API-spec reference

Config: `testing` and `apiSpecs` in `.the-loop/harness-config.yaml`. This file codifies the
integration-test scenario conventions and the API-contract conventions (issue #11) so
the essence is not lost.

## RULE: Gherkin docstrings on integration tests

Every **integration test** MUST carry a docstring (or the language's nearest comment
equivalent) that states the scenario being tested in **Gherkin-like syntax**
(`testing.gherkinDocstrings`, default `required`):

```
Feature: <capability under test>
Requirement: docs/specs/<id>/requirements.md#R<n>   (when tied to a requirements.md)

Scenario: <one-line behaviour>
    Given <precondition>
    When <action>
    Then <observable outcome>
```

- **One `Scenario:` per test**; a file-level `Feature:` applies to every scenario that
  follows it (until the next `Feature:`).
- **`Requirement:` links the test to its spec** (`testing.linkRequirements`, default
  true): if a test exists because of a `requirements.md`, the docstring MUST link that
  file — ideally with the requirement anchor (`…/requirements.md#R2`) — so coverage is
  traceable in both directions.
- The convention is **language-agnostic**: Python docstrings, JS/TS block comments and
  Go comments all work — the extractor strips comment markers before matching keywords.
- Unit tests MAY use the same convention but are not required to; the rule targets
  integration tests, where the *scenario* (not the function) is the unit of meaning.

### Querying the scenarios (harness-facing)

A coding-agent harness (Claude, Cursor, …) — or a human — can enumerate everything the
integration suite covers **without running it**:

```bash
the-loop scenarios                      # aligned table
the-loop scenarios --format markdown    # GitHub-flavoured table (paste into PRs/docs)
the-loop scenarios --format json        # machine-readable, for the harness
```

- Files scanned come from `testing.integrationTestGlobs`; when empty, the CLI's
  built-in defaults cover common layouts (`**/tests/integration/**`,
  `*.integration.test.ts`, `*_integration_test.py`, Go `integration/**/*_test.go`).
- Each row reports **Feature, Scenario, Requirement, `file:line`** — the tabular view
  the harness presents when asked "what scenarios are tested?".
- The markdown output is what the reviewer briefing / PR summary should embed when the
  change adds or alters integration behaviour.

## RULE: REST APIs are contract-first OpenAPI

All API specs for **RESTful APIs** are authored in the **`specs/openapi/`** folder
(`apiSpecs.rest.dir`) in the **OpenAPI** format (`apiSpecs.rest.format`, default
`openapi-3.1`):

- **Spec first, then code.** The OpenAPI document is the contract; handlers/clients
  conform to it, not the other way round. Design-phase API changes edit the spec file —
  the design review reviews the contract.
- One spec file per service/API (`specs/openapi/<service>.yaml`); shared components may
  be `$ref`'d across files.
- **Documentation is generated, never hand-written** (`apiSpecs.rest.generateDocs`,
  default true) using `apiSpecs.rest.docsTool` (default `redocly`; free-form — use
  whatever the project standardises on). Generated docs are build artifacts: do not
  check them in or hand-edit them.
- Lint the specs like any other source (e.g. `redocly lint`, spectral) with the same
  command locally and in CI.
- Integration tests SHOULD exercise the API **through the contract** (request/response
  shapes from the spec), and their Gherkin scenarios name the endpoint behaviour.

## GraphQL best practice (SDL-first)

The GraphQL equivalent of contract-first OpenAPI (`apiSpecs.graphql`):

- **The SDL schema is the contract**, checked in under `specs/graphql/`
  (`apiSpecs.graphql.dir`, `schemaFormat: sdl`). Resolvers conform to the SDL; when the
  schema is code-generated, snapshot the generated SDL into `specs/graphql/` so diffs
  are reviewable and breaking changes are visible in the PR.
- **Docs are generated from the SDL** (`generateDocs: true`, `docsTool` default
  `spectaql`; free-form) plus the built-in introspection/GraphiQL surface.
- Descriptions (`"""docstrings"""`) on types/fields are mandatory — they are the docs.
- Lint the schema (e.g. graphql-schema-linter / graphql-eslint) and run a
  breaking-change check against the previous snapshot in CI.

## How this feeds the loop

- **Design phase**: `design.md`'s testing strategy names the integration scenarios
  (their `Scenario:` titles) and, for API work, links the OpenAPI/SDL files under
  `specs/`.
- **Implementation phase**: each `tasks.md` task's `_Test:_` for integration behaviour
  is a Gherkin scenario; red→green evidence references the scenario title.
- **Review/evidence**: `the-loop scenarios --format markdown` output goes into the
  reviewer briefing so the human sees coverage at a glance, mapped to requirements.
