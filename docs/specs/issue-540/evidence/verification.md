---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#540"
---

# Verification (issue-540)

Run on 2026-11-18 on branch `the-loop/issue-540-prompts-and-strings` at `d0470779`.

**Environment note.** This session runs inside a live the-loop daemon, which exports
`THE_LOOP_CLI_CONFIG`, `THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM`. With them set, 22
tests that read the live config fail. They fail identically on `origin/main`, and they
pass once the variables are unset. The suite runs below unset them, as CI's
environment does (the same finding as issue-538's verification).

## Verification results

See the table in [`testing-plan.md`](../testing-plan.md#verification-results). Raw output follows.

## V1 — new tests (T1, T3, T4, T6, T14)

```text
$ cd cli && uv run python -m pytest -q tests/test_prompts.py tests/test_strings_catalog.py tests/test_prompts_guard.py
36 passed in 2.58s
```

These cover the loader, the name check (`..`, absolute and uppercase names refused),
the missing-file error, the skill-template ↔ packaged-prompt sync, literal `$x`/`{x}`
in untrusted values, the catalog's shape, the locale fallback (translated key, missing
key, missing locale, invalid locale), `KeyError` on an unknown key, used-keys ↔ catalog
parity, and the guard with planted offenders.

**Guard red on `main`.** The guard's `offenders()` run over `origin/main`'s package
reports the six inline prompts this item moved:

```text
red on main: ['core/selfdiagnosis.py:91 _PROMPT', 'core/standing.py:71 _DIRECTIVE',
 'interaction.py:80 _WORK_ITEM_DIRECTIVE', 'interaction.py:103 _CLI_DIRECTIVE',
 'webhook/dispatcher.py:297 DEFAULT_PROMPT_TEMPLATE', 'webhook/dispatcher.py:329 DEFAULT_SPAWN_TEMPLATE']
```

## V2 — full suite (T2: existing tests pin today's text)

```text
$ cd cli && env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_INSTANCE -u THE_LOOP_WORK_ITEM uv run python -m pytest -q
6992 passed, 3 warnings in 254.16s (0:04:14)
```

With the daemon variables left set, the same tree gives `6967 passed, 22 failed`.
Those 22 (`test_poll_status.py`, `test_poll_command.py`, `test_instances_cmd.py`,
`test_lifecycle_cmd.py`, `test_critics.py::test_policy_text_is_one_key_per_line`,
`test_ask_reply_integration.py::test_the_ask_verb_warns_when_the_bus_names_no_channel`)
also fail on an `origin/main` export in the same shell (`22 failed`), and pass with the
variables unset (`22 passed in 1.02s`).

### Byte-identical rendering, old vs new

Beyond the suite, the renderers were run over a grid of inputs on the pre-change tree
(a `git archive` export) and on the new tree, and the outputs were hashed:

| Renderers | Cases | Old = new |
|---|---|---|
| `render_graph_context` (every status, loop, surface, Claude artifact/doc, handoff, PR, verdict, reason, messages) + `render_assignment` | 65,664 | yes (`014382a2…`) |
| `prnotice.render` (every transition), `cimonitor.render_section`, `attachments.render_section`, `framed_record`, `_framed_reply`, standing `_framed` / `_surfaces` / `_boot_prompt` | 508 | yes (`96b5810d…`) |
| `selfdiagnosis.build_dossier` | 2 | yes (`70eaa068…`) |

Values containing `{x}` and `$x` were part of the grid. The Codex AGENTS.md block was
checked by `test_codex_support.py` and by reading it against the old literal. (The old
export lacks the bundled skills, so its `prepare_instructions` refuses before rendering.)

## V3 — packaging (T5)

```text
$ uv build --wheel cli -o <tmp>
Successfully built <tmp>/the_loopy_one-20.14.0-py3-none-any.whl
$ unzip -l <wheel> | grep -E 'the_loop/(prompts|strings)/'   # 104 entries
  101 × the_loop/prompts/**/*.md, incl. the_loop/prompts/webhook/event.md
  the_loop/strings/en.json
$ <fresh venv>/bin/python -I -c "from the_loop import prompts, strings; …"   # run outside the checkout
# $event_source event for $work_item
Decision needed
101 prompts
```

## V4 — static checks (T7)

```text
$ uv run ruff format cli hooks        # 6 files reformatted (new tests/modules), then clean
$ uv run ruff check cli hooks
All checks passed!
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1927 file(s)
Summary: 0 error(s)
$ uv run python scripts/validate_config.py
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   skills/the-loop/templates/gateway-config.yaml
```

`cli/pyproject.toml` dependencies are unchanged (NFR: no new runtime dependency).

## V5 — scope extension: the whole application

Run on 2026-11-18 after the owner asked for the whole application in this PR (tasks 11–19).
Every human-facing string of the CLI and the UI now comes from `en.json` (2,275 keys, 428
of them `ui.*`). The 37 MCP tool descriptions and the stop hook's feedback are prompt files
(144 prompt `.md` files in all).

```text
$ cd cli && env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_INSTANCE -u THE_LOOP_WORK_ITEM uv run python -m pytest -q
6998 passed, 2 warnings in 261.70s (0:04:21)
$ uv run python -m pytest -q tests/test_strings_catalog.py tests/test_prompts.py tests/test_prompts_guard.py tests/test_harness_gate.py
80 passed in 2.54s
$ cd ui && npm test            # Node 26 locally needs NODE_OPTIONS=--no-experimental-webstorage
Test Files  23 passed (23)
     Tests  379 passed (379)
$ npm run typecheck && npm run lint && npm run build     # all clean
$ grep -c '"eventlog.event-type' ui/dist/assets/*.js    # the build keeps only ui.* keys
0
$ uv run ruff format --check cli hooks   # 527 files already formatted
$ uv run ruff check cli hooks            # All checks passed!
$ uv run pyright cli                     # 0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"   # 1936 files, 0 error(s)
$ uv run python scripts/validate_config.py       # 3 × VALID
```

The existing CLI and UI suites assert today's exact text, so a green run shows that the
rendered output did not change. Each migration group also compared its renderers' output
before and after on sample inputs and found them identical.
