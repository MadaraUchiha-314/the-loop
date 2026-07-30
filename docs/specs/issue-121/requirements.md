---
type: requirements
phase: requirements-definition
workItem: issue-121
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
collaborators: [engineer, technical-writer]
overrides: {}
---

# Requirements: why the CLI reads `harness-config.yaml`, and the rule that says when it may

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #121](https://github.com/MadaraUchiha-314/the-loop/issues/121) asks three
questions about one sentence in the CLI docs — *"Repo-scoped — reads the repo's
`harness-config.yaml`"*:

1. Can we reason on why the CLI is reading the harness config?
2. Should it be doing it?
3. If not, can we move it to `cli-config`?

The answers, established by tracing the tree and recorded here so nobody has to trace it
again: **because those values are the repository's own policy and the CLI executes that
policy on the repository's behalf**; **yes**; and **no — moving them would be a
regression**, for the four reasons in [Analysis](#analysis).

The question is worth an issue because the documentation *invited* it. The rule the docs
state is per-**process** ("daemons read `cli-config.yaml`, repo-scoped commands read
`harness-config.yaml`"), and that rule is both the wrong shape and — since issue-113 —
factually false in four places. The rule that actually holds is per-**direction**. This
work item replaces the one with the other, and pins the resulting read surface with a
test so it cannot drift again.

### What the CLI reads today

Three readers, five keys, all of them per-repository policy the plugin/skill reads too:

| Reader | Keys | Consumers |
|---|---|---|
| `graph/bootstrap.py::load_harness_config` | `workflow.phaseLabelPrefix`, `workflow.specDir`, `notifications` | `the-loop check`, `the-loop graph`, **and the daemon** via `graphlink.py` |
| `critics.py::load_critics` | `reviews.critics[]` | `the-loop critic list/show/run` |
| `commands/scenarios.py::_load_config_globs` | `testing.integrationTestGlobs` | `the-loop scenarios` |

Each reader carries its own copy of the same `harness-config.yaml` → pre-rename
`config.yaml` fallback (issue-82, decision-035) — three copies of one rule, in three
modules, with three different failure behaviours for an unparseable file.

### The documentation is wrong, not the code

`graphlink.py` is constructed by `webhook/dispatcher.py`, which **both** ingresses share,
and `GraphLinkConfig.enabled` defaults to `true`. So on every spawn and every routed
event with a spec directory, the daemon calls `build_runtime(root)` → and reads the
checkout's `harness-config.yaml`. That has been true since issue-113 shipped. Four
documents still say it never happens:

| Document | The claim |
|---|---|
| `docs/config/index.md` | *"The daemon never reads a repository's harness config … Not for anything"* |
| `docs/cli/concepts.md` | *"The daemon **never** reads a repository's harness config"* |
| `docs/cli/commands/index.md` | daemon commands *"read the CLI config — not any repository's harness config"* |
| `docs/cli/index.md` | a Mermaid split of *"Daemon — reads cli-config.yaml"* vs *"Repo-scoped — reads the repo's harness-config.yaml"* |

The *intent* behind those sentences is correct and important — it is decision-032's
consequence that the daemon's own settings (who may trigger it, what it watches) never
come from a checkout. Overstating it into "never reads the file at all" is what makes it
false, and what made #121 a reasonable question to ask.

## Analysis

Recorded here because the issue asks for reasoning, not just an outcome. The four
reasons `reviews.critics[]`, `workflow.*`, `notifications` and
`testing.integrationTestGlobs` cannot move to `cli-config.yaml`:

1. **Wrong cardinality.** They are per-repository values. `cli-config.yaml` is one
   machine-scoped file for a daemon that watches N repositories, so holding them there
   needs a hand-maintained `OWNER/REPO →` map that drifts from the repository it
   describes the moment someone edits one and not the other.
2. **Two sources of truth for one value.** The skill reads `reviews.critics[]`
   (`reference/reviewing.md`) and `workflow.specDir` from the harness config. If the CLI
   read them from `cli-config.yaml`, `the-loop critic run` and the agent following the
   skill could disagree about what the critics *are* — the same fork decision-043 refused
   when it kept the review loop in one implementation.
3. **It breaks the checkout-only cases.** `the-loop check` is a CI gate: it runs in a bare
   checkout, as a job with no operator home directory and no `cli-config.yaml` anywhere.
   `the-loop scenarios` is the same. Sourcing their settings from the operator's machine
   config would make them unconfigurable exactly where they are used.
4. **The trust argument runs one way only.** Decision-032 removed the plugin → daemon
   fallback because a *checkout* must not be able to tell the daemon who may trigger it
   or what to watch — a repository is untrusted input to an operator's machine. The
   reverse carries no such risk: a repository saying "my specs live in `docs/specs`" can
   only affect work on that same repository. The one genuinely powerful key,
   `reviews.critics[]`, is already labelled executable config, is reviewed like code, and
   is never run implicitly (`critic run` names exactly one critic).

## Requirements

### Requirement 1 — the rule is recorded as a decision

**User story:** As a maintainer, I want the direction-based rule written down as a
decision record, so that the next "why does the CLI read this?" is answered by a link.

#### Acceptance criteria

1. WHEN a reader opens `docs/decisions/` THEN the repository SHALL contain a decision
   record stating the invariant: **a repository's harness config may configure work done
   on that repository; it may never configure the daemon itself.**
2. WHEN that record is read THEN it SHALL name the three current readers and their keys,
   and SHALL record the four reasons the keys cannot move to `cli-config.yaml`.
3. WHEN that record is read THEN it SHALL state its relationship to decision-032 —
   refining its consequence, not reversing it — and SHALL be listed in
   `docs/decisions/decisions.md`.

### Requirement 2 — the false claims are corrected

**User story:** As a CLI user, I want the docs to describe what the code does, so that I
do not have to read `graphlink.py` to find out which file configures what.

#### Acceptance criteria

1. WHEN `docs/config/index.md`, `docs/cli/concepts.md`, `docs/cli/commands/index.md` and
   `docs/cli/index.md` are read THEN none SHALL claim that the daemon never reads a
   repository's harness config.
2. WHEN those pages are read THEN each SHALL state the direction-based rule, and SHALL
   keep the still-true, load-bearing part of the old sentence: `authorizedUsers` and a
   poll source's `repos` are CLI-config-only, with no fallback, failing closed.
3. WHEN `docs/config/harness-config.md` is read THEN it SHALL carry a section enumerating
   every key the CLI reads, which command reads it, and what it falls back to.
4. WHEN `docs/cli/index.md`'s diagram is read THEN it SHALL show the daemon's read of a
   work item's own checkout, rather than partitioning the two files by command.

### Requirement 3 — one reader, not three

**User story:** As a contributor, I want a single module that reads the harness config, so
that "which keys does the CLI read?" is a question with a place to look.

#### Acceptance criteria

1. WHEN the CLI resolves a harness config path THEN it SHALL do so in exactly one module,
   and `graph/bootstrap.py`, `critics.py` and `commands/scenarios.py` SHALL delegate to
   it.
2. WHEN a repository has `.the-loop/config.yaml` but not `.the-loop/harness-config.yaml`
   THEN the CLI SHALL still read it (issue-82, decision-035), with the fallback expressed
   once.
3. WHEN a harness config is absent, unparseable, or not a YAML mapping THEN the shared
   reader SHALL return an empty mapping, AND `critic` SHALL continue to raise
   `CriticConfigError` on an unparseable file — a critic that silently reviews nothing is
   worse than one that refuses.
4. WHEN the change is complete THEN every existing public name
   (`bootstrap.load_harness_config`, `critics.config_path`) SHALL still resolve, so no
   caller or test outside the CLI package breaks.

### Requirement 4 — the read surface is pinned by a test

**User story:** As a maintainer, I want a red build when a new harness-config key is read
without being declared, so that the rule survives contact with the next feature.

#### Acceptance criteria

1. WHEN the shared reader is added THEN it SHALL declare the read surface as data — each
   key, the command that reads it, and why it is repo-scoped.
2. WHEN the test suite runs THEN it SHALL assert every declared key resolves in
   `.the-loop/harness-config.schema.json`.
3. WHEN the test suite runs THEN it SHALL assert that no module outside the shared reader
   opens a harness config file, naming the offending file and line when one does.
4. WHEN the test suite runs THEN it SHALL assert every declared key is documented in
   `docs/config/harness-config.md`, and that no key documented as CLI-read is absent from
   the declaration.
5. WHEN `docs/` is absent (a source distribution) THEN the documentation assertions SHALL
   skip rather than fail, matching `test_docs_parity.py`.

### Requirement 5 — no behavioural change

**User story:** As an operator, I want this to be a rename-and-explain, so that upgrading
changes nothing about how my daemon or my CI gate behaves.

#### Acceptance criteria

1. WHEN the CLI runs after this change THEN every command SHALL read exactly the keys it
   read before, from exactly the same paths, with the same defaults.
2. WHEN the full test suite runs THEN it SHALL pass with no pre-existing test modified to
   accommodate the change.
3. WHEN the capability docs are read THEN `docs/capabilities/cli.md` SHALL describe the
   invariant and carry a history row for this work item.

## Security considerations

**Threat model (lite).** The asset is the operator's machine; the untrusted input is any
repository checkout the daemon can reach. The question this work item answers is a
*trust-direction* question, so it is a security question.

- **Trust boundary unchanged.** No new key is read, no key is read from a new place, and
  no read moves across the boundary decision-032 drew. `authorizedUsers`,
  `polling.sources[].repos` and every other ingress setting remain CLI-config-only with
  no fallback; nothing in this change gives a checkout a say in them.
- **The keys the CLI does read from a checkout are bounded by blast radius.**
  `phaseLabelPrefix`, `specDir`, `notifications` and `integrationTestGlobs` affect only
  work done on that same repository. `reviews.critics[]` is the exception that matters —
  it is executable configuration — and it is unchanged here: still committed, still
  reviewed like code, still only ever spawned by an explicit `the-loop critic run <name>`
  with `shell=False` (decision-043).
- **The daemon's read is already gated.** `graphlink._checkout_belongs_to` proves, via
  the checkout's `origin` remote, that the directory really is a checkout of the work
  item's repository before any harness config there is read, and fails closed when it
  cannot tell (issue-113, A6). Writing the rule down makes that gate's purpose legible;
  it does not relax it.
- **Documenting the read surface is not disclosure.** Every key named is already in the
  published schema and the shipped template.
- **Risk tier: 3** (`autonomy.defaultTier`). Docs, a decision record, an internal
  refactor with no behavioural delta, and a test. `security.review.humanSignOffMinTier`
  is 4, so no human security sign-off is required; the PR review is the tier-3 gate.
