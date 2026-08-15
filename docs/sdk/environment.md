# Environment expectations

the-loop drives other people's programs. It spawns a harness CLI inside `tmux`, it reads and
writes tickets through `gh`, it clones with `git`. None of that is a Python dependency, so
none of it arrives with `pip install the-loopy-one` — and a container image that is missing
one finds out at the first dispatch, in production.

This page is the contract. `loop.check_environment()` is the same contract, executable.

## The contract

| Binary | Renamed by | Required when | What it serves |
|--------|-----------|---------------|----------------|
| `gh` | [`integrations.github.cli.binary`](/config/cli/integrations-options) | `routing.enabled`, `polling.enabled` or `webhooks.ghWebhook.enabled` | GitHub ticket reads and writes: comments and the paper trail, reactions, announcements, polling, and the process graph's GitHub integration |
| `claude` | — | `routing.enabled` and `routing.defaultHarness: claude` (the default) | spawning, resuming and one-shot critic runs of Claude Code sessions |
| `cursor-agent` | — | `routing.enabled` and `routing.defaultHarness: cursor` | the same, for Cursor |
| `tmux` | — | `routing.enabled` | hosting harness sessions — the only runner since issue-156, and what makes a session attachable |
| `git` | [`routing.workspace.gitBinary`](/config/cli/routing-options) | `routing.enabled` | cloning and worktree checkouts for spawned sessions |
| `ttyd` | — | `routing.webTerminal.enabled` | serving tmux sessions to a browser (the web terminal) |

Two readings of that table are worth stating plainly.

**Nothing is required unconditionally.** `routing.enabled` defaults to **false** — verify
and log only — so a service that mounts the-loop to *read* work items, events and session
state needs none of these binaries. Turning routing on is what makes four of them
load-bearing at once.

**`gh` is the one an operator renames.** Enterprise installs and wrapper scripts are common,
so the check resolves whatever `integrations.github.cli.binary` names rather than the literal
`gh`.

## Checking it

```python
report = loop.check_environment()
if not report["ok"]:
    missing = [c["binary"] for c in report["checks"] if c["required"] and not c["present"]]
    raise SystemExit(f"the-loop cannot run here: missing {', '.join(missing)}")
```

```jsonc
{
  "ok": false,
  "checks": [
    {
      "binary": "gh",
      "present": false,
      "path": "",
      "required": true,
      "capability": "GitHub ticket reads and writes: …",
      "configKey": "integrations.github.cli.binary"
    },
    // … one per row of the table above, in that order
  ]
}
```

`ok` is false only when a binary *this configuration requires* is absent. An optional one
missing is a fact worth reporting, not a failure.

Two properties are deliberate:

- **It resolves, it does not execute.** `shutil.which` and nothing more. A preflight that
  runs `--version` on whatever a hostile `PATH` yields is a way to become the vulnerability
  it is checking for.
- **It is a report, never a gate.** Nothing here blocks a call. A missing binary keeps
  failing exactly where it fails today, reported by the code that needed it. Assert on it
  at startup if you want a hard failure — that is your policy to set, and one line.

## Putting them in an image

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git tmux ca-certificates curl gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
         -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
         https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# The harness CLI: Claude Code (npm) or cursor-agent (vendor installer). Only the one
# `routing.defaultHarness` names is required.
RUN npm install -g @anthropic-ai/claude-code

RUN pip install the-loopy-one
```

Install hints per platform: `tmux` and `ttyd` are in every major package manager
(`brew install tmux` · `apt install tmux` · `dnf install tmux`); `gh` follows
[cli.github.com](https://cli.github.com); the harness CLIs follow their vendors'
instructions.

## Credentials, not just binaries

A present binary is not an authenticated one. Beyond the executables:

- **`gh` must be authenticated** as the identity the-loop posts as — `gh auth login`, or
  `GH_TOKEN`/`GITHUB_TOKEN` in the process environment. the-loop posts with the operator's
  own credentials, which is exactly why every comment it writes carries the
  `<!-- the-loop:agent-comment -->` marker.
- **The harness CLI must be logged in** with a plan or key that permits non-interactive
  runs.
- **State must persist.** `state.root` holds the session registry, the portable work-item
  records and the event log; a container that loses it loses the loop's memory of what is in
  flight.

None of these are checked by `check_environment()` — checking them means calling out to a
network with somebody's credentials, which a preflight has no business doing.
