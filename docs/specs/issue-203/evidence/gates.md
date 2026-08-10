# Evidence — whole suite and repository gates (issue-203)

The same commands CI runs (`hooks.prePush` = lint, typecheck, unit-test; local == CI by
`reference/tooling.md`). Captured after the last change to the branch.

## `make test`

```console
$ make test
uv run --project cli python -m pytest -q cli
........................................................................ [ 96%]
.....................................................................    [100%]
1796 passed, 1 skipped in 68.00s (0:01:08)
```

1796 passed against 1782 before this work item: the 6 precedence/abuse tests (2 of them
parametrised over both transports, so 9 test ids), the 3 integration scenarios, and 2
regression guards. The single skip is pre-existing and unrelated.

## `make lint`

```console
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 556 file(s)
Summary: 0 error(s)
```

Markdown is linted too, which is the gate the spec chain, the decision record and the
docs page all pass through.

## `make format-check`

```console
$ make format-check
uv run ruff format --check cli hooks
189 files already formatted
```

## `make typecheck`

```console
$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

Pyright is why `_slack()` in the unit tests narrows its `resolve()` result with an
`isinstance(provider, _SlackBase)` assertion instead of reaching through the `Integration`
protocol: the protocol deliberately exposes `call` and nothing else, and the narrowing
doubles as the claim that both transports share one URL resolver.

## `make validate`

```console
$ make validate
uv run python scripts/validate_config.py
… 7 configs
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

All 7 configs VALID, including both CLI configs — neither of which sets an inline `url`,
which is the point: the property is optional and a config written before this change is
unchanged and still valid.
