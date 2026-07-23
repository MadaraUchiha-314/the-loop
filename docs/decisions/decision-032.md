# Decision 032: split the-loop's config into a per-repo plugin config and an independently-configurable CLI config

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #63, PR #69 review)
- **Work item:** issue-63
- **Spec:** `docs/specs/issue-63/`

## Context

`.the-loop/config.yaml` grew to serve two different consumers: the Claude/Cursor
**plugin** (installed per repo; drives `/the-loop:*` commands and the skill working
*that* repo — ticketing, workflow, tooling, reviews, autonomy, security, …) and the
**CLI daemon** (`gh-webhook`/`poll`/`sessions`/`events`), which routes GitHub activity
into harness sessions. Issue #63: "the cli is expected to work across multiple repos and
is not tied to a single repo … the settings for the claude/cursor plugin should be
independent of the CLI configs." Concretely, `polling.sources` already lists arbitrary
`OWNER/REPO` entries, but the file holding that list has to live inside *one* repo's
checkout for the daemon to find it — the CLI's own settings were hostage to whichever
repo happened to be installed with the-loop first.

## Decision

Split into two files with two schemas, and centralize CLI-side config loading in a new
`the_loop.cli_config` module:

- **Plugin config** — `.the-loop/config.yaml` (unchanged location/name), validated by
  `.the-loop/config.schema.json` (trimmed). Everything not named below.
- **CLI config** — a new file, `cli-config.yaml`, validated by a new
  `.the-loop/cli-config.schema.json` (shipped alongside the plugin schema). Holds
  `webhooks` (the `gh-webhook` receiver), `polling` (the poller), and `eventLog` (was
  `observability.eventLog`, flattened — the CLI config has no other reason to carry an
  `observability` wrapper).

The CLI config's **location is operator-configurable**, resolved in priority order:

1. `--config`/`-c` — an explicit CLI flag.
2. `$THE_LOOP_CLI_CONFIG` — an explicit env var, same priority as the flag (whichever
   is set wins; the flag takes precedence if both are).
3. `./.the-loop/cli-config.yaml` — repo-relative to wherever `the-loop <command>` is
   invoked from. Opt-in by construction: it only engages if that file exists, so an
   operator who wants their CLI config tracked and versioned in a specific repo (a
   "dev box" repo, say) gets that by simply putting the file there — no flag, no env
   var, just running the CLI from that checkout.
4. `~/.the-loop/cli-config.yaml` — the operator's home directory, the always-available
   fallback that never privileges any one monitored repo.

`/the-loop:init` also gains one plain yes/no onboarding question: whether to scaffold a
repo-local `cli-config.yaml` for this repo (from the shipped template) or rely on the
home-directory default — never assumed either way.

Consequences:

- **The plugin config never feeds the CLI daemon — no exceptions.** The original cut of
  this decision kept one fallback: `routing.authorizedUsers` and a GitHub poll source's
  `repos` defaulted from the plugin config's `ticketing.github.owner`/`repo` when the
  daemon happened to be started from within the repo it watches. Follow-up review: this
  re-introduced exactly the coupling the split was meant to remove — which repos to
  watch and who may trigger a Claude/Cursor session are CLI-config concerns, full stop;
  `.the-loop/config.yaml` is *only* for the plugin. Both fallbacks are removed:
  `authz.resolve_authorized_users` takes just the configured list (no `owner` param);
  `GitHubPollProvider`/`build_provider` take just the source's own `repos` (no
  `fallback_repos` param) — an empty/unset value means "nothing configured," not "guess
  from wherever this process happens to be running," and both fail closed/raise clearly
  rather than silently borrowing another file's settings.
- **Runtime state paths are unchanged (deliberately out of scope).** Pidfiles, the
  session registry dir, `poll-state.json`, and the event-log path stay configurable,
  cwd-relative `.the-loop/...` defaults. Only the config *file* moved/became
  configurable — see Alternatives.
- **Hot-reload keeps working, now against the right, resolved file.** `Reloader`
  content-hashes whatever `_CONFIG_PATH` points at; `cli.py`'s `main()` resolves
  `--config`/env/cwd/home *before* `gh_webhook.py`/`poll.py` compute their other flags'
  defaults (a small pre-scan — argparse otherwise builds every subcommand's defaults
  before a normal parse would reveal `--config`'s value), then reassigns both modules'
  `_CONFIG_PATH` accordingly.
- **A module-level `set_override`, not a threaded parameter.** The CLI is a short-lived,
  single-invocation process — no concurrent-request state to corrupt — so a settable
  module global (reset every `main()` call, including to `None` so it never leaks
  across repeated calls e.g. under test) fits this codebase's existing style
  (`eventlog._log` is the same shape).
- **Migration is mechanical, and `/the-loop:upgrade-the-loop` performs it, not just
  documents it (PR #69 review).** The initial cut of this decision described the move
  ("existing operators cut the block out and paste it") as something an operator would
  do by hand; review asked whether the upgrade command actually handles it. It didn't —
  fixed: `/the-loop:upgrade-the-loop`'s schema-migration step now names this case
  explicitly (extract `webhooks`/`polling`/`observability.eventLog`, rename `eventLog`,
  ask where the CLI config should live, validate both resulting files, flag an empty
  `authorizedUsers`/`repos` under needs-user since Requirement 4 removed their
  fallback, report the migration as its own line). Verified mechanically against this
  repo's own pre-split config (design doc's Testing strategy).

## Alternatives considered

- **A single fixed global default (`$THE_LOOP_CLI_CONFIG`, else `~/.the-loop/config.yaml`,
  no cwd tier, no flag)** — the first cut of this decision. Simple, and it does satisfy
  "not tied to a single repo," but only by making "global" the *sole* option: an
  operator who wants their CLI config checked in and versioned in a specific repo (a
  real, legitimate use case — PR #69 review) had no supported path there short of an
  env var they'd have to set every session. Superseded by the 4-tier order above, which
  keeps the home-directory default (nothing is *forced* into one repo) while making a
  repo-local, versioned choice equally first-class (nothing *forbids* it either).
- **Relocate runtime state (pidfiles/registry/poll-state/event-log) under the CLI's home
  directory too**, for full consistency with the config file's resolution — deferred. It
  would triple the surface of this change (every documented default path, every
  existing deployment's pidfile/registry location) for a concern neither issue #63 nor
  the review raised; today's cwd-relative defaults already let an operator co-locate
  all daemon state simply by starting it from a chosen directory. Revisit if operators
  ask for it.
- **Keep one file, split only the JSON Schema** (two schemas validating disjoint views
  of the same `config.yaml`) — rejected: does nothing for "not tied to a single repo",
  the actual complaint; a plugin install/upgrade in one repo would still silently carry
  (or clobber) another concern's settings.
- **Per-subcommand `--config` flags** instead of one global flag ahead of the
  subcommand — rejected: repeats the same flag on `gh-webhook`/`poll`/`sessions`/`events`
  for no benefit; a global flag is the standard argparse shape for "one setting affects
  every subcommand."
- **Per-poll-source `authorizedUsers`** (so a multi-repo daemon can trust different
  logins per repo) — deferred; `routing.authorizedUsers` stays one flat list shared by
  the receiver and every poll source, as today. Listed as a re-evaluation trigger in the
  design doc.
- **Keeping the `ticketing.github.owner`/`repos` convenience fallback** (the original cut
  of this decision) — reverted on review: it kept the plugin config in the CLI daemon's
  read path for the single-operator-in-one-repo case, undermining "not tied to a single
  repo" the moment that repo's plugin config happened to be reachable. The cwd tier
  (`./.the-loop/cli-config.yaml`) already covers the same convenience — an operator who
  wants zero-config in one repo puts an explicit CLI config there — without reading a
  file whose *purpose* is the plugin, not the daemon.
