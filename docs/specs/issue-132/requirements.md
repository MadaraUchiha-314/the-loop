---
type: requirements
phase: requirements-definition
workItem: "issue-132"
status: approved
approvedBy: [MadaraUchiha-314]
collaborators: [product-manager, engineer]
overrides: {}
riskTier: 3
---

# Requirements: verifiable custom instructions — make `customInstructions` findable and checkable

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #132](https://github.com/MadaraUchiha-314/the-loop/issues/132) asks whether the-loop
lets a project declare its own rules and guidelines — "and if not, the-loop should allow
such specification of a list of files to be understood when the agent-harness like
cursor/claude works with it."

**It already does.** `config.customInstructions` shipped in
[issue-59](../issue-59/) / [decision-029](../../decisions/decision-029.md): an ordered list
of instruction docs (repo-relative or absolute), each with optional `notes`, plus an
`onMissing` policy, read at the start of every work item with documented precedence
(`skills/the-loop/reference/instructions.md`).

So the capability is not the deliverable. **The deliverable is what the issue's existence
proves is missing.** The repository's own owner — who merged the feature — could not find
it, and had no way to confirm the docs were being read. Two concrete defects follow:

1. **It is undiscoverable from the front door.** `README.md` never names
   `customInstructions`, and its enumeration of the skill's reference docs omits
   `instructions` entirely (along with `context`, `security` and `token-economy`). A
   reader evaluating the-loop cannot learn the feature exists without reading the schema.
2. **Nothing verifies it.** `onMissing` is honoured by the agent's good behaviour and by
   nothing else. A mistyped or moved path silently contributes no guidance; the run looks
   identical to a correct one. There is no way to ask the harness *which docs it actually
   resolved*, so `onMissing: error` is a setting that never errors, and a CI job cannot
   catch a broken registration. The-loop's own idiom for exactly this problem already
   exists — `the-loop scenarios` makes the Gherkin obligation queryable — and custom
   instructions have no counterpart.

This work item closes both, and changes no existing configuration shape.

## Requirements

### Requirement 1 — Query the registered instruction docs

**User story:** As an operator who registered instruction docs, I want to ask the-loop
which ones it resolves and whether each is actually readable, so that I can trust the
guidance is reaching the agent instead of assuming it.

#### Acceptance criteria (EARS)

1. WHEN the operator runs `the-loop instructions` in a repository THEN the system SHALL
   report every entry of `customInstructions.docs`, in configured order, with its
   configured path, its resolved absolute path, its `notes`, and its state.
2. WHEN a registered doc exists and is readable THEN the system SHALL report its state as
   `present`.
3. WHEN a registered doc does not exist at its path THEN the system SHALL report its state
   as `missing`.
4. WHEN a registered doc exists but cannot be read as text THEN the system SHALL report its
   state as `unreadable`, distinctly from `missing`.
5. WHEN a doc's `path` is absolute THEN the system SHALL use it as given; IF it is relative
   THEN the system SHALL resolve it against the repository root.
6. WHEN the repository registers no docs THEN the system SHALL report an empty result and
   succeed, because configuring nothing is not an error.
7. WHEN `--format json` or `--format markdown` is passed THEN the system SHALL render the
   same facts in that format, so a harness or a PR comment can consume them.

### Requirement 2 — `onMissing` becomes an enforceable policy

**User story:** As an operator who set `onMissing: error`, I want a broken registration to
actually fail, so that the setting means what it says and CI can gate on it.

#### Acceptance criteria (EARS)

1. WHEN a registered doc is `missing` or `unreadable` AND `onMissing` is `error` THEN the
   system SHALL exit non-zero.
2. WHEN a registered doc is `missing` or `unreadable` AND `onMissing` is `warn` (the
   default) THEN the system SHALL exit zero and emit a warning naming each unresolved doc.
3. WHEN a registered doc is `missing` or `unreadable` AND `onMissing` is `ignore` THEN the
   system SHALL exit zero and emit no warning, while still reporting the doc's state in
   the output.
4. WHEN every registered doc is `present` THEN the system SHALL exit zero under every
   `onMissing` value.
5. IF the harness config is absent, unparseable, or not a mapping THEN the system SHALL
   report no docs and exit zero, matching the best-effort contract every other
   repo-scoped reader honours — a half-edited config must not fail a build for a reason
   unrelated to instructions.

### Requirement 3 — The read is declared, documented and pinned

**User story:** As a maintainer, I want a new CLI read of a repository's harness config to
be declared and documented like every other one, so that the read surface stays
enumerable.

#### Acceptance criteria (EARS)

1. WHEN the CLI reads `customInstructions` from a repository's harness config THEN the
   system SHALL declare it in `harness_config.READS` with the command that reads it and
   why it is the repository's to declare (decision-044).
2. WHEN the read is declared THEN it SHALL appear in the CLI-read table of
   `docs/config/harness-config.md`, so `test_harness_config.py` H3/H4 hold in both
   directions.
3. WHEN a new command is registered THEN it SHALL have a page under `docs/cli/commands/`,
   so `test_docs_parity.py` P1/P2 hold.
4. WHEN the harness config is read THEN it SHALL be read through `the_loop.harness_config`
   and no other module, so H2 holds.

### Requirement 4 — The feature is discoverable from the front door

**User story:** As someone evaluating the-loop, I want to learn from the README that it
reads my project's own rules, so that I do not have to read the schema to find out.

#### Acceptance criteria (EARS)

1. WHEN a reader reads `README.md` THEN it SHALL state that the-loop reads the project's
   own registered instruction docs, and link the instructions reference.
2. WHEN the README enumerates the skill's reference docs THEN the list SHALL be complete
   with respect to `skills/the-loop/reference/`, so a future reference doc is not
   silently omitted the way `instructions` was.
3. WHEN the reference doc describes the feature THEN it SHALL also describe how to verify
   a registration, naming the command from R1.

## Non-functional requirements

- **Pure and CI-safe.** The command performs filesystem reads only — no network, no
  subprocess, no mutation — matching `the-loop check` and `the-loop scenarios`.
- **No new dependency.** Rendering reuses the plain-table/markdown/json idiom already in
  `commands/scenarios.py` (minimalism ladder: reuse before introducing).
- **No config-shape change.** `customInstructions` keeps its schema exactly; a repository
  that upgrades gains a way to check what it already declared.

## Security considerations

- **Actors & trust:** the operator (trusted — they author the harness config) and anyone
  who can open a PR against the repository (untrusted, because a PR may edit
  `.the-loop/harness-config.yaml` and thereby the list of paths). The command itself is
  run by an operator or by CI.
- **Trust boundaries & data:** two crossings, each a trust boundary the design must
  enforce with a named mechanism.
  - **Config path → filesystem read.** A `path` value decides which file is *stat*-ed and
    read. An absolute path is deliberately supported (decision-029: per-machine docs
    outside the repo), so path traversal is not a vulnerability here — it is the feature.
    The boundary that matters is therefore **output**, not access: nothing this command
    reads may be executed, interpreted, or trusted as instruction *by the command*.
  - **File content → terminal/JSON output.** The command reports *facts about* docs
    (path, state, byte count), never their contents. A hostile doc body therefore cannot
    reach the output at all.
  - Doc **contents** remain what they always were: operator-configured, trusted
    installation input at the same level as the harness config
    (`reference/instructions.md` § Security note). This work item does not widen that
    trust — it narrows the blast radius of a *typo*, which today is silent.
- **Abuse cases (EARS):**
  1. WHEN a registered `path` points outside the repository THEN the system SHALL report
     its state without reading its contents into the output.
  2. WHEN a registered `path` is a directory, a device node, an unpermitted file, or a
     binary file THEN the system SHALL report `unreadable` — something is there, but it
     is not a readable instruction doc — and SHALL NOT raise an unhandled exception.
  2b. WHEN a registered `path` is a broken symlink THEN the system SHALL report
     `missing`, because nothing resolves at that path at all.
  3. WHEN `notes` or `path` contains terminal control sequences or markdown/JSON
     metacharacters THEN the system SHALL render them as inert text (escaped for
     markdown, encoded for JSON) rather than as formatting or control codes.
  4. WHEN the harness config is malformed THEN the system SHALL fail closed to "no docs
     registered" rather than crash (R2.5).
- **Fail closed:** an entry that is not a mapping, or that has no usable `path`, is
  reported as an invalid entry and counts as unresolved for `onMissing` — the-loop never
  silently drops a registration it could not understand, because silence is the exact
  defect this work item exists to remove.

## Out of scope

- **Extending the config shape** — globs, directory registration, phase- or path-scoped
  applicability. All were considered and deferred (YAGNI): #132 asks for "a list of
  files", which `docs[]` already is. A future work item can add them against a schema
  that is now observable.
- **Gating the process graph on instruction docs.** The obligation is per-*work-item*
  ("read every configured doc when starting work"), not per-node, so a `pdlc.yaml` hook
  would be the wrong shape. The command is what the agent and CI call.
- **Verifying that the agent *understood* the guidance.** Not mechanically checkable;
  availability is.

## Open questions

Scope was confirmed with the requester before the spec was written
([#132 comment](https://github.com/MadaraUchiha-314/the-loop/issues/132#issuecomment-5170995297)):
answer the question, close the discoverability gap, and add the mechanical check —
without extending the config shape.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
