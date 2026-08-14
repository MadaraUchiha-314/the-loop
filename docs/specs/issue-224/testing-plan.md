---
type: testing-plan
phase: test-planning
workItem: issue-224
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the learnings tree is a configured location, and it defaults into `docs/`

> Derived from [`design.md`](design.md) and reviewed together with it. Authored at
> `test-planning`, completed at `verification` — one artifact, written once as a plan and
> once as a record.

## What this work item has to prove

The change ships no runtime code, so "does it work?" is not the question. Three claims
carry what risk there is:

1. **The three statements of the default agree.** A schema default, a shipped template and
   a packaged default that disagree is the failure mode this repository has a test for
   already (`test_harness_config.py` pins the template and the packaged copy byte-for-byte,
   and `test_manifest_schemas.py` validates the shipped configs against their schemas).
   Both must still hold after the edit, and the schema's default must be the same string.
2. **Nothing still points at the old path.** A move that leaves a reference behind is worse
   than no move: the agent writes to one directory and the docs describe another. This is
   provable exactly — a repository-wide search, with the historical spec records under
   `docs/specs/` excluded, since those are the record of what was true at the time.
3. **The tree moved with its history and its links.** `git mv`, not delete-and-add, and
   every relative link inside the moved files resolves from the new depth.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Schema validation | yes | the edited `harness-config.schema.json` is itself valid, and all three shipped configs (this repo's, the template, the packaged default) validate against it with the new key present (R1.3, R2.1, NFR-1) | `make validate` |
| T2 | Unit — config parity | yes | `skills/the-loop/templates/harness-config.yaml` and `cli/the_loop/harness-config.default.yaml` are byte-for-byte identical after the edit (R2.2) | `uv run pytest cli/tests/test_harness_config.py` |
| T3 | Unit — manifest/schema mapping | yes | every shipped config still resolves to its schema and validates (R2.3) | `uv run pytest cli/tests/test_manifest_schemas.py` |
| T4 | Unit — harness-config read surface | yes | `READS` is unchanged and still resolves against the edited schema — H1–H4 confirm the CLI gained no read (NFR-2) | `uv run pytest cli/tests/test_harness_config.py` |
| T5 | Docs↔code parity | yes | the documentation suite still passes after the docs edits (R4.3, NFR-3) | `uv run pytest cli/tests/test_docs_parity.py` |
| T6 | Regression — full suite | yes | nothing else in the repository depended on the moved path or the schema shape (NFR-3) | `make test` |
| T7 | Lint / format / types | yes | ruff (lint + format), pyright and markdownlint over every markdown file, including the moved and new documents (NFR-3) | `make lint format-check typecheck` |
| T8 | Reference sweep — no dead path | yes | no file outside `docs/specs/` (the historical record) mentions the pre-move `learnings/` path; the moved files' own relative links resolve (R3.2, NFR-5) | `git grep` sweep recorded in evidence |
| T9 | Migration / upgrade | yes | a config that omits `learningsDir` still validates, and so does one pinning the old location (an already-adopted project is broken by neither), and the upgrade command states both supported outcomes for an existing root-level tree (R2.3, R5.1, R5.2) | `jsonschema` validation of the loaded config with the key removed / pinned + review of `commands/upgrade-the-loop.md` |
| T10 | History preservation | yes | git records the move as a rename, not as a delete plus an add (NFR-4) | `git log --follow` / `git show --stat` in evidence |
| T11 | Integration | n/a — no component boundary is crossed by this change. The only "integration" would be an agent reading the key, and the agent is not a process this repository can drive in a test; T1/T2/T3 pin the contract it reads instead | | |
| T12 | End-to-end | n/a — `cli/tests/test_pdlc_e2e/` drives the process graph against a mocked harness. The learnings lifecycle is not a graph node, so there is nothing for the e2e runner to walk | | |
| T13 | UI / visual | n/a — no user-facing surface. The Control Plane UI edits the **CLI** config; the harness config has no UI | | |
| T14 | Performance | n/a — no code path is added, so there is nothing whose cost could change | | |
| T15 | Security / abuse case | yes, by review | the three abuse cases in `requirements.md` are argued against the diff: no new reader, no new writer, `READS` unchanged (asserted mechanically by T4), and the published-`docs/` consequence is stated in the schema description and the config reference | review against `requirements.md` §Security considerations + T4 |
| T16 | Accessibility | n/a — no interactive surface is added or changed | | |
| T17 | Snapshot | n/a — T2 is the byte-exact comparison that matters and it names *what* must be equal; a snapshot would only say *that* something changed | | |
| T18 | Manual exploratory | yes | read the moved tree as a reader would: open `docs/learnings/learnings.md` and follow each link; and — because the move puts the tree inside the VitePress `srcDir` — build the site and confirm the learnings render, are reachable from the authored nav/sidebar, and leave the generated spec sidebar untouched | `cd docs && bun run docs:build`, recorded in evidence |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.3, R2.1 | `Scenario: the schema accepts the new key and states docs/learnings as its default` |
| T1, T9 | R2.3, NFR-1 | `Scenario: a config that omits learningsDir is still valid` |
| T2 | R2.2 | `Scenario: the shipped template and the packaged default do not drift` |
| T3 | R2.1 | `Scenario: every shipped config validates against its schema` |
| T4 | NFR-2 | `Scenario: the CLI read surface did not grow` |
| T5 | R4.3 | `Scenario: the documentation still matches the code it documents` |
| T8 | R3.2, R4.1, R4.2, NFR-5 | `Scenario: nothing outside the historical record names the old path` |
| T10 | NFR-4 | `Scenario: the learnings kept their history across the move` |
| T9 | R5.1, R5.2 | `Scenario: an upgrading project is offered both outcomes and neither is taken for it` |
| T18 | R3.2 | `Scenario: every link in the moved learnings index resolves` |

## Verification environment

- **Repositories:** this one, alone.
- **Services / containers:** none.
- **Fixtures & data:** the shipped configs themselves (`.the-loop/harness-config.yaml`,
  the template, the packaged default); a throwaway copy with `learningsDir` removed for T9.
- **Credentials:** none. No test reads a token, a secret or an environment variable.
- **Bring-up:** `uv sync` (and `npx markdownlint-cli2` fetched by `make lint`).
- **Tear-down:** none.
- **If bring-up fails:** record it under the verification results, leave the dependent
  activities unticked, and escalate. An activity that could not run is never ticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T7 | command, exit status and output per row, plus the full-suite counts | `verification.md` |
| T8 | the `git grep` sweep and its result, with the exclusions stated and every surviving occurrence accounted for | `verification.md` |
| T9 | the validation run with the key removed, and again with it pinned to `learnings` | `verification.md` |
| T10 | `git show --stat` / `git status` showing renames | `verification.md` |
| T18 | the read-through result: each link in the moved index, and its target | `verification.md` |

Redaction: every command is run in a public repository against committed files; no output
carries a token, a personal path or an internal hostname. Absolute paths are rewritten to
repository-relative form.

## Verification activities

- [x] T1 — `make validate`
- [x] T2, T4 — `uv run pytest cli/tests/test_harness_config.py`
- [x] T3 — `uv run pytest cli/tests/test_manifest_schemas.py`
- [x] T5 — `uv run pytest cli/tests/test_docs_parity.py`
- [x] T6 — `make test`
- [x] T7 — `make lint format-check typecheck`
- [x] T8 — `git grep` sweep for the pre-move path
- [x] T9 — schema validation with `learningsDir` removed + upgrade-command review
- [x] T10 — `git status --short` rename check (nine `R`/`RM` entries, no delete+add)
- [x] T15 — security review against `requirements.md` §Security considerations
- [x] T18 — manual read-through of the moved tree + `cd docs && bun run docs:build`
