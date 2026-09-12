# Harness config

`.the-loop/harness-config.yaml` — the **per-repository** configuration, written by
`/the-loop:init` and read by the `/the-loop:*` commands and the operating skill. It is
what makes "how work is done" a property of the project rather than of whoever is running
the agent. Validated against `harness-config.schema.json`, which ships with the plugin
rather than being copied into your repository — see
[where the schemas live](/config/#where-the-schemas-live).

**The CLI never reads this file.** Since
[issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352)
([decision-123](/decisions/decision-123)) it is the agent's alone. Everything the CLI
used to take from it has another home — the table below says where — and the skill tells
the agent what to hand the CLI as flags. For the daemon's own settings see the
[CLI config](/config/cli/); the two never share a key ([decision-032](/decisions/decision-032)).

Why the file exists at all, and what it looked like before it shrank, is the audit in
[Is `harness-config.yaml` required?](/reports/harness-config-audit).

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
source, a webhook delivery, a work item somebody assigned to a cloud session. The agent
works such a repository under the **schema's defaults** — the same baseline
`/the-loop:init --defaults` writes — and says so in the execution log. Nothing writes a
config into the repository on its behalf: until issue-352 the daemon *adopted* an
unconfigured checkout by planting the-loop's default there before the spawn
([issue #193](https://github.com/MadaraUchiha-314/the-loop/issues/193)); a CLI that
reads no harness config has no reason to write one, so that path is gone, along with the
`harness.config_scaffolded` event. Run `/the-loop:init` in the project when you want the
file.

## Sections

| Section | Covers |
|---------|--------|
| `repository` | Monorepo tooling (nx/yarn/pnpm/bun), whether scripts run from root. |
| `workflow` | Where the-loop's checked-in knowledge lives (`specDir`/`capabilitiesDir`/`learningsDir`). The phases are the [process graph's](/capabilities/process-graph) and the labels are `loop:<phase>`, fixed — neither is configured. A project which **publishes** its `docs/` tree publishes its learnings with it unless `learningsDir` points elsewhere. |
| `tooling` | Per-language package manager, unit/integration test runner, lint, type-check, release tooling. |
| `customInstructions` | User-provided instruction docs the agent reads before working — see [instructions reference](/operating-model/reference/instructions). The agent passes them to [`the-loop instructions`](/cli/commands/instructions) as `--doc`. |
| `testing` | Gherkin docstring requirement, `integrationTestGlobs` — which the agent passes to [`the-loop scenarios`](/cli/commands/scenarios) as `--glob`. |
| `apiSpecs` | Contract-first REST (OpenAPI) / GraphQL (SDL) locations and doc generation. |
| `design` | UI/UX design-artifact directory/format — see [design-artifacts reference](/operating-model/reference/design-artifacts). |
| `hooks` | Pre-commit / pre-push gate lists, commit convention. |
| `observability` | Dev/runtime log levels, browser logging — see [observability reference](/operating-model/reference/observability). |
| `reviews` | Self/critic review counts and stop conditions. **Which** critics exist is the operator's [`critics[]`](/config/cli/critics-options) — see [reviewing reference](/operating-model/reference/reviewing) and [review-loop](/capabilities/review-loop). |

## What moved out of it in issue-352

The CLI used to read eight keys from this file ([decision-044](/decisions/decision-044),
now superseded). Each has a new home. The file also lost the keys nothing read, and the
nine blocks that configured behaviour which is now simply the-loop's rule — the same in
every repository, so not a setting:

| Was in the harness config | Now |
|---|---|
| `workflow.specDir` *(still here, for the agent)* | The CLI resolves the same directory from its own [`routing.graph.specDir`](/config/cli/routing-options#graph-specdir) (default `docs/specs`), or `--spec-dir` on [`check`](/cli/commands/check) and [`graph`](/cli/commands/graph). A repository that moves its specs sets both. |
| `workflow.phaseLabelPrefix` | Removed. Labels are `loop:<phase>`, one vocabulary everywhere. |
| `workflow.phases` | Removed. The graph is the only phase list; `/the-loop:init` creates the labels from it. |
| `ticketing` | Removed. A work item's ticket is its ref (`github:owner/repo#n`); in-session the CLI derives the repository from the checkout's `origin` remote when no `--ref` is given. |
| `notifications` | Removed. The graph's `notify` hook publishes on the event bus; which channel receives what is [`channels.<name>.subscribe`](/config/cli/channels-options) in the CLI config. |
| `reviews.critics[]` | The CLI config's top-level [`critics[]`](/config/cli/critics-options), same entry shape. `reviews.criticReviewCount` stays here. |
| `graph.hooks` | The CLI config's [`routing.graph.hooks`](/config/cli/routing-options#graph-hooks), same shape; a `path` resolves against each checkout. |
| `testing.integrationTestGlobs` *(still here, for the agent)* | [`the-loop scenarios --glob`](/cli/commands/scenarios). |
| `customInstructions` *(still here, for the agent)* | [`the-loop instructions --doc … --on-missing …`](/cli/commands/instructions). |
| `workflow.specApproach`, `workflow.requireHumanReviewPerPhase`, `localOrchestration` | Removed — read by nothing. |
| `autonomy` | Removed — the rule is fixed: risk tiers 1–2 are autonomous-complete, 3–4 human-approves-pr, 5 human-approves-spec-and-pr; the tier is inferred from the change (default 3), and a fixed set of sensitive paths (schemas, `.the-loop/**`, `.github/workflows/**`, auth/secret/credential paths) raises it. See the [workflow reference](/operating-model/reference/workflow). |
| `security` | Removed — the rule is fixed: every requirements/bugfix carries a Security considerations section, the design enforces the trust boundaries, a security review passes at the ready-to-ship gate (the built-in security-review skill when available, else the checklist), and tier 4+ waits for a named human security sign-off. See the [security reference](/operating-model/reference/security). |
| `tdd` | Removed — the rule is fixed: `standard`, always — tests alongside the implementation, a bug fix reproduced red first. See the [workflow reference](/operating-model/reference/workflow). |
| `minimalism` | Removed — the rule is fixed: always on, at standard intensity, per the ladder in the [minimalism reference](/operating-model/reference/minimalism). |
| `tokenEconomy` | Removed — the rule is fixed: the [token-economy reference](/operating-model/reference/token-economy) is guidance, always advisory. The harness runs whatever model the operator chose (no routing table); thinking effort and verbosity follow the guidance's stage table; disclosure, sub-agent delegation, compaction and telemetry are practices, not switches. |
| `selfImprovement` | Removed — the rule is fixed: learnings are always on, the index stays under 200 lines, a learning is written at the third occurrence. `workflow.learningsDir` stays. See the [workflow reference](/operating-model/reference/workflow). |
| `contextManagement` | Removed — the rule is fixed: clear at a phase boundary, compact after each task, never clear mid-task. See the [context reference](/operating-model/reference/context). |
| `userInteraction` | Removed — the rule is fixed: mermaid diagrams; the PR briefing (the bundled `pr-briefing.md` template, condensed, with diagrams) is required before human review; educating the user is mandatory; the writing contract is the bundled `the-loop:writing` skill — diagram-first, fixed formal registers, no length limits ([decision-061](/decisions/decision-061)). See [writing-style](/capabilities/writing-style). |
| `externalTools` | Removed, nothing replaces it: the harness discovers its tools (MCP servers, plugins, skills, CLIs) itself. |

`/the-loop:upgrade-the-loop` performs the migration (harness config `0.2.0` → `0.3.0`) and
[`the-loop migrate-config`](/cli/commands/migrate-config) the CLI config's half
(`0.8.0` → `0.9.0`).

::: tip The rule, in one line
The harness config is the **agent's**: it describes how work is done in this repository,
and the agent reads it in every session. The CLI is the **operator's** and reads only the
operator's `cli-config.yaml`. What the CLI needs from a repository, the agent hands it as
a flag. See [decision-123](/decisions/decision-123).
:::

## Collaborators

`.the-loop/collaborators.yaml` — the single source of truth for **who** collaborates on
the project and in which **roles** ([decision-035](/decisions/decision-035)).
CODEOWNERS-like: the stewards of the repository. Validated against the plugin's
`collaborators.schema.json`.

Each collaborator declares a handle, `kind` (individual/group) and `roles`. Roles are what
everything else targets: the loop pulls a phase's required reviewers and approvers from
this file. Decisions themselves always land as ticket/PR comments — the paper trail.

```yaml
collaborators:
  - handle: "@octocat"
    kind: individual
    roles: [engineer, approver]
```

::: warning People, not delivery
A collaborator declares no channel of their own. Until issue-304 this file also carried a
per-person `notifications` block — an `enabled` switch, a channel `type`, a `via`
transport and a `channel-list` — and **no code ever read it**, so an operator who filled it
in configured nothing and was never told.

A notification goes to a **channel**: one Slack bot for the whole daemon, configured under
[`channels.slack`](/config/cli/channels-options) in the CLI config and subscribed to the
events you want by name. Per-person routing is not built. A `collaborators.yaml` still
carrying the old block is refused by the schema, with `channels.slack` and
[`the-loop migrate-config`](/cli/commands/migrate-config) named in the message.
:::

## Manifest

`.the-loop/manifest.yaml` tracks every file and directory the-loop creates or maintains in
a project, so
`/the-loop:upgrade-the-loop` can reconcile a project against the installed plugin version
instead of guessing what it owns. It also declares the two things the-loop deliberately
does **not** put in a project — `templatesDir` and `schemasDir`, both relative to the
installed plugin — and lists under `deprecated` the paths older versions created so that
upgrading removes them.
