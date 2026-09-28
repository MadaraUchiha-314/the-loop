---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#343"
---

# Self-review: an operator can bring their own graphs and bind commands to them

> The `self-review` node's proof, per `reference/reviewing.md`. Critic rounds: no critic is
> configured on this machine (`the-loop critic list`: *No critics configured*), so they are
> recorded **unavailable** and do not count toward the operator's `criticReviewCount`.
> Round 2 was run by a fresh-context reviewer (a sub-agent of this session, same model —
> an independent reading, **not** a critic).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) | new findings | 3 found, 3 fixed |
| 2 | fresh-context reviewer | new findings | 10 found: 9 fixed, 1 fixed in the docs rather than the code (F5) |
| 3 | self (this session) | zero (converged) | re-read the whole diff against the requirements, the design's security table and the round-2 fixes; no new finding |
| critic 1–3 | — | **unavailable** | no critic configured on this machine |

## Round 1 findings

**S1 — a relative graph path followed the working directory.** A config found as
`./.the-loop/cli-config.yaml` gave a relative base, so a graph path moved if the process's
working directory changed. **Fixed**: `config_base()` is made absolute.

**S2 — a hook a custom graph names directly was reported as "attached to no node".**
`extensions.apply`'s warning counted attachments only. **Fixed**: hooks named in the
graph's own chains count as used.

**S3 — a new keyword equal to a configured one would make every such comment
ambiguous.** **Fixed**: `ControlConfig.from_mapping` refuses the clash at load
(`test_a_new_keyword_that_clashes_with_a_configured_one_is_refused`).

## Round 2 findings

**F1 (blocker) — `the-loop graph loops` reported every real graph as broken.** It compiled
without registering the shipped hooks; in-process tests had them imported already.
**Fixed** in both places — `compile_custom` and the report import the registry — and pinned
by `test_graph_loops_compiles_in_a_fresh_process`, which runs the CLI in a subprocess.

**F2 (major) — an override held only for a comment.** `the-loop sessions start` and a
spawn with no start required recorded no loop and walked the shipped graph; the Slack
slash command refused a new word. **Fixed**: with no usable recorded loop,
`_outer_loop_name` applies the command's current binding (`start`'s when there is no
record); `_command_for` knows the operator's words. Tests:
`test_an_overridden_start_applies_without_a_comment`,
`test_the_slack_command_knows_the_operators_words`. Requirements R4.5 added.

**F3 (major) — `graph loops` checked less than a load.** **Fixed**: the config is read
strictly (an unparseable file is an error, not "nothing declared"), attachments that apply
to a graph must name a node it declares, `x-` hooks need a declared module, and the
keyword clash check runs. The doc sentence now says exactly what is checked. Tests: three
`test_graph_loops_reports_*`.

**F4 (minor) — `core/sessions.py`'s `on_pr_linked` built a `GraphLink` without the
control config**, so a custom item resolved to the default there. **Fixed**: it passes
`_control_config(config)`.

**F5 (minor) — `guest: true` does not carry the shipped loops' prompt lines** ("no outer
loop", "change no code"). **Fixed in the docs**: the schema, the config reference, the
capability doc and R5.1 now describe `guest` as the posture only (spec tree out of git,
the plan on the thread) and tell the operator to put session guidance in the graph's own
nodes. Keying the prompt on `guest` would impose the review loop's "change no code" on a
guest graph that is a contribution — a wrong default either way.

**F6 (minor) — the parser was looser than R1.5/R6.1.** **Fixed**: a non-list `graphs`
(including `{}`, `""`, `false`) raises; `name`/`path` must be strings; an empty
`attach[].loops` is refused.

**F7 (minor, hardening) — a new word could be one of the-loop's own verbs**, so a comment
quoting `the-loop graph complete …` would arm. **Fixed**: CLI sub-command names and the
Slack verbs are reserved (`test_a_new_word_may_not_be_one_of_the_loops_own_verbs`).

**F8 (nit) — a removed override fell back to the default loop**, not the command's own.
**Fixed**: `do` armed onto a since-removed graph walks the ad-hoc loop
(`test_a_removed_override_falls_back_to_the_commands_shipped_loop`); R4.2 says so.

**F9 (nit) — output mismatches.** **Fixed**: `graph hooks` shows an attachment's `loops`;
`graph loops` prints the configured keyword and omits a disabled one
(`test_graph_loops_shows_the_configured_keyword`); the design no longer claims
`channels/slack.py` passes the graph block.

**F10 (nit) — `config_base()` resolved symlinks**, contradicting "this file's directory".
**Fixed**: `os.path.abspath`, no symlink resolution.

The reviewer found **nothing** in the two security categories that matter most: no path
lets an agent-writable value select an undeclared graph or be used as a path, and no path
lets comment text choose the loop other than through the operator's bindings.

## Round 4 — the owner's shape (PR #425 review)

The owner asked for a top-level `graphs` list with commands bound under
`routing.control.commands`, and approved the proposal on the thread ("Yes"). Implemented,
then re-read against the diff:

- **One home per fact.** `graphs[]` entries refuse a `commands` key with a hint naming
  `routing.control.commands`. A `keyword` on a built-in command is refused with a pointer
  to `routing.control.keywords`.
- **A binding may name a shipped loop.** This fell out of the reshape. `graphlink`'s
  `selectable()` makes a binding to the default loop read as the default, so it does not
  fall through to the command's shipped loop. Covered by
  `test_a_command_bound_to_the_default_loop_selects_the_default`.
- **The routing-only readers.** The dispatcher, the Slack command, inbound channels and
  `core/sessions` get the routing block alone. The loader fans `graphs` into
  `routing._graphs`, as `instance` travels as `_instance`, and each builder reads it there.
  The integration scenarios build the dispatcher from `load_cli_config`'s output, so the
  fan-in is on the tested path.
- **Schema.** `propertyNames` was left out: the in-house validator does not implement it,
  and the parser enforces the word grammar anyway. The retired `routing.graph.graphs` fails
  validation (`test_the_schema_accepts_the_documented_shape_and_refuses_the_old_one`). It
  was never released, so no `RETIRED` migration entry is needed.
- **`graph loops`** lists a row's commands with the built-in words first, then the new
  ones. A re-pointed built-in moves to the row of the loop it now selects, including
  another shipped loop.

No finding is left open.
