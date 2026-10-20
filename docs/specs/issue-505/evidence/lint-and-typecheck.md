---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Regression: the whole suite, lint and types (T11)

## `uv run pre-commit run --all-files`

```text
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

The first run failed pyright with five errors: `RoomsResult.routed` was still typed
`List[int]`, and pyright cannot bind a zero-argument `Callable` class variable. Both were
fixed (`List[Tuple[int, str]]`, and `Callable[..., Any]`, the same shape
`ChannelState.publisher` gets away with), and the second run passed.
