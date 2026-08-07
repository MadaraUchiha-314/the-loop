# Installing the CLI

## From PyPI

The distribution is published as **`the-loopy-one`** — the base name `the-loop` was already
taken. The import package and the console script keep the natural names
([decision-019](/decisions/decision-019)):

| | Name |
|---|---|
| PyPI distribution | `the-loopy-one` |
| Import package | `the_loop` |
| Console script | `the-loop` |

```bash
pip install the-loopy-one
the-loop --help
```

PyYAML comes with it. There is nothing else to add.

### Verify

```bash
the-loop --version
```

The version is derived from the installed package metadata, not a hardcoded string, so it
always reports what you actually have.

## Upgrading (and installing the plugin)

Once the CLI is on the machine it installs the rest of the-loop — and itself:

```bash
the-loop install            # the CLI + every harness on PATH (`claude`, `cursor-agent`)
the-loop upgrade            # move them all to the current release
the-loop upgrade --dry-run  # see the exact commands first
```

`upgrade` works out how the running copy was installed — `uv tool`, `pipx` or `pip` — and
uses that installer's upgrade command, so you do not have to remember which one you used.
A development checkout is reported and left alone. See
[`install`](/cli/commands/install) and [`upgrade`](/cli/commands/upgrade) for scopes and
outcomes.

## Extras

**There are none, by design.** Everything the CLI can do resolves from a single
`pip install the-loopy-one`: hosting the [control-plane service](/cli/commands/service)
and its MCP endpoint (`fastapi`, `uvicorn`, the official `mcp` SDK), reading YAML
config (`pyyaml`), and the [Slack `sdk` transport](/config/cli/integrations-options#slack-transport)
(`slack-sdk`). Extras were removed on owner review — *"it creates a nightmare when
installing"* — so there is nothing to remember and nothing that silently degrades
when it is missing.

The previously documented names still resolve as **empty, deprecated no-ops**:

```bash
pip install "the-loopy-one[service]"   # still works, adds nothing
pip install "the-loopy-one[slack]"     # still works, adds nothing
pip install "the-loopy-one[config]"    # still works, adds nothing
```

They are kept only so pinned install lines in existing scripts and Dockerfiles keep
resolving without pip's "does not provide the extra" warning. Do not use them in new
scripts.

::: tip Python 3.10 or newer
The official MCP SDK requires Python 3.10+, so the-loop does too. Python 3.9 reached
end of life in October 2025.
:::

## For local development

the-loop uses **uv**, its declared Python package manager. From the repository root:

```bash
uv sync                     # install the workspace (CLI + dev tooling) from uv.lock
uv run the-loop --help      # run it
```

Or install the package on its own with any PEP 517 installer:

```bash
uv pip install -e .          # or: pip install -e .
uv pip install -e ".[dev]"   # + pytest and commitizen
```

Run the tests from the repository root:

```bash
make test                   # or: uv run --project cli python -m pytest -q cli
```

## Releases

Releases are **automatic**. On merge to `main`, `.github/workflows/release.yml` runs
`cz bump` to derive the next version from the Conventional Commits / PR titles since the
last tag (`feat` → minor, `fix` → patch, `BREAKING CHANGE` → major), tags it, and publishes
to PyPI via Trusted Publishing (OIDC — no stored token). Merges carrying no `feat`, `fix`
or breaking change publish nothing. See
[decision-019](/decisions/decision-019) and
[release & publishing](/capabilities/release-publishing).

## What else you may need

The CLI shells out to a few tools rather than reimplementing them. None is required for
every command:

| Tool | Needed for |
|------|-----------|
| `gh`, authenticated | GitHub reads and writes — the poller, reactions, session announcements, control paper-trail comments. The daemon holds no token of its own. |
| `git` | Per-work-item [workspaces](/config/cli/routing-options#workspace-root). |
| `tmux` | Hosting every spawned session — **required** by `gh-webhook start` and `poll start`. See [interactive sessions](/capabilities/interactive-sessions). |
| `ttyd` | The optional [browser terminal](/config/cli/routing-options#webterminal-enabled). |
| `claude` / `cursor-agent` | Whichever harness you spawn sessions with. |

## Next

- **[Getting started](/cli/getting-started)** — a working setup in five steps.
