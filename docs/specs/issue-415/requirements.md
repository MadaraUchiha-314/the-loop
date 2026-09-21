---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#415"
status: in-review            # draft | in-review | approved — tier 4: PR approval plus a named security sign-off
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 4                  # touches `.the-loop/**` (a sensitive path) and tells people where to keep Slack and GitHub credentials
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: the `/the-loop:init` onboarding a person can finish

> Phase 1 of 4 (requirements → design → testing plan → tasks). Source:
> [issue-415](https://github.com/MadaraUchiha-314/the-loop/issues/415).

## Introduction

`/the-loop:init` onboards a fraction of the-loop, and it is the wrong fraction. It walks
the four groups of `harness-config.yaml` — custom instructions, testing conventions,
people, API contracts — with a schema-driven, grouped, explained walkthrough that works
well. Then it asks **one** question about the CLI config, the file that holds every
automation the-loop has, and the question is about *where the file should live*:

> "Do you want the CLI daemon's config tracked and versioned in this repo, or should it
> default to your home directory?"

Everything the user actually came for is on the other side of that question. Whether the
daemon watches their repository at all (`routing.enabled`, default `false`), how events
reach it on the machine they are sitting at (`webhooks.ghWebhook` vs `polling`, both
default `false`), whether an armed work item waits for them to say go
(`control.requireStartCommand`), whether an approved pull request merges itself
(`mergeOnApproval`), who is allowed to drive it (`routing.authorizedUsers`, default `[]`),
and the entire Slack channel — none of it is asked, proposed, explained or checked. A
`cli-config.yaml` is scaffolded from a template and the session ends.

The consequence is not a bad config; it is a silent one. **Every automation knob ships
`false`**, so the honest description of a finished `/the-loop:init` today is: the slash
commands work, and nothing else is on. A user who wanted the-loop to watch their
repository has no signal that it is not watching, and the path from here to a working
deployment is the documentation site — the [Slack page](/guide/slack) alone is 868 lines.
That is a fine reference and a terrible first hour.

Three specific failures follow from it, and this work item is scoped to those three.

**The schema cannot drive the walkthrough it should drive.** `harness-config.schema.json`
carries an `x-onboarding` block — ordered groups, ask levels, per-key explanations — and
`reference/onboarding.md` is the procedure that reads it. `cli-config.schema.json` carries
no such block, so the machinery that already exists has nothing to point at, and init
falls back to prose in a command file, which is exactly the drift the `x-onboarding`
design was built to prevent.

**There is no way for a user to say how much autonomy they want.** The issue states it
plainly: not every user has the same threshold for automation. Today the only way to
express that threshold is to reason independently about six keys in four config blocks
and understand how they interact — `routing.enabled` with `spawnOnUnmatched` with
`control.requireStartCommand` with `mergeOnApproval` with the ingress with
`harnessTrust`. Asking those six questions one at a time is not onboarding, it is an
exam. Asking none of them, which is what happens now, leaves everything off.

**Credentials are named but never checked.** Every secret the-loop uses is *named* in the
config and *read* from the process environment — `channels.slack.botTokenEnv`,
`appTokenEnv`, `webhooks.ghWebhook.secretEnv`, `integrations.github.api.tokenEnv`. That
design is right and this work item does not touch it. But init writes a config naming
four environment variables and never asks whether a single one of them is set, so the
first evidence that `THE_LOOP_SLACK_APP_TOKEN` is missing arrives when the listener
refuses to connect — after the user has left the session that could have told them.

### Scope

In scope: what `/the-loop:init` asks, explains, proposes and verifies, and the schema
metadata that drives it.

Out of scope, and deliberately: the risk tiers, the phase gates and the approval nodes.
They are fixed rules of the skill and the process graph, not settings (issue-352,
decision-123), and **no answer to any question in this walkthrough may weaken one.** A
user choosing maximum autonomy is choosing who starts the work and how events reach the
daemon; they are not choosing to skip a human approval. Requirement 3 makes that a
testable property rather than an intention.

## Requirements

### Requirement 1 — the CLI config is onboarded from its own schema

**User story:** As someone running `/the-loop:init`, I want the automation config
established with me the way the harness config already is, so that I leave the session
knowing what the-loop will and will not do on my repository.

#### Acceptance criteria

1. WHEN `/the-loop:init` runs interactively THEN it SHALL walk the CLI config's groups
   from `x-onboarding.groups` in `cli-config.schema.json`, in the order the schema
   declares, with the same grouped, one-interaction-per-group procedure
   `reference/onboarding.md` already defines for the harness config.
2. `cli-config.schema.json` SHALL carry an `x-onboarding` block declaring those ordered
   groups, each group's `title`, its one-paragraph `explain`, its `ask` level and its
   `keys`, using the same `askLevels` vocabulary (`always` | `confirm` | `advanced`) as
   `harness-config.schema.json`.
3. Every key named in a group's `keys` SHALL exist in the schema's `properties`, and
   every top-level property of the schema SHALL be reachable from exactly one group —
   a key in no group is a key nobody is ever asked about, and a key in two is a
   question asked twice.
4. WHEN init presents a group THEN it SHALL read that group's explanation, each key's
   `description`, `default`, `enum` values and `examples` **from the schema**, and
   SHALL NOT restate them from the command file or from memory.
5. WHEN a group's `ask` level is `advanced` THEN init SHALL apply its defaults silently
   and SHALL offer the tour rather than walking it.
6. WHEN the user has answered no CLI-config question yet and asks to accept defaults for
   the rest THEN init SHALL apply the remaining proposals and report them, without
   asking again.
7. WHEN init runs with `--defaults` or `--dry-run` THEN it SHALL ask nothing, and SHALL
   route every un-defaultable CLI-config gap to the **needs-user** section of the final
   report, naming the exact key.
8. WHEN `/the-loop:init` is re-run on a repository whose CLI config is already
   established THEN it SHALL raise only gaps — empty required keys, `# TODO: verify`
   lines, keys a schema upgrade added — and SHALL NOT re-ask a settled question.

### Requirement 2 — one question sets the automation threshold

**User story:** As a user who has never seen this tool, I want to say how much of my
work I am willing to let it do unattended, in one answer I understand, so that I am not
asked to reason about six interacting keys before I have watched it work once.

#### Acceptance criteria

1. `cli-config.schema.json` SHALL declare, under `x-onboarding`, a set of named
   **autonomy profiles**, ordered from least to most autonomous, each carrying a
   `title`, a `summary` of what the user is agreeing to, and the exact config values it
   proposes.
2. WHEN init onboards the CLI config THEN it SHALL present the profiles as one question,
   with every profile shown and one marked as the recommendation.
3. WHEN the user picks a profile THEN init SHALL apply that profile's values as the
   *proposal* for the keys it covers, and SHALL show the resolved values before
   writing them — a profile is a starting point the user can still adjust, never a
   value applied behind their back.
4. Each profile's values SHALL be expressed as concrete config paths and values that
   exist in the schema, so that a key renamed in the schema and not in the profile is a
   detectable error rather than a silently dead entry.
5. The least autonomous profile SHALL be the shipped defaults — the-loop as slash
   commands, no daemon, nothing watching — so that "I don't want any of this yet" is a
   supported answer and not a user fighting the walkthrough.
6. WHEN a profile's summary describes what it turns on THEN it SHALL also state what
   still requires a human at that setting, so that the user's mental model of the rung
   they picked is correct when they leave the session.
7. The profile question SHALL be asked **before** the individual automation groups, and
   answering it SHALL reduce those groups to confirmations rather than open questions.

### Requirement 3 — autonomy never buys away a human gate

**User story:** As the owner of a repository, I want to know that the most autonomous
setting still stops where it should, so that I can offer this walkthrough to someone who
will pick the boldest option without reading it.

#### Acceptance criteria

1. No autonomy profile SHALL set any value that removes, skips or pre-answers a process
   graph human node, an artifact approval gate, the `phase-selection` checklist or a
   risk-tier threshold.
2. Every value any profile declares SHALL be a key under `webhooks`, `polling`,
   `routing`, `service`, `selfDiagnosis` or `channels` — the ingress-and-execution
   surface — and SHALL NOT be a key the process graph or the risk tiers read.
3. WHEN init presents the most autonomous profile THEN it SHALL state, in that profile's
   own summary, which approvals still hold.
4. WHEN init has finished THEN its report SHALL name the profile that was applied, so
   that the choice is recoverable from the transcript and from the config.

### Requirement 4 — init knows what kind of machine it is on

**User story:** As someone setting the-loop up on my laptop, I want it to propose the
ingress that works on a laptop, so that I do not configure a webhook receiver on a host
GitHub can never reach.

#### Acceptance criteria

1. WHEN init onboards the ingress group THEN it SHALL first establish where this
   deployment runs — a personal machine, or an always-on host with an inbound route —
   asking the user where detection cannot answer it.
2. WHERE the answer is a personal machine THEN init SHALL propose `polling` as the
   ingress and SHALL explain that a webhook receiver needs an inbound route the machine
   does not have.
3. WHERE the answer is an always-on reachable host THEN init SHALL propose
   `webhooks.ghWebhook`, and SHALL name the webhook secret environment variable
   (`webhooks.ghWebhook.secretEnv`) as a credential the user must set.
4. WHEN either ingress is proposed THEN init SHALL also propose a
   `routing.workspace.root`, because a daemon that spawns sessions needs a checkout
   location and the shipped default is empty.
5. WHEN the user declines both ingresses THEN init SHALL leave routing off, say so in
   the report, and SHALL NOT scaffold a half-configured daemon.

### Requirement 5 — Slack is explained, configured and proved in the session

**User story:** As a user who wants to answer the-loop from my phone, I want init to set
Slack up with me and tell me whether it actually works, so that I am not reading an
868-line reference page to find out which scope I am missing.

#### Acceptance criteria

1. WHEN init reaches the channels group THEN it SHALL first explain, in a form short
   enough to read in a session, what the Slack integration is: one thread per work item,
   what `subscribe` means, what `publish` means, and that GitHub remains the ledger.
2. WHEN the user wants Slack THEN init SHALL walk the app setup in order — import the
   manifest (`the-loop channels manifest`), mint the bot token, mint the app-level
   token, invite the bot, take the conversation id — and SHALL point at
   [the Slack guide](/guide/slack) for the detail it does not restate.
3. WHEN init proposes `channels.slack.subscribe` and `publish` THEN it SHALL explain
   that `subscribe` is what the channel hears and `publish` is what a message there may
   become, and SHALL NOT propose a `publish` grant the user did not ask for.
4. WHEN the user declines Slack THEN init SHALL leave `channels.slack.enabled: false`
   and SHALL NOT ask any further Slack question.
5. WHEN Slack has been configured THEN init SHALL run `the-loop channels status` — and
   `--probe` where a token is present — and report what it found, so that a missing
   scope or an unreachable channel is named in the session rather than discovered later.
6. WHERE the CLI is not installed on this machine THEN init SHALL say so, print the
   command the user should run themselves, and SHALL NOT report the channel as verified.

### Requirement 6 — every credential the config names is checked before init ends

**User story:** As a user finishing init, I want to be told which environment variables
are still missing, so that the deployment I just configured actually starts.

#### Acceptance criteria

1. WHEN init has written a config THEN it SHALL collect every environment variable name
   that config declares — at minimum `channels.slack.botTokenEnv`,
   `channels.slack.appTokenEnv`, `webhooks.ghWebhook.secretEnv` and
   `integrations.github.api.tokenEnv` — and report, per name, whether it is set.
2. Init SHALL report **presence only**, and SHALL NOT print, log, echo or store the
   value of any credential, nor write one into any config file.
3. WHEN a required credential is unset THEN init SHALL name the variable, say which
   feature it gates, say where to obtain it, and list it under **needs-user**.
4. WHEN a credential is unset and the config declares an `env.file` THEN init SHALL
   point the user at that file as the place to put it.
5. WHEN init proposes an `env.file` THEN it SHALL state that the file holds secrets, and
   SHALL verify it is git-ignored — offering to add it to `.gitignore` when it is not.
6. IF init cannot determine whether a variable is set — a value that would only exist in
   the daemon's environment and not the session's — THEN it SHALL report it as
   *unverified* and distinguish that from *unset*.

### Requirement 7 — the walkthrough is explained, not narrated

**User story:** As a reader with a finite attention span, I want each question to carry
exactly the context I need to answer it, so that I read the walkthrough instead of
skipping it.

#### Acceptance criteria

1. Each group's presentation SHALL lead with what the group decides and why it matters,
   in at most a short paragraph, before any value is shown.
2. WHEN a key is an `enum` THEN init SHALL show every legal value with a one-line
   meaning, and SHALL mark the proposed one.
3. WHEN a key is free-form THEN init SHALL show the schema's `examples`, so the expected
   shape is never guessed.
4. Init SHALL state where each proposed value came from — *detected*, *default*, *from
   the profile you picked*, or *already configured*.
5. Init SHALL NOT reproduce reference documentation in the session: where a topic has a
   page on the documentation site, the explanation SHALL be the short form and the page
   SHALL be linked.
6. Init SHALL offer an exit from the walkthrough at every group — accept the remaining
   proposals and finish — and SHALL honour it immediately.

## Non-functional requirements

- **Idempotence is unchanged.** Every property init has today — non-clobbering,
  re-runnable, `--dry-run` writes nothing — holds for everything added here. A second
  `/the-loop:init` asks the profile question only if no profile was ever applied.
- **The schema stays the single source of truth.** No group explanation, enum meaning,
  default or example is authored in `commands/init.md` or in this session's prose. The
  command file says *how to ask*; the schema says *what to ask*.
- **No new runtime dependency and no new command.** The verification steps use the CLI
  surface that already exists (`the-loop channels status --probe`, `the-loop doctor
  slack`) and degrade to an instruction when the CLI is absent.
- **The packaged schema copy stays byte-identical** to the authored one
  (`cli/the_loop/schemas/cli-config.schema.json`), as `test_config_schema_parity.py`
  requires.

## Security considerations

> Threat-model-lite, captured with the requirements.

- **Actors & trust.** The user running init is trusted — it is their machine and their
  repository. The repository being initialized is **not**: a `CONTRIBUTING.md` proposed
  as a custom-instruction doc, a `.gitignore`, and any file init reads to detect a signal
  are attacker-controllable in a repository the user has cloned but not audited. Nothing
  read during detection is executed or followed as an instruction; it is only proposed as
  a path for the user to confirm, which is the behaviour init already has.
- **Trust boundaries & data.** This work item moves the walkthrough *closer* to
  credentials than it has ever been, which is the whole security argument. Four
  environment variables are read for presence. The boundary rule is absolute and stated
  as a requirement (R6.2): **the value never crosses into anything init writes, prints or
  logs**. The config keeps naming variables, never holding values — the design that
  `envfile.py` documents and that this work item must not erode. Init also gains an
  opinion about `.gitignore` (R6.5), which is a hardening step: the most likely way a
  the-loop user leaks a Slack bot token is committing the `.env` the config told them to
  create.
- **Abuse cases (EARS):**
  1. WHEN a repository's `.gitignore` does not cover the `env.file` init proposes THEN
     init SHALL report it and offer to add it, and SHALL NOT write any credential into a
     file that would be committed.
  2. WHEN init reports on a credential environment variable THEN it SHALL emit only the
     variable's name and whether it is set, and SHALL NOT emit the value, a prefix of
     the value, its length, or a hash of it.
  3. WHEN a detected candidate file (a `CONTRIBUTING.md`, a convention doc) contains
     text shaped like an instruction to the agent THEN init SHALL treat it as a path to
     propose and SHALL NOT act on its contents during the walkthrough.
  4. WHEN an autonomy profile is applied THEN it SHALL NOT add any entry to
     `routing.authorizedUsers` — who may drive the loop is established with the user by
     name, never implied by a threshold they picked.
  5. WHEN init verifies a Slack channel THEN it SHALL report the channel id and name and
     the scopes the app holds, and SHALL NOT report any token, consistent with
     `channels status`'s existing contract.
- **Fail closed.** An unanswered autonomy question leaves the shipped defaults, which are
  every automation off. An unset credential blocks the feature it gates and is reported;
  it never causes init to fall back to a less safe configuration. `authorizedUsers`
  empty means nobody can drive the loop, and init reports that as a gap rather than
  filling it.

## Out of scope

- Any change to the process graph, the phase gates, the risk tiers or the approval nodes.
- Any new CLI command. The verification steps use `channels status` and `doctor slack`
  as they exist.
- Cursor's plugin install path (issue-157) and the Slack app manifest itself.
- Automating the Slack app creation. Importing a manifest at `api.slack.com` is a
  browser step; init walks the user through it and verifies the result.
- Rewriting `docs/guide/slack.md`. It stays the reference; init links to it.

## Open questions

None outstanding. The one judgement call — how many autonomy rungs to offer — is settled
in `design.md` §The profile ladder, with the reasoning recorded there.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
