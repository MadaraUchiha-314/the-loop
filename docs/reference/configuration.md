# Configuration

the-loop's per-repo configuration is split from its CLI daemon configuration — they
never share keys. See [decision-032](/decisions/decision-032) for why.

## Plugin config — `.the-loop/harness-config.yaml`

Written by `/the-loop:init` (schema-driven guided onboarding — see the
[onboarding reference](/operating-model/reference/onboarding)), validated against
`.the-loop/harness-config.schema.json`. Read by `/the-loop:*` commands and the operating
skill. A subset of keys can be overridden per work item via the markdown front-matter
of that item's spec files.

Top-level sections:

| Section | Covers |
|---------|--------|
| `ticketing` | GitHub or Jira; owner/repo, whether to use GitHub Projects. |
| `repository` | Monorepo tooling (nx/yarn/pnpm/bun), whether scripts run from root. |
| `workflow` | The spec approach, phase list, `specDir`/`capabilitiesDir`, phase label prefix. |
| `tooling` | Per-language package manager, unit/integration test runner, lint, type-check, release tooling. |
| `customInstructions` | User-provided instruction docs the harness reads before working — see [instructions reference](/operating-model/reference/instructions). |
| `testing` | Gherkin docstring requirement, `integrationTestGlobs` for `the-loop scenarios`. |
| `apiSpecs` | Contract-first REST (OpenAPI) / GraphQL (SDL) locations and doc generation. |
| `design` | UI/UX design-artifact directory/format — see [design-artifacts reference](/operating-model/reference/design-artifacts). |
| `hooks` | Pre-commit / pre-push gate lists, commit convention. |
| `observability` | Dev/runtime log levels, browser logging — see [observability reference](/operating-model/reference/observability). |
| `reviews` | Self/critic review counts and stop conditions — see [reviewing reference](/operating-model/reference/reviewing). |
| `autonomy` | Risk-tiered autonomy (1–5) and sensitive-path detection. |
| `security` | Threat-model, design, and review gate requirements — see [security reference](/operating-model/reference/security). |
| `tdd` | TDD mode: `standard` \| `tdd-first` \| `off`. |
| `minimalism` | Generation-time bloat guard — see [minimalism reference](/operating-model/reference/minimalism). |
| `tokenEconomy` | Model routing, thinking effort, output verbosity and other cost levers (advisory only) — see [token-economy reference](/operating-model/reference/token-economy). |
| `selfImprovement` | Learnings index cap and write-gate occurrence threshold. |
| `contextManagement` | Checkpoint-then-reset behaviour at phase/task boundaries — see [context reference](/operating-model/reference/context). |
| `userInteraction` | Diagram format, mandatory PR briefing/education requirements. |
| `notifications` | Which harness-raised events notify which roles (recipients resolve from `.the-loop/collaborators.yaml`). |
| `externalTools` | Inline registry of MCPs/CLIs/skills the harness may use. |

The full, commented template ships at
[`skills/the-loop/templates/harness-config.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/templates/harness-config.yaml)
in the repository.

## Collaborators — `.the-loop/collaborators.yaml`

The single source of truth for who collaborates on the project and how they are
notified ([decision-035](/decisions/decision-035)). CODEOWNERS-like: the stewards of
the repository. Validated against `.the-loop/collaborators.schema.json`.

Each collaborator declares a handle, `kind` (individual/group), `roles`, and their
`notifications`: a per-user `enabled` switch and a list of channels — each with a
`type` (only `slack` for now), its own `enabled` switch, `via`
(`mcp` \| `cli` \| `api` — how the harness interacts with the channel) and
channel-specific `config` (slack: `channel-list`). Recipients of a harness-raised
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

## Everything the-loop manages — `.the-loop/manifest.yaml`

Tracks every file/directory the-loop creates or maintains in a project, so
`/the-loop:upgrade-the-loop` can reconcile a project against the installed plugin
version.

## CLI config — `cli-config.yaml`

Read only by the CLI's daemon commands (`gh-webhook`, `poll`, `sessions`, `events`):
`webhooks`, `polling`, `eventLog`, plus the operator's own `collaborators` (same
structure as `.the-loop/collaborators.yaml`, declared here because the daemon never
reads any repo's collaborators file — [decision-035](/decisions/decision-035)) and
`notifications` (daemon-side event filters: `work-item-spawned`, `dispatch-failed`,
`session-died`, `event-dropped-unauthorized`). Not tied to any one repo — see the
[CLI reference](/cli#two-independent-config-files-decision-032) for the full
resolution order (`--config` flag → `$THE_LOOP_CLI_CONFIG` → repo-relative → home
directory).
