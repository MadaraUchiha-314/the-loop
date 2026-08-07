# Evidence — lint, formatting, types, markdown

> Work item: [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172) ·
> captured 2026-08-07.
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

Pyright's first run over the new tests flagged seven `reportOptionalMemberAccess` errors —
`resolve_link()` returns `Optional[WorkItemRef]`, and the tests were reading `.ref` off it
directly. Fixed at the assertion rather than by silencing the rule: the unit tests go through
a `bound_ref()` helper that asserts the binding is present and returns its `.ref`, so a
missing binding now fails with *"no binding recorded for …"* instead of an `AttributeError`.

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

No schema changed in this work item — the binding introduces no configuration key. This runs
because `make check` runs it, and a clean result is the assertion that nothing was added that
should have been declared.
