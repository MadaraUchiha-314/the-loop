---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#352"
status: draft
approvedBy: []
collaborators: [maintainer]
overrides: {}
---

# Requirements: audit how `harness-config.yaml` is used and whether it is required

> An **audit** work item: the deliverable is a report, not code. Following the shape
> issue-212 used for its vendor-SDK analysis — the questions become requirements, the
> answers become `docs/reports/harness-config-audit.md`, and every change the audit
> recommends is raised as its own ticket rather than made here.

## Introduction

[Issue-352](https://github.com/MadaraUchiha-314/the-loop/issues/352) asks five
questions about `.the-loop/harness-config.yaml`:

> - `reviews.critics` should be moved to `cli-config.yaml` as it's really the operator
>   who controls it
> - `workflow.phases` is redundant since the whole workflow is controlled through graphs
> - why is a `harness-config` even necessary? which system reads it? how is it enforced?
> - can we completely remove it?
> - if yes, what are the candidates to move to cli-config to be controlled more by
>   the-loop's operator rather than the repository owner

[decision-044](../../decisions/decision-044.md) answered the *narrow* form of this
question (issue-121: why does the CLI read it) with a declared, test-pinned read
surface. This audit answers the *wide* form: every reader, every key, and whether the
file has a reason to exist at all.

## Requirement 1 — Every reader of the file is named, with evidence

**User story:** As the owner, I want to know exactly which systems read
`harness-config.yaml`, so that "which system reads it?" has one answer with a file and
line behind each claim.

### Acceptance criteria (EARS)

1. THE report SHALL list every reader by surface — the agent (skill, commands), the CLI
   (`the_loop.harness_config.READS`), the hooks and rules, this repository's own tests
   and CI, and the writers — with the mechanism each uses. (AC1)
2. THE report SHALL classify every top-level schema key by who reads it and how it is
   enforced (code gate, prompt-following, or nothing), in one table. (AC2)
3. WHEN a key is claimed unread THEN the claim SHALL rest on a search of the skill, the
   commands and the CLI source, not on memory. (AC3)

## Requirement 2 — The two named examples are settled on evidence

**User story:** As the owner, I want `reviews.critics` and `workflow.phases` each
examined against what actually reads them, so that the ticket's two propositions are
confirmed or refuted rather than restated.

### Acceptance criteria (EARS)

1. THE report SHALL state what `workflow.phases` is read by, what pins it to the graph,
   and what would replace its one remaining job (label creation at `/init`). (AC4)
2. THE report SHALL weigh `reviews.critics[]` against each of decision-044's four
   arguments for keeping it in the harness config, and state which survive. (AC5)

## Requirement 3 — "Can it be removed?" gets a yes or a no, with the consequences

**User story:** As the owner, I want a direct answer to whether the file can go, so that
the decision is mine to make on stated consequences.

### Acceptance criteria (EARS)

1. THE report SHALL answer removal directly and enumerate what breaks — per key, per
   command, per session kind (daemon-spawned, cloud, CI checkout). (AC6)
2. THE report SHALL list the keys that belong to the operator with a proposed home in
   `cli-config.yaml`, and the keys read by nothing as deletion candidates. (AC7)
3. THE report SHALL raise each recommended change as a follow-up with a tier, and SHALL
   itself change no config, schema, code or rule. (AC8)

## Out of scope

- Making any of the recommended changes. Each is a ticket of its own; the biggest
  (moving `reviews.critics[]`) refines decision-044 and needs its own decision record.
- The CLI config's own surface. Only what might *move into* it is considered.

## Security considerations

The report handles no secrets and changes no executable configuration. It does discuss
the security posture of `reviews.critics[]` (executable config in a committed file) as
an input to the recommendation; that analysis is descriptive.

## Risk tier

**Tier 2** (`autonomous-complete`): documentation only — one report, its two index
entries, one pointer from the config reference, and this spec. No schema, config, code
or workflow touched, so `autonomy.sensitivePaths` is not hit. The full spec chain is not
required at this tier (`CLAUDE.md`, `config.autonomy`); the phases walked and skipped are
recorded in [`execution-log.md`](execution-log.md).
