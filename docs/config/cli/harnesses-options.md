---
configBase: ""
---

# Harnesses, models and effort

Three top-level sections say **what a session can be run as**: which harnesses this machine
has, which models a work item may be put on, and how much effort it may be asked for.

```yaml
harnesses:
  - name: claude
    default: true
    args: ["--dangerously-skip-permissions"]
  - name: cursor

models:
  - opus-5
  - fable-5.1
  - name: gpt-5.6-sol
    harnesses: [cursor]

effort:
  - low
  - medium
  - high
  - xhigh
  - max
  - ultra
```

They sit at the top level, beside [`repositories`](/config/cli/repositories-options) and
[`critics`](/config/cli/critics-options), rather than under
[`routing`](/config/cli/routing-options). `routing` configures how an event *reaches* a
session; these configure what a session *is*. A work item then picks a model and an effort
level at the `phase-selection` gate, and the choice is frozen with the rest of that gate's
answers ([issue-358](https://github.com/MadaraUchiha-314/the-loop/issues/358),
[decision-124](/decisions/decision-124)).

## Two rules carry the whole design

**A declaration may narrow; only the probe may confirm.** Nothing you write here asserts
that a harness can run a model. `the-loop models check` asks the harness and caches the
answer, and only an `ok` (or an unprobed `unknown`) makes a model offerable. What a
declaration *can* do is restrict which combinations are offered and probed at all.

**the-loop owns the effort vocabulary; the provider owns the model name.** An effort level
is a the-loop concept that harnesses spell differently, so there is one enum and each
adapter translates it. A model name is the provider's identifier, so it is copied verbatim
and never parsed for a vendor.

## The declarations

## The harnesses

The `harnesses` list declares the agent harnesses this instance has. Unset, the-loop falls
back to [`routing.defaultHarness`](/config/cli/routing-options#defaultharness), which is
what every install written before this key has.

The agent harnesses this instance has. `models` and `effort` refer to these names, and a
work item's harness is what decides which models it may be offered.

Today an entry carries `name`, `default` and `args`. The other three per-harness keys —
[`routing.harnessTrust`](/config/cli/routing-options#harnesstrust),
[`routing.harnessPlugins`](/config/cli/routing-options#harnessplugins) and
[`routing.defaultHarness`](/config/cli/routing-options#defaultharness) — belong here by
exactly the same argument, and moving them is a named follow-up rather than a silent
migration.

### `harnesses[].name`

- **Type:** `string`
- **Default:** none — required

The harness's name as the-loop's adapters know it: `claude` or `cursor`. A name with no
adapter is declared but unusable; `the-loop models check` reports that rather than letting
a spawn discover it.

### `harnesses[].default`

- **Type:** `boolean`
- **Default:** `false`

Whether an unmatched event spawns on this harness. With no entry claiming it, the-loop
falls back to `routing.defaultHarness`. Two entries claiming it is a config error — a work
item's harness decides which models it may be offered, so it cannot be ambiguous.

### `harnesses[].args`

- **Type:** `string[]`
- **Default:** `[]`

Extra CLI arguments every session on this harness is launched with. This is the new home of
`routing.harnessArgs.<harness>`, which still works and warns.

A work item's own model and effort are **appended** to this list, never merged into it:

```text
harnesses[].args        →  --dangerously-skip-permissions
+ the model's args      →  --model fable-5.1
+ the effort's args     →  (whatever that harness's adapter produces)
```

the-loop does not remove, rewrite or reorder an argument you declared, and never adds a
permission flag you did not. If your list already carries the same flag a choice would
append, `the-loop diagnose` warns — whether the appended one wins is the harness's own
argument-parsing rule, not the-loop's to assert.

## The models

The `models` list declares the models a work item may be put on, in each provider's own
naming convention. Unset — the default — **offers no model choice**, exactly as before this
key existed.

An entry is either a **bare name** (the common case) or a **mapping** that narrows it:

```yaml
models:
  - opus-5                      # candidate for every declared harness
  - fable-5.1
  - name: gpt-5.6-sol
    harnesses: [cursor]         # narrowed: offered and probed on cursor only
    about: for the OpenAI-shaped work
```

A name matches `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`. That grammar is the guard, not
decoration: the name is passed to the harness's own model flag **verbatim**, and this is
what makes copying a provider's spelling safe — a name can never be a flag, a path or a
shell fragment. An entry that declares no usable name contributes nothing, so a fault can
only ever shrink the set.

**A name is not tied to a harness.** Which harness can run which name is measured:

```text
                 claude        cursor
  opus-5         ok            refused
  fable-5.1      ok            refused
  gpt-5.6-sol    refused       ok
```

There is deliberately **no `args` escape hatch** on a model. A harness with no model flag
cannot be handed a model at all, so it is offered no model section rather than given a
hand-written flag that nothing validates.

### `models[].name`

- **Type:** `string`
- **Default:** none — required in the mapping form; a bare string entry *is* the name

The model's name as its provider spells it. the-loop neither normalises it nor parses it
for a vendor.

### `models[].harnesses`

- **Type:** `string[]`
- **Default:** unset — the model is a candidate for **every** declared harness

Narrow this model to these declared harnesses: it is offered only on them, and probed only
against them — which is also how you keep the probe matrix small. A harness named here that
you did not declare in `harnesses` contributes nothing.

This **narrows; it never confirms.** A harness that refuses the model still refuses it, so
a declaration here can never assert support that does not exist.

### `models[].about`

- **Type:** `string`
- **Default:** `""`

One line rendered beside the model's row on the phase-selection checklist — what a human
picking between two models wants to know.

## The effort levels

### `effort`

- **Type:** `string[]` — each one of `low`, `medium`, `high`, `xhigh`, `max`, `ultra`
- **Default:** `[]` — unset offers no effort choice

Which of the-loop's effort levels this instance offers. There are **no flags in this
section, by design**: an operator writing a per-harness effort flag is how two configs come
to disagree about what `high` means. The vocabulary is one enum; each adapter translates it.

The enum is the **union** of what the harnesses the-loop knows about can express, which is
what makes it a normalisation rather than an invention:

| the-loop | Claude Code | Codex |
|---|---|---|
| `low` | low | Low *(its default)* |
| `medium` | medium | Medium |
| `high` | high | High |
| `xhigh` | xhigh *(its default)* | **Extra high** |
| `max` | max | Max |
| `ultra` | — | Ultra |

Two rows carry the argument for the whole design. **`xhigh`** is one concept with two
spellings — which is exactly why an operator should not be writing per-harness flags.
**`ultra`** is a level only one harness has, so it is simply not offered for the other: a
harness that cannot express a level returns no arguments for it, and the row never appears
on that work item's checklist.

A level a given harness cannot express is simply not offered for a work item on that
harness, and `the-loop models check` says which levels each harness supports.

::: warning No adapter ships an effort mapping yet
Neither `claude` nor `cursor-agent` exposes a CLI flag for thinking effort today, so
declaring `effort` currently offers nothing. the-loop does not invent a flag: a mapping is
added when a harness has one, read from that CLI's own `--help`, and then validated by the
same probe that validates a model. Declaring the section now is harmless and starts working
the day an adapter gains a mapping.
:::

## Checking what your declarations actually buy you

```console
$ the-loop models check
harness  kind    name          verdict   checked
claude   model   opus-5        ok        2m ago
claude   model   fable-5.1     ok        2m ago
claude   model   gpt-5.6-sol   refused   2m ago
cursor   model   gpt-5.6-sol   ok        2m ago
claude   effort  high          refused   (no mapping on this adapter)
```

Each row is one non-interactive run of the harness with a fixed the-loop prompt — never any
text from a work item — and the verdicts are cached for 24 hours, keyed by the argv probed,
so a changed flag or a changed mapping asks again. `unknown` (the harness could not be run
at all) stays offerable: a machine with no binary installed must not silently lose a
capability you declared.

## What a work item does with them

The `phase-selection` checklist grows two independent sections — one per offerable model,
one per offerable effort level — answered by the same authorized `the-loop execute` that
already freezes the phases, the outer-loop surface and `sessionPerPr`. The choice is
recorded on the work item, applied at every spawn and respawn, and shown by
`the-loop sessions list`.

A work item that picks nothing runs on `harnesses[].args` alone, exactly as every work item
did before this feature existed.
