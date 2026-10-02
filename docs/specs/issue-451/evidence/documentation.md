# Documentation (issue-451)

## Capability docs

| Doc | What changed |
|-----|--------------|
| `docs/capabilities/interactive-sessions.md` | a requirement bullet for the default model (which launches get it, read at launch, grammar, per-harness, probed, refused-drop, unset behaviour); the re-validation bullet now says where a dropped choice lands; a history row |

## Documentation

| Doc | What changed |
|-----|--------------|
| `docs/config/cli/harnesses-options.md` | a `harnesses[].defaultModel` section (when it applies, unset behaviour, argv shape, precedence, grammar, read-at-launch and drift, probe and warnings, what does not read it); the example and the key list name it |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the `defaultModel` property, with the model-name pattern |
| `docs/cli/commands/models.md` | `list`/`check` name each harness's `defaultModel` among the combinations |
| `skills/the-loop/templates/cli-config.yaml` | the commented example harness entry carries `defaultModel` |
| `skills/the-loop/reference/workflow.md` | the phase-selection model section says what an unticked section runs on, and that `do`/`contribute`/`review` get the same default |

`README.md` and `skills/the-loop/SKILL.md` were not changed: neither describes how a
session's model is resolved below "which model and how much effort" at the gate, and
that sentence is still true.
