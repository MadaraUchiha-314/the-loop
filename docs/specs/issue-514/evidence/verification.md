---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#514"
---

# Verification: split `/the-loop:init` into `/init`, `/init-cli` and `/init-gateway`

> Written **only when the work item declared `test-planning` away** (issue-179). With a
> `testing-plan.md` the `verification` node records its results *there*, against the
> matrix rows it planned. Without one, this is where the proof lives — and `verification`
> blocks until it is filled in, because skipping the plan removes the document, never the
> verifying.

The plan is [`design.md`](../design.md) § Testing strategy. Every activity it names ran.

## Verification results

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| C1 — every shipped command is listed in the command reference and the skill (R2.1, R3.1, R5.1) | `uv run pytest cli/tests/test_init_commands.py` | pass (red first: `init-cli`, `init-gateway` and the already-missing `explain` were unlisted) | commit `fd89577a` |
| C2 — `/init` names no daemon or gateway file and no credential key, and its hand-off names both other commands (R1.2, R1.3, R1.6, abuse case 2) | same | pass (red first: the old `commands/init.md`) | commit `fd89577a` |
| C3 — each init command offers `--dry-run` and `--defaults` (R4.1) | same, parametrized over the three commands | pass (red first for `init-cli` and `init-gateway`, which did not exist) | commit `fd89577a` |
| The two Jira migration messages name `/the-loop:init-cli` (R5.4 spirit) | `uv run pytest cli/tests/test_migrations.py` | pass (2 red first) | commit `fd89577a` |
| The schema description edit is the only schema change; onboarding metadata and schema copies still agree | `uv run pytest cli/tests/test_onboarding_schema.py cli/tests/test_manifest_schemas.py cli/tests/test_config_schema_parity.py` | pass | commit `fd89577a` |
| The full repository gate | `uv run pre-commit run --all-files` (ruff, ruff format, pyright, pytest, markdownlint, config validation) | pass, 6491 tests, with the session's `THE_LOOP_CLI_CONFIG` and `THE_LOOP_WORK_ITEM` unset | below |
| `/init --dry-run` lists only repository files and phase labels, names `/init-cli` and `/init-gateway`, and writes nothing (R1, R4) | headless `claude -p --plugin-dir` run | pass | [dry-runs.md](dry-runs.md#the-loopinit---dry-run) |
| `/init-cli --dry-run` lists only the CLI config, the Slack manifest and the arming label, reports credentials by name and presence only, and writes nothing (R2, abuse case 1) | same | pass | [dry-runs.md](dry-runs.md#the-loopinit-cli---dry-run) |
| `/init-gateway --dry-run` lists only `gateway-config.yaml`, preflights its secrets by name, and writes nothing (R3) | same | pass | [dry-runs.md](dry-runs.md#the-loopinit-gateway---dry-run) |
| Nothing written by any dry run | `git status --short --ignored` in the throwaway repo; `ls -la ~/.the-loop` before vs after | pass (empty; identical) | [dry-runs.md](dry-runs.md) |

### The full gate, and the one environment finding

The first full run inside this session failed 21 tests in `test_poll_command.py`,
`test_poll_status.py`, `test_instances_cmd.py`, `test_lifecycle_cmd.py` and
`test_critics.py`. None of them touch this change. The session exports
`THE_LOOP_CLI_CONFIG`, which points at the live daemon's config, and those tests resolve
their config from it. With the two session variables unset, the same suite passed:

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

CI runs without those variables, so it sees the second result.

### Deviation from the spec

R3.2 and the design say `/init-gateway` walks `gateway-config.schema.json` →
`x-onboarding.groups`. That schema has **no** `x-onboarding` block, and adding one would
be a schema change the requirements put out of scope. `/init-gateway` therefore walks the
schema's top-level blocks in a fixed order its command file gives, as today's `/init`
already did, and `reference/onboarding.md` now says so. Giving the gateway schema its own
`x-onboarding` block is a candidate follow-up.
