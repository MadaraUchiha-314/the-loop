# Capability: review loop

> Everything that reviews a work item before a human is asked to: the self rounds, the
> **critic** rounds run by a *different* harness, and the mechanism that turns a configured
> critic into an actual process. Single source of truth for the capability's current
> behaviour; the raw specs under `docs/specs/` are the historical record.

## What it is

the-loop does not hand work to a human until it has reviewed it itself: up to the
operator's `reviews.selfReviewCount` self rounds, then up to `reviews.criticReviewCount`
**critic** rounds by a different harness/model, then the security-review gate, then the
human. The round counts and stop conditions are the **operator's** — top-level `reviews`
in the CLI config, read by the agent with `the-loop critic policy`. The *procedure* those
counts drive — attribution prefixes, reply-first-then-fix, one finding per commit,
stop-on-zero-new-findings, escalate-on-repeat — lives in the skill's
[`reference/reviewing.md`](../../skills/the-loop/reference/reviewing.md). This capability
also covers the *mechanism*: how the harness running the work spawns another harness to
critique it, and how that critique gets back (issue-108).

## Current behaviour

### The rounds

- The loop SHALL run up to the operator's `reviews.selfReviewCount` self rounds, then up
  to `reviews.criticReviewCount` critic rounds, before escalating to a human. Both are
  **caps**, not quotas.
- The review-round policy SHALL be the operator's: top-level `reviews` in the CLI config
  ([`reviews`](/config/cli/critics-options#review-rounds) — `selfReviewCount` 3,
  `criticReviewCount` 3, `stopOnNoNewFindings` true, `escalateOnRepeatFinding` true by
  default), never a repository's harness config. `the-loop critic policy` SHALL print it
  (`--format json` for the agent), and the defaults SHALL apply both when the operator's
  config has no `reviews` block and when the CLI is not installed.
- Every finding SHALL carry a `[<harness>/<model>]` attribution prefix and the-loop's
  own-comment marker; every reply to a finding SHALL carry the marker too.
- The loop SHALL stop early when a round yields no new actionable finding (the operator's
  `reviews.stopOnNoNewFindings`) and SHALL escalate when two consecutive rounds surface
  the same finding (the operator's `reviews.escalateOnRepeatFinding`).
- Every round SHALL be recorded in the execution log's review table with its outcome —
  new findings · zero · escalated · **unavailable**.

### The design critic round (opt-in, issue-188)

- The outer loop SHALL offer an **opt-in** `design-critic-review` node between `design` and
  `test-planning` — a critic round whose subject is the **locked `design.md`** read against
  `requirements.md`/`bugfix.md`, rather than a diff read against the whole spec chain.
- It SHALL be **off unless selected**: the node is `optIn: true`, rendered unticked at
  `phase-selection`, and it runs only when an authorized human ticks it
  ([decision-071](../decisions/decision-071.md), [process-graph](process-graph.md)
  § Opt-in phases). The harness SHALL never select it.
- WHEN it runs THEN its exit gate SHALL require a non-empty **`## Design critic review`**
  section in `execution-log.md` — a section of its own, not a row of the review table, so
  the node cannot pass on a round another node recorded.
- The **procedure** SHALL be unchanged: attribution prefix, own-comment marker,
  reply-first-then-fix, stop on zero new findings, escalate on a repeated finding, and a
  round that could not run recorded as `unavailable` with its cause.
- Findings SHALL be applied to `design.md` in place; the node SHALL NOT route back to
  `design`, because `design-approval` has not read the design yet.
- The node SHALL declare `stage: critic-review`, so the token-economy guidance's stage
  table treats it as reasoning-heavy (high thinking effort) without a new key anywhere.

### Declaring a critic (`critics[]` in the CLI config)

- Critics SHALL be declared in the **operator's** CLI config (`critics[]`, issue-352,
  [decision-123](../decisions/decision-123.md)), never in a repository's harness config:
  a critic is a harness and a model installed on the machine that runs the round, and
  executable configuration belongs in a file no pull request to the repository can edit.
  The operator keeps both the roster and the review **bar** (`reviews.criticReviewCount`,
  in the same file): `the-loop critic list` is how a session learns what this machine
  has, `the-loop critic policy` how many rounds to run with it.
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
  operator's ambient credentials) and SHALL NOT hold secrets: name a variable, keep the
  value in `env.file` or the ambient environment.
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
- A round that cannot run SHALL be recorded `unavailable` and SHALL NOT count toward the
  operator's `reviews.criticReviewCount`; if no critic can run at all, the gap is stated
  in the execution log and the PR briefing rather than reported as converged.

### Security posture

- A `critics[]` entry is **executable configuration** in the operator's own file. Until
  issue-352 it lived in the repository's harness config, where anyone who could land a
  commit could propose one; moving it to the CLI config removed that surface entirely. It
  is still reviewed like code and nothing runs implicitly (one named critic per
  invocation); `.the-loop/**` is one of the fixed sensitive paths that raise a change's
  risk tier, for the same reason.
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
- Config contract: `.the-loop/cli-config.schema.json` (`critics` and `reviews` — the
  roster and the round counts, both the operator's) and the annotated
  `skills/the-loop/templates/cli-config.yaml`.
- Mechanism: `cli/the_loop/critics.py` (load → resolve → run) and
  `cli/the_loop/commands/critic_cmd.py` (`the-loop critic list|run`).
- Built-in invocations: `cli/the_loop/harness/` (`HarnessAdapter.oneshot_argv`,
  `model_flag`) — shared with session dispatch, see [cli](cli.md).
- Where the rounds sit in the lifecycle: the `design-critic-review` (opt-in) /
  `self-review` / `critic-review` / `security-review` nodes of
  [process-graph](process-graph.md).

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-352 | The critic roster moved to the operator (2026-09-12): `reviews.critics[]` in the harness config became the top-level `critics[]` in the CLI config, same entry shape, read by `the-loop critic list\|run` through the resolved CLI config and never from a repository. A critic entry committed to a repository is inert. The `autonomy` block left the harness config in the same change: `.the-loop/**` is a fixed sensitive path, not a configured one. Third pass: the round counts followed the roster — `reviews` (`selfReviewCount`, `criticReviewCount`, `stopOnNoNewFindings`, `escalateOnRepeatFinding`) is now the CLI config's top-level `reviews`, read by the agent with `the-loop critic policy`; the defaults (3/3, true, true) apply when the operator set none or the CLI is not installed | [spec](../specs/issue-352/), [decision-123](../decisions/decision-123.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/352) |
| issue-188 | The design critic round (2026-08-10): an **opt-in** `design-critic-review` node between `design` and `test-planning`, reviewing the locked `design.md` against the requirements while a structural finding still costs an edit; off unless an authorized human ticks it at `phase-selection`, gating the execution log's own `## Design critic review` section, `stage: critic-review` so it routes to a frontier model; the procedure, the `unavailable` rule and the reply-first-then-fix protocol unchanged | [spec](../specs/issue-188/), [decision-071](../decisions/decision-071.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/188) |
| issue-108 | Minted this capability. Made `reviews.critics[]` runnable — `command`/`args` with element-wise placeholders (or a built-in `harness` deriving them), `env`/`cwd`/`outputFormat`/`timeoutSeconds`/`enabled` — added `the-loop critic list\|run` returning one JSON envelope on stdout, and wrote the critic-round procedure (including the `unavailable` outcome) into `reference/reviewing.md`. | [spec](../specs/issue-108/), [decision-043](../decisions/decision-043.md) |
