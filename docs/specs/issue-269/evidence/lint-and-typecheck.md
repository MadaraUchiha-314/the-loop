# Evidence — lint, format and type check

## `ruff check` / `ruff format`

```sh
uv run ruff check cli hooks
uv run ruff format --check cli hooks
```

The first run raised two findings, both fixed rather than quietly dropped:

- `F541 f-string without any placeholders` — a test fixture body in
  `test_webhook_routing_integration.py` written with an `f` prefix it did not need.
- three files needed `ruff format` (`test_routing.py`, `announce.py`, `router.py`) — line
  wrapping in the new blocks.

After the fixes:

```text
All checks passed!
244 files already formatted
```

## `pyright`

```sh
uv run pyright cli
```

```text
0 errors, 0 warnings, 0 informations
```

## Config validation

```sh
uv run python scripts/validate_config.py
```

```text
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

No configuration key was added, removed or changed by this work item, so nothing here
could have moved — the run is the proof that it did not.

## Markdown

```sh
npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-269/**/*.md"
```

The first run raised four `MD049/emphasis-style` findings — two placeholder lines written
with underscores where this repository's rules want asterisks (`design.md` §Review comments,
`testing-plan.md` §Verification results). Fixed:

```text
Summary: 0 error(s)
```
