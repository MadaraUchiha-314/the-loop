# Evidence: schema and config validation (T10)

Work item: issue-165 · re-run after the owner's review removed length budgets (PR #168).

## Both configs against the schema

```console
$ make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## Migration and fail-closed cases

`userInteraction.writingStyle` is optional (absent from the schema's `required`),
so a project scaffolded before this change validates unchanged and inherits the
schema defaults. `additionalProperties: false` rejects a re-added budget key and a
typo'd formal register.

```console
writingStyle keys: ['diagramFirst', 'enabled', 'formalRegisters', 'skill']
no `budgets` key — length limits removed on the owner's call (decision-061)

VALID   pre-issue-165 config (no writingStyle block)
REJECTED re-added budgets key -> Additional properties are not allowed ('budgets' was unexpected)
REJECTED typo'd formalRegisters value -> 'typo-register' is not one of ['ears-acceptance-criteria', 'abuse-cases', 'api-contracts', 'schema-descriptions', 'rfc-2119']
```
