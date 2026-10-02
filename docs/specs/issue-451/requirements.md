---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#451"
status: in-review
approvedBy: []
collaborators: [product-manager, architect, engineer, security-reviewer]
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: a default model per harness in `cli-config.yaml`

## Introduction

[Issue-451](https://github.com/MadaraUchiha-314/the-loop/issues/451): *"the-loop should
allow to configure (in cli-config.yaml) a default model for use-cases where the user
doesn't select a model in phase-selection or phase-selection is not applicable like
`the-loop do` or `the-loop contribute`. Currently in such cases, the-loop doesn't pass a
model and the default model is selected which might be configured by the enterprise org
or user etc."*

**What is broken.** A work item's session gets a model flag only when its
`phase-selection` reply froze one (issue-358). Everything else — a gate answered without
a model tick, an install with no `models[]`, an ad-hoc `the-loop do`, a review — launches
with no `--model` at all, so the harness picks. That pick is whatever the enterprise
policy, the user's `~/.claude/settings.json` or the vendor's current default says on that
machine on that day. The operator has no say in it short of writing `--model` into
`harnesses[].args`, which then fights every model a work item does choose (two `--model`
flags, the winner decided by the harness's parser).

**What this adds.** One optional key per harness, `harnesses[].defaultModel`: the model a
session on that harness is launched on when nothing chose one. A work item's own choice
still wins; an install that does not set the key launches exactly as it does today.

## Requirements

### Requirement 1 — the operator declares a default model per harness

**User story:** As the operator of a the-loop instance, I want to name the model each
harness runs on by default, so a session that chose no model runs on a model I picked
rather than on whatever the harness's own settings say today.

#### Acceptance criteria (EARS)

1. The CLI config schema SHALL accept an optional `defaultModel` string on each
   `harnesses[]` entry, constrained to the model-name grammar
   `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`.
2. The system SHALL NOT require a `defaultModel` to also be declared in `models[]`: the
   default applies where no choice is offered at all.
3. IF a `defaultModel` value does not match the model-name grammar THEN the system SHALL
   treat the harness as having no default model.

### Requirement 2 — a session that chose no model launches on the default

**User story:** As the operator, I want every work-item session that has no model of its
own — `the-loop do`, `the-loop contribute`, `the-loop review`, and a `phase-selection`
reply with no model ticked — to run on its harness's default model.

#### Acceptance criteria (EARS)

1. WHEN a work item's session is launched on a harness that declares a `defaultModel` AND
   the work item froze no model THEN the system SHALL append the harness's model flag and
   the default model to the launch arguments, after the harness's own `args`.
2. WHEN a work item froze a model that is valid for the harness THEN the system SHALL
   launch on the frozen model and SHALL NOT add the default model.
3. WHEN a frozen model is discarded on re-validation (no longer declared, or narrowed to
   another harness) THEN the system SHALL launch on the harness's default model.
4. The session record, the `session.spawned` event and the lifecycle hooks SHALL name the
   model the session was actually launched on, including a default model.
5. IF the harness's adapter has no model flag THEN the system SHALL NOT apply a default
   model, and `the-loop models list|check` SHALL say so.
6. IF the availability cache holds a standing `refused` verdict for the default model on
   that harness THEN the system SHALL launch without it, as it does for a refused frozen
   model.

### Requirement 3 — the gate tells the human what "no tick" means

**User story:** As the person answering `phase-selection`, I want to read which model the
work item will run on if I tick none, so the default is a visible outcome rather than a
surprise.

#### Acceptance criteria (EARS)

1. WHEN the checklist renders a model section AND the default harness declares a
   `defaultModel` THEN the section's closing line SHALL name that model as what an
   unticked section means.
2. WHEN the confirmation reports no model choice AND the resolved harness declares a
   `defaultModel` THEN the confirmation SHALL name that model and say it is the harness's
   default.

### Requirement 4 — the probe covers the default

1. `the-loop models check` SHALL probe each harness's `defaultModel` on that harness,
   alongside the declared `models[]`, so a default the harness refuses is reported before
   a spawn discovers it.

### Requirement 5 — nothing changes for an operator who does not use it

1. IF no `harnesses[]` entry declares a `defaultModel` THEN launch arguments, session
   records, checklists and confirmations SHALL be exactly as they are today.

## Non-functional requirements

- **No new I/O on the dispatch path.** The default is read from the CLI config the
  dispatcher already holds.
- **Documentation.** The key is described in the configuration reference, the CLI config
  template and schema, and `interactive-sessions.md`.

## Security considerations

This adds one more value that reaches a launch argv. The value comes only from the
operator's own `cli-config.yaml`; no comment, label or state file can set it.

- **Actors & trust:** untrusted — anyone who can comment on a work item or edit an
  agent-writable `work-item-state.json`; trusted — the operator's `cli-config.yaml` and
  the adapters shipped in the-loop.
- **Trust boundary:** the argv builder. The default model is read from the operator's
  config, checked against the model-name grammar, and placed after the adapter's own
  model flag. Nothing from a reply or a state file selects or alters it.
- **Data:** no secrets are read or moved. A model name is not sensitive.
- **Abuse cases (EARS):**
  1. WHEN a `defaultModel` is a flag, a path or a shell fragment (for example
     `--dangerously-skip-permissions` or `x; rm -rf /`) THEN the system SHALL NOT place it
     in any argv (R1.3).
  2. WHEN a state file is hand-edited to name an undeclared model THEN the system SHALL
     launch on the harness's default model, never on the forged one (R2.3).
  3. WHEN one harness declares a `defaultModel` THEN the system SHALL NOT apply it to a
     session on any other harness.
- **Fail closed:** every invalid or unusable default resolves to *no model flag*, which
  is what every session gets today.

## Out of scope

- **A default effort level.** The issue asks for the model only; the same key shape can
  carry `defaultEffort` later if someone asks.
- **Standing sessions** (`standingSessions.sessions[]`). They are channel sessions with
  their own `harnessArgs`, not work-item sessions; an operator can already put `--model`
  in those arguments.
- **Critics.** A critic entry already carries its own `model`.

## Open questions

1. Should a session already running on no model be re-launched when the operator adds a
   `defaultModel`? Proposed: yes, by the existing drift rule — a live session whose
   recorded arguments differ from what resolves now is re-launched with its conversation
   resumed, exactly as when `harnesses[].args` changes.
