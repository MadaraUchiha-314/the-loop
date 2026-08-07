# `install`

Put the-loop on a machine: the **CLI** and the plugin, in **Claude Code**, **Cursor** or
both, at user or project scope.

```bash
the-loop install [COMPONENT ...] [--scope user|project] [--project-dir .]
                 [--from owner/repo] [--dry-run] [--format table|json]
```

```text
$ the-loop install --dry-run
the-loop install · components: cli, claude, cursor · scope: user · marketplace: MadaraUchiha-314/the-loop · dry run
Component  Outcome  Step                                            Command / file
---------  -------  ----------------------------------------------  --------------------------------------------------------
cli        planned  install the the-loopy-one CLI                   /usr/bin/uv tool install the-loopy-one
claude     planned  register the the-loop marketplace (…/the-loop)  claude plugin marketplace add MadaraUchiha-314/the-loop …
claude     planned  install the-loop@the-loop                       claude plugin install the-loop@the-loop --scope user
cursor     planned  clone …/the-loop into ~/.cursor/plugins/…       /usr/bin/git clone -- https://github.com/…/the-loop.git …
```

Components are `cli`, `claude`, `cursor`, or `all`. **Naming none** means the CLI plus
every harness actually found on `PATH` — the useful default when setting a machine up.

> This installs **software**. Scaffolding a repository is
> [`/the-loop:init`](/reference/commands), and reconciling a project's the-loop files with
> a newer plugin is `/the-loop:upgrade-the-loop`. Different jobs, deliberately different
> commands.

## It plans, then executes

Every run builds an ordered plan of steps and prints the exact argv (or the file path) of
each one, then executes it. `--dry-run` is the same plan with the execution left out —
not a separate code path that could drift from the real one — so a preview shows the
skips too.

Each step reports one outcome:

| Outcome | Meaning |
|---------|---------|
| `applied` | It ran, or the file was written. |
| `already` | The desired state already held; nothing was run or rewritten. |
| `skipped` | A precondition is missing — the reason is printed, and so is the manual way. |
| `failed` | It ran and returned an error (exit code and the last line of its output). |
| `planned` | `--dry-run` only: this is what would happen. |

Only `failed` makes the process exit non-zero. A `skipped` component is a reported gap,
not a failure, and it never stops the other components.

## What happens per component

### `claude` — the harness's own installer

the-loop does not re-implement a harness's plugin manager. It **asks the binary** what it
supports (`claude plugin --help`, then `plugin install --help` — which must work, since
that is the command actually driven — and whether it lists a `--scope` flag) and uses that
surface:

```bash
claude plugin marketplace add MadaraUchiha-314/the-loop --scope user
claude plugin install the-loop@the-loop --scope user
```

If `claude` is missing, or exposes no usable plugin surface, it falls back to the route
this project already documents — never to a guess: the two settings keys
`/plugin marketplace add` + `/plugin install` write,
`extraKnownMarketplaces["the-loop"]` and `enabledPlugins["the-loop@the-loop"]`, in
`<config dir>/settings.json` (user scope) or `<project>/.claude/settings.json` (project
scope). Same non-destructive writer the daemon uses for
[`routing.harnessPlugins`](/config/cli/routing-options): merged into what is there, atomic
replace, nothing written when the state already holds, an unparseable file reported rather
than overwritten.

A binary that offers `plugin marketplace` but no working `plugin install` counts as **no
surface**, and takes the fallback — running an install that cannot work would report
`failed` for what is really an absent feature.

### `cursor` — the same probe, a different fallback

Cursor is asked the same question in the same way (`cursor-agent plugin --help`, then
`plugin install --help`). **Which of the two routes runs on your machine is decided by
that answer**, so `--dry-run` tells you before anything happens:

| What `cursor-agent` reports | What runs |
|---|---|
| a plugin surface with `--scope` | `cursor-agent plugin marketplace add …` + `plugin install …`, with your scope passed through |
| a plugin surface without `--scope` | the same two commands at user scope; `--scope project` is **skipped** |
| `plugin marketplace` but no working `plugin install` | the fallback below |
| no `cursor-agent` on `PATH`, or the probe fails | the fallback below |

**The fallback is the local checkout the [installation guide](/guide/installation) already
prints** — nothing invented:

```bash
git clone -- https://github.com/MadaraUchiha-314/the-loop.git ~/.cursor/plugins/local/the-loop
```

| Situation | Outcome |
|---|---|
| the directory does not exist, `install` | `applied` — cloned |
| the directory is already a checkout, `install` | `already` — nothing run, nothing written |
| the directory is already a checkout, `upgrade` | `applied` — `git -C … pull --ff-only` |
| the directory does not exist, `upgrade` | `skipped` — "run `the-loop install cursor` first"; an upgrade never becomes an install |
| the directory exists but is **not** a checkout | `skipped` — naming the path; nothing there is deleted, overwritten or written into |
| `git` is not on `PATH` | `skipped` — with the command above, to run by hand |

`--ff-only` is deliberate: this is also the route the guide calls *"locally, for
development"*, so a clone you have committed on reports `failed` with git's own message
rather than acquiring a merge commit the-loop invented.

**Project scope has no Cursor mechanism today**, so `--scope project` is reported
`skipped` with the manual instruction (`/add-plugin` in that workspace). It is not
permanent: the moment `cursor-agent` reports a `--scope` flag, the probe passes yours
straight through.

The clone route assumes the marketplace repository **is** the-loop (or a fork of it) —
that is the only shape `--from` is meant to take, since Cursor loads the checkout as a
plugin from its root manifest. The resolved repository is printed in the plan header
before anything is fetched.

### `cli` — the-loopy-one from PyPI

The installer is read off the copy you are running rather than asked for as a flag:

| Where the running package lives | What runs |
|---|---|
| a source checkout (`cli/pyproject.toml` beside it) | **skipped** — `git pull` there instead |
| `…/uv/tools/…` | `uv tool install the-loopy-one` |
| `…/pipx/…` | `pipx install the-loopy-one` |
| anything else | `<python> -m pip install the-loopy-one` |

At `--scope project` the CLI is installed into the **project's virtualenv**
(`<project-dir>/.venv`); if the project has none, the step is skipped with the reason.
It deliberately does not run `uv add` — installing a tool must not rewrite your
`pyproject.toml`.

## Scope

| | `--scope user` (default) | `--scope project` |
|---|---|---|
| Claude Code | the harness's user scope / `<config dir>/settings.json` | the harness's project scope, run in `--project-dir` / that repo's `.claude/settings.json` |
| Cursor | the harness's user scope / `~/.cursor/plugins/local/the-loop` | the harness's project scope if `cursor-agent` expresses one — otherwise **skipped** |
| CLI | `uv tool` / `pipx` / `pip` | the project's `.venv` |

A scope that cannot be expressed is **skipped, never widened** — an install asked for one
repository never quietly becomes a machine-wide one.

## Where the plugin comes from

`--from owner/repo` → the CLI config's
[`routing.harnessPlugins.marketplaceRepo`](/config/cli/routing-options) → the shipped
default `MadaraUchiha-314/the-loop`. One source of truth with the daemon: point that key
at your fork and every path — spawn and install alike — follows it.

Installing a plugin means running whatever that repository ships, in every session at
that scope. So the value is validated as `owner/repo` **before** it can reach a command
line, a URL or a settings file (anything else exits `2` and touches nothing), it is
printed in the plan header before anything is trusted, and every step is executed as an
argv list with no shell.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| *(positional)* | `cli` + detected harnesses | `cli`, `claude`, `cursor`, `all` |
| `--scope` | `user` | `user` or `project` |
| `--project-dir` | `.` | The project for `--scope project` |
| `--from` | config, else `MadaraUchiha-314/the-loop` | Marketplace `owner/repo` |
| `--dry-run` | off | Print the plan; change nothing |
| `--format` | `table` | `table` or `json` |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Every step `applied`, `already` or `skipped` |
| `1` | At least one step `failed` |
| `2` | Could not run — an unknown component, or a marketplace value that is not `owner/repo` |

## See also

- [`upgrade`](/cli/commands/upgrade) — the same plan, moving what is installed forward.
- [Installing the CLI](/cli/installation) · [Installing the-loop](/guide/installation)
- [decision-057](/decisions/decision-057) — why the harness's own installer, and why the
  Claude fallback is exactly that one.
- [decision-064](/decisions/decision-064) — why Cursor came back, and why its fallback is
  a clone.
