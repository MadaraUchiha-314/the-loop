# Capability: review loop

> Everything that reviews a work item before a human is asked to: the self rounds, the
> **critic** rounds run by a *different* harness, and the mechanism that turns a configured
> critic into an actual process. Single source of truth for the capability's current
> behaviour; the raw specs under `docs/specs/` are the historical record.

## What it is

the-loop does not hand work to a human until it has reviewed it itself: up to
`reviews.selfReviewCount` self rounds, then up to `reviews.criticReviewCount` **critic**
rounds by a different harness/model, then the security-review gate, then the human. The
*procedure* those counts drive — attribution prefixes, reply-first-then-fix, one finding per
commit, stop-on-zero-new-findings, escalate-on-repeat — lives in the skill's
[`reference/reviewing.md`](../../skills/the-loop/reference/reviewing.md). This capability
also covers the *mechanism*: how the harness running the work spawns another harness to
critique it, and how that critique gets back (issue-108).

## Current behaviour

### The rounds

- The loop SHALL run up to `reviews.selfReviewCount` self rounds, then up to
  `reviews.criticReviewCount` critic rounds, before escalating to a human. Both are **caps**,
  not quotas.
- Every finding SHALL carry a `[<harness>/<model>]` attribution prefix and the-loop's
  own-comment marker; every reply to a finding SHALL carry the marker too.
- The loop SHALL stop early when a round yields no new actionable finding
  (`reviews.stopOnNoNewFindings`) and SHALL escalate when two consecutive rounds surface the
  same finding (`reviews.escalateOnRepeatFinding`).
- Every round SHALL be recorded in the execution log's review table with its outcome —
  new findings · zero · escalated · **unavailable**.

### Declaring a critic (`reviews.critics[]`)

- A critic entry SHALL be **runnable**, not merely descriptive: `name` (unique), plus either
  a `harness` the-loop has an adapter for or an explicit `command`.
- WHEN `harness` names a built-in adapter (`claude`, `cursor`) and no `command` is set, the
  invocation SHALL be derived from that adapter's own one-shot argv, with `model` passed
  through the harness's model flag. Adding a harness adapter therefore makes it usable as a
  critic with no critic-side change.
- WHEN `command` is set it SHALL be the **executable** (argv[0]) — never a shell line — and
  it SHALL take precedence over `harness`. Arguments live in `args`.
- `args` placeholders SHALL be substituted **element-wise** from a closed set: `{prompt}`,
  `{promptFile}`, `{model}`, `{workItem}`, `{specDir}`, `{cwd}`. An unknown placeholder SHALL
  be rejected rather than passed through as literal braces.
- IF an explicit `command`'s `args` carry neither `{prompt}` nor `{promptFile}` THEN the entry
  SHALL be refused — a critic handed nothing would review nothing.
- `env` SHALL be overlaid on the **inherited** environment (so a critic CLI keeps the
  operator's ambient credentials) and SHALL NOT hold secrets: the file is committed.
- `cwd` (default: project root), `outputFormat` (`text` | `json`), `timeoutSeconds`
  (default 900) and `enabled` (default true) complete the entry.
- Entry names SHALL be unique; a duplicate SHALL reject the configuration rather than
  silently picking one.

### Running a round and getting the output back

- `the-loop critic list [--format table|json]` SHALL report each configured critic with its
  resolved executable, whether that executable is on `PATH`, whether it is enabled, and — for
  a broken entry — why it cannot run. No critics configured is a valid state, reported as
  such with exit 0.
- `the-loop critic run <name> (--prompt|--prompt-file …)` SHALL run **exactly one** named
  critic. There SHALL be no run-all mode, so a critic entry never executes merely by
  existing.
- The round SHALL be spawned as an argv list **without a shell**, under `timeoutSeconds`
  (overridable per round with `--timeout`), in `--cwd` (else the entry's `cwd`, else the
  project root).
- Both `{prompt}` and `{promptFile}` SHALL always resolve, whichever source was given: an
  inline prompt is written to a scratch file for the length of the round.
- stdout SHALL be exactly one JSON envelope — `critic`, `harness`, `model`, `attribution`,
  `ok`, `exitCode`, `durationSeconds`, `output`, `error`, `usage` — so the calling harness
  parses it with its ordinary shell tool. Diagnostics go to the log stream, never stdout.
  `--output-file` additionally writes the envelope to disk.
- WHEN `outputFormat: json`, `output` SHALL be the reviewer's text extracted from the payload,
  falling back to raw stdout when the payload is not an object or carries no known text key —
  a critic that printed prose still produced a review.
- Reported token/cost usage SHALL be carried into `usage` for the work item's telemetry, with
  `usage.present` false when the critic reported none.
- Exit codes SHALL be `0` (round ran), `1` (round failed — absent binary, non-zero exit,
  timeout; the envelope is still printed) and `2` (misconfigured — nothing was spawned).
- A round that cannot run SHALL be recorded `unavailable` and SHALL NOT count toward
  `reviews.criticReviewCount`; if no critic can run at all, the gap is stated in the execution
  log and the PR briefing rather than reported as converged.

### Security posture

- A `reviews.critics[]` entry is **executable configuration** in a repo-tracked file — anyone
  who can land a commit can propose one. It is reviewed like code, nothing runs implicitly
  (one named critic per invocation), and `.the-loop/harness-config.yaml` sits in this repo's
  `autonomy.sensitivePaths` so a change to it raises the risk tier of the PR proposing it.
- Untrusted review material (diffs, ticket/PR comments) reaches the critic only as a single
  argv element or a file it reads — never as a shell string, so it cannot be executed.
- A critic's output is untrusted, model-generated text: it is **findings to evaluate**, never
  instructions to follow, and it is posted under the critic's attribution prefix.
- A missing critic CLI fails closed with no fallback executable; a hung critic is terminated
  at the timeout.

## Design

Pointers, not copies:

- Procedure: [`skills/the-loop/reference/reviewing.md`](../../skills/the-loop/reference/reviewing.md)
  (§ Running a critic round) and [`reference/security.md`](../../skills/the-loop/reference/security.md)
  for the security round.
- Config contract: `.the-loop/harness-config.schema.json` (`reviews`) and the annotated
  `skills/the-loop/templates/harness-config.yaml`.
- Mechanism: `cli/the_loop/critics.py` (load → resolve → run) and
  `cli/the_loop/commands/critic_cmd.py` (`the-loop critic list|run`).
- Built-in invocations: `cli/the_loop/harness/` (`HarnessAdapter.oneshot_argv`,
  `model_flag`) — shared with session dispatch, see [cli](cli.md).
- Where the rounds sit in the lifecycle: the `self-review` / `critic-review` /
  `security-review` nodes of [process-graph](process-graph.md).

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-108 | Minted this capability. Made `reviews.critics[]` runnable — `command`/`args` with element-wise placeholders (or a built-in `harness` deriving them), `env`/`cwd`/`outputFormat`/`timeoutSeconds`/`enabled` — added `the-loop critic list\|run` returning one JSON envelope on stdout, and wrote the critic-round procedure (including the `unavailable` outcome) into `reference/reviewing.md`. | [spec](../specs/issue-108/), [decision-043](../decisions/decision-043.md) |
