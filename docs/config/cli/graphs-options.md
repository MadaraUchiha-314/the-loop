---
configBase: ""
---

# Graphs

The loops the-loop ships are its own. **Graphs of your own** are declared here, at the top
level of the CLI config
([issue-343](https://github.com/MadaraUchiha-314/the-loop/issues/343),
[decision-136](/decisions/decision-136)). Which **command** selects which graph is a
separate declaration,
[`routing.control.commands`](/config/cli/routing-options#control-commands): declaring a
graph selects nothing by itself.

```yaml
graphs:
  - name: acme-triage-loop
    path: graphs/acme-triage-loop.yaml   # relative to this file's directory
  - name: acme-quick-loop
    path: ~/.the-loop/graphs/quick.yaml

routing:
  control:
    commands:
      triage: {graph: acme-triage-loop}  # a new word → `the-loop triage`
      do: {graph: acme-quick-loop}       # `the-loop do` now walks this graph
```

[Bringing your own graph](/cli/graphs) walks through writing one.

## The declaration

### graphs

- **Type:** `object[]` — `name`, `path`, and optionally `guest`
- **Default:** `[]` — only the shipped loops
- **Related:** [bringing your own graph](/cli/graphs) · [process-graph](/capabilities/process-graph) · [`the-loop graph loops`](/cli/commands/graph#loops) · [`routing.control.commands`](/config/cli/routing-options#control-commands)

Each entry names a graph YAML you wrote. Your graph is compiled by the same code as the
shipped loops and held to the same rules:

- known hooks only — shipped, or `x-` hooks a
  [`routing.graph.hooks.modules`](/cli/hooks) entry
  registers;
- the-loop's phases only, because the `loop:<phase>` labels are one vocabulary for every
  repository;
- a well-formed `command:` per node, which may name another plugin's slash command as
  `plugin:command`.

A work item's recorded loop selects your graph **only while this list declares it**. Any
other name reads as the default loop. **A graph decides which gates a work item passes**,
so review it like code. `the-loop graph loops` lists every loop and checks that each of
yours compiles.

### `graphs[].name`

- **Type:** `string`, matching `^[a-z][a-z0-9-]*$`
- **Default:** none — required

The loop's name, recorded in `work-item-state.json` and named by
`routing.control.commands.<word>.graph`. It cannot be a shipped loop's name or start with
`pdlc-`, which is reserved for the loops the-loop ships. It must be unique across the list.

### `graphs[].path`

- **Type:** `string`
- **Default:** none — required

The graph YAML: absolute, `~/…`, or relative to the directory of **this** config file.
It is never resolved against a work item's checkout, so no session can edit the graph it
walks. A missing, unreadable or invalid file fails the load, naming the entry.

### `graphs[].guest`

- **Type:** `boolean`
- **Default:** `false`

Walk this graph as a **guest**, as the shipped contribution and review loops do. The spec
tree is kept out of the repository's git history, and `publish-artifact` posts the plan to
the thread. Set it on a graph that replaces `contribute` or `review`.

It sets the posture only. The session-prompt lines the-loop writes for its own
contribution and review loops ("this item has no outer loop", "change no code") belong to
those loops and are not applied. Say what your session must know in your graph's nodes and
slash commands.
