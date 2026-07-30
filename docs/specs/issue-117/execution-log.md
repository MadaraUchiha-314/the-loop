---
type: execution-log
workItem: issue-117
phase: tasks-breakdown
status: in-progress
---

# Execution Log: the CLI documented as a product, and the docs restructured around it

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-30 | | Gap measured from the tree, not assumed — see the first progress entry |
| design | 2026-07-30 | | |
| tasks-breakdown | 2026-07-30 | | |
| implementation | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| _pending_ | spec + T1–T12 | — |

## Progress entries

### 2026-07-30 — spec written (requirements → design → tasks)

- **Phase:** not-started → requirements-definition → design → tasks-breakdown
- **Did:** Measured the gap before specifying it, rather than restating the ticket:

  | Claim | How it was established |
  |---|---|
  | 679-line single page | `wc -l cli/README.md`; `docs/scripts/sync-content.mts` copies it verbatim to `docs/cli.md`; `config.mts` exposes it as one nav entry `{ text: "CLI", link: "/cli" }` |
  | 3 of 9 commands undocumented | `grep 'name = ' cli/the_loop/commands/*.py` → 9 registered (`gh-webhook`, `sessions`, `poll`, `events`, `scenarios`, `critic`, `check`, `graph`, `migrate-config`); `cli/README.md` has `###` sections for 6 |
  | 4 config blocks undocumented | Walked `.the-loop/cli-config.schema.json` → 80 leaves; `integrations.*`, `routing.workspace.*`, `routing.graph.*`, `polling.maxRetries` appear in none of the README's tables |
  | `ghBinary` documented but removed | 5 occurrences in `cli/README.md`, `grep -c ghBinary .the-loop/cli-config.schema.json` → **0**. `cli_config.apply_integrations()` fans `integrations.github.cli.binary` out to `control`/`reactions`/`announce` under a private key; `migrations.py` makes the old key a hard refusal (`ConfigTooOld`) |

  The finding that shaped the design: **the flat shape is why the content is wrong.** A
  single file has nowhere to put a new command, so issue-109's three commands got no
  entry while a key it deleted stayed documented. A structure with a slot per command and
  a slot per option turns that from "someone forgot" into a failing test — hence R4.5 and
  the parity test at T1.

  Wrote `requirements.md` (6 requirements, 26 EARS criteria + threat-model-lite),
  `design.md` (23 new pages, the `configBase` per-option contract, the four parity
  assertions, the exhaustive `cli/README.md` → new-home mapping), `tasks.md` (12-task DAG,
  red-first).
- **Checkpoint/tests:** none yet — no code or pages written.
- **Next:** T1 — `cli/tests/test_docs_parity.py`, red first.
- **Blockers:** none. Two open questions recorded on the ticket with assumptions taken
  (retiring `/reference/configuration`; treating `ghBinary` as doc drift rather than a
  lost migration path). Neither blocks implementation.

### 2026-07-30 — T1–T12 implemented

- **Phase:** tasks-breakdown → implementation → needs-review
- **Did:** All twelve tasks. 24 pages authored, `cli/README.md` reduced from 679 lines to
  86, the sync copy retired, navigation restructured, links repaired repo-wide, and the
  `documentation` capability minted.
- **Checkpoint/tests:** the four gate runs below, all green.
- **Next:** human review of the three phase gates and the PR (tier 3 →
  `human-approves-pr`).
- **Blockers:** none.

#### Red → green

The TDD cycle this work item is built on. `cli/tests/test_docs_parity.py` first:

```text
$ pytest cli/tests/test_docs_parity.py          # T1 — before any page existed
FAILED test_p1_every_registered_command_has_a_page
        registered but undocumented — add docs/cli/commands/<name>.md for:
        check, critic, events, gh-webhook, graph, migrate-config, poll, scenarios, sessions
FAILED test_p3_every_documented_option_exists_in_the_schema
        no option headings found under docs/config/cli
FAILED test_p4_every_schema_leaf_is_documented
        in the schema but undocumented — 80 paths
3 failed, 1 passed
```

| Checkpoint | Transition |
|---|---|
| after **T3** (six CLI config pages) | **P3 + P4 green** — all 80 schema leaves documented, no phantom key |
| after **T5** (command pages) | **P1 + P2 green** — 9 registered commands, 9 pages, no orphan |
| final | `4 passed` |

P4 is what *forced* the four undocumented blocks to be written: `integrations.*` (10
leaves), `routing.workspace.*` (6), `routing.graph.*` (2) and `polling.maxRetries`. P3 is
what forced `ghBinary` out — it now appears nowhere outside the migration that retires it.

#### Gates

| Gate | Result |
|---|---|
| `make lint` (ruff + markdownlint over 292 `.md`) | `All checks passed` · `0 error(s)` |
| `make format-check` | `107 files already formatted` |
| `make typecheck` (pyright) | `0 errors, 0 warnings` |
| `make validate` (schema) | all 5 config files `VALID` |
| `make test` | **808 passed, 1 skipped** |
| `npm run docs:build` | `build complete` — and no `docs/cli.md` produced |

#### Built-site evidence

`ignoreDeadLinks: true` means VitePress does **not** catch a broken internal link, so link
correctness was verified against the built output rather than assumed:

- **42,962 internal page links and anchors across 251 pages — all resolve.** This also
  caught one *pre-existing* dead anchor unrelated to this work
  (`guide/installation.md → /reference/commands#the-loop-init`, a fragment for a table row
  that was never a heading); fixed to `#superset-commands`.
- **23 new routes**: 15 under `/cli/`, 8 under `/config/`.
- **Search (R6.5):** every command page and config-area page is its own document in the
  generated local-search index — verified by grepping
  `assets/chunks/@localSearchIndexroot.*.js` for `cli/commands/migrate-config`,
  `cli/commands/check`, `cli/commands/graph`, `config/cli/routing-options`,
  `config/cli/integrations-options`, `cli/getting-started`, `cli/concepts`. Before this,
  the whole CLI was one result.
- **Screenshots** of the rendered site in `design/` (see `design.md` §UI/UX).
- **Anchor-scheme finding:** VitePress's slugify replaces a run of punctuation with one
  `-` (`` `state.root` `` → `#state-root`), while markdownlint's MD051 uses GitHub's rule,
  which strips dots. They disagree on any dotted heading. Same-page fragment links
  therefore target dot-free `##` section headings; cross-page links use the VitePress
  form, all confirmed by the link check above. An em dash is in *neither* replacement set
  and survives into the id, so two headings were reworded. Recorded in
  `capabilities/documentation.md` so the next author does not rediscover it.

#### `cli/README.md` fidelity walk (R5.4)

Every section of the old 679-line file, and where it now lives. Nothing was dropped:

| Old section (lines) | New home |
|---|---|
| Intro, `## Install` (1–43) | `/cli/` · `/cli/installation` |
| `## Two independent config files` (45–75) | `/config/` · `/config/cli/` |
| `#### Top level`, `#### state` (77–121) | `/config/cli/` |
| `#### webhooks.ghWebhook` (122–133) | `/config/cli/webhook-options` |
| `#### …routing` + control · harnessTrust · tmux · announce · reactions · webTerminal (134–342) | `/config/cli/routing-options` |
| `#### polling`, `polling.sources[]` (343–361) | `/config/cli/polling-options` |
| `#### eventLog`, `collaborators`, `notifications` (362–397) | `/config/cli/observability-options` |
| `### gh-webhook` (400–448) | `/cli/commands/gh-webhook` |
| `### sessions` (449–512) | `/cli/commands/sessions` |
| `### poll` (513–585) | `/cli/commands/poll` |
| `### events` (586–620) | `/cli/commands/events` |
| `### scenarios` (621–636) | `/cli/commands/scenarios` |
| `### critic` (637–665) | `/cli/commands/critic` |
| `## Adding a command` (666–674) | `/cli/extending` |
| `## Test` (675–679) | retained in `cli/README.md` |

Additions with no old counterpart, because they were never documented: `/cli/concepts`,
`/cli/getting-started`, `/cli/commands/check`, `/cli/commands/graph`,
`/cli/commands/migrate-config`, `/config/cli/integrations-options`, and the `workspace` /
`graph` / `maxRetries` sections.

#### Security review (`security.review`, tier 3 → no named human sign-off)

Run as the checklist from `design.md` §Security design, over every new page:

| Check | Result |
|---|---|
| No literal secret, token or webhook URL in any example — grepped `ghp_`, `github_pat_`, `xox[bpasr]-`, `hooks.slack.com/services`, `ATATT` | clean |
| No `secret:`/`token:`/`password:`/`apiKey:` key carrying a value | clean — every one is an **env-var name** (`secretEnv`, `urlEnv`, `tokenEnv`) |
| `authorizedUsers` stated as REQUIRED · no fallback · empty fails closed | 9 pages, incl. its own option, `/cli/concepts#guards`, and **both** ingress command pages |
| Self-comment marker guard documented | 6 pages, incl. `/cli/concepts#guards` and both ingress pages |
| Copyable example does not widen exposure | `host: 127.0.0.1`, `webTerminal.enabled: false`, `authorizedUsers` set explicitly |
| Getting-started YAML is genuinely valid | validated against `.the-loop/cli-config.schema.json` with `jsonschema` — **VALID** |
| New attack surface | **none.** No runtime, no input, no network, no dependency. The one code change removes a file copy; the one new test only reads files. |

Two controls were *strengthened* in the move rather than merely preserved: `webTerminal`
now carries an explicit "ttyd has no authentication of its own" danger callout (it had a
one-line note), and `integrations.slack.urlEnv` says outright that the webhook URL *is* the
credential.

#### Defect found, not fixed here

A CLI config that fails the version gate raises `ConfigTooOld` during **parser
construction**, so the user gets a Python traceback rather than the carefully worded
message the exception carries:

```text
Traceback (most recent call last):
  ...
the_loop.migrations.ConfigTooOld: this CLI config is version 0.1.0; the installed
the-loop needs 0.2.0. Run `/the-loop:upgrade-the-loop` to migrate.
```

The message is right; the presentation buries it. Out of scope here — this work item
changes no runtime behaviour — so it is filed separately rather than folded in.

## Risk tier

**3** — documentation, navigation and one build-script line; no runtime behaviour change,
no schema change, no touched `sensitivePaths`. `autonomy.tiers."3": human-approves-pr`.
Below `security.review.humanSignOffMinTier` (4), so no named human security sign-off is
required; the security-review gate itself still runs at T11.

## Reviews

| Round | Kind | Reviewer | Findings | Where |
|-------|------|----------|----------|-------|
| | | | | |

## Requirement → evidence

| Requirement | Evidence |
|-------------|----------|
| | _filled at T12_ |
