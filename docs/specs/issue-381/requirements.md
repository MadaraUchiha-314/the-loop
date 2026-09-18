---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#381"
status: in-review            # draft | in-review | approved
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: a work item is armed by a set of labels, all of which must be present

> Phase 1 of 4 (requirements → design → testing plan → tasks). Following the Kiro spec
> approach (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by
> the required collaborators before moving to design.

## Introduction

[Issue-381](https://github.com/MadaraUchiha-314/the-loop/issues/381): *"Currently if
multiple people are using the-loop and have `autoExecuteLabel: 'the-loop: auto-execute'`
in their config, everyone's issues are being tracked by everyone's instances of the-loop.
We want to make this a list so that each user can add the common label as well as a
specific label for themselves, and the-loop only looks at the issue if all the labels in
the list are present."*

`routing.autoExecuteLabel` is one string, read in four places — the receiver's router,
the dispatcher's arming check, the poller's `gh … --label` listing, and the poller's
presence event — and every operator ships the same default. Two operators on one
repository therefore arm every labelled item on both machines, and the only remedy is for
one of them to rename the label everywhere, which breaks the shared convention that
`/the-loop:work-on` and the Slack kickoff rely on.

| Today | Consequence |
|---|---|
| One label arms an item | An item labelled for one operator is armed for every instance that watches the repository |
| The default is shared by every install | Renaming it to escape another instance breaks the convention the commands and the Slack kickoff apply |
| `polling.sources[].label` is one string too | The poll ingress cannot express a narrower set than the receiver's either |

**The unit of the change is one key becoming a list, with every-label-present semantics,
on both ingresses, with the old key migrated rather than silently honoured.** The instance
scope of issue-322 answers *which instance takes a work item that already names one*; this
answers *which items an instance looks at in the first place*.

## Requirements

### R1 — the arming gate is a set of labels, and every one must be present

**User story:** As an operator sharing a repository with other the-loop instances, I want
to declare the common label plus one of my own, so that only the items carrying both are
armed on my machine.

#### Acceptance criteria (EARS)

1. `routing.autoExecuteLabels` SHALL be a list of label names, default
   `["the-loop: auto-execute"]`; an operator who never set the key SHALL see exactly the
   behaviour of the single-label default.
2. WHEN an issue or pull-request event's item carries **every** label in the list THEN
   the router SHALL flag the event as labelled and the dispatcher SHALL treat the item as
   armed under `spawnOnUnmatched: labeled`.
3. WHEN the item carries only some of the labels THEN the event SHALL NOT be flagged and
   the item SHALL NOT be armed, whatever the missing label is.
4. WHEN a `labeled` action adds the last missing label THEN the item SHALL count as armed
   on that event: the label being added is read together with the item's label set, as
   the single label was.
5. IF the list is empty THEN nothing SHALL be armed (fail closed); the schema SHALL
   require at least one entry so an empty list is a validation error rather than a silent
   `never`.
6. The dispatcher's spawn-policy refusal and the poller's start-up line SHALL name the
   whole list, so an operator reading a refusal sees which labels the item was measured
   against.

### R2 — the poll ingress lists by the same set

**User story:** As an operator on a host a webhook cannot reach, I want the poller to
discover exactly the items the receiver would arm, so that the two ingresses never
disagree about which items are mine.

#### Acceptance criteria (EARS)

1. WHEN a `github` source lists a repository THEN it SHALL pass every configured label to
   `gh` (one `--label` per label) AND SHALL drop from the listing any returned item that
   does not carry every label — so the gate holds whatever `gh` returns.
2. `polling.sources[].labels` SHALL be a list; an empty or absent list reuses
   `routing.autoExecuteLabels`, a non-empty one replaces it for that source.
3. The presence event a listed item produces SHALL carry `labeled` computed against the
   full set, so the dispatcher's arming check and the poller's listing agree.

### R3 — the old keys are migrated, never honoured silently

**User story:** As an operator upgrading, I want a config that still says
`autoExecuteLabel` to be refused with the fix named, so that my custom label is never
quietly replaced by the default.

#### Acceptance criteria (EARS)

1. WHEN a CLI config declares `routing.autoExecuteLabel` or `polling.sources[].label`
   THEN the runtime SHALL refuse to start, naming the key, its replacement and
   `/the-loop:upgrade-the-loop`.
2. `the-loop migrate-config` SHALL move `autoExecuteLabel: x` to `autoExecuteLabels: [x]`
   and `label: x` to `labels: [x]`, remove an empty `label: ""` (it meant "reuse", which
   an absent `labels` still means), bump `version` to `0.10.0`, and report each move.
3. The migration SHALL be idempotent, and `needs_migration` SHALL detect the old keys by
   name as well as by version.
4. WHEN both the old and the new key are present THEN the migration SHALL keep the new
   one, drop the old one, and say so in a note.

### R4 — the change ships with its documentation

#### Acceptance criteria (EARS)

1. The config reference (`routing-options.md`, `polling-options.md`, and every page that
   links `#autoexecutelabel`), both schema copies, the shipped template and this
   repository's own `cli-config.yaml` SHALL name the new keys; the docs-parity and
   schema-parity suites SHALL pass.
2. `commands/work-on.md` and `commands/execute-tasks.md` SHALL tell the agent to apply
   **every** label in the list to the issue or pull request it arms.
3. `docs/capabilities/webhook-triggers.md` SHALL state the every-label-present rule and
   carry a history row; a decision record SHALL record the all-of choice and the
   breaking migration.

## Non-functional requirements

- **No new API calls.** Label presence stays a read of the webhook payload or the poll
  listing, as it is today.
- **No wider queries.** The poller still asks `gh` for labelled open items only; adding
  labels narrows the listing.
- **Observability unchanged.** `routing.routed` keeps its `labeled` flag; no new event type.

## Security considerations

- **Actors & trust:** anyone with triage rights on the repository can apply labels; the
  label set is therefore a *narrowing* of what an instance looks at, never an
  authorization. `routing.authorizedUsers` and `control.requireStartCommand` are untouched
  and still decide who may start an armed item.
- **Trust boundaries & data:** the list is operator configuration, read from the CLI
  config only; label names are compared by exact string equality and never interpolated
  into a shell — `gh` receives them as separate argv entries, as the single label was.
- **The upgrade is the boundary that matters.** An operator who had set a custom
  `autoExecuteLabel` and whose config were silently read under the new key would fall
  back to the shared default, which is *wider* than what they set — the exact drift the
  migration doctrine exists to prevent. Hence R3.1 refuses rather than reads.
- **Abuse cases (EARS):**
  1. WHEN an item carries a subset of the configured labels THEN the system SHALL NOT arm
     it, on either ingress.
  2. WHEN a `labeled` action adds a label that is *not* the missing one THEN the system
     SHALL NOT arm the item on that event.
  3. WHEN the list resolves to empty at runtime THEN the system SHALL arm nothing.
  4. WHEN a config still carries the old key THEN the system SHALL refuse to start rather
     than read the default.
- **Fail closed:** an empty list arms nothing; an un-migrated config runs nothing.

## Out of scope

- Any-of (OR) semantics, or a per-label policy. The ticket asks for all-of.
- Deriving a per-instance label from `instance.name` automatically; the operator declares
  the labels they want.
- A migration of the labels already applied on GitHub; the operator's own items already
  carry the common label and gain the specific one by hand.
- Jira or any provider other than `github` for the poll source.

## Open questions

None raised on the ticket; the owner's request names the semantics (all labels present).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
