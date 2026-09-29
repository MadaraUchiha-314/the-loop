---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#433"
---

# Documentation: two bugs in the `hooks[]` declaration loader

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Updated in this PR

**[`docs/capabilities/lifecycle-hooks.md`](../../../capabilities/lifecycle-hooks.md)**
— the capability that owns the `hooks[]` declaration and its loader.

- Under *Current behaviour › Declaration and loading*, a new requirement: the key `on` is
  accepted bare as well as quoted, the loader maps the YAML 1.1 boolean back before any
  other rule runs, both spellings on one entry are refused, and an unknown-key refusal is
  a `HooksConfigError` naming the entry and every key whatever its type.
- A history row for issue-433, above issue-344.

**[`docs/config/cli/hooks-options.md`](../../../config/cli/hooks-options.md)**
§ `hooks[].on` — one paragraph: write the key bare or quoted, both load; YAML 1.1 reads the
bare key as a boolean and the loader undoes it; both spellings on one entry are refused.
The page is the reference an operator reads when a declaration is refused, so the trap is
named where they would look for it, without changing the example they copy.

## Not affected, on purpose

- [`docs/cli/lifecycle-hooks.md`](../../../cli/lifecycle-hooks.md) (the guide) and the
  commented example in `.the-loop/cli-config.yaml` — both write the key bare, and that
  spelling now loads. Quoting it there would teach the trap the fix removes.
- `.the-loop/cli-config.schema.json` — the `on` property's description is correct: the
  operator writes `on`, and the loader now reads `on`. It is also a sensitive path, and
  no change to it is needed.
- [`docs/cli/commands/hooks.md`](../../../cli/commands/hooks.md) — the command's contract
  (report or `error:`, exit 0/1) is unchanged; it now gets the right error class from
  the loader, which the page already describes.
- `docs/api-specs/openapi/the-loop.v1.yaml` — no route, parameter or response changed.
- `README.md` — it does not describe the declaration's keys.
- No decision record: nothing overturns a recorded decision. The one choice (normalise
  rather than rename or quote) follows the precedent already in the graph loader and is
  argued in [`bugfix.md`](../bugfix.md) § The fix.
- No learning yet: this is the **second** occurrence of the YAML 1.1 `on` trap in this
  codebase (the first was the graph loader's edge `on`). The write-gate is the rule of
  three; a third occurrence should mint the learning "a bare `on:` key is `True` under
  `yaml.safe_load`; normalise it in every loader that accepts the key".
