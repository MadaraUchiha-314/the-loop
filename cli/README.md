# the-loop CLI

A lightweight, **extensible** command-line companion to the the-loop plugin, written in
Python (stdlib-only core — zero runtime dependencies). Python is intentional: it leaves
room to add self-learning / ML capabilities later (mostly exposed as Python SDKs).

## Install

the-loop uses **uv** (its declared Python package manager). From the repo root:

```bash
uv sync                     # installs the workspace (this CLI + dev tooling) from uv.lock
uv run the-loop --help      # run the CLI
```

Or install this package on its own with any PEP 517 installer:

```bash
uv pip install -e .            # or: pip install -e .
uv pip install -e ".[config]"  # PyYAML, for reading .the-loop/config.yaml defaults
uv pip install -e ".[dev]"     # pytest + commitizen
```

This exposes the primary CLI: `the-loop`.

## Commands

### `gh-webhook` — GitHub webhook receiver

```bash
the-loop gh-webhook start [--host 127.0.0.1] [--port 8787] [--path /gh-webhook] \
                          [--pidfile .the-loop/gh-webhook.pid] \
                          [--secret-env THE_LOOP_GH_WEBHOOK_SECRET]
the-loop gh-webhook stop  [--pidfile .the-loop/gh-webhook.pid]
```

- Verifies the GitHub `X-Hub-Signature-256` HMAC when the secret env var is set
  (export `THE_LOOP_GH_WEBHOOK_SECRET=...`). The secret is read from the environment,
  never a flag, so it doesn't leak into process listings.
- `GET /health` returns `200 ok`.
- Defaults can come from `.the-loop/config.yaml` (`webhooks.ghWebhook`) when PyYAML is
  installed; flags always override.
- Receiving events and routing them to the agent harness is future work — this is the
  receiver scaffold the issue asks the CLI to provide.

### `scenarios` — query the Gherkin scenarios integration tests cover

```bash
the-loop scenarios [--root .] [--glob PATTERN ...] [--format table|markdown|json]
```

- Scans integration-test files for the Gherkin-syntax docstrings the-loop requires
  (`Feature:` / `Scenario:` / Given-When-Then, plus an optional `Requirement:` link to a
  `requirements.md`) and presents them as a table — so a coding-agent harness can answer
  "what scenarios are tested?" without running anything.
- Language-agnostic: Python docstrings, JS/TS block comments and Go comments all work.
- Globs come from `--glob` (repeatable), else `testing.integrationTestGlobs` in
  `.the-loop/config.yaml` (when PyYAML is installed), else built-in defaults covering
  common layouts.
- `--format markdown` emits a GitHub-flavoured table (for PR briefings); `--format json`
  is machine-readable (includes each scenario's steps and `file:line`).

## Adding a command (extensibility)

1. Create `the_loop/commands/<your_command>.py`.
2. Subclass `Command`, set `name`/`help`, implement `add_arguments` and `run`, and
   decorate the class with `@register`.
3. Import the module in `the_loop/commands/__init__.py`.

The CLI discovers registered commands automatically.

## Test

```bash
pytest        # from this directory
```
