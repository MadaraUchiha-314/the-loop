# the-loop CLI

`the-loop` is a lightweight, extensible command-line companion to the
[the-loop plugin](/guide/what-is-the-loop). The plugin is the operating model an agent
follows inside a session; the CLI is what **starts those sessions, keeps them attached to
work items, and tells you what happened**.

```bash
pip install the-loopy-one
the-loop --help
```

## You do not need it

Worth saying plainly, because "there is a CLI" reads like a prerequisite. It is not. Run
`/the-loop:work-on <ticket>` in Claude Code or Cursor and the whole loop works with no CLI
installed at all.

You want the CLI when you stop driving the loop by hand:

| You want to… | Use |
|---|---|
| Have a comment on a GitHub issue start an agent, unattended | [`start`](/cli/commands/start) with the [webhook receiver](/cli/commands/gh-webhook) or [polling](/config/cli/polling-options) enabled |
| Keep one session per work item and route later activity to it | [`sessions`](/cli/commands/sessions) |
| Watch an agent work, live, and type into it | [`sessions attach`](/cli/commands/sessions) |
| Answer "why did nothing happen?" | [`events`](/cli/commands/events) |
| Gate CI on a work item's own phase rules | [`check`](/cli/commands/check) |
| Hand a review round to a *different* model | [`critic`](/cli/commands/critic) |

## What it is

A Python package — import package `the_loop`, console script `the-loop`, published to PyPI
as [`the-loopy-one`](https://pypi.org/project/the-loopy-one/) — with an extensible command
registry.

- **One runtime dependency**, PyYAML. Its whole configuration is YAML, so reading it is
  not optional ([decision-038](/decisions/decision-038)); everything else is stdlib.
- **Python is deliberate.** It leaves room to add self-learning / ML capabilities later,
  which are mostly exposed as Python SDKs.
- **Extensible by design.** Commands are discovered from a registry — see
  [adding a command](/cli/extending).

## Two halves

Some commands are **daemons**: long-running, machine-scoped, watching several repositories
at once. Others are **repo-scoped**: they run once, inside a checkout. Worth knowing which
is which, because it decides what you have to configure to run them — a daemon needs a
`cli-config.yaml`, a repo-scoped command needs nothing but the checkout.

```mermaid
graph TD
  CFG["cli-config.yaml<br/><i>your machine</i>"]
  subgraph D["Daemon commands"]
    GW["gh-webhook<br/>push ingress"]
    PO["poller<br/>pull ingress (via start)"]
    SE["sessions<br/>registry + control"]
    EV["events<br/>the trail"]
  end
  subgraph R["Repo-scoped commands"]
    CH["check"]
    GR["graph"]
    CR["critic"]
    SC["scenarios"]
  end
  HC["the work item's checkout<br/>.the-loop/harness-config.yaml"]
  MC["migrate-config<br/>upgrades cli-config.yaml"]
  CFG --> D
  CFG --> MC
  D -->|"phase label, specDir,<br/>notifications"| HC
  R --> HC
```

Note the one arrow people expect to be missing: the daemon reads a **work item's own
checkout** too, for the values that repository declares about itself. What it never does
is take its *own* settings from a repository. That direction rule is
[decision-044](/decisions/decision-044); the split into two files is
[decision-032](/decisions/decision-032), and both files are explained in
[Configuring the-loop](/config/).

## Next

- **[Installation](/cli/installation)** — get it on your machine.
- **[Getting started](/cli/getting-started)** — from nothing to a work item an agent picks
  up by itself.
- **[Concepts](/cli/concepts)** — the model the command pages assume.
- **[State on disk](/cli/state)** — what it writes, what is inside, and what you can carry
  to another machine.
- **[Commands](/cli/commands/)** — the full reference.
