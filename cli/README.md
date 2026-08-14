# the-loop CLI

A lightweight, **extensible** command-line companion to
[the-loop](https://github.com/MadaraUchiha-314/the-loop) — an opinionated
product-development-lifecycle harness shipped as a Claude Code and Cursor plugin.

The plugin is the operating model an agent follows inside a session. This CLI is what
**starts those sessions, keeps them attached to work items, and tells you what happened**:
a GitHub webhook receiver and a poller that turn ticket activity into agent runs, a session
registry, execution control, a structured event log, and repo-scoped commands for the
process graph, critic rounds and test-scenario discovery.

Written in Python with **one runtime dependency**, PyYAML — its whole configuration is YAML,
so reading it is not optional — and stdlib otherwise. Python is intentional: it leaves room
to add self-learning / ML capabilities later, which are mostly exposed as Python SDKs.

## Install

Published to PyPI as **`the-loopy-one`** — the base name `the-loop` was taken. The import
package and the console script keep the natural `the_loop` / `the-loop`:

```bash
pip install the-loopy-one   # PyYAML comes with it — nothing else to add
the-loop --help
```

From there the CLI installs the rest of the-loop — and upgrades itself:

```bash
the-loop install            # this CLI + the Claude Code plugin (Cursor: issue #157)
the-loop upgrade            # move both to the current release
the-loop install claude --scope project --project-dir .   # one repository only
```

`upgrade` uses the installer that owns the copy you are running (`uv tool`, `pipx`,
`pip`), and `--dry-run` prints the exact commands first.

No extras: one `pip install the-loopy-one` brings everything, including hosting the
control-plane service and its MCP endpoint. (`[service]`, `[slack]` and `[config]` are
deprecated no-ops, kept so pinned install lines keep resolving.) Needs Python 3.10+.

## In one minute

```bash
# 1. Tell the daemon who may drive it, in ~/.the-loop/cli-config.yaml
#      routing.authorizedUsers: ["your-github-login"]
#      polling.enabled: true    # polling needs no inbound networking
#      polling.sources: [{ provider: github, repos: ["your-org/your-repo"] }]

# 2. Bring the-loop up: starts every service the config enables — here the
#    control-plane service and the poller — detached, logging under .the-loop/logs/.
the-loop start

# 3. Label a GitHub issue "the-loop: auto-execute", then comment:
#      the-loop start

# 4. Watch
the-loop status             # per-service liveness + the poller's last cycle (exit 0/1)
the-loop sessions list
the-loop events --follow
```

## Documentation

Full docs at **<https://madarauchiha-314.github.io/the-loop/cli/>**:

| | |
|---|---|
| [Overview](https://madarauchiha-314.github.io/the-loop/cli/) | What the CLI is, and when you need it |
| [Installation](https://madarauchiha-314.github.io/the-loop/cli/installation) | PyPI, uv, extras, what else to have on `PATH` |
| [Getting started](https://madarauchiha-314.github.io/the-loop/cli/getting-started) | Zero to an auto-executing work item, in five steps |
| [Concepts](https://madarauchiha-314.github.io/the-loop/cli/concepts) | Ingress, sessions, guards, workspaces, the process graph |
| [Commands](https://madarauchiha-314.github.io/the-loop/cli/commands/) | `gh-webhook` · `poll` · `sessions` · `events` · `check` · `graph` · `critic` · `scenarios` · `instructions` · `install` · `upgrade` · `migrate-config` |
| [Configuration](https://madarauchiha-314.github.io/the-loop/config/cli/) | Every option, by area, with types and defaults |
| [Adding a command](https://madarauchiha-314.github.io/the-loop/cli/extending) | The `Command` / `@register` contract |

> **Two config files, and they never overlap.** The CLI daemon reads `cli-config.yaml`
> (yours, machine-scoped, resolved via `--config` → `$THE_LOOP_CLI_CONFIG` →
> `./.the-loop/cli-config.yaml` → `~/.the-loop/cli-config.yaml`). A repository's
> `.the-loop/harness-config.yaml` is the *plugin* config and is never read by the daemon —
> including `authorizedUsers` and a poll source's `repos`, which have no fallback and fail
> closed when unset. See
> [Configuring the-loop](https://madarauchiha-314.github.io/the-loop/config/).

## Development

the-loop uses **uv**. From the repository root:

```bash
uv sync                     # install the workspace from uv.lock
uv run the-loop --help
make test                   # pytest
make check                  # ruff · pyright · schema validation · pytest
```

Releases are automatic: on merge to `main`, `cz bump` derives the next version from the
Conventional Commits since the last tag and publishes to PyPI via Trusted Publishing
(OIDC — no stored token).

## License

MIT.
