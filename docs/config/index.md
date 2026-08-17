# Configuring the-loop

the-loop reads **two** configuration files. They never share a key, and knowing which one
you want is the whole trick:

| | [Harness config](/config/harness-config) | [CLI config](/config/cli/) |
|---|---|---|
| **File** | `.the-loop/harness-config.yaml` | `cli-config.yaml` |
| **Installed** | **per repository**, by `/the-loop:init` | **per operator**, wherever you keep it |
| **Read by** | the `/the-loop:*` commands and the operating skill — the agent doing the work | the CLI daemon: `gh-webhook`, `poll`, `sessions`, `events` |
| **Governs** | *how work is done here* — ticketing, phases, tooling, reviews, autonomy, security | *how work is triggered and hosted* — ingress, routing, sessions, integrations, logging |
| **Schema** | `harness-config.schema.json` | `cli-config.schema.json` |
| **Where the schema lives** | [with the plugin](#where-the-schemas-live), never copied into your repo | [with the plugin](#where-the-schemas-live), never copied into your repo |
| **Committed?** | yes — it is a statement about the project | usually not; it describes *your machine* |

The split is deliberate ([decision-032](/decisions/decision-032)). The daemon is expected
to watch **several** repositories at once, so tying its settings to any one checkout would
mean the same operator maintaining N copies of their own webhook port. Conversely, "this
project requires three critic rounds" is a property of the project, not of whoever happens
to be running the daemon today.

::: warning A repository never configures the daemon
The rule runs in **one direction** ([decision-044](/decisions/decision-044)): a
repository's harness config configures work done *on that repository*, and never the
daemon itself. The two settings people most expect to be inherited —
`routing.authorizedUsers` (who may trigger it) and a poll source's `repos` (what it
watches) — are **CLI-config-only**, with no fallback. Set them explicitly, or the daemon
fails closed and does nothing.
:::

## Which one am I editing?

```mermaid
graph TD
  Q{"What are you changing?"}
  Q -->|"phases, specs, reviews,<br/>autonomy, tooling, security"| H["<b>harness config</b><br/>.the-loop/harness-config.yaml<br/>in the repo"]
  Q -->|"webhook port, polling,<br/>who may trigger,<br/>event log, GitHub/Slack transport"| C["<b>CLI config</b><br/>cli-config.yaml<br/>on your machine"]
  H --> H2["written by <code>/the-loop:init</code>"]
  C --> C2["copied from<br/>skills/the-loop/templates/cli-config.yaml"]
```

The picture is not "daemons read one file, other commands read the other" — it is the
direction. Anything the-loop does **to a repository** is configured by that repository:

- `the-loop check` and `the-loop graph` read the repo's `workflow` and process graph.
- `the-loop scenarios` reads the repo's `testing.integrationTestGlobs`.
- `the-loop critic` reads the repo's `reviews.critics[]`.
- **The daemon does too**, for the work item's *own* checkout: the graph coupling reads
  `workflow.phaseLabelPrefix`, `workflow.specDir` and `notifications` from there, after
  proving via the checkout's `origin` remote that it really is that repository's. It has
  to — the `loop:<phase>` label it writes is named by the repository, and a daemon
  watching several cannot know the name for each without asking.

What never happens is the reverse: no checkout supplies the daemon's *own* settings. The
full list of keys the CLI reads from a repository is in
[the harness config reference](/config/harness-config#what-the-cli-reads-from-it).

## Where the schemas live

**With the plugin, not with your repository.** the-loop's three JSON schemas —
`harness-config.schema.json`, `collaborators.schema.json` and `cli-config.schema.json` —
ship inside the installed plugin at `${CLAUDE_PLUGIN_ROOT}/.the-loop/`, declared once as
`schemasDir` in `.the-loop/manifest.yaml`. `/the-loop:init` and
`/the-loop:upgrade-the-loop` read them from there to validate what they write, and
`/the-loop:upgrade-the-loop` **deletes** the copies older versions used to leave behind
(up to 118 KB of the-loop's internals per repository — [issue #220](https://github.com/MadaraUchiha-314/the-loop/issues/220)).

Your editor is not left out. Every config the-loop scaffolds opens with a modeline:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/MadaraUchiha-314/the-loop/main/.the-loop/harness-config.schema.json
```

It is a comment, and only the *editor* ever reads it — the-loop always validates against
the installed plugin's schema on disk, so it works offline and cannot be redirected by
editing that line. It has to stay on the **first line** to work at all; delete it if you
prefer, and you lose completion while typing, nothing else.

## Reference

- **[Harness config](/config/harness-config)** — every section of
  `.the-loop/harness-config.yaml`, plus the two files beside it
  (`collaborators.yaml`, `manifest.yaml`).
- **[CLI config](/config/cli/)** — how the file is found and versioned, then the options
  by area:
  [webhook](/config/cli/webhook-options) ·
  [routing](/config/cli/routing-options) ·
  [polling](/config/cli/polling-options) ·
  [integrations](/config/cli/integrations-options) ·
  [channels](/config/cli/channels-options) ·
  [observability](/config/cli/observability-options).

Every CLI-config option on those pages is checked against
`cli-config.schema.json` by a test in the repository, in **both** directions: an
option documented here that the schema does not define fails the build, and so does a
schema key nobody documented.
