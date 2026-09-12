# Decision 123: the harness config is the agent's alone — the CLI reads no key of it

- **Status:** proposed
- **Date:** 2026-09-12
- **Work item:** [issue-352](https://github.com/MadaraUchiha-314/the-loop/issues/352)
- **Deciders:** MadaraUchiha-314 (the ask, on [PR #353](https://github.com/MadaraUchiha-314/the-loop/pull/353):
  *"Let's remove most of the harness-config. Additionally the CLI shouldn't read any of
  the harness config. the-loop's skill should tell the coding harness about the config
  and how to use it. CLI shouldn't depend on it at all. Make this breaking change."*);
  the-loop (design)
- **Supersedes:** [decision-044](decision-044.md), which allowed the CLI to read a
  repository's harness config in one direction (work done *on* that repository) and
  pinned the eight keys it read. Both directions are closed now.
- **Refines:** [decision-032](decision-032.md) (the two-file split stands; what changes
  is that the CLI's file is the *only* file the CLI reads), [decision-043](decision-043.md)
  (a critic entry is executable configuration, spawned only by an explicit
  `the-loop critic run` — unchanged, but the file it lives in changes),
  [decision-073](decision-073.md) (adoption of an unconfigured repository — retired),
  [decision-096](decision-096.md) (repository hooks — re-homed).
- **Spec:** `docs/specs/issue-352/`

## Context

[Issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352) asked what reads
`.the-loop/harness-config.yaml`, how it is enforced, and whether it is needed at all. The
audit ([`docs/reports/harness-config-audit.md`](../reports/harness-config-audit.md))
found four readers of very different weight: the agent, for nearly every key; the CLI, for
exactly eight, declared and test-pinned since decision-044; two hooks that only check the
file exists; and this repository's own tests. It also found that two of the CLI-read keys
described the operator's machine rather than the repository (`reviews.critics[]`,
`tokenEconomy`'s model ids), that `workflow.phases` was a mirror of the graph kept
faithful by a test, and that a handful of keys were read by nothing.

The audit recommended shrinking the file and moving the critic roster. The owner's review
went further, and this record is that decision: the CLI does not depend on the file at
all, and the skill is what tells the coding harness about it.

Decision-044 rested on four arguments for the CLI reading a repository's config. They are
answered here rather than dismissed:

| decision-044 said | What this decision does about it |
|---|---|
| The keys are per-repository; one machine-scoped file would need an `OWNER/REPO →` map that drifts. | The spec directory becomes one value per instance (`routing.graph.specDir`), which the owner accepts; the label prefix becomes a constant; the origin repository comes from the work item itself. Nothing needs a map. |
| The skill reads the same values, so a second source would let CLI and agent disagree. | The agent now *hands* the CLI its values (`--spec-dir`, `--glob`, `--doc`), so there is one source — the agent's read — and the CLI has no copy to disagree with. |
| `check` and `scenarios` run in bare CI checkouts with no CLI config. | They still do, on defaults, with `--spec-dir` / `--glob` for a repository whose layout differs. |
| The trust argument only runs one way: a checkout saying where its specs are can only affect work on itself. | True, and no longer needed: removing every read removes the question of which direction is safe. |

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The CLI never opens a repository's harness config.** `the_loop.harness_config`, its `READS` table and its tests are deleted; the packaged default and the adopt-on-spawn path (issue-193, issue-201) go with them, and `harness.config_scaffolded` leaves the event catalog. | A reader with zero keys is a reader that will grow one; deleting the module makes the rule structural. Adoption existed to give the agent a file to read; a CLI that reads no harness config has no business writing one into somebody's repository. |
| D2 | **The spec directory is the operator's**: `routing.graph.specDir` (default `docs/specs`, one value per instance) and `--spec-dir` on `check`/`graph` (CLI, API, SDK). The harness config keeps `workflow.specDir` for the agent, and the skill says the two must agree. | The daemon must resolve the directory before any session exists; an instance-wide value is what a CLI with no repository read can have. issue-123's per-repository layout is the cost the owner accepted. |
| D3 | **The phase label is `loop:<phase>`, a constant.** `workflow.phaseLabelPrefix` and `workflow.phases` are removed; `/the-loop:init` creates the labels from the graph's phases. | The graph was already the only source of truth (issue-148's parity test kept the config a mirror); one vocabulary is what a dashboard built on the labels needs (issue-73). |
| D4 | **The origin repository is the work item's ref**, passed by the daemon, or the checkout's `origin` remote in-session; `ticketing` is removed from the harness config. | The owner's inline review: *"Users can use whatever ticketing system they want. Repository shouldn't enforce."* The daemon always knew the repository; in-session the remote is the same fact `_checkout_belongs_to` already trusts. |
| D5 | **`repoInitialized` becomes `guestLoop`.** A contribution or a review keeps its spec tree out of git and posts its plan to the thread; the work item's own loops never do. | The question was always about the loop's posture, not about a file in the checkout; asking the loop removes the last reason to look at `.the-loop/`. |
| D6 | **`notifications` is removed.** The `notify` hook publishes on the bus; roles come only from the node's `with:`. | Nothing resolved a role to a person since issue-304, and delivery is the channel's `subscribe` list (issue-309). The owner's inline review: *"delete."* |
| D7 | **Critics move to the CLI config** (`critics[]`, same entry shape); `reviews` keeps the counts. `the-loop critic` reads the resolved CLI config, strictly. | A critic is a harness and a model installed on the machine that runs the round. Executable configuration leaves the one file a pull request to the repository can edit — the reason the harness config sat in this repository's `sensitivePaths`. The owner's inline review: *"this should be moved to cli-config."* |
| D8 | **Graph hooks move to the CLI config** (`routing.graph.hooks`, same shape; a `path` resolves against each checkout). `routing.graph.repoHooks` is removed and `migrate-config` strips it. | The declaration of what runs inside the-loop's process is the operator's; a switch for refusing a repository's declaration has nothing left to refuse. The module may still live in the repository — what may not is the decision to run it. |
| D9 | **`scenarios` and `instructions` take what the agent read as flags**: `--glob`, and `--doc` (a path, or a JSON object with `notes`) plus `--on-missing`. The harness config keeps `testing.integrationTestGlobs` and `customInstructions` for the agent. | Both commands exist to make an obligation the agent has observable; the agent is the one who read the obligation, so it hands the list over. The commands work in a bare checkout exactly as before. |
| D10 | **Dead keys go**: `workflow.specApproach`, `workflow.requireHumanReviewPerPhase`, `localOrchestration`. Harness config `0.2.0` → `0.3.0`; CLI config `0.8.0` → `0.9.0`; `/the-loop:upgrade-the-loop` carries the migration. | Found by the audit, confirmed by the owner's inline review (*"delete"*, *"remove this. not needed."*). |
| D12 | **Policy is the skill's, not a key.** `autonomy`, `security`, `tdd`, `minimalism`, `tokenEconomy`, `selfImprovement`, `contextManagement`, `userInteraction` and `externalTools` leave the harness config; the behaviour each configured is stated as the loop's fixed rule in the reference file that owns it (risk tiers 1–2 autonomous, 3–4 human-approves-pr, 5 human-approves-spec-and-pr, with fixed sensitive paths; the security gates always on with a named sign-off at tier 4+; TDD standard; minimalism on; the token economy advisory; learnings with a 200-line index and a third-occurrence write gate; clear at a phase boundary, compact after a task; mermaid, the PR briefing and the `the-loop:writing` contract), and the harness discovers its own tools. | The owner's second review of the shrunken file: *"remove all the bs in harness config pls"*, one *"we should remove it"* per block, and for `externalTools`: *"the harness can auto discover it."* A knob nobody turns is a promise the loop cannot keep; a rule stated once in the skill is the same behaviour with nothing to drift. |
| D11 | **The skill tells the harness.** `SKILL.md` § Configuration states that the file is the agent's, that the CLI never reads it, and — key by key — what the agent passes to which command. | The owner's ask, verbatim. A rule the agent does not know is a flag it will not pass. |

## Consequences

- **Breaking.** A repository on harness config `0.2.0` still validates nowhere the CLI
  looks (the CLI does not look), but the agent's schema refuses the removed keys until
  `/the-loop:upgrade-the-loop` migrates it. A CLI config declaring `routing.graph.repoHooks`
  is refused until `the-loop migrate-config` runs. A critic or a hook declared in a
  repository is **inert** until the operator copies it into their CLI config — that is
  the point, and the migration says so.
- **Eleven keys remain** — `version`, `repository`, `workflow`, `tooling`,
  `customInstructions`, `testing`, `apiSpecs`, `design`, `hooks`, `observability`,
  `reviews`: facts about the repository the agent cannot infer and the round counts.
  Everything that was a policy switch is now a sentence in a reference file; changing it
  is a change to the-loop, reviewed as one.
- **One directory per instance.** Two repositories with different spec layouts can no
  longer be driven by one daemon. An operator with that need runs two instances
  (issue-322 made that cheap) or aligns the layouts.
- **No adoption.** A session spawned into a repository without `.the-loop/` works on the
  schema's defaults and says so; nothing is written for it. The pre-rename `config.yaml`
  is read by nothing any more.
- **What stays pinned.** `test_config_schema_parity` still holds the packaged CLI schema
  to the authored one; `test_docs_parity` documents every new CLI-config leaf; the graph
  parity tests lose P4 (the phase mirror) and keep P1–P3. No test opens a harness config
  from CLI code, because no CLI code does.

## Alternatives considered

- **Keep decision-044's eight reads and only move `reviews.critics[]`** — the audit's own
  recommendation. Rejected by the owner: a reader with seven keys is still a dependency,
  and the rule "the CLI does not depend on it at all" is simpler to hold than "the CLI
  reads these and only these".
- **Read the harness config for `specDir` only, by existence/size rather than content** —
  rejected; it is the same dependency in a thinner coat, and `specDir` is exactly the key
  an instance-wide value serves.
- **Derive `repoInitialized` from the existence of `.the-loop/`** — rejected in favour of
  the loop's own posture (D5): the directory's existence is a fact about the checkout the
  CLI was asked to stop reading, and the behaviour was always about guests.
- **Keep `routing.graph.repoHooks` as a switch for the operator's own hooks** — rejected;
  an operator who wants no hooks declares none.
- **Delete the `instructions` command instead of giving it flags** — rejected; the
  command, its API route and its SDK method exist, and the observable-obligation argument
  (issue-132) still holds once the agent passes the list.
