# the-loop CLI

A lightweight, **extensible** command-line companion to the the-loop plugin, written in
Python (stdlib-only core — zero runtime dependencies). Python is intentional: it leaves
room to add self-learning / ML capabilities later (mostly exposed as Python SDKs).

## Install

From PyPI (published as **`the-loopy-one`** — the base name `the-loop` was taken; the
import package and CLI keep the natural `the_loop`/`the-loop`):

```bash
pip install the-loopy-one            # or: uv pip install the-loopy-one
pip install "the-loopy-one[config]"  # + PyYAML, for reading .the-loop/config.yaml defaults
the-loop --help
```

For local development the-loop uses **uv** (its declared Python package manager). From the
repo root:

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

This exposes the primary CLI: `the-loop`. Releases are **automatic**: on merge to `main`,
`.github/workflows/release.yml` runs `cz bump` to derive the next version from the
Conventional Commits / PR titles since the last tag (`feat` → minor, `fix` → patch,
`BREAKING CHANGE` → major), tags it, and publishes to PyPI via Trusted Publishing (OIDC —
no stored token). Merges with no `feat`/`fix`/breaking change publish nothing. See
`docs/decisions/decision-019.md`.

## Commands

### `gh-webhook` — GitHub webhook receiver

```bash
the-loop gh-webhook start [--host 127.0.0.1] [--port 8787] [--path /gh-webhook] \
                          [--pidfile .the-loop/gh-webhook.pid] \
                          [--secret-env THE_LOOP_GH_WEBHOOK_SECRET] \
                          [--route | --no-route]
the-loop gh-webhook stop  [--pidfile .the-loop/gh-webhook.pid]
```

- Verifies the GitHub `X-Hub-Signature-256` HMAC when the secret env var is set
  (export `THE_LOOP_GH_WEBHOOK_SECRET=...`). The secret is read from the environment,
  never a flag, so it doesn't leak into process listings.
- `GET /health` returns `200 ok`.
- Defaults can come from `.the-loop/config.yaml` (`webhooks.ghWebhook`) when PyYAML is
  installed; flags always override.
- **`--route`** (default from `webhooks.ghWebhook.routing.enabled`) routes each verified
  event to the registered harness session working that item: the router extracts the
  work item(s) from the payload (issue/PR number, PR head-branch `issue-<n>` convention,
  closing keywords, `workflow_run`/`check_*` PRs), deduplicates on `X-GitHub-Delivery`,
  and the dispatcher resumes the matched session via its official CLI
  (`claude -p … --resume <session-id>` / `cursor-agent -p … --resume <chat-id>`), one
  event at a time per session, in parallel across sessions. Unmatched events follow
  `routing.spawnOnUnmatched` (`never` drops; `always` spawns + registers a session).
  Design: `docs/specs/issue-15/design.md`, `docs/decisions/decision-016.md`.

### `sessions` — link work items to harness sessions (webhook routing)

```bash
the-loop sessions register --work-item github:OWNER/REPO#N --harness claude \
    --harness-session-id "$CLAUDE_SESSION_ID" [--cwd .] [--force]
the-loop sessions list  [--status active|closed] [--format table|json]
the-loop sessions close --work-item github:OWNER/REPO#N
```

- The registry lives in `webhooks.ghWebhook.routing.registryDir` (default
  `.the-loop/sessions/`, git-ignored) as one human-inspectable JSON file per session;
  writes are atomic, so concurrent sessions on the same machine are safe.
- One work item ↔ one active session; `--force` replaces a stale registration.
- Claude Code sessions register with `$CLAUDE_SESSION_ID`; Cursor sessions register
  with the chat id they were launched with (non-interactive `cursor-agent ls` is
  unreliable for id discovery, so the id is captured at registration time).
- When a work item's PR is merged or closed, the receiver **auto-closes** the session
  (on the `pull_request` `closed` event) — no manual `sessions close` needed.

**Label-gated auto-execution** (`spawnOnUnmatched: labeled`): give an issue/PR the
configurable `routing.autoExecuteLabel` (default `the-loop: auto-execute`) and the
receiver spawns a session and starts `/the-loop:work-on` on it — then routes that item's
later activity (comments, reviews, CI, its linked PR) to the same session, and
auto-closes on PR merge. Label presence is read straight from the webhook payload (no
extra API call). A new issue *without* the label is received and ignored.

### `poll` — pull ingress (provider-agnostic) when a webhook can't reach you

```bash
the-loop poll start [--interval 60] [--once] \
                    [--state-file .the-loop/poll-state.json] \
                    [--pidfile .the-loop/poll.pid]
the-loop poll stop  [--pidfile .the-loop/poll.pid]
```

A **pull-based** alternative to `gh-webhook` for hosts a webhook cannot reach (behind
NAT/a firewall, a laptop, unreachable infra). Every `--interval` seconds it asks each
configured **provider** for the label-gated work items in its scope and drives them
through the **same** routing/dispatch/session stack the webhook receiver uses — so
spawning, one-session-per-work-item, the `tmux` runner, harness adapters and prompt
templates are all reused unchanged.

- **Provider-agnostic:** the poller core and CLI carry no GitHub knobs. Which systems
  are polled is defined purely by `polling.sources` in `.the-loop/config.yaml` — each
  entry names a `provider` (GitHub ships; the seam admits others). GitHub is reached
  *only* through a configured source:

  ```yaml
  polling:
    intervalSeconds: 60
    sources:
      - provider: github
        repos: [octo/repo]         # empty = fall back to ticketing.github
        monitor: { issues: true, pullRequests: true }
        label: ""                  # empty = reuse routing.autoExecuteLabel
  ```

- **Label-gated:** only items carrying the configured label are polled. A source's
  `label` defaults to `webhooks.ghWebhook.routing.autoExecuteLabel`, so one label drives
  both ingresses.
- **No duplicate sessions:** a session is spawned for a labelled item only when the
  registry has none; a live session is never doubled (the registry is the source of
  truth), so a work item maps to exactly one session — the same one on later polls.
- **Spawns tmux sessions** when `webhooks.ghWebhook.routing.runner: tmux` — attach with
  `the-loop sessions attach --work-item github:OWNER/REPO#N` (issue-32).
- **New comments** are forwarded to the item's session exactly once, deduped across
  polls **and restarts** via `--state-file` (git-ignored runtime state). The pre-existing
  thread is baselined on first sight, not replayed.
- **Config:** ingress defaults come from `polling` in `.the-loop/config.yaml` (when
  PyYAML is installed); dispatch behaviour is reused from `webhooks.ghWebhook.routing`.
  Flags cover only the run loop.
- **Hot reload:** edit `polling.sources` / `intervalSeconds` while it runs and the change
  is picked up on the next cycle — no restart. An invalid edit is logged and the previous
  config kept. (The shared dispatch config still needs a restart.)
- **`--once`** runs a single cycle and exits (for a cron/systemd timer); otherwise it
  loops until `poll stop` (or SIGINT/SIGTERM), writing a pidfile like the receiver.
  Design: `docs/specs/issue-34/design.md`, `docs/decisions/decision-022.md`.

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
