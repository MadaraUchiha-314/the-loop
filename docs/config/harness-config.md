# Harness config

`.the-loop/harness-config.yaml` — the **per-repository** configuration, written by
`/the-loop:init` and read by the `/the-loop:*` commands and the operating skill. It is
what makes "how work is done" a property of the project rather than of whoever is running
the agent. Validated against `harness-config.schema.json`, which ships with the plugin
rather than being copied into your repository — see
[where the schemas live](/config/#where-the-schemas-live).

For the daemon's own, repo-independent settings see the [CLI config](/config/cli/) —
the two never share a key ([decision-032](/decisions/decision-032)).

## Writing it

```text
/the-loop:init            # guided, schema-driven onboarding; idempotent
/the-loop:init --defaults # skip the interaction, take sensible defaults
```

The walkthrough is described in the
[onboarding reference](/operating-model/reference/onboarding). The full commented
template ships at
[`skills/the-loop/templates/harness-config.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/templates/harness-config.yaml).

A subset of keys can be **overridden per work item** through the `overrides` front-matter
of that item's spec markdown, so one unusual work item does not force a project-wide
setting.

## When a repository has no config

the-loop is routinely pointed at a repository that never ran `/the-loop:init` — a poller
source, a webhook delivery, a work item somebody assigned to a cloud session. Such a
repository is worked under the **built-in default**: the same commented baseline
`/the-loop:init --defaults` writes, shipped inside the CLI as
`the_loop/harness-config.default.yaml` so a bare `pip install the-loopy-one` resolves it
with no plugin checkout in sight ([issue #193](https://github.com/MadaraUchiha-314/the-loop/issues/193),
[decision-073](/decisions/decision-073)).

The default is not only held in memory — it is **written into the repository**, once, the
first time the-loop starts working there:

| Where | Adopts? |
|---|---|
| The daemon's ingress→graph coupling (poller and webhook alike), after it has proved via the `origin` remote that the checkout is the work item's own repository | yes — **before the session is spawned**, and it fills in `ticketing.github.owner`/`repo` from the work item |
| `the-loop graph complete` / `advance` / `force` / `skip` | yes |
| `the-loop check`, `the-loop graph status` / `show` | **no** — reads write nothing |
| A **contribution** (`the-loop contribute`, `pdlc-contribution-loop`) | **no** — the-loop was invited into that repository as a guest and stays out of its history ([issue #185](https://github.com/MadaraUchiha-314/the-loop/issues/185)) |

The written file carries a header saying the-loop wrote it and how to replace it with a
considered one, and each write is recorded as `harness.config_scaffolded` in
[`the-loop events`](/cli/commands/events).

Nothing about the repository is **detected** — the baseline's `repository`, `tooling` and
`ticketing.system` values are the template's, not your project's, and only
`ticketing.github.owner`/`repo` are filled in from the work item. Detection and the
questions that go with it are `/the-loop:init`'s job; a scaffolded config is a working
default meant to be tailored, not a survey of your repository.

**An existing config is never opened.** A repository that already carries
`harness-config.yaml` — or the pre-rename `config.yaml` — is left byte-for-byte as it is,
so no inbound event can replace your `autonomy` tiers, `sensitivePaths` or
`reviews.critics[]` with the-loop's defaults. To move an existing config forward, run
`/the-loop:upgrade-the-loop`; to tailor a scaffolded one, run `/the-loop:init`.

## Sections

| Section | Covers |
|---------|--------|
| `ticketing` | GitHub or Jira; owner/repo, whether to use GitHub Projects. |
| `repository` | Monorepo tooling (nx/yarn/pnpm/bun), whether scripts run from root. |
| `workflow` | The spec approach, phase list, `specDir`/`capabilitiesDir`, phase label prefix. |
| `tooling` | Per-language package manager, unit/integration test runner, lint, type-check, release tooling. |
| `customInstructions` | User-provided instruction docs the harness reads before working — see [instructions reference](/operating-model/reference/instructions). |
| `testing` | Gherkin docstring requirement, `integrationTestGlobs` for [`the-loop scenarios`](/cli/commands/scenarios). |
| `apiSpecs` | Contract-first REST (OpenAPI) / GraphQL (SDL) locations and doc generation. |
| `design` | UI/UX design-artifact directory/format — see [design-artifacts reference](/operating-model/reference/design-artifacts). |
| `hooks` | Pre-commit / pre-push gate lists, commit convention. |
| `observability` | Dev/runtime log levels, browser logging — see [observability reference](/operating-model/reference/observability). |
| `reviews` | Self/critic review counts, stop conditions, and the **runnable** `critics[]` entries that [`the-loop critic run`](/cli/commands/critic) spawns — see [reviewing reference](/operating-model/reference/reviewing) and [review-loop](/capabilities/review-loop). |
| `autonomy` | Risk-tiered autonomy (1–5) and sensitive-path detection. |
| `security` | Threat-model, design, and review gate requirements — see [security reference](/operating-model/reference/security). |
| `tdd` | TDD mode: `standard` \| `tdd-first` \| `off`. |
| `minimalism` | Generation-time bloat guard — see [minimalism reference](/operating-model/reference/minimalism). |
| `tokenEconomy` | Model routing, thinking effort, output verbosity and other cost levers (advisory only) — see [token-economy reference](/operating-model/reference/token-economy). |
| `selfImprovement` | Learnings index cap and write-gate occurrence threshold. |
| `contextManagement` | Checkpoint-then-reset behaviour at phase/task boundaries — see [context reference](/operating-model/reference/context). |
| `userInteraction` | Diagram format, mandatory PR briefing/education requirements, and `writingStyle` — the diagram-first rule and formal-language carve-out the bundled `the-loop:writing` skill reads (no length limits, by decision). See [writing-style](/capabilities/writing-style). |
| `notifications` | Which harness-raised events notify which roles (recipients resolve from `.the-loop/collaborators.yaml`). |
| `externalTools` | Inline registry of MCPs/CLIs/skills the harness may use. |

### `reviews.critics[]` is executable config

Each entry becomes an **argv** that `the-loop critic run` spawns — an executable, its
arguments and an environment overlay, in a committed file. Review a critic entry the way
you would review code, and never put a secret in `env`. See
[`the-loop critic`](/cli/commands/critic) for the entry shape and the placeholders it
accepts.

## What the CLI reads from it

The file's primary reader is the agent — the `/the-loop:*` commands and the operating
skill. But the [CLI](/cli/) reads seven of its keys too, and it is worth being precise
about which, because "why is the CLI reading my harness config?" is a fair question
([issue #121](https://github.com/MadaraUchiha-314/the-loop/issues/121)).

The answer is that these seven are the **repository's own policy**, and the CLI is
executing that policy on the repository's behalf. None of them could live in
`cli-config.yaml`: that is one machine-scoped file for a daemon watching N repositories,
the skill already reads the same values, and `check`/`scenarios` run in bare CI checkouts
where no CLI config exists.

| Key | Read by | Why it is the repository's to declare |
|---|---|---|
| `workflow.phaseLabelPrefix` | `check`, `graph`, and the daemon's graph coupling | The `loop:<phase>` label namespace is this project's convention. |
| `workflow.specDir` | `check`, `graph`, and the daemon's graph coupling | Where this project keeps its specs is a fact about its layout. |
| `notifications` | `check`, `graph`, and the daemon's graph coupling | Recipients resolve against this repository's own `collaborators.yaml`. |
| `reviews.critics` | `critic` | The review bar is a property of the project — and the skill reads the same entries, so a second source could make the two disagree. |
| `testing.integrationTestGlobs` | `scenarios` | Where the integration tests live is part of the layout. |
| `ticketing.github` | `check`, `graph`, and the daemon's graph coupling | The repository the ticket was created in is what makes `pr-loops/pr-<n>/` attributable once a work item spans several repositories ([issue #183](https://github.com/MadaraUchiha-314/the-loop/issues/183)). |
| `customInstructions` | `instructions` | Which conventions govern work on this repository is a fact about this repository — and the agent reads the same entries, so a check resolving a different list would verify nothing. |

Everything else in this file is read by the agent alone.

`workflow.specDir` was the one of the five the daemon *claimed* to read but did not:
`routing.graph.specDir` defaulted to `docs/specs` and reached the graph runtime as an
explicit override, so a watched repository's value was never consulted and a repository
that had moved its specs had its graph silently skipped. Fixed in
[issue #123](https://github.com/MadaraUchiha-314/the-loop/issues/123) — that CLI key is
now unset by default and is an override only.

::: tip The rule, in one line
A repository's harness config configures work done **on that repository** — including
when a daemon is the one doing it. It never configures the daemon itself: no checkout
supplies `authorizedUsers`, a poll source's `repos`, a port, or anything else about the
operator's machine. See [decision-044](/decisions/decision-044).
:::

The table above is enforced: `cli/tests/test_harness_config.py` fails the build if the CLI
reads a key that is not listed here, if a key listed here is no longer read, or if any
module other than `the_loop.harness_config` opens the file.

## Collaborators

`.the-loop/collaborators.yaml` — the single source of truth for who collaborates on the
project and how they are notified
([decision-035](/decisions/decision-035)). CODEOWNERS-like: the stewards of the
repository. Validated against the plugin's `collaborators.schema.json`.

Each collaborator declares a handle, `kind` (individual/group), `roles`, and their
`notifications`: a per-user `enabled` switch and a list of channels — each with a `type`
(only `slack` for now), its own `enabled` switch, `via` (`mcp` \| `cli` \| `api` — how the
harness reaches the channel) and channel-specific `config`. Recipients of a harness-raised
notification are resolved from this file by the roles listed in the harness config's
`notifications.events`; decisions themselves always land as ticket/PR comments.

```yaml
collaborators:
  - handle: "@octocat"
    kind: individual
    roles: [engineer, approver]
    notifications:
      enabled: true
      channels:
        - type: slack
          enabled: true
          via: mcp
          config:
            channel-list: ["#the-loop"]
```

::: tip The daemon has its own copy
`cli-config.yaml` carries a `collaborators` list of the same shape, because the CLI daemon
never reads any repository's `collaborators.yaml` — see
[collaborators](/config/cli/observability-options#collaborators).
:::

## Manifest

`.the-loop/manifest.yaml` tracks every file and directory the-loop creates or maintains in
a project, so
`/the-loop:upgrade-the-loop` can reconcile a project against the installed plugin version
instead of guessing what it owns. It also declares the two things the-loop deliberately
does **not** put in a project — `templatesDir` and `schemasDir`, both relative to the
installed plugin — and lists under `deprecated` the paths older versions created so that
upgrading removes them.
