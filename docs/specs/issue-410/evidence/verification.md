---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#410"
---

# Verification: roll running sessions onto a refreshed environment (issue-410)

Results for the matrix in [`testing-plan.md`](../testing-plan.md). Verification
environment: the suite's scripted tmux for T1–T6, and a real tmux 3.4 on the development
host for T7, against a scratch `TMUX_TMPDIR` so nothing touched any operator's server.

## Activities checklist

- [x] T1 — `envstate` unit tests
- [x] T2 — runner argv tests (`respawn_in`, the `env_provider` folding)
- [x] T3 — `restart_sessions` integration, one case per outcome
- [x] T4 — `environment_drift` and the `status` line
- [x] T5 — CLI ↔ docs parity
- [x] T6 — redaction: no declared value in any sink, on every path
- [x] T7 — end to end against a real tmux (including the scrollback claim)
- [x] T8 — full regression (`make check`)
- [x] T12 — no config key, state file or registry field added

## Results

| Row | Command | Outcome | Artifact |
|-----|---------|---------|----------|
| T1 | `uv run pytest -q cli/tests/test_envstate.py` | 17 passed | `cli/tests/test_envstate.py` |
| T2 | `uv run pytest -q cli/tests/test_tmux_runner.py` | 130 passed (13 new) | `cli/tests/test_tmux_runner.py::TestEnvironmentRefresh` |
| T3, T4, T6 | `uv run pytest -q cli/tests/test_sessions_restart_integration.py` | 28 passed | `cli/tests/test_sessions_restart_integration.py` |
| T5 | `uv run pytest -q cli/tests/test_docs_parity.py` | 5 passed | — |
| T7 | `bash` transcript, real tmux 3.4 | pass — below | this file |
| T8 | `make check` (ruff, ruff format, pyright, markdownlint, `validate_config`, full pytest) | green — see § Regression | — |

## T7 — end to end against a real tmux

### The relaunch, in place

A tmux server started carrying the **retired** token, a rotation written to `env.file`,
then `respawn_in`. Values are shown here because both are fabricated test strings, never
a real credential.

```console
== 1. a tmux server started with the RETIRED token ==
pane pid 4830 holds: SLACK_BOT_TOKEN=xoxb-bot-b-retired
loop-github-octo-repo-15 windows=1

== 2. the operator rotates the credential in env.file ==
SLACK_BOT_TOKEN=xoxb-bot-a-the-new-one

== 3. respawn_in: the same pane, the new value, the session untouched ==
respawn ok: True
new pane pids: [4845]
verdict: ('fresh', ())
fingerprint declared: f505f93c

== 4. the session, its name and its window survived ==
loop-github-octo-repo-15 windows=1
pane pid 4830 -> 4845
SLACK_BOT_TOKEN=xoxb-bot-a-the-new-one
old process is gone
```

What this proves, against R1.4 and R2.1: the tmux **session name and window are the ones
that were there before** (so an attached operator stays attached), the pane's process is a
new pid, that new process carries the rotated value, and the old process is gone.

### The whole command, end to end

`restart_sessions` itself — the registry, the selection, the respawn and the
verification — against the same real tmux, with `sh` standing in for the harness:

```console
== a session running on the RETIRED token, as the reporter's 20 were ==
SLACK_BOT_TOKEN=xoxb-bot-b-retired

== the rotation is written; now: the-loop sessions restart --all ==
  [out] restarting 1 session(s) against 1 declared variable(s) [SLACK_BOT_TOKEN]
  [out] github:octo/repo#15                      restarted
exit code: 0

== the pane now ==
pid 7956 -> 7968
SLACK_BOT_TOKEN=xoxb-bot-a-the-new-one
loop-github-octo-repo-15 windows=1
```

This transcript is the one that **caught a defect**: on the first pass
`restart_sessions` built its `TmuxRunner` with no `env_provider`, so the respawn
carried no `-e` at all — every session was relaunched straight back onto the retired
credential and then correctly reported stale. A busy no-op. The scripted-runner
integration tests could not see it, because the double is the seam. Fixed, and now
covered by
`test_the_respawned_pane_is_handed_the_file_not_the_frozen_environment`, which asserts
on what the pane is *handed* rather than only that a respawn happened.

### Scrollback — a claim checked rather than assumed

The first draft of the design and the operator docs said the respawn keeps the pane's
scrollback. Checked directly on tmux 3.4, it does not:

```console
--- before ---
1            # MARKER-FROM-BEFORE-THE-RESPAWN is in the pane history
--- after respawn ---
0 (scrollback cleared)
```

`respawn-pane` clears the pane, as a fresh session would. What the verb actually buys
over kill-and-`new-session` is that the tmux session and window keep their identity, so
an attached operator is not dropped and nothing else has to re-find the name — which is
still the right trade, but it is a smaller claim than the one first written.

Corrected in `design.md`, `docs/cli/commands/sessions.md` and
`docs/capabilities/interactive-sessions.md`: the cost is now stated to operators rather
than glossed. The conversation itself survives, which is what `--resume` is for, and the
retention `remain-on-exit` gives a *finished* session (issue-86) is a different promise
that this does not weaken.

### A session spawned after the rotation is not born stale (R4.1)

The same scenario one step earlier — the tmux **server** still holds the retired token, as
the reporter's did (`tmux server global env 89100053 -> bot B`), and the spawning client
holds it too:

```console
== a tmux SERVER started before the rotation, holding the retired token ==
SLACK_BOT_TOKEN=xoxb-bot-b-retired

== the rotation happens; env.file now names bot A ==

== a session spawned NOW, from a client that also holds the retired value ==
without the fix (no provider)    pane holds 'xoxb-bot-b-retired'      -> stale
with the fix                     pane holds 'xoxb-bot-a-the-new-one'  -> fresh
```

The first line is the defect, reproduced: a session spawned *after* the rotation, by a
process that itself holds the new value, is still born on the retired one, because the
pane inherits the tmux server's long-frozen environment. The second is the fix.

## Regression

`uv run pre-commit run --all-files` — ruff, `ruff format`, pyright, markdownlint,
`validate_config` and the full pytest suite, the exact hook set CI runs. Green.

The pytest hook runs `cd cli && uv run python -m pytest -q`:

```text
4400 passed, 1 skipped in 165.13s (0:02:45)
```

**One observation, filed rather than fixed here.** `make test` runs the same suite from
the **repository root** (`uv run --project cli python -m pytest -q cli`), and on that
invocation four tests in `cli/tests/test_instance.py` fail —
`test_an_unnamed_instance_spawns_with_the_argv_it_used_before`,
`test_a_spawn_for_a_work_item_exports_its_ref`,
`test_a_standing_session_carries_no_work_item`,
`test_only_the_configured_name_reaches_tmux_and_the_comment`. They assert an exact `-e`
set on the spawn argv, and from the root `default_cli_config_path()` finds this
repository's own `.the-loop/cli-config.yaml`, so `THE_LOOP_CLI_CONFIG` is exported and
the expected set is one short.

It reproduces on `main` at `030cdf1` with this branch stashed, so it is not this change.
It is worth its own work item all the same: the Makefile's `check` target claims CI
parity in its own comment, and on this one target it does not have it — `make check` is
red on a tree CI calls green. Fixing it (anchor the tests' config path, or run the
Makefile's pytest from `cli/`) is a different diff and is left to that work item.
