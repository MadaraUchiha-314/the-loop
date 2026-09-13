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

# Requirements: per-work-item model and effort choice, answered at the phase-selection gate

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.
>
> **Revision 2** — rewritten against the owner's review of PR #359. Three things changed:
> model and effort are **two independent inputs** (not one coupled choice), a model the
> harness will not accept is now a **stated requirement** (R7) rather than an unexamined
> case, and the key is `routing.models`. The fourth point — that a session should not exist
> before the gate is answered — is answered in `design.md` § *Why a session exists before
> the gate, and why it should not*, and is proposed as a prerequisite work item.

## Introduction

[Issue-358](https://github.com/MadaraUchiha-314/the-loop/issues/358). Today the model a
spawned session runs on is `routing.harnessArgs.<harness>` — **one list, every session**.
An operator who wants five of eighteen work items on a different model has no supported
path: the reporter typed `/model fable` into each tmux pane by hand, which the-loop cannot
see, does not record, and loses on the next respawn.

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
| a configurable label-to-args map | an operator-declared, closed set of **models** and, separately, of **effort levels**, per harness (R2) |
| merge, do not replace | R3 |
| applied at spawn and at respawn | R4 |
| visible in the registry | R5 |
| unlabelled items unchanged | R6 — a work item that chooses nothing runs exactly as today |

And they answer the two questions the owner's review added: a model the harness does not
accept is **never offered and never reaches a spawn** (R7), and the declarations are **per
harness**, because a model id is only meaningful to the harness that has it.

## Requirements

### Requirement 1 — an authorized human picks the model and the effort for one work item

**User story:** As an operator running eighteen work items from Slack on a phone, I want to
say which model *this* item's session runs on, and how hard it should think, without editing
config or restarting the daemon, so that a small item can run cheaply and a hard one can run
on the strongest model at full effort.

#### Acceptance criteria (EARS)

1. WHEN the `phase-selection` checklist is posted for a work item whose harness has declared
   models THEN the system SHALL render one row per declared model, in the order the operator
   declared them, in a section of its own, distinct from the phase rows.
2. WHEN that harness has declared effort levels THEN the system SHALL render them as a
   **second, independent** section — a work item chooses a model and an effort separately,
   and choosing one SHALL NOT require or imply the other.
3. WHEN an authorized user replies with the execute keyword THEN the system SHALL freeze both
   choices by the same authorization and the same freeze that already record the phase skips,
   the outer-loop surface and `sessionPerPr`.
4. IF a section has exactly one ticked row THEN the system SHALL record that choice for this
   work item.
5. IF a section has no ticked row, or more than one THEN the system SHALL record no choice
   for **that section** and SHALL name the outcome in the gate's confirmation comment — the
   same fail-closed resolution `pr-sessions-*` already uses, resolved per section, so an
   ambiguous model never discards a valid effort.
6. WHEN the gate confirms a selection THEN the confirmation comment SHALL name the model and
   the effort the work item will run on, including when either is the operator's default.
7. IF the work item's harness has declared no models THEN the system SHALL render no model
   section, and likewise for effort — each section appears only if it has something to offer.

### Requirement 2 — the choices are the operator's, declared and closed

**User story:** As the operator, I want the pickable models and effort levels to be lists I
wrote in my own config, so that a comment can never introduce a model, a flag or an argument
I did not declare.

#### Acceptance criteria (EARS)

1. The system SHALL read the pickable models from `routing.models.<harness>` and the pickable
   effort levels from `routing.effort.<harness>` in the operator's CLI config, and SHALL NOT
   infer, discover or fetch either list from a harness, a vendor API or the network.
2. The declarations SHALL be **per harness**. The system SHALL NOT accept a
   harness-independent list, because a model id is meaningful only to the harness that has it
   and attributing one to a harness would be a guess — the same reason a repository is never
   inferred from prose (decision-120).
3. WHEN a reply names a token that is not a declared choice for this work item's harness THEN
   the system SHALL ignore it and record no choice — no text from a comment SHALL ever reach
   an argv.
4. The system SHALL resolve a declared **model** to argv from the operator's declaration: the
   entry's own `args` when it has them, otherwise the harness adapter's model flag followed by
   the entry's id.
5. The system SHALL resolve a declared **effort level** to the entry's own `args`. IF an
   effort entry carries no `args` and its harness's adapter exposes no effort flag THEN
   config validation SHALL reject that entry, naming it — the-loop SHALL NOT invent an effort
   flag, and no adapter it ships today has one.
6. IF a declared model entry carries no `args` and its harness's adapter has no model flag
   THEN config validation SHALL reject that entry, naming it — the failure SHALL be reported
   at validation, never discovered at spawn.
7. WHEN more choices are declared in a section than the checklist renders THEN the system
   SHALL render the first N and SHALL say how many were not shown, rather than truncating
   silently (the `CANDIDATE_LIMIT` convention kickoff already uses).
8. IF no models and no effort levels are declared for any harness THEN the system SHALL
   behave exactly as it does today, everywhere.

### Requirement 3 — the choices are merged onto the operator's arguments, never a replacement

**User story:** As the operator, I want my global `--dangerously-skip-permissions` to keep
applying to a session that chose a model, so that choosing a model is not also, silently, a
permission change.

#### Acceptance criteria (EARS)

1. WHEN a work item has a frozen choice THEN the effective arguments SHALL be
   `routing.harnessArgs.<harness>`, then the model entry's arguments, then the effort entry's
   arguments — in that order, each contributing nothing when there is no choice.
2. The system SHALL NOT remove, rewrite or reorder any argument the operator declared in
   `routing.harnessArgs.<harness>`.
3. The system SHALL NOT add a permission-widening argument that the operator did not declare,
   under any selection — a choice SHALL only ever contribute the arguments its declaration
   carries.
4. WHEN the operator's global arguments already carry the same flag as a declared choice THEN
   config validation SHALL warn, naming both, because whether the appended flag wins is the
   harness's argument-parsing rule and not the-loop's to assert.

### Requirement 4 — the choice survives the session

**User story:** As the operator, I want a work item to come back on the model I chose after a
crash, a restart or a `the-loop sessions reset`, so that I never re-type it.

#### Acceptance criteria (EARS)

1. WHEN a session is spawned for a work item with a frozen choice THEN the system SHALL
   launch the harness with the effective arguments of R3.1.
2. WHEN a session is **respawned** (the recorded session was dead, or was reset) THEN the
   system SHALL re-resolve the effective arguments from the frozen record rather than from the
   arguments the previous session happened to be launched with.
3. WHILE a session is running with arguments that differ from the currently resolved effective
   arguments, the system SHALL re-launch it — resuming its conversation — on the next event
   delivered to that work item, rather than delivering into a session running on the wrong
   model. *(Needed only while a session is spawned **before** the gate is answered; see the
   prerequisite in `design.md`. Once the gate precedes the spawn, this criterion is a safety
   net that no ordinary path exercises, and it is what makes the feature correct under either
   ordering.)*
4. WHEN such a re-launch happens THEN the system SHALL emit an event-log record naming the
   work item, the previous choice and the new one, so the change is auditable.
5. IF the frozen record is missing, unreadable, or names a choice no longer declared THEN the
   system SHALL use `routing.harnessArgs.<harness>` unchanged, and SHALL log that it did.

### Requirement 5 — a human can see what a work item is running on

**User story:** As the operator, I want `the-loop sessions list` to tell me which model each
work item is running, so that I can tell without attaching to a pane or reading `/proc`.

#### Acceptance criteria (EARS)

1. WHEN a session is registered or re-registered THEN the system SHALL record on the session
   record the model and effort in force and the effective arguments the harness was launched
   with.
2. WHEN `the-loop sessions list` renders its table THEN it SHALL show the model in force for
   each session, and `-` for a session that has none recorded.
3. The JSON form of a session (`--format json`, the control-plane API and the SDK) SHALL carry
   the model, the effort and the effective arguments.
4. IF a session record was written before this change THEN it SHALL still parse, and SHALL
   render as `-` rather than failing the listing.

### Requirement 6 — a work item that chose nothing is unchanged

**User story:** As an operator who never wanted this feature, I want every work item to run
exactly as it does today, so that upgrading costs me nothing.

#### Acceptance criteria (EARS)

1. IF a work item has no frozen choice THEN its sessions SHALL be launched with
   `routing.harnessArgs.<harness>` and nothing else.
2. IF the CLI config declares no models and no effort levels THEN the phase-selection
   checklist SHALL be byte-identical to the one the same work item gets today.
3. The system SHALL NOT require any repository to create a label, and SHALL NOT read a label,
   to resolve a choice.

### Requirement 7 — a model the harness will not accept is never offered and never spawned

**User story:** As the operator, I want a model my harness rejects — a typo, a model retired
by the vendor, one my account has no access to — to be caught before a human picks it, so
that a work item never dies in a pane nobody is watching.

#### Acceptance criteria (EARS)

1. The system SHALL provide a command (`the-loop models check`) that, for every declared
   model and effort level, runs the harness's own cheapest non-interactive invocation with
   those arguments and records the verdict as `ok`, `refused` or `unknown` (the harness could
   not be run at all).
2. The system SHALL cache each verdict in the machine-local state, keyed by harness, id and
   the arguments probed, with a bounded lifetime, and SHALL refresh a verdict whose
   declaration has changed.
3. WHEN the checklist is rendered THEN the system SHALL offer only choices whose cached
   verdict is `ok` or `unknown`, and SHALL NOT render one cached as `refused`.
4. WHEN a choice cached as `refused` is nonetheless resolved — a frozen record older than the
   verdict, a hand-edited record — THEN the system SHALL launch the session on
   `routing.harnessArgs.<harness>` unchanged, SHALL post one comment on the work item naming
   the refused choice and what it ran instead, and SHALL NOT retry that choice until its
   verdict changes.
5. WHEN a session whose arguments carried a non-default choice is found dead with no
   conversation to resume THEN the system SHALL re-probe that choice once before respawning,
   so a verdict that went stale becomes `refused` rather than an unbounded respawn loop.
6. IF a verdict is `unknown` THEN the system SHALL treat the choice as offerable and SHALL
   NOT block a spawn on it — an unprobeable harness (no binary on this machine, no network)
   SHALL NOT remove a capability the operator declared.
7. WHEN `the-loop diagnose` runs THEN it SHALL report each declared choice and its cached
   verdict, so an operator can see what their config actually buys them.

## Non-functional requirements

- **No new I/O on the dispatch path.** The frozen choice is read from the portable record the
  dispatcher already reads for `sessionPerPr` (`_tmux_for`), and availability is read from a
  cache — resolving a choice SHALL add no network call and no harness invocation per event.
  Probing happens in `models check`, at daemon start, and on the one stale-verdict path of
  R7.5; never inline in a delivery.
- **Observability.** The resolved model and effort appear in the spawn/respawn event-log
  records that already name the harness, so an operator can answer "what did this session
  actually run on" from `the-loop events` alone.
- **Documentation.** The two choices are described where the other per-work-item questions
  are: the configuration reference, the interactive-sessions capability doc, and the
  phase-selection section of the operating model.

## Security considerations

This work item creates one new path from **comment text to an argv of an unattended agent**.
That is the whole of its risk, and every criterion below exists to keep the path a lookup
into operator-owned configuration rather than a passthrough.

- **Actors & trust:**
  - *Untrusted:* anyone who can comment on, or edit a comment on, a work item; anyone who can
    add or remove a label; any webhook payload.
  - *Semi-trusted:* `routing.authorizedUsers` — named humans who may direct the-loop.
  - *Trusted:* the operator's `cli-config.yaml`, which is executable configuration on the
    machine that runs the daemon and is not editable by a pull request to a repository (the
    posture `critics[]` took in decision-123).
- **Trust boundaries & data:** the boundary is the gate's parse. A reply yields, at most, a
  **token matched against the declared set**; the argv is then built from the operator's own
  declaration. No sensitive data is stored or moved: a model id is not a secret, and nothing
  here reads or writes credentials.
- **The probe is an egress, and it is bounded.** R7 runs the harness non-interactively. It
  SHALL use a fixed, the-loop-authored prompt — never any text from a work item — and SHALL
  run only the declared arguments. It is the one new outbound action in this work item, it is
  not on the delivery path, and it carries no repository content.
- **Why not a label (the rejected mechanism):** GitHub's label permission is `triage` on the
  repository and is not the-loop's `authorizedUsers` boundary. Accepting a label here would
  let anyone with triage rights choose the argv of an unattended agent — and would do it
  *silently*, because GitHub does not attribute a label to a person in the payload the-loop
  already authorizes on. The label channel is therefore refused, not merely unsupported.
- **Abuse cases (EARS):**
  1. WHEN an unauthorized user ticks a row on the checklist and asks for execution THEN the
     system SHALL ignore the reply entirely, exactly as it does for phase ticks today.
  2. WHEN an authorized user's reply names `--dangerously-skip-permissions`, a shell
     metacharacter, a path, or any string that is not a declared id THEN the system SHALL
     treat it as no choice and run the operator's arguments unchanged.
  3. WHEN a declared entry's own `args` would widen permissions THEN the system SHALL apply
     them as declared and SHALL NOT be considered at fault — the operator wrote them, in the
     same file that already carries `harnessArgs` — and the-loop SHALL NOT add such an
     argument on its own initiative in any other circumstance.
  4. WHEN the portable record for a work item has been hand-edited to name an undeclared
     choice, or to carry an `args` list of its own THEN the system SHALL re-validate against
     the declared set on read and SHALL fall back to the operator's arguments (the portable
     tree is agent-writable; it is re-validated on the way in, as `_tmux_for` already
     re-validates `sessionPerPr`).
  5. WHEN a label named after a model is present on the work item THEN the system SHALL
     ignore it.
  6. WHEN the gate cannot read its own checklist comment (an outage, a deleted comment) THEN
     the system SHALL resolve to the operator's arguments unchanged.
  7. WHEN the availability cache file is hand-edited to mark an undeclared choice `ok` THEN
     the system SHALL still resolve only against the declared set, so a forged verdict can
     withhold a choice but SHALL NOT introduce one.
- **Fail closed:** every ambiguity — no tick, several ticks, an unknown token, an unreadable
  record, a `refused` verdict, a missing declaration — resolves to
  `routing.harnessArgs.<harness>` unchanged. The closed direction here is *the operator's own
  configuration*, never the narrowest or cheapest model: a malformed reply must not silently
  downgrade a tier-5 work item.

## Out of scope

- **Moving the spawn to after the gate.** The owner's review asks why a session exists before
  phase selection is answered. It should not, and `design.md` says how — but that changes the
  spawn contract for **every** work item, not only those choosing a model, so it is proposed
  as a **prerequisite work item** rather than folded in here. This work item is written to be
  correct under either ordering (R4.3).
- **A model choice for standing sessions.** They already have per-entry `harnessArgs`
  (issue-277) and are not work items.
- **Changing an already-running session's model in place.** No harness exposes that; R4.3
  re-launches instead.
- **Model choice for the inner (per-PR) loops** independently of their work item. A PR's
  session inherits its work item's choice.
- **A control keyword** (`the-loop model: …`). One surface for a per-work-item decision, and
  the gate is it.
- **Enumerating what a harness can run.** R7 *validates* what the operator declared; it does
  not discover a catalogue.

## Open questions

1. **Is the prerequisite ordering ticket wanted, and does this work item wait for it?**
   Recommended: raise it, land it first, and drop R4.3's re-launch to a safety net that
   nothing exercises. The alternative is to land this work item first and carry the re-launch
   as a bridge. The owner's call.
2. **What lifetime should an availability verdict have?** Proposed: 24 hours, plus
   invalidation whenever the declaration's arguments change, plus the one re-probe of R7.5.

## Review comments

### 2026-09-13 — @MadaraUchiha-314, review of PR #359

| Feedback | Disposition |
|---|---|
| "handle the error condition when the user chooses a model that's not available in the harness" | **R7**, new: probe, cache, do not offer a `refused` choice, fall back visibly, re-probe once on a dead session, report in `diagnose`. |
| "Should we let the user specify the models per harness or overall for all harnesses?" | **Per harness** — R2.2, with the reason: a harness-independent list would make the-loop attribute an id to a harness, which is a guess. |
| "this couples model and effort … keep model and effort as 2 separate inputs" | **Accepted** — two declarations (`routing.models`, `routing.effort`), two checklist sections, two frozen keys, resolved independently (R1.2, R1.5, R2.1, R3.1). No cross product. |
| "just models" (on the `harnessModels` vs `models` question) | **Accepted** — `routing.models`, and `routing.effort` beside it. |
| "Why do we start a session before the phase selection is complete? … We ideally shouldn't" | **Agreed.** Answered in `design.md` § *Why a session exists before the gate, and why it should not*; proposed as a prerequisite work item, with R4.3 keeping this work item correct under either ordering. |
