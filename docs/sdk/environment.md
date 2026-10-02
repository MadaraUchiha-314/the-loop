# Environment expectations

the-loop drives other people's programs. It spawns a harness CLI inside `tmux`, it clones
with `git`, it serves a terminal with `ttyd`. None of that is a Python dependency, so none
of it arrives with `pip install the-loopy-one` — and a container image that is missing one
finds out at the first dispatch, in production. GitHub is the exception since issue-442: the
daemon reads and writes tickets through [PyGithub](https://github.com/pygithub/pygithub/),
which *does* arrive with the wheel, under a token you name — a credential to provide, not a
binary to install (see [Credentials](#credentials-not-just-binaries)).

This page is the contract. `loop.check_environment()` is the same contract, executable.

## The contract

| Binary | Renamed by | Required when | What it serves |
|--------|-----------|---------------|----------------|
| `claude` | — | `routing.enabled` and `routing.defaultHarness: claude` (the default) | spawning, resuming and one-shot critic runs of Claude Code sessions |
| `codex` | — | `routing.enabled` and `routing.defaultHarness: codex` | Codex TUI hosting, exact-session resume, and JSONL critic runs |
| `cursor-agent` | — | `routing.enabled` and `routing.defaultHarness: cursor` | the same, for Cursor |
| `tmux` | — | `routing.enabled` | hosting harness sessions — the only runner since issue-156, and what makes a session attachable |
| `git` | [`routing.workspace.gitBinary`](/config/cli/routing-options) | `routing.enabled` | cloning and worktree checkouts for spawned sessions |
| `ttyd` | — | `routing.webTerminal.enabled` | serving tmux sessions to a browser (the web terminal) |

Two readings of that table are worth stating plainly.

**Nothing is required unconditionally.** `routing.enabled` defaults to **false** — verify
and log only — so a service that mounts the-loop to *read* work items, events and session
state needs none of these binaries. Turning routing on is what makes three of them
load-bearing at once.

**`git` is the one an operator renames.** Wrapper scripts and vendored builds are common,
so the check resolves whatever `routing.workspace.gitBinary` names rather than the literal
`git`.

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
      "binary": "tmux",
      "present": false,
      "path": "",
      "required": true,
      "capability": "hosting harness sessions — …",
      "configKey": ""
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
        git tmux ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# No `gh`: the daemon reaches GitHub through PyGithub (a dependency of the wheel) under
# the token in GH_TOKEN — pass it at run time, never bake it into the image.

# The harness CLI: Claude Code (npm) or cursor-agent (vendor installer). Only the one
# `routing.defaultHarness` names is required.
RUN npm install -g @anthropic-ai/claude-code

RUN pip install the-loopy-one
```

Install hints per platform: `tmux` and `ttyd` are in every major package manager
(`brew install tmux` · `apt install tmux` · `dnf install tmux`); the harness CLIs follow
their vendors' instructions.

## Credentials, not just binaries

A present binary is not an authenticated one. Beyond the executables:

- **A GitHub token must be in the environment** — the first set variable of
  [`integrations.github.api.tokenEnv`](/config/cli/integrations-options#github-api-tokenenv)
  (default `GH_TOKEN`, then `GITHUB_TOKEN`); an `env.file` can carry it. A fine-grained
  token needs *Issues: read and write*, *Pull requests: read* and *Metadata: read* on every
  repository the instance works with (a classic token: `repo`). the-loop posts as that
  token's login, which is exactly why every comment it writes carries the
  `<!-- the-loop:agent-comment -->` marker. Without it, every writer says
  `no GitHub token: set GH_TOKEN or GITHUB_TOKEN` and does nothing else, and
  `the-loop start`'s pre-flight names the variables.
- **The harness CLI must be logged in** with a plan or key that permits non-interactive
  runs.
- **State must persist.** `state.root` holds the session registry, the portable work-item
  records and the event log; a container that loses it loses the loop's memory of what is in
  flight.

None of these are checked by `check_environment()` — checking them means calling out to a
network with somebody's credentials, which a preflight has no business doing.
