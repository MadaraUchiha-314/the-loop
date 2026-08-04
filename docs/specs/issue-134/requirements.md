---
type: requirements
phase: requirements-definition
workItem: "issue-134"
status: approved
approvedBy: []               # tier-4: the human gate is the PR review + security sign-off — see execution-log
collaborators: [product-manager, engineer]
overrides: {}
riskTier: 4                  # additive, but `.the-loop/cli-config.schema.json` matches autonomy.sensitivePaths (`**/*schema*`)
---

# Requirements: say where a spawned session takes its answers from — CLI or the work item

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #134](https://github.com/MadaraUchiha-314/the-loop/issues/134): a session the CLI
daemon spawns or resumes is never told **where a human is**. The dispatcher renders a
prompt that says what happened and what the-loop's rules are, and then leaves the single
most consequential question unanswered — when the agent needs a decision, does it ask in
the terminal it is running in, or on the GitHub issue/PR?

Today the answer is whatever the model guesses, and both guesses fail:

- **Guessing "the terminal"** in a `process`-runner session is a dead end. That session is
  a headless one-shot subprocess with no human attached; an interactive question is asked
  into a pipe and the run stalls or, worse, the agent invents an answer and proceeds.
- **Guessing "the ticket"** when the operator *is* sitting in an attached tmux pane turns a
  live conversation into a round-trip through GitHub, which is slower and noisier than
  simply answering.

The operator knows which one they want. There is nowhere to say it.

The issue adds a second, sharper rule that is independent of that choice: **once an
artifact exists** (`brainstorm.md`, `requirements.md`/`bugfix.md`, `design.md`,
`tasks.md`), iteration on it belongs in **pull-request review** — not in a fresh ticket
comment that re-pastes its contents, and not in an interactive back-and-forth that leaves
no trail. That is the natural extension of the loop's existing *reference, don't duplicate*
rule (`SKILL.md`): the artifact is a checked-in file, so the review surface for a file is
the PR that carries it.

This work item adds the operator's knob, makes the resolved choice reach the agent in the
prompt, and writes the artifact-iteration rule into the skill so it holds for **every**
the-loop session, not only daemon-driven ones.

## Requirements

### Requirement 1 — Declare where answers come from

**User story:** As an operator running the-loop daemon, I want to declare whether the
sessions it drives ask me questions in the CLI or on the work item, so that a session
never waits for an answer on a channel nobody is watching.

#### Acceptance criteria (EARS)

1. WHEN the operator sets `webhooks.ghWebhook.routing.interaction.mode` to `work-item` or
   `cli` THEN the system SHALL resolve that mode for every session the receiver and the
   poller spawn or resume.
2. IF `interaction` (or `interaction.mode`) is absent THEN the system SHALL resolve
   `work-item`.
3. IF `interaction.mode` carries a value outside the declared set THEN the system SHALL
   fall back to `work-item` and log a warning naming the offending value — never `cli`,
   because `work-item` is the only channel guaranteed to reach a human.
4. WHEN the config is validated against `.the-loop/cli-config.schema.json` THEN an
   undeclared `mode` value SHALL fail validation.
5. WHEN a session is spawned THEN the `session.spawned` event SHALL carry the resolved
   mode, so `the-loop events` shows which channel a session was told to use.
6. IF the resolved mode is `cli` WHILE `routing.runner` is `process` THEN the system SHALL
   warn — that combination reproduces the exact defect this work item removes, since a
   headless one-shot session has no terminal to be asked in. A **warning**, not a refusal:
   the operator may be hosting the harness somewhere the-loop cannot observe, and a daemon
   that refuses to start over a prompt hint is worse than a loud one.

### Requirement 2 — The choice reaches the agent, in the prompt

**User story:** As the agent working a ticket, I want the prompt that starts or resumes me
to state which channel I take answers from, so that I do not have to guess from the shape
of my own stdin.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher renders an event prompt or a spawn prompt THEN it SHALL substitute
   the `$interaction_directive` placeholder with the directive text for the resolved mode.
2. WHEN the resolved mode is `work-item` THEN the directive SHALL instruct the agent to
   ask every question as a comment on the work item (or its PR), mark it as its own, and
   stop and wait for the reply to arrive as a new event — never to block on an
   interactive prompt and never to treat silence as consent.
3. WHEN the resolved mode is `cli` THEN the directive SHALL instruct the agent to ask
   interactively in its own session, **and** to still record the outcome of every human
   decision on the work item — the paper-trail rule is not waived by asking in the
   terminal.
4. IF the configured `promptTemplate`/`spawnPromptTemplate` does not contain the
   placeholder THEN the system SHALL append the directive to the rendered prompt, so an
   operator's custom template cannot silently drop the rule.
5. WHEN the bundled prompt templates are compared with the dispatcher's built-in fallbacks
   THEN they SHALL be identical, so a project without the plugin files installed gets the
   same directive.

### Requirement 3 — Artifact iteration happens in pull-request review

**User story:** As a reviewer, I want every iteration on a generated artifact to happen on
the PR that carries it, so that the file, the discussion and the approval are in one place
instead of scattered across ticket comments and terminal scrollback.

#### Acceptance criteria (EARS)

1. WHEN an artifact of the chain (`brainstorm.md`, `requirements.md`/`bugfix.md`,
   `design.md`, `tasks.md`) exists THEN the-loop SHALL iterate on it **only** through
   review comments and replies on the pull request that carries it — in **both**
   interaction modes.
2. WHEN the-loop has produced such an artifact and needs feedback THEN it SHALL commit and
   push it and open (or update) the PR that carries it, rather than pasting its contents
   into a ticket comment.
3. WHEN the rule is stated THEN it SHALL live in the skill (`SKILL.md` +
   `reference/collaboration.md`), so it binds every the-loop session — including one a
   human started with `/the-loop:work-on`, where no daemon prompt is rendered at all.
4. WHEN a daemon prompt is rendered THEN the directive SHALL restate the rule in one line,
   because that prompt is the first and sometimes only instruction an unattended session
   reads.

### Requirement 4 — Documented where operators look

**User story:** As an operator reading the configuration reference, I want the new option
documented next to the options it interacts with, so that I can find it without reading
the schema.

#### Acceptance criteria (EARS)

1. WHEN the CLI config reference is built THEN `interaction.mode` SHALL have its own
   option heading under `docs/config/cli/routing-options.md` with `Type` and `Default`
   bullets (enforced by `test_docs_parity.py` P4/P5).
2. WHEN the capability docs are read THEN the current behaviour statement for the
   interaction channel SHALL be present with a history row pointing at this work item.
3. WHEN the durable choice is recorded THEN a decision record SHALL state why the mode is
   a two-value enum defaulting to `work-item`, and why the artifact rule is an invariant
   rather than a third setting.

## Non-functional requirements

- **No new dependency, no new I/O.** The directive is a constant string chosen by an enum;
  rendering it adds no network call, no subprocess and no filesystem read.
- **Backwards compatible.** An existing config with no `interaction` block keeps working
  and needs no migration; `version` stays `0.3.0` because nothing was removed or moved.
- **Observable.** The resolved mode appears on `session.spawned` in the event log.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). See `reference/security.md`.

- **Actors & trust:** the **operator** authors the CLI config and is trusted — the config
  is a local file on their machine. **GitHub commenters** are untrusted: their text arrives
  in the payload excerpt of every rendered prompt.
- **Trust boundaries & data:** the directive is a **constant per mode**, selected by a
  closed enum. No payload-derived value is interpolated into it — deliberately, including
  the work-item ref, which the templates already carry in their own `$work_item` slot. So
  the feature adds **no new path from untrusted input into the prompt**. The directive is
  rendered *above* the untrusted payload block in both templates, keeping every the-loop
  instruction on the trusted side of the same boundary the templates already draw.
- **Abuse cases (EARS):**
  1. WHEN a comment body instructs the agent to "just answer in the terminal instead" THEN
     the system SHALL still render the operator's configured directive, unchanged, outside
     the untrusted excerpt — the payload cannot rewrite it, only argue with it, and the
     templates already brand the payload as data rather than instructions.
  2. WHEN a hand-edited or corrupted config carries an unknown `interaction.mode` THEN the
     system SHALL resolve `work-item` and warn, never silently pick the mode that lets a
     question disappear into an unattended pipe.
  3. WHEN an operator's custom prompt template omits the placeholder THEN the system SHALL
     still deliver the directive by appending it, so the interaction rule cannot be
     stripped by a template edit.
- **Fail closed:** an absent, empty or unrecognised mode resolves to `work-item`. The
  failure mode of `work-item` is a comment nobody replies to yet (visible, recoverable);
  the failure mode of `cli` is a question asked into a void (invisible, unrecoverable).

## Out of scope

- Making the agent's questions machine-detectable (a "waiting for input" state in the
  session registry). The directive tells the agent what to do; observing whether it did is
  a separate work item.
- A per-work-item override of the mode. The runner is receiver-global today
  (`routing.runner`), so per-item interaction would be the only per-item routing setting —
  YAGNI until an operator asks.
- Changing anything about how replies come *back*. The webhook/poll path already delivers
  comments into the session; this work item only tells the agent to use it.
- The harness-side config (`.the-loop/harness-config.yaml`). The issue asks for a
  **cli-config** option, and the choice is a property of the machine the daemon runs on,
  not of the repository being worked.

## Open questions

None outstanding. The two judgement calls — a two-value enum (no `auto`) and the artifact
rule as an invariant rather than a setting — are recorded in
[decision-051](../../decisions/decision-051.md) and are review items on the PR.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
