# Testing & API-spec reference

Config: `testing` and `apiSpecs` in `.the-loop/harness-config.yaml`. This file codifies the
testing plan and the verification node (issue-163), the integration-test scenario
conventions and the API-contract conventions (issue #11) so the essence is not lost.

## The testing plan (`testing-plan.md`) — phase `test-planning`

A work item is only *done* when the-loop can **prove** it is done. The proof is planned
as a first-class artifact, derived from `design.md` and locked before `tasks.md` is
written — each task's `_Test:_` names a row of the plan's matrix, so the DAG and the plan
cannot describe different work.

**It is reviewed with the design, not separately.** The `test-planning` node sits between
`design` and `design-approval`, so the one human gate approves `design.md` and the plan
together and `record-feedback` writes the reviewer's notes into **both** — a note about
the test matrix belongs in the plan, not filed under the design. `changes-requested`
returns to `design`, which re-derives the plan on the way back through. The plan is a
visible phase (`loop:test-planning`) without being an extra stop.

Authored from `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/testing-plan.md`. The
`test-planning` node gates on four sections being present and non-empty: **Test matrix**,
**Verification environment**, **Evidence plan** and **Verification results** (the last
one authored up front holding "not yet executed", so the `verification` node fills a
section rather than inventing one).

### The test matrix — every type gets a decision

One row per candidate testing type. The catalogue below is the starting set; add rows for
anything it does not cover (chaos, load-soak, i18n, data-migration dry-run…).

| Type | Proves |
|------|--------|
| Unit | a unit behaves as specified, in isolation |
| Integration (scenario) | components together, Gherkin-documented (see below) |
| Contract | request/response shapes match the OpenAPI / GraphQL SDL contract |
| End-to-end | a whole user journey through a running system |
| UI / visual | rendered states match the locked design artifacts |
| Snapshot | serialized output does not change unintentionally |
| Performance / load | latency/throughput/resource budgets hold |
| Security / abuse case | each trust boundary from `design.md` §Security design resists its abuse case |
| Accessibility | keyboard, contrast, semantics, assistive-tech behaviour |
| Migration / upgrade | existing data/config survives the change |
| Manual exploratory | what automation cannot reach, with the procedure written down |

**Nothing here is mandatory in itself — the matrix is work-item dependent.** A CLI flag
does not get a performance suite; a docs change does not get an e2e run. What *is*
mandatory is the decision: a type that does not apply is marked `n/a` **with a written
reason**. An unexplained blank is not a decision, and the reviewer's job is to notice
reasons, not absences — the same footing as "no new attack surface", which is written
and justified rather than implied (`reference/security.md`).

Security-relevant work items are the one place the matrix is effectively forced: a trust
boundary named in `design.md` §Security design needs its negative test named here, and
abuse cases are tests like any other.

### The verification environment — the-loop facilitates, it does not own

Real systems are not one repository with one test command: several checkouts, a staging
environment, seeded databases, a bespoke harness. **the-loop does not model any of
that.** It owns the *declaration* — the plan states what the verification needs, and the
loop runs the project's own commands:

- **Repositories** to check out (and at which ref), **services/containers** to run,
  **fixtures and data** to seed.
- **Credentials by reference only** — the env var name or secret-store key, never the
  value. A literal secret in a committed plan is a leaked secret: rotate it, do not
  merely edit it out.
- **Bring-up and tear-down commands**, which are the project's, not the-loop's.
- Where the operator has already written this down, **link the doc registered in
  `customInstructions.docs`** instead of restating it — the loop reads those docs when
  work on the item starts (`reference/instructions.md`), so planning has them in hand.

A testing plan **names commands an agent will run**, which makes it executable content:
review it like code, exactly as `reviews.critics[]` entries are reviewed (decision-043).
If the environment cannot be brought up, that is recorded, the dependent activities stay
unticked, and the item escalates — a gate is never passed on an environment that never
came up.

## Verification — phase `verification`

After implementation, the `verification` node executes the locked plan and turns it into
a record. It re-gates the **same** `testing-plan.md` — every activity ticked
(`checkmarks: complete`) and a non-empty **Verification results** section — the shape
`implementation` already uses to re-gate `tasks.md`.

- **Tick only what ran**, and only once its evidence is recorded. An activity that cannot
  be executed is left unticked; record why, then replan the matrix (with the reason) or
  escalate.
- **Results are per activity:** the exact command or manual procedure, the outcome, and a
  link to the committed evidence.

### Evidence

Evidence is **committed** under `<specDir>/<id>/evidence/`, alongside the spec. A link to
a CI run that expires, or to a path on the machine that ran it, is not evidence.

**Textual evidence is markdown** (`.md`), never `.txt` — every other artifact the loop
writes is markdown, it renders on the repository host and the docs site, and a reviewer
opening it gets headings and fenced blocks rather than a wall of console output. Give each
file a title, a line saying which work item and which activity it belongs to, a section per
command, and the raw output inside a fenced block so it is never reflowed. It is linted
like every other markdown file (`tooling.lint.markdown`). Binary captures — screenshots,
GIFs, recordings — stay in their own formats and are *referenced* from the markdown.

- **Test output** — the summary that shows counts and the red→green transitions.
- **UI verification** — rendered screenshots of each verified state, and an **animated
  capture (GIF or equivalent) when the behaviour under test is a *flow*** rather than a
  state. Screenshots of the *locked design artifacts* remain a design-phase concern
  (`reference/design-artifacts.md`); these are of the *implementation*, and the pair is
  what makes "implementation matches the visual contract" checkable.
- **Scenario coverage** — when the change adds or alters integration behaviour, the
  reviewer briefing embeds `the-loop scenarios --format markdown` (below); the plan
  references it rather than duplicating the list.

**Redact before committing.** The directory is as public as the repository, and captured
output and screenshots routinely contain tokens, cookies, personal data and internal
hostnames. Strip them; if a capture cannot be redacted, do not commit it — say so in the
results row instead.

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

## RULE: an asynchronous test waits on the state it depends on

A test that drives work onto a background thread MUST wait on **the state its next line
needs** — never on an earlier signal that merely tends to arrive first. The two are
different events, and which one wins is decided by how busy the machine is that minute.

The distinction to hold on to is **attempt vs outcome**:

| | What it is | Why it attracts the wait |
|---|---|---|
| **The attempt** | the call the test's double records — a spawn, a delivery, an HTTP request | it is the visible one, and it is usually already true |
| **The outcome** | everything the worker writes afterwards — registry records, dedup releases, event-log lines, announcements, graph moves | it is what the assertion (or the *next step*) actually depends on |

```python
# WRONG — waits for the attempt, then depends on its outcome
assert wait_until(lambda: len(tmux.delivers) == 1)
time.sleep(0.2)                                    # <- time standing in for a signal
post_webhook(port, ..., "e-1")                     # deduped away if the release is late

# RIGHT — wait for the fact the next line needs; assert the rest underneath
assert wait_until(lambda: "e-1" not in dispatcher.deduper)
assert len(tmux.delivers) == 1
```

Three habits follow:

- **A fixed `time.sleep` before a positive assertion is a defect**, not a safety margin:
  no value is correct, only values that are unlucky less often. (A sleep guarding a
  *negative* assertion — "give a would-be dispatch time to wrongly happen" — is a
  different thing and stays.)
- **Wait on a compound predicate when the test depends on several writes.** Two waits in
  sequence are not the same as one wait for both.
- **A real barrier beats a clever predicate.** Where the component offers one — draining
  and joining its workers, closing its pool — take it, then assert everything afterwards.

### Finding the shape instead of arguing about it

This is a happens-before property, so no amount of reading the test proves it. Move time
and watch what breaks: delay the writes that follow the attempt, and a test waiting on the
wrong signal fails **every** run instead of one in three.

In this repository that is a flag:

```bash
pytest --dispatch-lag=0.5 cli      # every post-spawn/post-delivery write, delayed
```

Nothing is patched unless the flag is passed. A failure under it names a test whose wait
is one step early; the same test at lag 0 is the control. Run it when async tests are
added, or when a flake goes hunting for its cause — a suite that only passes when it is
fast is a suite that has not been tested. (issue-251.)

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

- **Design phase**: `design.md`'s testing strategy is the strategy *in a paragraph* — how
  requirements map to test levels and, for API work, links to the OpenAPI/SDL files under
  `specs/`. The executable detail belongs to `testing-plan.md`.
- **Test-planning phase**: the matrix decides which types apply and which are `n/a` and
  why; the integration rows name their Gherkin `Scenario:` titles; the environment and
  the evidence plan are declared.
- **Tasks phase**: each task's `_Test:_` names a matrix row, so the DAG and the plan
  agree by construction.
- **Implementation phase**: each `tasks.md` task's `_Test:_` for integration behaviour
  is a Gherkin scenario; red→green evidence references the scenario title.
- **Verification phase**: the plan's activities are executed and ticked; results and
  committed evidence are recorded in the plan itself.
- **Review/evidence**: `the-loop scenarios --format markdown` output goes into the
  reviewer briefing so the human sees coverage at a glance, mapped to requirements, and
  the `evidence` node summarises the verification results against the acceptance criteria
  rather than re-deriving them.
