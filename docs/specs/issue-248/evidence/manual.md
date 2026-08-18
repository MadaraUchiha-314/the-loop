# Evidence: manual exploratory run (T11)

A repository built by hand at `/tmp/.../demo`, declaring one hook module and one
attachment, driven with the real CLI and the real runtime on 2026-08-18.

## The repository

```yaml
# .the-loop/harness-config.yaml
version: "0.2.0"
graph:
  hooks:
    modules:
      - path: .the-loop/hooks/house.py
    attach:
      - hook: x-licence-header
        node: complete
```

```python
# .the-loop/hooks/house.py
from the_loop.graph import HookResult, Message, hook


@hook("x-licence-header")
def licence_header(ctx):
    missing = [p.name for p in (ctx.repo / "src").glob("*.py") if "SPDX" not in p.read_text()]
    if missing:
        return HookResult.blocked(
            "x-licence-header", [Message(text="missing SPDX header", path=p) for p in missing]
        )
    return HookResult.ok("x-licence-header")
```

`src/a.py` starts as `x = 1` — no licence header.

## Inspection, importing nothing (R5.1)

```text
$ the-loop graph --repo <demo> hooks
shipped hooks (19): await-inner-loops, classify-adhoc-reply, classify-feedback,
classify-goal, classify-phase-selection, deliver-assignment, enforces-boundaries-from,
lint-artifacts, log-entry, mcp-call, notify, post-goal-request, post-phase-selection,
publish-artifact, record-feedback, request-review, set-phase-label, validate-artifacts,
verify-tests

this repository declares 1 module(s) and 1 attachment(s) — nothing here has been imported:
  module  .the-loop/hooks/house.py
  attach  x-licence-header → implementation (exit)

`the-loop check <work item>` is what loads them; a declaration that cannot load fails there
rather than being skipped.
```

## The hook gating a node (R1.1, R1.3, R1.4)

```text
$ python -c "…build_runtime(<demo>).evaluate('complete', item)…"
complete: block
`x-licence-header` did not pass:
- missing SPDX header (a.py)

# after writing '# SPDX-License-Identifier: MIT' at the top of src/a.py
after the header is added: pass
```

## A shipped gate still decides first (abuse case 1)

With the same hook attached to `implementation` instead, whose shipped chain starts with
`validate-artifacts`, and a spec folder missing `tasks.md`:

```text
status: block
`validate-artifacts` did not pass:
- required artifact is missing (docs/specs/issue-1/tasks.md)
```

The repository hook never ran: the chain short-circuited at the shipped gate, which is the
property that makes an appended hook unable to relax anything.

## `the-loop check` against the same repository

```text
$ the-loop check issue-1 --repo <demo>
issue-1: UNMET (at phase-selection)
  WAIT   phase-selection
         · waiting for an authorized user to choose the phases and reply `the-loop execute`
  ····   15 node(s) not reached yet
```

The declaration loads on the ordinary `check` path — the module is imported, the graph
compiles, and the work item is reported exactly as it would be without hooks.
