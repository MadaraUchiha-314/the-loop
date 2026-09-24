<!-- Written per the `the-loop:writing` skill. -->

# Decision 136: an operator declares graphs of their own in the CLI config; a command selects one by name, and a new command is `start` with a loop

- **Status:** proposed
- **Date:** 2026-09-23
- **Work item:** [issue-343](https://github.com/MadaraUchiha-314/the-loop/issues/343)
- **Deciders:** MadaraUchiha-314 (the ask, on the ticket: *"Users of the-loop should be
  able to provide their own graphs (yamls) and override existing commands to use that
  graph or provide new commands that use that graph"*); the-loop (design)
- **Refines:** [decision-041](decision-041.md) and [decision-042](decision-042.md) (the
  graph is declarative so user-defined graphs could arrive later — this is that arrival),
  [decision-096](decision-096.md) (hooks of the operator's own — the other half of the
  same deferral), [decision-123](decision-123.md) (what runs in the-loop's process is the
  operator's; the phase labels are one fixed vocabulary)
- **Spec:** `docs/specs/issue-343/`

## Context

The process has been data since issue-109, with *"user-defined graphs and user-authored
hooks"* deferred on the stated grounds that the declarative form and the registry exist so
they can arrive safely. issue-248 delivered the hooks. Graphs stayed the-loop's: five
shipped loops, four fixed arming words choosing between them, and a repository's
`.the-loop/*.yaml` ignored with a warning. The ticket asks for the rest — a graph the user
writes, reachable from an existing command or a new one.

Three questions decide the shape: where the declaration lives, what a new command *is* to
the control plane, and how much of the shipped rules a custom graph must keep.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The declaration is the operator's CLI config, in two parts.** Which graphs exist is the top-level `graphs[]` — `name`, `path`, optional `guest`. Which command selects which graph is `routing.control.commands` — `<word>: {graph, keyword?}`, where `graph` is a shipped outer-path loop or a declared one. A command with no entry keeps its shipped loop. A relative `path` resolves against the config file's directory, never against a checkout. | decision-123 D7/D8: what runs in the-loop's process is decided on the operator's machine. A graph file in the checkout would also be **agent-writable** — the session could rewrite the gates of the graph it walks. The split is the owner's (PR #425 review): a graph is a top-level fact like `critics[]`, and the command vocabulary already lives in `routing.control`. It also lets a command be re-pointed at another *shipped* loop without declaring anything. |
| D2 | **A new command is `start` with a loop attached.** The parser reports `command=start, loop=<graph>`; an overridden arming command reports itself with a loop. The loop is recorded on the control record (`loop`) and read by the graph coupling before the command. | Every seam that branches on `start` — authorization, spawn policy, arming, disarming, `start_requested` — keeps working with no edits, and `ControlStore` needs no config to answer whether an item is armed. Recording the loop also freezes an override against a config edit between arming and spawn. |
| D3 | **Only arming spawn commands can be overridden** (`start`, `contribute`, `do`, `review`); `stop`, `pause`, `resume`, `execute`, `cleanup` and the argument commands are refused. A new word's keyword is its `keyword`, else `the-loop <word>`. | Those commands do not select a loop; binding one would change what it means. A built-in command's keyword stays in `routing.control.keywords`, so each keyword has one home. |
| D4 | **Selection fails closed to the declaration.** `resolve_outer_loop(name, declared)` accepts a custom name only while the operator declares it; the state file's and the control record's `loop` both go through it. | The state file is agent-writable (issue-185). The set of selectable loops grows only by what the operator writes down. |
| D5 | **A custom graph is held to the shipped rules**: the same compiler, shipped hooks or the operator's `x-` hooks, the shipped phase vocabulary (`PHASE_VOCABULARY`), and a slash-command grammar on `command:` (a namespaced `plugin:command` renders as `/plugin:command`). | One label vocabulary for every repository (decision-123 D3); a mistake fails at load, not mid-walk; the text a session is told to run is always one token. |
| D6 | **`pdlc-` is reserved** for shipped loops. | The next shipped loop can never collide with a graph an operator already runs. |
| D7 | **Attachments may be scoped to loops** (`attach[].loops`). Unscoped keeps today's behaviour, including failing a load whose graph lacks the node. | Without it, an attachment on `design` would make every custom graph without a `design` node fail to load; silently skipping instead would turn a typo into a check that never runs. |
| D8 | **`the-loop graph loops`** lists every loop with its commands and compiles each custom graph without importing a module. | The operator finds a mistake before a ticket does, and reads what would run before running it — the stance `graph hooks` already takes. |

## Consequences

**Good.** A team's process can be executed rather than described: `the-loop triage` walks
a triage graph, `the-loop do` walks the team's quick loop, and the dashboards built on the
`loop:<phase>` labels keep working. No existing behaviour changes for an operator who
declares nothing.

**Costs.** A custom graph may omit gates the shipped loops have — phase selection,
approvals, reviews. That is the feature, and it is the operator's choice on the operator's
machine, as choosing critics and hooks already is; it is stated in the schema and the docs
as executable configuration to review like code. Removing or renaming a graph while a work
item walks it reads that item as the default loop — the operator is told to remove a graph
only when nothing walks it. A CI job without the operator's config sees a custom item as
the default loop.

**What it does not change.** The shipped loops, the inner pull-request loop (not
replaceable), repository graph files (still ignored, now with a pointer to the supported
way), the hook API, and the keywords of the built-in commands.

## Alternatives considered

- **Graphs in the repository** (`.the-loop/graphs/`). Rejected: the CLI reads no
  repository configuration (decision-123), and a checked-out graph is one the session
  could edit.
- **New commands as new entries in `COMMANDS`.** Rejected: every constant set
  (`SPAWN_COMMANDS`, the arming set) and `ControlStore` would need the operator's config
  to answer questions they answer today from constants.
- **Free-form phases.** Rejected: a phase is a label, and the label vocabulary is fixed
  so dashboards work across repositories.
- **Silently skip attachments whose node a graph lacks.** Rejected: a typo'd node would
  become a check that never runs — the failure issue-248 exists to prevent.
