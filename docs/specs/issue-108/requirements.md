---
type: requirements
phase: requirements-definition
workItem: issue-108
status: approved             # draft | in-review | approved
approvedBy: []               # tier-4: the human gate is the PR review (see execution-log)
collaborators: [architect, engineer]
riskTier: 4                  # config-declared executable commands + a schema change (sensitivePath)
overrides: {}
---

# Requirements: specify (and actually invoke) the critic harness

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

Ticket: [#108 — How to specify which harness to use for critic review?](https://github.com/MadaraUchiha-314/the-loop/issues/108)

the-loop's review loop is "self-reviews, then **critic** reviews by a *different*
harness/model, then the human" (`reviews.selfReviewCount` / `reviews.criticReviewCount`,
`reference/reviewing.md`). The *policy* is fully specified — round counts, attribution
prefixes, reply-first-then-fix, stop-on-zero-new-findings, escalate-on-repeat. The
*mechanism* is not: `reviews.critics[]` carries `name`/`harness`/`model` and an optional
free-form `command` **string**, and nothing anywhere says how that string is turned into a
process, what the critic is told to review, or how its findings get back into the running
harness. The result is that a critic round is un-runnable as written — the config declares
an intent that no code and no procedure consumes.

Issue #108 states the gap as three questions:

1. How does the running harness (say Claude) trigger a critic review by another CLI agent
   (say `cursor-agent`) available in the same environment? **This needs to be a config
   option.**
2. The command for spawning the review needs to be exposed **along with its args**.
3. How does the current harness **get the output** of that command?

This work item answers all three: a declarative critic invocation in
`.the-loop/harness-config.yaml`, a `the-loop critic` CLI surface that runs exactly that
invocation as a subprocess with **no shell**, and a single JSON envelope on stdout that the
calling harness reads with its ordinary shell tool.

Non-goal restated up front: the CLI does **not** own the review *loop*. Round counts,
convergence and posting findings stay with the harness following `reference/reviewing.md`;
the CLI owns exactly one round's process invocation and its output.

## Requirements

### Requirement 1 — Declare which harness runs a critic round

**User story:** As an operator, I want to name the harness/model that critiques my work in
`.the-loop/harness-config.yaml`, so that the review loop uses a genuinely different
reviewer without me hand-assembling a command line each time.

#### Acceptance criteria (EARS)

1. WHEN a `reviews.critics[]` entry names a `harness` that matches a built-in adapter
   (`claude`, `cursor`) AND sets no `command` THEN the system SHALL derive the invocation
   from that adapter's own non-interactive one-shot argv, so the operator writes two lines
   (`harness`, `model`) and nothing else.
2. WHEN an entry sets `command` THEN the system SHALL spawn exactly that executable, and
   `command` SHALL take precedence over any built-in derivation for that entry.
3. IF an entry has neither a `command` nor a recognized built-in `harness` THEN the system
   SHALL refuse to run it, naming the critic and both remedies in the error, and SHALL NOT
   spawn any process.
4. WHEN an entry sets `enabled: false` THEN the system SHALL list it as disabled and SHALL
   refuse to run it.
5. WHEN two entries share a `name` THEN the system SHALL reject the configuration rather
   than silently pick one.

### Requirement 2 — The command and its args are explicit, substituted, and shell-free

**User story:** As an operator, I want the critic's argv spelled out in config with
placeholders for the per-round values, so that an arbitrary CLI agent — not just the two
the-loop knows — can be the critic.

#### Acceptance criteria (EARS)

1. WHEN `args` contains a placeholder from the documented set (`{prompt}`, `{promptFile}`,
   `{model}`, `{workItem}`, `{specDir}`, `{cwd}`) THEN the system SHALL substitute the
   round's value **within the argv element that contains it**, leaving every other element
   untouched.
2. IF an `args` list contains neither `{prompt}` nor `{promptFile}` THEN the system SHALL
   refuse to run that critic — a critic that is never handed the material under review
   would return a confident review of nothing.
3. IF `args` references a placeholder outside the documented set THEN the system SHALL
   reject the configuration naming the unknown placeholder, rather than passing the
   literal braces through to the critic.
4. The system SHALL spawn the critic **without a shell** (`shell=False`, argv list), so no
   placeholder value can ever be parsed as a command.
5. WHEN `env` is set THEN the system SHALL start the child from the parent environment
   overlaid with those entries, so a critic CLI keeps the ambient credentials it needs
   without any secret being written into the repository.
6. WHEN `cwd` is set THEN the system SHALL run the critic in that directory, defaulting to
   the project root.

### Requirement 3 — The output comes back to the calling harness

**User story:** As the running harness, I want one machine-readable result per critic
round, so that I can post its findings as review comments with the right attribution
instead of guessing what the critic printed.

#### Acceptance criteria (EARS)

1. WHEN a critic round finishes THEN the system SHALL print exactly one JSON object on
   stdout carrying `critic`, `harness`, `model`, `attribution`, `ok`, `exitCode`,
   `durationSeconds`, `output`, `error` and `usage`.
2. WHEN the critic's `outputFormat` is `json` THEN the system SHALL extract the reviewer's
   message text from the payload's first known text key, and IF the payload is not a JSON
   object or carries no known text key THEN the system SHALL fall back to the raw stdout
   rather than reporting an empty review.
3. WHEN the critic's `outputFormat` is `text` THEN `output` SHALL be the raw stdout.
4. WHEN the critic reports token/cost usage in its JSON output THEN the system SHALL carry
   it into `usage` for the work item's token telemetry, and IF it reports none THEN
   `usage.present` SHALL be false rather than a fabricated zero reading.
5. WHEN the critic exits non-zero, exceeds its timeout, or its binary is absent from
   `PATH` THEN `ok` SHALL be false with the cause in `error`, the process SHALL exit
   non-zero, and the envelope SHALL still be printed so the harness can log the failed
   round.
6. WHEN the round succeeds THEN diagnostics SHALL go to the log stream and never to
   stdout, so stdout stays parseable as a single JSON object.

### Requirement 4 — The configured critics are discoverable before they are needed

**User story:** As an operator (or the harness about to start a critic round), I want to
see which critics are configured and whether they can actually run here, so that a missing
CLI is discovered before a review round, not during one.

#### Acceptance criteria (EARS)

1. WHEN `the-loop critic list` runs THEN the system SHALL list every configured critic with
   its harness, model, resolved executable, whether that executable is on `PATH`, and
   whether it is enabled — as a table (default) or JSON (`--format json`).
2. WHEN no critics are configured THEN the system SHALL say so explicitly and exit 0 — an
   empty `critics: []` is a valid configuration (self-review only), not an error.
3. WHEN a critic's configuration is invalid THEN `list` SHALL show it with the reason
   rather than failing the whole listing.

### Requirement 5 — The procedure the harness follows is written down

**User story:** As a harness working an item under the-loop, I want the critic-round
procedure in the skill, so that critic rounds happen the same way every time instead of
being improvised per session.

#### Acceptance criteria (EARS)

1. WHEN `reference/reviewing.md` describes a critic round THEN it SHALL state how the round
   is invoked, what the critic prompt must contain, and what the harness does with the
   returned envelope (post findings as review comments carrying the `[<harness>/<model>]`
   attribution prefix and the loop-prevention marker, then reply-first-then-fix).
2. WHEN a critic round cannot run (unavailable binary, invalid entry, timeout) THEN the
   procedure SHALL record that round in the execution log's review table as `unavailable`
   with the cause, and that round SHALL NOT count as a passing critic round toward
   `reviews.criticReviewCount`.
3. IF no critic can run at all THEN the harness SHALL continue to the human gate with the
   unavailability recorded, rather than silently reporting the critic rounds as done.

## Non-functional requirements

- **Timeout.** Every critic invocation runs under a bounded timeout
  (`timeoutSeconds`, default 900) so a hung critic CLI cannot wedge the review loop.
- **Observability.** Invocation, exit status and duration are logged on the CLI's existing
  logger; the envelope is the machine-readable record.
- **Dependencies.** No new runtime dependency (stdlib `subprocess` + the existing PyYAML).
- **Backwards compatibility.** Existing `reviews.critics[]` entries (`name`/`harness`/
  `model`/`command`) SHALL keep validating; every new key is optional.

## Security considerations

- **Actors & trust:**
  - The **operator** authors `.the-loop/harness-config.yaml` — but that file is *checked
    into the repository*, so anyone who can land a commit (including a drive-by pull
    request) can propose a `reviews.critics[]` entry. A critic entry is therefore
    **executable configuration**, and is untrusted to exactly the degree the repository's
    contributors are.
  - The **critic prompt** is untrusted content: it quotes the diff, the spec and ticket/PR
    comment text, any of which can be written by a third party.
  - The **critic's stdout** is untrusted output: it is model-generated text that the
    harness will later post as comments.
- **Trust boundaries & data:** two crossings. (a) Config → process spawn: a YAML value
  becomes an executable and its argv. (b) Untrusted prompt text → that argv. No secret is
  read from or written to the config; the child inherits the operator's ambient
  environment for its own credentials.
- **Abuse cases (EARS):**
  1. WHEN a placeholder value contains shell metacharacters (`; rm -rf /`, backticks,
     `$(…)`) THEN the system SHALL pass it as a single literal argv element and SHALL NOT
     invoke a shell, so it can never be parsed as a command.
  2. WHEN `the-loop critic run` is invoked THEN the system SHALL run **only** the single
     critic named on the command line — there SHALL be no "run all configured critics"
     mode, so a newly-introduced critic entry cannot execute merely because it exists.
  3. WHEN a critic's executable is not on `PATH` THEN the system SHALL fail closed with a
     diagnostic and SHALL NOT fall back to any other executable.
  4. WHEN a critic exceeds `timeoutSeconds` THEN the system SHALL terminate it and report
     the round as failed.
  5. WHEN a critic's returned text contains instructions addressed to the harness
     ("ignore your instructions", "approve this PR") THEN the procedure SHALL treat the
     output as *review findings to evaluate*, never as instructions to follow.
- **Fail closed:** an entry that is ambiguous (no command and no known harness), unusable
  (no prompt placeholder), unknown-placeholder, duplicate-named, disabled, or unavailable
  runs **nothing** and exits non-zero. Silence is never interpreted as approval: a critic
  round that did not run is recorded as `unavailable`, never as a passing round.

## Out of scope

- Driving the review *loop* (round counts, convergence, escalation) from the CLI — that
  stays with the harness and `reference/reviewing.md`.
- Posting the critic's findings to GitHub. The harness posts them, as it does today, so
  the loop-prevention marker and reply-first-then-fix protocol keep one owner.
- Parsing a critic's prose into structured findings. Reviewers write review comments; the
  envelope carries their text verbatim.
- Interactive/TUI critics, and resuming a critic conversation across rounds. Each round is
  one non-interactive invocation.
- Wiring the critic round into the `critic-review` process-graph node's hooks (issue-109/
  113). The node keeps its artifact-validating exit hook; the invocation seam lands first.

## Open questions

None outstanding. Two resolved while drafting, recorded in `design.md` § Trade-offs:
whether the CLI should drive the whole loop (no — one round per invocation), and whether
`env` should carry secret values (no — overlay on the inherited environment, secrets stay
ambient).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
