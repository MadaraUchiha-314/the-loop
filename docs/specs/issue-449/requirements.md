---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#449"
status: in-review
approvedBy: []
collaborators: [product-manager, architect, engineer, security-reviewer]
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: Codex CLI as a hosting harness and critic

## Introduction

[Issue-449](https://github.com/MadaraUchiha-314/the-loop/issues/449) asks for OpenAI's
Codex CLI to run the loop end to end, as Claude Code does. Issue-440 made the harness a
per-work-item choice and named Codex as its first follow-up.

> **Provenance.** This file was recorded after implementation began, during the PR #450
> review: the PR shipped only `brainstorm.md` and `design.md` for a tier 4 change. It
> restates the contract in [`design.md`](design.md) and the brainstorm's hand-off as
> testable criteria. It is **in review, not approved**: a human must approve it at the
> `requirements-definition` gate.

## Requirements

### R1: Codex is a declared, hosting harness

- **R1.1** WHEN an operator declares `name: codex` under `harnesses`, the-loop SHALL
  offer `harness-codex` at `phase-selection` and spawn the work item's session on Codex.
- **R1.2** Model selection SHALL use `--model`; effort SHALL use the
  `model_reasoning_effort` configuration override, and an effort Codex cannot express
  SHALL NOT be offered.
- **R1.3** Codex SHALL be usable as a one-shot critic through `codex exec --json`, with
  usage reported from the final usage record and cached input not counted twice.

### R2: Conversation identity

- **R2.1** The-loop SHALL identify a Codex conversation positively, by a launch marker
  in the first prompt and the rollout's absolute working-directory metadata, and SHALL
  bind the native id once discovered.
- **R2.2** Resume SHALL use only a positively identified native id and SHALL NOT select
  a conversation by recency. Missing or ambiguous identity SHALL fail resume observably.
- **R2.3** Rollout reads SHALL stay inside `$CODEX_HOME/sessions` and refuse escaping
  symlinks and malformed records.
- **R2.4** Identity discovery SHALL NOT re-read the whole session store on every event
  once a conversation is identified.

### R3: Instructions, hooks and trust

- **R3.1** Environment preparation SHALL preserve the operator's `AGENTS.md` /
  `AGENTS.override.md` and maintain one identified managed block.
- **R3.2** The managed block SHALL NOT reach the project's history: an untracked
  instructions file in a work-item checkout SHALL be excluded from git, and a tracked
  one SHALL remain unchanged, with the managed block installed in Codex's global
  instructions instead.
- **R3.3** One Stop hook SHALL exist per Codex home. Reinstalling from another
  interpreter or install path SHALL replace the previous gate, not add a second one.
- **R3.4** Directory trust SHALL be written to `$CODEX_HOME/config.toml` without
  rewriting operator entries, and SHALL never blanket-trust `/` or the home directory,
  including as a linked worktree's main repository root.
- **R3.5** Every Codex path SHALL resolve `$CODEX_HOME` the same way (whitespace
  stripped, `~` expanded).
- **R3.6** Hook trust, sandbox and approval policy SHALL never be bypassed.

### R4: Configuration and delegation

- **R4.1** `migrate-config` SHALL move `routing.harnessArgs.<name>` onto a declared
  `harnesses[]` entry and SHALL NOT declare a harness the operator did not declare.
  A repeat run SHALL be a no-op, and a malformed block SHALL be dropped once.
- **R4.2** `mcp-call` SHALL delegate through the requested adapter's one-shot argv and
  SHALL NOT pass interactive launch arguments to it.
- **R4.3** An unknown harness SHALL block rather than fall back to Claude.

### R5: Diagnostics

- **R5.1** A declared default that cannot host SHALL be reported
  (`session.default_harness_bypassed`) once per configuration.
- **R5.2** An item filtered by arming labels SHALL be reported (`poll.item_filtered`)
  once per change in its missing labels, not on every poll cycle.
- **R5.3** A disconnected GraphQL read SHALL be retried once; a mutation SHALL NOT be.
- **R5.4** WHEN a CLI/API start is accepted and waits at the first human gate,
  THEN it SHALL report waiting successfully and preserve the start request so
  the gate's answer can launch the selected harness. A genuine spawn failure
  SHALL still clear the request and report failure.

## Out of scope

- Deduplicating the plugin's Stop hook against the daemon-installed one.

## Security considerations

The operator authorizes phase selections and the runtime controls the harness.
Repository instructions, rollout metadata and GitHub comment bodies are untrusted
inputs. Authentication stays in the operator's normal Codex home; it is never
copied into a per-session home or committed to a repository.

- WHEN a rollout has missing, relative or mismatched directory metadata, an unsafe
  native ID, an ambiguous marker or an escaping symlink THEN identity lookup SHALL
  refuse it rather than resume another conversation (R2.1–R2.3).
- WHEN instruction preparation encounters an escaping symlink or malformed managed
  block THEN it SHALL refuse the write rather than overwrite operator instructions
  or write outside its permitted location (R3.1–R3.2).
- WHEN trust preparation encounters the home directory or filesystem root THEN it
  SHALL refuse blanket trust; hook trust and execution policy remain operator-owned
  (R3.4–R3.6).
- WHEN a human gate is pending THEN preserving an accepted start SHALL NOT bypass
  authorization or launch a harness before the authorized answer (R5.4).
- WHEN delegation names an unknown harness THEN it SHALL block; retries SHALL NOT
  replay GitHub mutations (R4.3, R5.3).
