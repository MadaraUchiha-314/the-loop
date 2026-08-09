# Decision 051: the interaction channel is declared (two values); artifact iteration on the PR is an invariant

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #134)
- **Work item:** issue-134
- **Spec:** `docs/specs/issue-134/`
- **Builds on:** [decision-032](decision-032.md) — the CLI config is a property of the
  operator's machine, not of a repository — and [decision-016](decision-016.md), whose
  prompt-rendering path is the delivery mechanism.

## Context

A session the CLI daemon spawns or resumes was never told **where a human is**. The
rendered prompt described the event and restated the-loop's rules, then left the most
consequential question to the model: when it needs a decision, does it ask in the terminal
it is running in, or on the GitHub issue/PR?

Both guesses fail, and they fail asymmetrically:

- **"The terminal"** in a `process`-runner session is a dead end — a headless one-shot
  subprocess with no human attached. The question goes into a pipe and the run stalls, or
  the agent invents an answer and proceeds.
- **"The ticket"** while the operator sits in an attached tmux pane turns a live
  conversation into a round-trip through GitHub: slower, noisier, and pointless.

Only the operator knows which is true, and there was nowhere to say it.

Issue #134 adds a second rule that is independent of that choice: **once an artifact
exists** (`brainstorm.md`, `requirements.md`/`bugfix.md`, `design.md`, `tasks.md`),
iteration on it belongs in **pull-request review**. That is the *reference, don't
duplicate* rule reaching its conclusion — the artifact is a checked-in file, so the review
surface for a file is the PR that carries it.

## Decision

**1. The interaction channel is declared in the CLI config, with exactly two values.**
`webhooks.ghWebhook.routing.interaction.mode` is `work-item` or `cli`, defaulting to
`work-item`.

- `work-item`: every question is a comment on the work item or its PR; the session then
  stops and waits, and the reply arrives as the next event.
- `cli`: a human is attached to this terminal, so ask there — and still record the
  *outcome* on the work item, because the paper trail is not waived by asking in a
  terminal.

**2. No `auto`.** Deriving the mode from `routing.runner` (`tmux` → `cli`, `process` →
`work-item`) sounds helpful, but `runner` is **receiver-global**, so `auto` would be a
static alias for a fixed mapping — a third name for two behaviours (`reference/minimalism.md`).

**3. The default is `work-item`, not "whatever the runner suggests".** A tmux session is
*attachable*, not *attended*; the-loop announces the `tmux attach` command precisely
because nobody is there yet. An unrecognised value resolves to `work-item` **with a
warning**, never to `cli`.

**4. The directive is a constant per mode, rendered from code into the prompt.** It reaches
the agent through a `$interaction_directive` placeholder in both prompt templates. It
interpolates **nothing** — not even the work-item ref — so no payload-derived text can
enter it, and it is rendered *above* the excerpt both templates already label untrusted.
A template that does not declare the placeholder gets the directive **appended**, because
`string.Template.safe_substitute` is silent about a placeholder that was never declared —
which is exactly how a custom template would strip the rule with nobody the wiser.

**5. Artifact iteration on the pull request is an invariant, not a third setting.**
*(Amended by [decision-069](decision-069.md), issue-183: the invariant is now that
iteration happens on a **durable, reviewable** surface — the pull request **or the work
item** — never in a terminal. Which of the two the outer loop uses is declared per work
item at `phase-selection` (default: the work item); the inner loop still has no choice.
The configuration this paragraph refused — specs reviewed where the reasoning dies with
the scrollback — is still refused.)* It
holds in both modes, and its home is the **skill** (`SKILL.md`,
`reference/collaboration.md`) so it binds sessions the daemon never touched — including
one a human started with `/the-loop:work-on`. The daemon prompt restates it in one
paragraph because that prompt is the first, and sometimes only, instruction an unattended
session reads.

## Consequences

**Positive.**

- The failure mode that had no recovery — a question asked into a pipe — is gone by
  default, and the operator who *is* watching a terminal can opt out in one line.
- The rule travels with the prompt rather than living in a document the session may not
  read, and it cannot be lost to a template edit.
- The artifact rule puts the file, the discussion and the approval in one place, which is
  also the place a human reviewer already looks.
- The one unworkable combination (`cli` + the headless `process` runner) says so out
  loud instead of silently reproducing the original defect.
- `session.spawned` now carries the resolved mode, so `the-loop events` answers "which
  channel was this session told to use?" after the fact.
- The change is additive: no key removed or moved, so `CURRENT_CONFIG_VERSION` stays
  `0.3.0` and no migration is needed.

**Negative / accepted costs.**

- **It is guidance, not enforcement.** Nothing stops an agent in `work-item` mode from
  trying to prompt interactively; the daemon cannot observe the attempt. Making a
  "waiting for input" state observable is deliberately a separate work item.
- **No per-work-item override.** The mode is receiver-wide, like `runner`. An operator who
  wants to watch one item interactively while the rest run headless has to run two
  receivers or flip the mode. YAGNI until asked.
- **The invariant removes a choice.** An operator who genuinely wants artifacts iterated
  in the terminal cannot have it. Accepted: the configuration this rules out is one in
  which generated artifacts are reviewed nowhere durable.
- **Two copies of the directive's slot** (bundled template file + in-code fallback). Now
  cheaper than before: this work item turns the "kept in sync" comment that has ridden on
  those constants since issue-36 into a test.

## Alternatives considered

| Option | Why not |
|---|---|
| Put the setting in the harness config (`.the-loop/harness-config.yaml`) | Where a human is sitting is a property of the operator's machine, not of the repository being worked (decision-032). A repo cannot know whether *your* daemon runs headless. |
| A third `auto` value derived from `routing.runner` | `runner` is receiver-global, so `auto` resolves statically — a third name for two behaviours, with an extra branch to test and explain. |
| Default to `cli` when the runner is `tmux` | Attachable is not attended. The whole point of the session-announcement comment (issue-86) is that the human has not attached yet. |
| Make the artifact rule a third config key | Invites a configuration where generated artifacts are reviewed in a terminal and the reasoning dies with the scrollback. The issue states the rule absolutely. |
| Put the directive text in the template files only | A file can be edited to say the opposite of what the config declares. Templates keep the *slot*; code keeps the *content*. |
| Rely on `safe_substitute` alone and accept that custom templates opt out | The opt-out would be silent and accidental. A template written before this existed omits the placeholder by definition — that is the common case, not the exotic one. |
| Interpolate the work-item ref into the directive for a friendlier sentence | Adds a data flow into a string whose entire security argument is that it has none. The templates already carry `$work_item` in their own slot. |
