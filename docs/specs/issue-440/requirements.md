---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#440"
status: in-review
approvedBy: []
collaborators: [product-manager, architect, engineer, security-reviewer]
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: the harness is a per-work-item choice at `phase-selection`, beside model and effort

## Introduction

[Issue-440](https://github.com/MadaraUchiha-314/the-loop/issues/440): *"Harness should also
be selectable in phase selection along with model and effort — users should be able to
switch between harnesses like claude, cursor, codex, pi."*

Issue-358 made **model** and **effort** per-work-item answers on the `phase-selection`
checklist. The **harness** stayed one value per machine (`routing.defaultHarness`), so a
work item could pick a model its harness cannot run and could never pick the harness that
can. Worse, the gate and the daemon read that one value from different places: the gate
honours `harnesses[].default: true`, the daemon only `routing.defaultHarness` — so the
checklist can offer one harness's models while the session spawns on another.

This work item adds a third choice section, `harness-<name>`, with the same shape as the
other two: declared by the operator, offered by the gate, answered by the same signed
reply, frozen into `work-item-state.json`, re-validated by the daemon at spawn.

**What it does not do:** add adapters. Only a harness that can host a work item's session
(an interactive TUI in tmux with a pre-assignable session id) can be offered. Today that is
`claude` alone — `cursor-agent` cannot (its adapter says why), and there is no `codex` or
`pi` adapter. So on today's adapters the section stays hidden and nothing changes; each new
hosting adapter becomes selectable with no further gate work. Those adapters are follow-ups.

## Requirements

### Requirement 1 — an authorized human picks the harness for one work item

**User story:** As an operator with more than one agent CLI installed, I want to say which
harness *this* work item runs on at the same gate where I pick its model and effort, so a
work item is not bound to one machine-wide harness.

#### Acceptance criteria (EARS)

1. WHEN the `phase-selection` checklist is posted AND at least two **offerable harnesses**
   exist THEN the system SHALL render one `harness-<name>` row per offerable harness, in
   declaration order, in a section of its own placed before the model and effort sections.
2. An **offerable harness** SHALL be one declared in the top-level `harnesses[]` whose
   adapter exists in this build of the-loop AND can host a work item's session.
3. IF fewer than two offerable harnesses exist THEN the system SHALL render no harness
   section — one option is not a choice — and the checklist SHALL be byte-identical to the
   one the same work item gets without this change.
4. WHEN an authorized user replies with the execute keyword THEN the system SHALL resolve
   the harness choice by the same rule the model and effort use: exactly one ticked,
   offered row is a choice; none, several, or an unoffered token is no choice.
5. WHEN the gate confirms a selection that offered harnesses THEN the confirmation SHALL
   name the harness the work item will run on, including when it is the default.
6. The system SHALL freeze the harness choice into `work-item-state.json` (`harness`) and
   the frozen-graph record, beside `model` and `effort`; `""` SHALL mean *no choice*.

### Requirement 2 — model and effort are resolved against the chosen harness

**User story:** As the person answering the gate, I want a model I tick to be checked
against the harness I tick in the same reply, so I cannot freeze a pair that cannot run.

#### Acceptance criteria (EARS)

1. WHEN a harness section is rendered THEN the model and effort sections SHALL offer each
   declared choice that is offerable on **at least one** offered harness.
2. WHEN the reply is resolved THEN the system SHALL resolve the harness first and SHALL
   accept a model or effort choice only if it is offerable on the **resolved** harness (the
   chosen one, else the default).
3. IF a ticked model or effort is not offerable on the resolved harness THEN the system
   SHALL record no choice for that section and the confirmation SHALL say which choice was
   dropped and why.

### Requirement 3 — the daemon spawns on the frozen harness, never on a forged one

**User story:** As the operator, I want a work item's first session to start on the
harness its gate froze, and a hand-edited record to buy nothing.

#### Acceptance criteria (EARS)

1. WHEN a work item's session is spawned after the gate THEN the system SHALL launch it on
   the frozen harness's adapter, with that harness's launch arguments and the frozen model
   and effort merged as issue-358 R3.1 defines.
2. The system SHALL re-validate the frozen harness on read: IF it is not declared in
   `harnesses[]`, has no adapter, or its adapter cannot host a session THEN the system SHALL
   spawn on the default harness and SHALL log that it did.
3. The session record, the spawn event and the lifecycle hooks SHALL name the harness the
   session was actually launched on.
4. A **respawn** of an existing session SHALL keep that session's recorded harness — a
   conversation cannot be resumed in a different harness. A frozen harness that differs
   from a live session's SHALL apply to the next fresh session (after `the-loop sessions
   reset`), not by killing the running one.

### Requirement 4 — the gate and the daemon agree on the default

**User story:** As the operator, I want the harness the checklist calls "the default" to
be the harness the session actually spawns on.

#### Acceptance criteria (EARS)

1. The system SHALL resolve the default harness in one place, used by both the gate and the
   daemon: the `harnesses[]` entry with `default: true` if it is offerable, else
   `routing.defaultHarness`.
2. IF the entry marked `default: true` cannot host a session THEN the system SHALL NOT make
   it the default, and `the-loop models check`/`diagnose` SHALL say so.

### Requirement 5 — nothing changes for an operator who does not use it

1. IF `harnesses[]` declares fewer than two offerable harnesses THEN checklists, spawns and
   session records SHALL be exactly as they are today.
2. A `work-item-state.json` written before this change SHALL still load, and SHALL read as
   *no harness choice*.

## Non-functional requirements

- **No new I/O on the dispatch path.** The frozen harness is read from the same state file
  the dispatcher already reads for `model`, `effort` and `sessionPerPr`.
- **Documentation.** The choice is described where the other per-work-item questions are:
  the configuration reference, `interactive-sessions.md`, `process-graph.md`, and the
  phase-selection section of the operating model.

## Security considerations

This work item adds one path from **comment text to which binary an unattended agent
runs**. That is the risk, and every rule below keeps the path a lookup into the operator's
own configuration.

- **Actors & trust:** untrusted — anyone who can comment on or edit a comment on the work
  item; semi-trusted — `routing.authorizedUsers`; trusted — the operator's
  `cli-config.yaml` and the adapter classes shipped in the-loop.
- **Trust boundary:** the gate's parse. A reply yields at most a token matched against the
  offered set; the binary and its arguments come from the adapter and the operator's
  `harnesses[].args`. No text from a comment reaches an argv or a binary path.
- **Data:** no secrets are read or moved. A harness name is not sensitive.
- **Abuse cases (EARS):**
  1. WHEN an unauthorized user ticks a harness row and replies with the execute keyword THEN
     the system SHALL ignore the reply, exactly as for phase ticks.
  2. WHEN an authorized reply names a harness that is not offered — undeclared, a path, a
     binary name, a flag — THEN the system SHALL record no choice.
  3. WHEN `work-item-state.json` is hand-edited to name an undeclared or non-hosting harness
     THEN the daemon SHALL spawn on the default harness (R3.2).
  4. WHEN a harness is chosen THEN the system SHALL launch it with only the arguments the
     operator declared for that harness plus the resolved model and effort — choosing a
     harness SHALL NOT carry another harness's arguments (for example a permission flag)
     onto it.
- **Fail closed:** every ambiguity resolves to the default harness, which is what every
  work item runs on today.

## Out of scope

- **New adapters** — `codex`, `pi`, and an interactive `cursor-agent`. Each is a work item
  of its own (argv, resume, trust seeding, plugin install, effort mapping, probe). This
  work item makes each selectable the moment it lands.
- **Moving a running session to another harness.** No harness can resume another's
  conversation.
- **A per-phase harness.** The issue title says "phase selection", which is the name of the
  gate; like model and effort, the choice is per work item.
- **A UI or Slack control for the choice.** The Slack mirror already sends model and effort
  back to GitHub; the harness follows the same rule.

## Open questions

1. Should an unhosted-but-declared harness (e.g. `cursor`) appear in the section as a
   disabled row with the reason? Proposed: no — `the-loop models check` already reports it,
   and a row nobody can tick is noise on a phone.
