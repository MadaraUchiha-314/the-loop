---
type: execution-log
workItem: issue-117
phase: needs-review
status: in-progress
---

# Execution Log: the CLI documented as a product, and the docs restructured around it

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-30 | | Gap measured from the tree, not assumed — see the first progress entry |
| design | 2026-07-30 | | |
| tasks-breakdown | 2026-07-30 | | |
| implementation | 2026-07-30 | | T1–T12 |
| needs-review | 2026-07-30 | | Tier 3 → human-approves-pr; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#118](https://github.com/MadaraUchiha-314/the-loop/pull/118) | spec + T1–T12 | open |

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
- **Did:** All twelve tasks. 23 pages authored (15 under `docs/cli/`, 8 under
  `docs/config/`) plus the `documentation` capability doc; `cli/README.md` reduced from 679
  lines to 88; the sync copy retired; navigation restructured; links repaired repo-wide.
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

P4 is what _forced_ the four undocumented blocks to be written: `integrations.*` (10
leaves), `routing.workspace.*` (6), `routing.graph.*` (2) and `polling.maxRetries`. P3 is
what forced `ghBinary` out — it now appears nowhere outside the migration that retires it.

#### Gates

| Gate | Result |
|---|---|
| `make lint` (ruff + markdownlint over 292 `.md`) | `All checks passed` · `0 error(s)` |
| `make format-check` | `107 files already formatted` |
| `make typecheck` (pyright) | `0 errors, 0 warnings` |
| `make validate` (schema) | all 5 config files `VALID` |
| `make test` | **809 passed, 1 skipped** |
| `npm run docs:build` | `build complete` — and no `docs/cli.md` produced |

#### Built-site evidence

`ignoreDeadLinks: true` means VitePress does **not** catch a broken internal link, so link
correctness was verified against the built output rather than assumed:

- **42,962 internal page links and anchors across 251 pages — all resolve.** This also
  caught one _pre-existing_ dead anchor unrelated to this work
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
  form, all confirmed by the link check above. An em dash is in _neither_ replacement set
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

Two controls were _strengthened_ in the move rather than merely preserved: `webTerminal`
now carries an explicit "ttyd has no authentication of its own" danger callout (it had a
one-line note), and `integrations.slack.urlEnv` says outright that the webhook URL _is_ the
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

### 2026-07-30 — CI caught an unlocked artifact

- **Phase:** needs-review (unchanged)
- **Did:** the-loop's own gate (`.github/workflows/the-loop-gate.yml`) failed #118 on its
  first run, and it was right:

  ```text
  issue-117: UNMET (at requirements-definition)
    BLOCK  requirements-definition
           · artifact is not locked — front-matter says status: in-review,
             expected status: approved (docs/specs/issue-117/requirements.md)
  ```

  I had left all three artifacts at `status: in-review`, reading "in review" as "the human
  has not approved yet". That conflates two different things, and the graph keeps them
  apart deliberately: `requirements-definition` is an **agent** node meaning _the artifact
  is written and locked_, and `requirements-approval` is the **human** node after it. The
  gate runs `--fail-on block`, i.e. only on what an agent can fix — so classifying this as
  `BLOCK` was the graph saying "your half isn't finished", not "the reviewer hasn't
  answered".

  Locked all three to `status: approved` with `approvedBy: []` and a note naming the PR
  review as the gate — the same form issue-108 used for an open tier-4 PR. Re-running the
  exact CI command now gives the correct open-PR state:

  ```text
  $ the-loop check issue-117 --recompute --fail-on block
  issue-117: UNMET (at requirements-approval)
    WAIT   requirements-approval
           · no authorized feedback yet
  exit=0
  ```

- **Worth noting:** this is the harness catching its own operator, on the very work item
  whose subject is documentation being out of step with reality. The gate did exactly what
  `--fail-on block` was designed to do — fail on the agent's omission, wait on the human's.
- **Next:** unchanged — human review of the three phase gates and the PR.

### 2026-07-30 — CI green; a pre-existing flake fixed on the way

- **Phase:** needs-review (unchanged)
- **Did:** The second CI round failed `checks` on
  `test_an_unresumable_conversation_falls_back_to_a_fresh_session` — tmux respawn, a code
  path this work item does not touch. Established that it was **not** mine before treating
  it as such:

  | Check | Result |
  |---|---|
  | in isolation on this branch | 8/8 pass |
  | in isolation on `origin/main` (fresh worktree) | 10/10 pass |
  | full suite locally | 809 passed |
  | CI | `1 failed, 808 passed` |

  The race: `session.respawned` is emitted **after** `registry.register()` and
  `registry.touch()` (`dispatcher.py:1390–1408`), but both of the test's `wait_until`
  guards are satisfied by those registry writes — so it read the event log before the
  record existed. The dispatcher wins that race on an idle laptop and loses it on a loaded
  runner.

  Proved rather than argued: injecting `time.sleep(0.4)` before the emit reproduced the CI
  failure exactly on the old test — same line 620, same
  `ValueError: not enough values to unpack (expected 1, got 0)` — and passed with a
  `wait_until` guard added. The dispatcher change was then reverted; the diff is seven
  test-only lines.

  Fixed here rather than filed because it is test-only and was blocking this PR; a re-run
  would only have hidden it until the next contributor hit it. Flagged on the PR as
  out-of-scope, with an offer to drop the commit if the reviewer would rather it landed
  separately.
- **Checkpoint/tests:** both CI checks **green** on `9a952ae` — `gate` success, `checks`
  success. PR `mergeable_state: clean`.
- **Next:** unchanged — human review of the three phase gates and the PR.

## Risk tier

**3** — documentation, navigation and one build-script line; no runtime behaviour change,
no schema change, no touched `sensitivePaths`. `autonomy.tiers."3": human-approves-pr`.
Below `security.review.humanSignOffMinTier` (4), so no named human security sign-off is
required; the security-review gate itself still runs at T11.

## Reviews

`reviews.selfReviewCount: 3`, `reviews.criticReviewCount: 3`. `reviews.critics` is **empty**
in this repo's `.the-loop/harness-config.yaml`, so there is no configured harness for
`the-loop critic run` to spawn — the critic rounds are recorded as not-run rather than
silently skipped.

| Round | Kind | Reviewer | Findings | Where |
|-------|------|----------|----------|-------|
| 1 | self | the-loop (implementing agent) | **1 finding, fixed.** R3.3 ("every option states Type and Default") and R3.4 ("defaults equal the schema's") had **no automated proof** — P3/P4 check that a path exists on both sides, never that the block beneath it says anything. Cross-checked all 80 documented defaults against the schema with a throwaway script: 4 apparent mismatches, all artefacts of the matcher (`monitor.issues`/`pullRequests` carry a `*(github)*` qualifier; `harnessArgs.claude`/`.cursor` have no schema default, and `harness/__init__.py` confirms the code applies `[]` — which is what R3.4 permits). So the values were right, but nothing would have caught the next one. Added **P5**: every documented option must carry `- **Type:**` and `- **Default:**`. Presence, not value — defaults are written with deliberate prose qualifiers (`<state.root>/…`, `none — required`, `eyes (👀)`), so an equality check would need a normaliser fuzzy enough to be its own maintenance burden, and a gate that misfires is one people route around. Verified it bites by deleting a `Type` bullet: `webhooks.ghWebhook.port: no Type`. | this PR |
| 2 | self | the-loop (implementing agent) | **1 finding, fixed — a real bug in my own copyable example.** The getting-started config said `state.root: ~/.the-loop`. `state.py` uses `Path(self.root)` with **no** `expanduser()`, so that creates a directory literally named `~` in the daemon's working directory. Worse, the asymmetry is invisible: `workspace.py` line 125 _does_ call `.expanduser()`, and I had (correctly) used `~/.the-loop/workspace` as the workspace example two pages away. Fixed the example, and documented the asymmetry on **both** options so the next reader sees it from either side. | this PR |
| 3 | self | the-loop (implementing agent) | **3 findings, fixed.** Three sample command outputs were plausible reconstructions from the source rather than captured runs, and two were wrong: `graph show` claimed `start: requirements` with `--approved-->`/`--rejected-->` edges when the real graph starts at `brainstorming` and uses `--pass-->` / `--approved-with-comments-->` / `--changes-requested-->`; `check` named a node `design-approved` that does not exist (`design-approval` does). `migrate-config --dry-run` was right in shape but omitted the `('gh')` value and the `version` move. All three replaced with real captured output. The lesson is the mundane one: a sample output read _from_ the print statements is a guess, and a docs page is exactly where a guess gets believed. | this PR |
| — | critic | none configured (`reviews.critics: []`) | Not run. There is no critic entry in this repo's `.the-loop/harness-config.yaml`, so `the-loop critic run` has nothing to spawn — recorded rather than silently skipped. | — |

## Requirement → evidence

| Requirement | Evidence |
|-------------|----------|
| R1.1 CLI is a top-level nav section | `config.mts` nav + `cliSidebar`; `design/cli-overview.png` |
| R1.2 overview · install · getting-started · concepts | 4 pages under `docs/cli/` |
| R1.3 uninstalled → startable work item, every step runnable | `/cli/getting-started`, 5 steps |
| R1.4 all four config locations + a complete file | `/cli/getting-started` §2 — YAML validated against the schema |
| R1.5 every onboarding page links its next step | `## Next` on `/cli/`, installation, getting-started, concepts |
| R2.1 every registered command has a page | **P1** |
| R2.2 commands overview table | `/cli/commands/` |
| R2.3 synopsis · options · behaviour, defaults matching the code | 9 pages written from argparse + schema; e.g. `poll --max-retries` and `check --repo` were absent/wrong before |
| R2.4 command pages link their config | every page's option table links `/config/cli/*` |
| R2.5 `check`/`graph`/`migrate-config` at equal depth | 3 new pages from `graph_cmd.py`, `migrate_cmd.py` |
| R3.1 Config is top-level, landing explains both files | `/config/` + nav entry |
| R3.2 CLI config split by area | 6 pages under `/config/cli/` |
| R3.3 Type + Default on every option | uniform block; `design/config-routing.png` |
| R3.4 defaults equal the schema's | authored from the schema dump; **P3/P4** bound the set |
| R3.5 harness config in the same section | `/config/harness-config` |
| R4.1 documented keys exist in the schema | **P3** |
| R4.2 `ghBinary` removed, replacement documented | **P3**; `/config/cli/integrations-options#github-cli-binary` |
| R4.3 `integrations`, `workspace`, `routing.graph`, `polling.maxRetries` documented | **P4** |
| R4.4 `check`, `graph`, `migrate-config` listed and paged | **P1**, `/cli/commands/` |
| R4.5 automated parity check | `cli/tests/test_docs_parity.py` — 4 assertions, both directions on both axes |
| R5.1 README stands alone on PyPI | rewritten: what it is, install, one example, links |
| R5.2 outbound links absolute | grep for `](/`, `](../`, `](docs/` in `cli/README.md` → none |
| R5.3 not copied into the site | `FILE_MAPPINGS = []`; `docs:build` produces no `docs/cli.md` |
| R5.4 nothing lost | the fidelity walk above, section by section |
| R6.1 no link to the removed `/cli` page | repo-wide grep clean outside `docs/specs/**`; 42,962 built links resolve |
| R6.2 CLI is first-class on the docs home | `docs/index.md` hero action + feature link |
| R6.3 repo README links the CLI docs | `README.md` CLI section |
| R6.4 build + markdown lint green | `docs:build` complete; markdownlint `0 error(s)` over 292 files |
| R6.5 per-command search results | local-search index verified per page |
