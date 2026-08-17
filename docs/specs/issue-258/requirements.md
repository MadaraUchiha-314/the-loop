---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#258"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: the operator chooses how many sessions a work item's pull requests get

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

**A pull request in the work item's own repository cannot be given a session of its own, in
any configuration.** Ticket:
[#258](https://github.com/MadaraUchiha-314/the-loop/issues/258) — *"users should have an
option to choose whether all the PR related sessions are individual tmux+claude sessions or
one single tmux+claude session"*.

`routing.tmux.sessionPerPr` was that option once. Yesterday
[issue-253](https://github.com/MadaraUchiha-314/the-loop/issues/253) /
[decision-088](../../decisions/decision-088.md) narrowed it to fix a real defect: the
endpoint session for a same-repository pull request was spawned into the **work item
session's own working tree**, so two harness conversations shared one branch with no lock.
D1 stated the collapse as a **rule, not a setting** — "a knob for it would be a documented
way to reproduce the bug" — and D4 kept the boolean's name and default with a narrower
meaning.

What the fix removed along with the defect is the *choice*. The setting reads:

| `sessionPerPr` | same-repository pull request | pull request in another repository |
|---|---|---|
| `true` (default) | work item's session — **forced** | its own session |
| `false` | work item's session | work item's session |

Both rows collapse the case the ticket is about. This work item gives the choice back — and
keeps the half of decision-088 that was not about choice at all: **an endpoint gets a
conversation only when it gets a working tree of its own** (D2). That refusal is what
separates "the operator asked for two owners and got two trees" from "the-loop reproduced
issue-253 on request".

The reading above was posted on the ticket before any code was written
([comment](https://github.com/MadaraUchiha-314/the-loop/issues/258#issuecomment-5310675593)),
because the ticket carries a title and no body.

## Requirements

### Requirement 1 — three named choices, not two

**User story:** As an operator, I want to state whether *every* pull request delivering a
work item gets its own tmux+claude session, only a pull request in another repository does,
or none of them do, so that the number of agents working my repository is my decision rather
than the-loop's.

#### Acceptance criteria (EARS)

1. WHEN `routing.tmux.sessionPerPr` is `never` THEN the system SHALL deliver every pull
   request's events into the work item's own session.
2. WHEN `routing.tmux.sessionPerPr` is `cross-repository` THEN the system SHALL give a pull
   request in a repository other than the work item's its own session, and SHALL deliver a
   pull request in the work item's own repository into the work item's session.
3. WHEN `routing.tmux.sessionPerPr` is `always` THEN the system SHALL give every pull
   request delivering the work item its own session, the work item's own repository
   included, subject to Requirement 2.
4. WHEN `routing.tmux.sessionPerPr` is absent THEN the system SHALL behave as
   `cross-repository`.
5. IF `routing.tmux.sessionPerPr` is a value the system does not recognise THEN the system
   SHALL behave as `cross-repository` and SHALL log the value it rejected.

### Requirement 2 — a session is still only given with a tree of its own

**User story:** As an operator who turned `always` on, I want the-loop to refuse the second
session rather than put two agents in one working tree, so that the option cannot reproduce
[#253](https://github.com/MadaraUchiha-314/the-loop/issues/253).

#### Acceptance criteria (EARS)

1. WHEN a pull request endpoint would spawn AND no checkout can be prepared for that pull
   request alone THEN the system SHALL NOT spawn it, SHALL deliver the event into the work
   item's session, and SHALL emit `session.pr_session_declined`.
2. WHEN a same-repository pull request endpoint's checkout is prepared AND it does not have
   that pull request's head branch checked out THEN the system SHALL treat the checkout as
   unavailable under 2.1, and SHALL NOT spawn a session onto a tree holding a different
   branch.
3. WHILE `routing.workspace.root` is unset the system SHALL decline every endpoint spawn,
   whatever `sessionPerPr` says.

### Requirement 3 — an existing configuration keeps its meaning

**User story:** As an operator upgrading the-loop, I want my current config file to keep
doing exactly what it does today, so that a new option is not a silent behaviour change.

#### Acceptance criteria (EARS)

1. WHEN `routing.tmux.sessionPerPr` is the boolean `true` THEN the system SHALL behave as
   `cross-repository`.
2. WHEN `routing.tmux.sessionPerPr` is the boolean `false` THEN the system SHALL behave as
   `never`.
3. WHEN a configuration file is validated against `cli-config.schema.json` THEN the schema
   SHALL accept the two booleans and the three names, and SHALL reject any other value.

## Non-functional requirements

- **Observability.** The choice is answerable from `the-loop events` without reading a
  config file: a spawn that did not happen already emits `session.pr_session_declined` with
  a `reason`, and this work item adds no new silent path.
- **No state migration.** The session record's `pullRequests[]` shape is unchanged, so a
  registry written by an older the-loop is read by this one and the reverse.
- **Cost.** `always` is opt-in. It multiplies harness conversations per work item, and every
  conversation is tokens; the default stays where it is for that reason as well as safety.

## Security considerations

> Threat-model-lite, captured with the requirements (`security.threatModel.required`).

- **Actors & trust:** unchanged from issue-172/issue-253. The untrusted input is the webhook
  or poll payload — attacker-influenceable fields being the pull request's repository
  (`owner/repo`) and head ref. The trusted input is the operator's own config file. Nothing
  in this work item reads a new field from a payload.
- **Trust boundaries & data:** the payload's repository decides *routing*, not
  *authorization* — `authorizedUsers` and the control keywords are untouched, and an event
  that is not authorized never reaches the endpoint decision. The head ref reaches `git
  fetch origin <ref>` exactly as it already does for a cross-repository endpoint; the
  argument vector is a list, never a shell string, so a crafted ref is an argument and not a
  command. No secret is read, stored or moved.
- **Abuse cases (EARS):**
  1. WHEN a payload names a head ref shaped like a git option (`--upload-pack=…`) THEN the
     system SHALL pass it as a positional argument to `git` and SHALL NOT execute it as a
     command, failing the checkout and declining the session rather than spawning.
  2. WHEN a payload names a repository the work item does not belong to THEN the system
     SHALL still require an authorized actor and the work item's own session record before
     any endpoint is considered, and SHALL NOT create a checkout for an unlinked repository.
  3. WHEN `always` is set and a hostile actor opens many pull requests against the work
     item's repository THEN each spawn SHALL remain subject to
     `maxConcurrentDispatches` and to the arming rules (`authorizedUsers`, the auto-execute
     label, the control keywords), so the option widens *concurrency*, never *authorization*.
- **Fail closed:** an unrecognised `sessionPerPr` value resolves to `cross-repository` — the
  shipped default, the narrower of the two splitting choices — never to `always`. A checkout
  that cannot be prepared, or that does not hold the pull request's branch, declines the
  session; it never falls back to sharing a tree.

## Out of scope

- **Two different work items sharing `spawnWorkdir`.** Recorded as out of scope by
  issue-253 and still open; this work item narrows nothing and widens nothing there.
- **Making `strategy: worktree` able to serve `always` for a same-repository pull request.**
  Two worktrees of one clone cannot hold one branch; that is git. `always` is served by
  `strategy: clone`, and declines under `worktree` when the work item's session already
  holds the branch.
- **Tearing down endpoint sessions an older the-loop spawned.** Unchanged from
  decision-088 D3: routing stops feeding them, `the-loop cleanup` ends them.
- **A per-work-item override of the choice.** The ticket asks for an operator option; a
  spec-front-matter override is a different question and nobody has asked it.

## Open questions

None outstanding. The one question this ticket raised — *which* of decision-088's
sub-decisions the ticket overrules — is answered on the ticket
([comment](https://github.com/MadaraUchiha-314/the-loop/issues/258#issuecomment-5310675593)):
D1 and D4 are overruled by their author, D2, D3 and D5 stand.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
