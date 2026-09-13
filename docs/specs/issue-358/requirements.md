---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#358"
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer, security-reviewer]
overrides: {}
riskTier: 4
---

# Requirements: per-work-item model choice, answered at the phase-selection gate

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue-358](https://github.com/MadaraUchiha-314/the-loop/issues/358). Today the model a
spawned session runs on is `routing.harnessArgs.<harness>` — **one list, every session**.
An operator who wants five of eighteen work items on a different model has no supported
path: the reporter typed `/model fable` into each tmux pane by hand, which the-loop
cannot see, does not record, and loses on the next respawn.

The ticket asked for a **label**-to-args map. The owner
[disagreed on that mechanism](https://github.com/MadaraUchiha-314/the-loop/issues/358#issuecomment-5654002784):
a label rides GitHub's permission model, not the-loop's, so anyone who can label an issue
could choose what argv an unattended agent runs on. That is the same argument that put
phase selection on a comment rather than a label in the first place (issue-177,
[selection.py](../../../cli/the_loop/graph/hooks/selection.py)), and it applies with more
force here, because this input reaches an **argv**. The owner named the venue instead:
the **phase-selection lifecycle**, where an authorized human already answers three
per-work-item questions with one signed reply.

So these requirements keep the reporter's five properties and move the channel:

| Reporter asked for | Kept as |
|---|---|
| a configurable label-to-args map | an operator-declared, closed set of **model choices** per harness (R2) |
| merge, do not replace | R3 |
| applied at spawn and at respawn | R4 |
| visible in the registry | R5 |
| unlabelled items unchanged | R6 — a work item that chooses nothing runs exactly as today |

The owner's three open questions are answered in the requirements rather than left to the
design: the-loop **discovers no models** (R2 — the operator declares them, as they already
declare repositories and critics), the list stays short because a human curates it (R2.4),
and the cross-harness answer is the adapter's own model flag (R2.5).

## Requirements

### Requirement 1 — an authorized human picks the model for one work item

**User story:** As an operator running eighteen work items from Slack on a phone, I want to
say which model *this* item's session runs on without editing config or restarting the
daemon, so that a small item can run cheaply and a hard one can run on the strongest model.

#### Acceptance criteria (EARS)

1. WHEN the `phase-selection` checklist is posted for a work item whose harness has
   declared model choices THEN the system SHALL render one row per declared choice, in the
   order the operator declared them, in a section of its own, distinct from the phase rows.
2. WHEN an authorized user replies with the execute keyword THEN the system SHALL freeze
   the model chosen by the tick state at that moment, by the same authorization and the
   same freeze that already record the phase skips, the outer-loop surface and
   `sessionPerPr`.
3. IF the reply ticks exactly one model row THEN the system SHALL record that choice for
   this work item.
4. IF the reply ticks no model row, or more than one THEN the system SHALL record the
   operator's default and SHALL name that outcome in the gate's confirmation comment —
   the same fail-closed resolution `pr-sessions-*` already uses, so two rows ticked by a
   reader who ticked before unticking can never be resolved by guessing.
5. WHEN the gate confirms a selection THEN the confirmation comment SHALL name the model
   the work item will run on, including when that is the operator's default.
6. IF the work item's harness has no declared model choices THEN the system SHALL render
   no model section at all.

### Requirement 2 — the choices are the operator's, declared and closed

**User story:** As the operator, I want the pickable models to be a list I wrote in my own
config, so that a comment can never introduce a model, a flag or an argument I did not
declare.

#### Acceptance criteria (EARS)

1. The system SHALL read the pickable choices from the operator's CLI config
   (`cli-config.yaml`), per harness, and SHALL NOT infer, discover or fetch a model list
   from a harness, a vendor API or the network.
2. WHEN a reply names a token that is not a declared choice for this work item's harness
   THEN the system SHALL ignore it and use the default — no text from a comment SHALL
   ever reach an argv.
3. The system SHALL resolve a declared choice to argv from the **operator's declaration**:
   the entry's own `args` when it has them, otherwise the harness adapter's model flag
   followed by the choice's id.
4. WHEN more choices are declared than the checklist renders THEN the system SHALL render
   the first N and SHALL say how many were not shown, rather than truncating silently
   (the `CANDIDATE_LIMIT` convention kickoff already uses).
5. IF a declared choice carries no `args` and its harness's adapter has no model flag
   THEN config validation SHALL reject that entry, naming it — the-loop SHALL NOT guess a
   flag, and SHALL NOT discover the problem at spawn time.
6. IF no choices are declared for any harness THEN the system SHALL behave exactly as it
   does today, everywhere.

### Requirement 3 — the choice is merged onto the operator's arguments, never a replacement

**User story:** As the operator, I want my global `--dangerously-skip-permissions` to keep
applying to a session that chose a model, so that choosing a model is not also, silently,
a permission change.

#### Acceptance criteria (EARS)

1. WHEN a work item has a frozen model choice THEN the effective arguments SHALL be
   `routing.harnessArgs.<harness>` followed by the choice's arguments, in that order.
2. The system SHALL NOT remove, rewrite or reorder any argument the operator declared in
   `routing.harnessArgs.<harness>`.
3. The system SHALL NOT add a permission-widening argument that the operator did not
   declare, under any selection — a model choice SHALL only ever contribute the arguments
   its declaration carries.
4. WHEN the operator's global arguments already carry the same model flag as a declared
   choice THEN config validation SHALL warn, naming both, because whether the appended
   flag wins is the harness's argument-parsing rule and not the-loop's to assert.

### Requirement 4 — the choice survives the session

**User story:** As the operator, I want a work item to come back on the model I chose after
a crash, a restart or a `the-loop sessions reset`, so that I never re-type it.

#### Acceptance criteria (EARS)

1. WHEN a session is spawned for a work item with a frozen model choice THEN the system
   SHALL launch the harness with the effective arguments of R3.1.
2. WHEN a session is **respawned** (the recorded session was dead, or was reset) THEN the
   system SHALL re-resolve the effective arguments from the frozen record rather than from
   the arguments the previous session happened to be launched with.
3. WHILE a session is running with arguments that differ from the currently resolved
   effective arguments, the system SHALL re-launch it — resuming its conversation — on the
   next event delivered to that work item, rather than delivering into a session running
   on the wrong model.
4. WHEN such a re-launch happens THEN the system SHALL emit an event-log record naming the
   work item, the previous model and the new one, so the change is auditable.
5. IF the frozen record is missing, unreadable, or names a choice no longer declared THEN
   the system SHALL use `routing.harnessArgs.<harness>` unchanged, and SHALL log that it
   did.

### Requirement 5 — a human can see which model a work item is on

**User story:** As the operator, I want `the-loop sessions list` to tell me which model each
work item is running, so that I can tell without attaching to a pane or reading `/proc`.

#### Acceptance criteria (EARS)

1. WHEN a session is registered or re-registered THEN the system SHALL record on the
   session record the model choice in force and the effective arguments the harness was
   launched with.
2. WHEN `the-loop sessions list` renders its table THEN it SHALL show the model in force
   for each session, and `-` for a session that has none recorded.
3. The JSON form of a session (`--format json`, the control-plane API and the SDK) SHALL
   carry the same two fields.
4. IF a session record was written before this change THEN it SHALL still parse, and SHALL
   render as `-` rather than failing the listing.

### Requirement 6 — a work item that chose nothing is unchanged

**User story:** As an operator who never wanted this feature, I want every work item to run
exactly as it does today, so that upgrading costs me nothing.

#### Acceptance criteria (EARS)

1. IF a work item has no frozen model choice THEN its sessions SHALL be launched with
   `routing.harnessArgs.<harness>` and nothing else.
2. IF the CLI config declares no model choices THEN the phase-selection checklist SHALL be
   byte-identical to the one the same work item gets today.
3. The system SHALL NOT require any repository to create a label, and SHALL NOT read a
   label, to resolve a model choice.

## Non-functional requirements

- **No new I/O on the dispatch path.** The frozen choice is read from the portable record
  the dispatcher already reads for `sessionPerPr` (`_tmux_for`); resolving a model SHALL
  add no network call and no additional file read per event.
- **Observability.** The resolved model appears in the spawn/respawn event-log records
  that already name the harness, so an operator can answer "what did this session
  actually run on" from `the-loop events` alone.
- **Documentation.** The choice is described where the other two per-work-item questions
  are described — the configuration reference, the interactive-sessions capability doc,
  and the phase-selection section of the operating model.

## Security considerations

This work item creates one new path from **comment text to an argv of an unattended
agent**. That is the whole of its risk, and every criterion below exists to keep the path
a lookup into operator-owned configuration rather than a passthrough.

- **Actors & trust:**
  - *Untrusted:* anyone who can comment on, or edit a comment on, a work item; anyone who
    can add or remove a label; any webhook payload.
  - *Semi-trusted:* `routing.authorizedUsers` — named humans who may direct the-loop.
  - *Trusted:* the operator's `cli-config.yaml`, which is executable configuration on the
    machine that runs the daemon and is not editable by a pull request to a repository
    (the same posture `critics[]` took in decision-123).
- **Trust boundaries & data:** the boundary is the gate's parse. A reply yields, at most, a
  **token matched against the declared set**; the argv is then built from the operator's
  own declaration. No sensitive data is stored or moved: a model id is not a secret, and
  nothing here reads or writes credentials.
- **Why not a label (the rejected mechanism):** GitHub's label permission is `triage` on
  the repository and is not the-loop's `authorizedUsers` boundary. Accepting a label here
  would let anyone with triage rights choose the argv of an unattended agent — and would
  do it *silently*, because GitHub does not attribute a label to a person in the payload
  the-loop already authorizes on. The label channel is therefore refused, not merely
  unsupported.
- **Abuse cases (EARS):**
  1. WHEN an unauthorized user ticks a model row on the checklist and asks for execution
     THEN the system SHALL ignore the reply entirely, exactly as it does for phase ticks
     today.
  2. WHEN an authorized user's reply names `--dangerously-skip-permissions`, a shell
     metacharacter, a path, or any string that is not a declared choice id THEN the
     system SHALL treat it as no choice and run the operator's default.
  3. WHEN a declared choice's own `args` would widen permissions THEN the system SHALL
     apply them as declared and SHALL NOT be considered at fault — the operator wrote
     them, in the same file that already carries `harnessArgs` — and the-loop SHALL NOT
     add such an argument on its own initiative in any other circumstance.
  4. WHEN the portable record for a work item has been hand-edited to name an undeclared
     model, or to carry an `args` list of its own THEN the system SHALL re-validate
     against the declared set on read and SHALL fall back to the operator's default
     (the portable tree is agent-writable; it is re-validated on the way in, as
     `_tmux_for` already re-validates `sessionPerPr`).
  5. WHEN a label named after a model is present on the work item THEN the system SHALL
     ignore it.
  6. WHEN the gate cannot read its own checklist comment (an outage, a deleted comment)
     THEN the system SHALL resolve to the operator's default.
- **Fail closed:** every ambiguity — no tick, several ticks, an unknown token, an
  unreadable record, a missing declaration — resolves to `routing.harnessArgs.<harness>`
  unchanged. The closed direction here is *the operator's own configuration*, never the
  narrowest or cheapest model.

## Out of scope

- **A model choice for standing sessions.** They already have per-entry `harnessArgs`
  (issue-277) and are not work items.
- **Changing an already-running session's model in place.** No harness exposes that; R4.3
  re-launches instead.
- **A separate "effort" axis.** The owner raised it alongside model choice, and it is
  served by the same mechanism rather than a second one: a declared choice is a *named
  argv*, so `opus-deep` can carry both a model and whatever effort flag its harness has.
  A dedicated effort key is deliberately not introduced — no harness the-loop adapts
  exposes a common one, so modelling it now would be a vocabulary with one member.
- **Model choice for the inner (per-PR) loops** independently of their work item. A PR's
  session inherits its work item's choice.
- **A control keyword** (`the-loop model: …`). One surface for a per-work-item decision,
  and the gate is it.

## Open questions

1. **The first session runs on the default.** The gate is answered *after* a session
   exists — the session is what posts the checklist — so the model chosen there takes
   effect when R4.3 re-launches it, on the delivery of the execute comment itself. The
   cost is one re-launch at the start of every work item that chooses a non-default model,
   and the alternative (asking before the spawn) has no authorized channel that exists
   before a session does. Raised on the ticket; the design proposes the re-launch.
2. **Whether the kickoff should also carry the choice.** A Slack kickoff (issue-349) could
   name the model as it names the repository, which would make the first session itself
   run on it. Out of scope here; noted as the natural follow-up if question 1's re-launch
   proves annoying in practice.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
