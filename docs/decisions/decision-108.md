# Decision 108: the env file is loaded by a stdlib parser, resolved against the config, and never overrides the environment

- **Status:** proposed
- **Date:** 2026-09-03
- **Work item:** [issue-318](https://github.com/MadaraUchiha-314/the-loop/issues/318)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (design)
- **Refines:** [decision-032](decision-032.md) (the CLI config is independent of any
  checkout), [decision-038](decision-038.md) (PyYAML is the CLI's one dependency)

## Context

Every credential the-loop uses is named in `cli-config.yaml` and read from the process
environment — the config never carries a value. That left the operator to export the
values by hand before `the-loop start`, in every terminal, or to wrap the command. The
owner asked for a `.env` file the config can name and the-loop loads at start.

Four things had to be chosen: *how* the file is parsed, *where* a relative path points,
*who wins* when the environment and the file disagree, and *when* it is read.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A stdlib parser (`the_loop.envfile`), not `python-dotenv`.** `NAME=value` lines, `#` comments, `export`, double quotes with five escapes, single quotes literal, unquoted trimmed with a trailing comment; no interpolation. | The CLI has one runtime dependency by decision (decision-038) and a second one for eighty lines is not a trade worth making; the subset an operator needs for tokens is small, and stating the grammar ourselves means the behaviour is the-loop's to document and test rather than a library's to change. |
| D2 | **A relative path resolves against the directory of the config file that names it; `~` expands.** | The config is found in four places — a flag, an env var, `./.the-loop/`, `~/.the-loop/` — two of them outside any checkout. "The file beside my config" reads the same from all four; "relative to wherever I ran the command" does not, and `state.root` already shows how a cwd-relative default surprises operators. |
| D3 | **The process environment wins.** A name already set is left alone; the file fills gaps. | A deliberately exported value must survive a config edit — anyone who can edit the config would otherwise be able to redirect a running operator's credential to a file of their choosing. It is also what every dotenv implementation defaults to, so nothing an operator brings from elsewhere is contradicted. |
| D4 | **Read once, at process start, by each entry point; never on reload.** `cli.main`, `daemon_entry.main` and `api/serve.main` each load it before their own work; children inherit and load again, idempotently. | The daemons hot-reload `cli-config.yaml`; a reload that could change the credentials a running process holds is a reload that can be used to swap them. A restart is the price, as it is for `service.host`. Each entry point loading independently means a systemd unit that runs `daemon_entry` directly gets the same variables as one `the-loop start` spawned. |
| D5 | **A missing or malformed file warns and loads what it can; it never stops the process.** | The config may be tracked in git while the file is per-machine (this repository's is): a checkout without the file must still run `the-loop --version` and `the-loop events`. Every credential-dependent feature already fails closed when its variable is absent, so a missing file degrades to exactly the 13.2.0 behaviour, and the warning says why. |

## Consequences

**Good.** One line of config replaces a shell ritual; every process the-loop runs sees
the same variables however it was started; the config still never carries a value; a
stale config, a missing file and a malformed line are each reported without stopping
anything.

**Costs, accepted.** No interpolation and no multi-line values (an operator with either
keeps their shell); a change to the file needs a restart; a world-readable file is
warned about, not refused, because the same values in a shell are as visible and a
refusal would push operators back to `export`.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Depend on `python-dotenv` | A second runtime dependency (decision-038) for a subset we can state in a page; its interpolation would also be a surface to document and defend |
| Resolve relative to the working directory | Wrong for `~/.the-loop/cli-config.yaml`, the common case, and a repeat of the `state.root` surprise |
| The file overrides the environment (`override=True`) | A config edit could redirect an exported credential; contradicts every dotenv default |
| Re-read on config reload | A reload could change a running process's credentials; the file is not the config |
| A `--env-file` flag / `$THE_LOOP_ENV_FILE` | The config already has both a flag and a variable to select *it*; a second pair for a file the config names is two more things to get wrong |
| Refuse to start on a missing file | Breaks `--version`, `migrate-config` and every checkout where the config is tracked and the file is per-machine |
