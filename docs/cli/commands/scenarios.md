# `scenarios`

The table of Gherkin scenarios the integration tests cover — so "what is actually tested?"
is a question you can answer without running anything.

```bash
the-loop scenarios [--root .] [--glob PATTERN ...] [--format table|markdown|json]
```

## What it reads

the-loop requires every integration test to carry a Gherkin-syntax docstring naming the
scenario under test:

```python
def test_unauthorized_comment_is_dropped():
    """
    Feature: Authorized-actor guard
    Scenario: A comment from an unlisted login is dropped before dispatch
      Given a receiver with authorizedUsers: [maintainer]
      When a comment authored by stranger arrives
      Then no dispatch happens and the drop reason is unauthorized-actor
    Requirement: docs/specs/issue-15/requirements.md#R4
    """
```

`scenarios` scans for those docstrings and presents them as a table. The optional
`Requirement:` line links the scenario back to the `requirements.md` it proves.

**Language-agnostic**: Python docstrings, JS/TS block comments and Go comments all work.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--root` | `.` | Project root to scan. |
| `--glob PATTERN` | see below | Glob for integration-test files. Repeatable; overrides config and defaults. |
| `--format` | `table` | `table`, `markdown` or `json`. |

### Glob resolution order

1. `--glob` (repeatable), else
2. `testing.integrationTestGlobs` in the repository's
   [harness config](/config/harness-config), else
3. built-in defaults covering common layouts.

## Formats

- **`table`** — for a human at a terminal.
- **`markdown`** — a GitHub-flavoured table, for pasting into a PR briefing.
- **`json`** — machine-readable; includes each scenario's steps and its `file:line`.

```bash
the-loop scenarios --format markdown >> pr-briefing.md
```

When no scenarios are found, `table` and `markdown` warn with the root and globs they
searched — an empty table and a bad glob look identical otherwise. `json` stays silent, so
it remains parseable.

## Why it exists

A coding-agent harness needs to know what is covered before it decides what to write. Making
that queryable — rather than something you learn by reading every test file — is what keeps
"add a test for this" from meaning "add a duplicate test for this".

## See also

- [testing reference](/operating-model/reference/testing) — the docstring convention.
- [testing & contracts](/capabilities/testing-and-contracts) — the capability doc.
