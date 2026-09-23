---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#343"
---

# Security review: an operator can bring their own graphs and bind commands to them

> The `security-review` gate's record (`reference/security.md`). **Risk tier 4**: the change
> widens the comment → daemon-action vocabulary and the agent-writable-state → graph
> selection seam, and touches the CLI config schema. Tier 4 requires a **named human
> security sign-off** before completion; it is requested on the pull request and is not
> claimed here.

## What the change introduces

1. A new operator-owned configuration list (`routing.graph.graphs`) naming YAML files on the
   operator's machine.
2. New control keywords (`the-loop <word>`) derived from that list.
3. A new field (`loop`) on the portable control record, and a wider set of names the
   state file's `loop` may resolve to.

No new network call, credential, secret, subprocess or permission.

## Abuse cases

| # | Abuse case (requirements) | Mechanism | Test |
|---|---|---|---|
| 1 | An agent writes an undeclared name, a path or `../…` into `work-item-state.json`'s `loop` | `resolve_outer_loop(name, declared)` accepts only an exact shipped outer-path name or a currently declared one; `build_runtime` refuses anything else with a warning; `load_graph` looks a name up in the catalog and never uses it as a path | `test_resolve_outer_loop_accepts_only_declared_names`, `test_forged_state_loop_reads_as_default`, `test_a_name_neither_shipped_nor_declared_is_refused` |
| 2 | A comment carries a keyword-shaped word the operator never declared | `parse_command` scans `COMMANDS` plus the declared words only | `test_undeclared_word_is_no_command`, `test_a_new_word_obeys_the_whole_token_boundary` |
| 3 | An unauthorized user types a declared new command | It parses as `START`, so the existing named-actor check refuses it (`unauthorized-actor`) before anything is recorded | `test_unauthorized_custom_command_is_refused` (integration) |
| 4 | A comment carries a new command and a built-in one | `found` holds words, so two different words are ambiguous: nothing executed, nothing forwarded | `test_custom_and_builtin_command_is_ambiguous` |
| 5 | A repository ships `.the-loop/<declared-name>.yaml` to shadow the operator's graph | The loader never reads a repository file; the warning names it and points at `routing.graph.graphs` | `test_repo_file_for_declared_name_is_ignored` |
| 6 | A declaration rebinds `stop`/`pause`/`resume`/`execute`/`cleanup`/an argument command, names a graph `pdlc-*`, or takes one of the-loop's own verbs as a new word | `read_catalog` refuses all three at parse | `test_catalog_refuses_binding_a_command_that_selects_no_loop`, `test_catalog_refuses_a_malformed_entry`, `test_a_new_word_may_not_be_one_of_the_loops_own_verbs` |

Further checks made over the diff:

- **The loop never comes from the body.** `ControlResult.loop` is `config.bindings[word]` —
  a lookup keyed by a matched declared word. The control record's `loop` is re-resolved
  against the current declaration on every read (`graphlink._outer_loop_name`), so a
  hand-edited portable record cannot select an undeclared graph either.
- **The text a session is told to run is one token.** `Node.command` is grammar-checked in
  every graph (`^[a-z0-9][a-z0-9-]*(:[a-z0-9][a-z0-9-]*)?$`), so a custom graph cannot put
  whitespace, a path or a second instruction into the `deliver-assignment` or
  `$graph_context` line.
- **No code execution is added.** A custom graph names hooks; it cannot import anything. An
  `x-` hook it names is bound only to a module the operator already declared in
  `routing.graph.hooks.modules` (issue-248's containment rules unchanged); `graph loops`
  imports nothing.
- **Paths are the operator's.** A graph path comes only from the CLI config and resolves
  against that file's directory, never a checkout — so a session cannot edit the graph it
  walks unless the operator placed both the config and the graph inside a checkout, which
  is no wider than the config file's own exposure today. One caveat, pre-existing and
  shared with `routing.graph.hooks.modules`: a CLI command run *inside a session* resolves
  the CLI config through the exported `THE_LOOP_CLI_CONFIG`, and when the daemon had no
  config file to export it falls back to the checkout's `./.the-loop/cli-config.yaml`.
  Loop **selection** for a daemon-driven work item happens in the daemon, so this does not
  let a session choose its graph; it is recorded here so the claim is not read wider than
  it is.
- **New words cannot shadow the-loop's own verbs.** A command word that is a CLI
  sub-command (`graph`, `check`, `sessions`, …) or a Slack verb is refused, so a comment
  quoting `the-loop graph complete …` — which sessions post — never arms a work item.
- **Fail closed.** Every malformed declaration, unreadable file, unknown phase or hook
  raises. A declared graph that fails to load raises from `build_runtime` rather than
  walking the default (R4.4).

## Accepted risk, stated

A custom graph may omit phase selection, approvals and reviews. That is the requested
capability, owned by the operator on their machine exactly as `critics[]` and hook modules
are; the schema, the config reference and the new docs page call it executable
configuration to review like code. It does not widen what an agent can do: the agent could
already select the shipped ad-hoc loop by editing the state file's `loop` (pre-existing),
and the set of selectable loops grows only by what the operator declares.

## Verdict

No finding requiring a code change. **Named human security sign-off requested** (tier 4) on
the pull request.
