# Evidence: lint, format, types, markdown and config validation (issue-277)

Re-run after the owner's ruling ([decision-100](../../../decisions/decision-100.md)) added
the `create`/`delete` verbs.

## `make lint` — ruff

```text
All checks passed!
```

## `make lint` — markdownlint

```text
Summary: 0 error(s)
```

## `make format-check`

```text
257 files already formatted
```

## `make typecheck` — pyright

```text
0 errors, 0 warnings, 0 informations
```

## `make validate` — every config against its schema

The `standingSessions` block is validated here in three places: this repository's own
config, the shipped template, and (through the packaged copy) whatever an operator writes.
A **created** session is not validated here — it never touches a config file — which is
why its name, `cwd` and harness are checked in code instead.

```text
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## The dashboard — `bun run lint && bun run test && bun run build` in `ui/`

The dashboard has its own toolchain (bun, oxlint, vitest) and its own CI job, so it is
verified separately from the Python suite.

```text
$ bun run lint
$ oxlint --type-aware          # clean, no findings

$ bun run test
Test Files  12 passed (12)
     Tests  157 passed (157)   # 149 before; +8 for the Standing screen

$ bun run build                # `tsc --noEmit` then vite
dist/assets/index-Iowr0hRB.css   29.93 kB │ gzip: 5.76 kB
dist/assets/index-D7q8B5Vu.js   287.59 kB │ gzip: 88.44 kB
✓ built
```
