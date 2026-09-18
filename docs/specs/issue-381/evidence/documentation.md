---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#381"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a work item is armed by a set of labels, all of which must be present

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `webhook-triggers.md` | A Current-behaviour clause stating the every-label-present rule on both ingresses, the poller's provider-side re-check, and the refused-and-migrated old keys; the spawn and PR-direct clauses reworded to "labels" | yes (issue-381) |
| `self-diagnosis.md`, `distribution.md` | **unaffected** — their prose says "the auto-execute label" generically; the guard they describe is unchanged | n/a |
| `channels.md` | **unaffected** — the kickoff's `labels` key is unchanged; the config reference says what to put in it | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/routing-options.md` | `autoExecuteLabel` → `autoExecuteLabels` (type, default, an example with two operators, the upgrade warning); the `labeled` row and the execution-control lead |
| `docs/config/cli/polling-options.md` | `sources[].label` → `sources[].labels`; the example |
| `docs/config/cli/index.md` | current version `0.10.0`; the two keys in the list of refused removals |
| `docs/config/cli/self-diagnosis-options.md`, `channels-options.md` | the label guard and the kickoff `labels` hint name the list |
| `docs/cli/commands/migrate-config.md` | current version; a paragraph on the wrap; the example report |
| `docs/cli/getting-started.md`, `concepts.md`, `state.md`, `commands/sessions.md` | the key and its anchor |
| `docs/guide/slack.md` | every label in `kickoff.labels`; the start-from-Slack paragraph |
| `docs/reports/gh-queries.md`, `labels-and-dashboards.md`, `cli-architecture-survey.md` | the `--label` row (one per label, re-checked), the label section, the arming line |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the two properties (byte-identical copies, pinned) |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | the list, with a commented second entry; version `0.10.0` |
| `skills/the-loop/reference/automation.md` | label-gated auto-execution names the list and says to apply the whole of it |
| `commands/work-on.md`, `commands/execute-tasks.md` | apply **every** label to the issue and to each PR |
| `commands/upgrade-the-loop.md` | the list-of-labels migration step, `0.9.0` → `0.10.0` |
| `docs/decisions/decision-131.md` + index | all-of, and refuse-and-migrate over alias |
| `README.md`, `cli/README.md` | **unchanged, deliberately** — both name the default label by value, which is still the default |
