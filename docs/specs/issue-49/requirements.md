---
type: requirements
phase: requirements-definition
workItem: issue-49
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: sensible defaults + guided onboarding in `/init`

> Phase 1 of 3 (requirements → design → tasks). Tracked as
> [issue #49](https://github.com/MadaraUchiha-314/the-loop/issues/49).

## Introduction

`/the-loop:init` scaffolds `.the-loop/config.yaml` from a template, but the config has
~25 top-level sections and the user is left to guess what each key means, what values
are legal, and which ones actually need their input. Init should instead ship sensible
defaults everywhere a default is sensible, and **establish the rest with the user**
through a guided onboarding: related configs clubbed into groups, each group explained
with examples (and, for enums, every possibility), driven by the config schema so the
walkthrough cannot drift from what the config accepts.

## Requirements

### Requirement 1 — sensible defaults everywhere

**User story:** As a user initializing the-loop, I want every config key to arrive with
a sensible value, so that I only decide the things that genuinely need me.

#### Acceptance criteria (EARS)

1. WHEN init resolves a config key THEN the system SHALL apply the first available of:
   the existing configured value, the value detected from the repository, the schema
   default.
2. WHEN init runs with `--defaults` THEN the system SHALL write the config without any
   interaction and SHALL list every un-defaultable gap under **needs-user** in the
   final report.

### Requirement 2 — grouped, interactive onboarding

**User story:** As a user initializing the-loop, I want related configs presented
together as groups I can confirm in one pass, so that onboarding is short and the
interactions match how the settings actually relate.

#### Acceptance criteria (EARS)

1. WHEN init runs interactively THEN the system SHALL walk the config groups in the
   schema-declared order, asking at most once per group.
2. IF a group has no sensible default (e.g. ticketing owner/repo, personas) THEN the
   system SHALL establish it with the user before completing init.
3. IF a group is marked advanced THEN the system SHALL default it silently and only
   tour it on request.
4. WHEN init re-runs on an initialized project THEN the system SHALL raise only gaps
   (empty required keys, `# TODO: verify` lines, keys added by an upgrade) and SHALL
   never re-ask or overwrite established answers.

### Requirement 3 — explain, with examples and all enum possibilities

**User story:** As a user being onboarded, I want each config group explained with
examples and every enum option spelled out, so that I understand what I am configuring
without guessing.

#### Acceptance criteria (EARS)

1. WHEN a group is presented THEN the system SHALL explain what it controls and why it
   matters, and SHALL mark where each proposed value came from (detected / default /
   already configured).
2. WHEN an enum key is presented THEN the system SHALL show ALL legal values with a
   one-line meaning each.
3. WHEN a free-form key is presented THEN the system SHALL show example values.

### Requirement 4 — the schema drives the onboarding

**User story:** As a maintainer, I want the onboarding metadata to live in the config
schema, so that the walkthrough, the docs and the validation can never drift apart.

#### Acceptance criteria (EARS)

1. The config schema SHALL declare the ordered onboarding groups (clubbed keys, title,
   explanation, ask level) as machine-readable metadata alongside the existing
   per-key descriptions, defaults and enums.
2. The schema SHALL carry `examples` for the gap-prone free-form keys (ticketing
   owner/repo, jira, personas, messaging, sensitive paths, integration-test globs,
   critics).
3. Adding the metadata SHALL NOT change what configs validate (validators ignore the
   annotation keywords).

## Non-functional requirements

- Onboarding stays harness-agnostic: structured-question UIs are used where available
  (Claude Code), plain chat otherwise (Cursor).
- Idempotence and non-clobbering of init are preserved unchanged.

## Out of scope

- A CLI/TUI implementation of the walkthrough (the commands remain prompt-driven).
- Changing any existing schema default or validation rule.

## Open questions

None.
