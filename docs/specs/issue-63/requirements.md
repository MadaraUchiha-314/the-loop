---
type: requirements
phase: requirements-definition
workItem: "issue-63"
status: approved
approvedBy: ["@MadaraUchiha-314"]
collaborators: [architect, engineer]
overrides: {}
---

# Requirements: split the-loop's config into CLI config and plugin config

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/).

## Introduction

`.the-loop/config.yaml` today conflates two audiences into one file:

1. **The plugin** — installed per repository (Claude Code / Cursor plugin) and read by
   the-loop's commands/skill while working *that* repo (ticketing, workflow, tooling,
   quality gates, reviews, autonomy, security, personas, …).
2. **The CLI daemon** — `the-loop gh-webhook` / `the-loop poll` / `the-loop sessions` /
   `the-loop events`, which route GitHub activity into harness sessions. Per issue #63,
   the CLI "is expected to work across multiple repos and is not tied to a single repo",
   but its settings (`webhooks`, `polling`, the event log) currently live inside one
   particular repo's `.the-loop/config.yaml` — so running the daemon means picking one
   repo's checkout to be its home, even though `polling.sources` already lists arbitrary
   `OWNER/REPO` entries.

Issue #63 asks for these two concerns to become independent: a CLI config the daemon
owns regardless of which repo(s) it is watching, and a plugin config scoped to the one
repo the-loop is installed into.

## Requirements

### Requirement 1 — Two independent config files, two schemas

**User story:** As an operator, I want the CLI daemon's settings kept separate from any
one repo's plugin settings, so that installing/upgrading the-loop in a repo never
touches how my daemon routes events, and vice versa.

#### Acceptance criteria (EARS)

1. WHEN the-loop is installed as a Claude/Cursor plugin in a repo THEN the system SHALL
   read only `ticketing`, `repository`, `workflow`, `tooling`, `customInstructions`,
   `testing`, `apiSpecs`, `design`, `localOrchestration`, `hooks`, `observability`
   (`devLevel`/`runtimeLevel`/`browserLogging`), `reviews`, `autonomy`, `security`,
   `tdd`, `minimalism`, `tokenEconomy`, `selfImprovement`, `contextManagement`,
   `userInteraction`, `personas`, `messaging`, `externalTools` from `.the-loop/config.yaml`,
   validated against `.the-loop/config.schema.json`.
2. WHEN `the-loop gh-webhook`, `the-loop poll`, `the-loop sessions`, or `the-loop events`
   read defaults THEN the system SHALL read `webhooks`, `polling`, and `eventLog` from a
   separate **CLI config** file, validated against a new `.the-loop/cli-config.schema.json`.
3. IF a key exists in one schema THEN the system SHALL NOT also accept it in the other
   (`additionalProperties: false` on both, no key duplicated between them).

### Requirement 2 — The CLI config's location is configurable, not hard-coded

**User story:** As an operator, I want to choose where my CLI config
(`cli-config.yaml`) lives — my home directory by default, but a specific repo (e.g. a
"dev box" repo I version and track it in) or an arbitrary path when I want that — so
that no single monitored repo is *forced* to be the daemon's home, but I can still
*choose* one if that fits my setup. (Revised per PR #69 review: an operator wants their
CLI config checked in and versioned in their own dev-box repo.)

#### Acceptance criteria (EARS)

1. WHEN the CLI resolves its config THEN the system SHALL check, in order: (1) an
   explicit `--config`/`-c` flag, (2) the `THE_LOOP_CLI_CONFIG` environment variable
   (same priority as the flag — whichever is set wins, the flag taking precedence if
   both are), (3) `./.the-loop/cli-config.yaml` relative to the process's current
   working directory, (4) `~/.the-loop/cli-config.yaml` in the operator's home
   directory — the first that resolves (for 1–2, being set at all; for 3–4, the file
   existing) wins.
2. WHEN no override is given and no repo-relative file exists THEN the system SHALL
   fall back to `~/.the-loop/cli-config.yaml` — never a path privileging one specific
   monitored repo by default.
3. WHEN the CLI config file is absent (fresh install, no PyYAML) THEN the system SHALL
   fall back to the same built-in defaults it uses today — never fail to start.
4. WHEN `/the-loop:init` runs THEN it SHALL ask the user (as part of the guided
   onboarding) whether they want a repo-local CLI config scaffolded
   (`.the-loop/cli-config.yaml`, from the shipped template) for this repo, or to rely on
   `~/.the-loop/cli-config.yaml` — never assume one or the other.

### Requirement 3 — No loss of existing behaviour

**User story:** As an existing operator with a working `.the-loop/config.yaml`
`webhooks`/`polling` block, I want a documented, mechanical migration, so that
upgrading doesn't silently stop routing my events.

#### Acceptance criteria (EARS)

1. WHEN an operator moves their existing `webhooks`/`polling`/`observability.eventLog`
   block from `.the-loop/config.yaml` into the new CLI config file (renaming
   `observability.eventLog` to the CLI config's top-level `eventLog`, and setting
   `routing.authorizedUsers` / a poll source's `repos` explicitly — see Requirement 4)
   THEN the daemon SHALL behave identically to before the split.
2. WHEN hot-reload is exercised (edit-while-running) THEN the system SHALL keep
   reloading `webhooks.ghWebhook.routing` / `polling.sources` from the CLI config file,
   not the plugin config file.

### Requirement 4 — The plugin config never feeds the CLI daemon

**User story:** As an operator, I want the CLI daemon to never read a repo's plugin
config for anything — including "convenience" fallbacks — so that `.the-loop/config.yaml`
stays exactly what it claims to be: settings for the Claude/Cursor plugin, nothing else.
(Added per PR #69 review, after the first cut of this work kept one fallback.)

#### Acceptance criteria (EARS)

1. WHEN the webhook receiver or poller resolves `routing.authorizedUsers` THEN the
   system SHALL use exactly the CLI config's configured list — no fallback to any
   repo's `ticketing.github.owner`. An empty/unset list SHALL fail closed (no
   human-authored event is acted on), with a warning naming the CLI config key to set.
2. WHEN a GitHub poll source resolves its `repos` THEN the system SHALL use exactly
   that source's configured `repos` — no fallback to any repo's `ticketing.github`. A
   source with no `repos` SHALL raise a clear error when discovery runs, not silently
   discover zero items or borrow another file's repo.
3. WHEN reviewing `gh_webhook.py`/`poll.py` THEN neither module SHALL import, resolve,
   or read a path to any repo's `.the-loop/config.yaml` for any purpose.

## Non-functional requirements

- **Zero new runtime dependencies** — the split reuses the existing best-effort
  PyYAML-optional loading pattern; a missing/unparseable CLI config degrades to
  built-in defaults exactly like today's missing/unparseable `.the-loop/config.yaml`.
- **Docs parity** — `cli/README.md`, the observability/webhook-triggers capability docs
  and the shipped templates are updated in the same PR (ready-to-ship gate item).

## Security considerations

> Threat-model-lite (`security.threatModel.required`).

- **Actors & trust:** unchanged — GitHub webhook payloads and polled comments remain the
  only untrusted input; the CLI config file itself is operator-authored, same trust
  level as the plugin config today.
- **Trust boundaries & data:** `routing.authorizedUsers` (decision-023's prompt-injection
  guard) still governs which GitHub actors the daemon acts on. Splitting the file
  strengthens this, if anything: the guard now reads *only* the CLI config, with no
  fallback to any repo's plugin config (Requirement 4) — one config surface to reason
  about, not two.
- **Abuse cases (EARS):**
  1. WHEN the CLI config file is world-writable or lives on shared infrastructure THEN
     the system SHALL document (README) that `secretEnv` still names an environment
     variable, never a config value, so the webhook secret is never at rest in either
     config file.
  2. WHEN `THE_LOOP_CLI_CONFIG` or `--config` points at a path the operator does not
     control THEN the system SHALL apply the same strict/lenient parse-error handling
     as today (bad edit logged, previous in-memory config kept) — a hostile file can
     misconfigure routing but not crash the process.
  3. WHEN the CLI is started from a directory the operator does not fully trust (e.g. a
     shared or third-party checkout) and that directory contains a `.the-loop/cli-config.yaml`
     THEN the system SHALL still only apply the same bounded, schema-validated
     `webhooks`/`polling`/`eventLog` keys — never code execution — so the worst a planted
     file can do is misroute/misconfigure the daemon, not compromise the process. Operators
     who do not want cwd auto-discovery pass `--config` explicitly.
- **Fail closed:** an empty/unset `authorizedUsers` in the CLI config SHALL still mean
  no human-authored event is acted on (decision-023) — with no plugin-config fallback
  to silently narrow that exposure instead of the operator setting it explicitly.

## Out of scope

- Relocating runtime *state* (pidfiles, session registry dir, poll-state file, event
  log file) off `.the-loop/...`-relative defaults. Those stay configurable, cwd-relative
  paths — only the config *file itself* moves off the plugin file. Consolidating them
  under the CLI's home directory is a reasonable follow-up but not required to satisfy
  issue #63's literal ask.
- A full schema-driven onboarding for the CLI config (`x-onboarding` groups, ask levels,
  per-key detection) matching the plugin's `/init` machinery — out of proportion for a
  3-key schema. `/the-loop:init` instead asks one plain yes/no question (Requirement 2.4)
  and scaffolds from the shipped template on "yes".
- Per-source `authorizedUsers` (so a multi-repo daemon could trust different logins per
  repo it watches). `routing.authorizedUsers` stays one flat list shared by the
  receiver and every poll source; `polling.sources[].repos` already supports many
  repos under that one list.

## Open questions

None outstanding — @MadaraUchiha-314 confirmed the split (CLI vs. plugin) in issue #63;
requested the configurable `--config`/cwd/home resolution order and the `/init`
onboarding ask, then requested removing the plugin-config fallback entirely, in PR #69
review.
