# Evidence — lint, formatting, types, markdown

> Work item: [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172) ·
> captured 2026-08-07, re-run after the owner-review rebuild to the endpoint model.
>
> The same four tools CI runs, invoked through the repository's own `Makefile` targets
> (`make lint`, `make format-check`, `make typecheck`) — local and CI parity is the point
> (`hooks.prePush`, `reference/tooling.md`). Nothing needed redaction: every line below is a
> tool banner or a count.

## `ruff check` — lint

```console
$ uv run ruff check cli hooks
All checks passed!
```

## `ruff format --check` — formatting

```console
$ uv run ruff format --check cli hooks
167 files already formatted
```

`ruff format` reflowed one file during implementation (`cli/tests/test_routing.py`, a chained
comparison in the new `pr_work_item` test); the reflowed form is what is committed.

## `pyright` — types

```console
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

Pyright's first run over the new tests flagged `reportOptionalMemberAccess` errors —
the registry's resolvers return `Optional[Session]`, and early drafts read attributes off
them directly. Fixed at the assertions (explicit `is not None` narrowing), not by
silencing the rule.

## `markdownlint` — documentation

```console
$ npx markdownlint-cli2@0.18.1 "**/*.md"
Linting: 443 file(s)
Summary: 0 error(s)
```

One MD051 (invalid link fragment) was raised and fixed while writing `docs/cli/state.md`: a
cross-reference into the new *Session binding* heading, whose `—` and backticked path do not
produce the anchor the plain slug rule predicts. Replaced with the file name in bold rather
than guessing at an anchor that a docs-site upgrade could change.

## `validate_config.py` — schema validation

```console
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

One schema entry was added in this work item — `routing.tmux.sessionPerPr`
(`.the-loop/cli-config.schema.json`), documented in
`docs/config/cli/routing-options.md`; the docs-parity tests (P3/P4) pin the two against
each other, and this validation run is the assertion the schema still parses and every
shipped config still conforms.
