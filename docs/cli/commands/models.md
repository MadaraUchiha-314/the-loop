# `models`

What this machine's harnesses will **actually** run — measured, not assumed.

```bash
the-loop models list [--format table|json]
the-loop models check [--refresh] [--format table|json]
```

You declare models and effort levels in the
[CLI config](/config/cli/harnesses-options); this is what makes the declaration true.

## Why a measurement at all

A model name is the **provider's** identifier — `opus-5`, `fable-5.1`, `gpt-5.6-sol` —
and the-loop neither normalises it nor parses it for a vendor. So the only way to know
whether *this* machine's Claude Code can run `gpt-5.6-sol` is to ask it.

That measurement is also what lets [`models`](/config/cli/harnesses-options#models) be a
plain list with no harness attached: the model × harness relation is **observed**, not
declared ([decision-124](/decisions/decision-124)).

The rule the two halves follow: **a declaration may narrow, only the probe may confirm.**

## `list`

Prints the declared combinations and whatever is already known, asking nothing:

```console
$ the-loop models list
Harness  Kind    Name         Verdict   Checked
claude   model   opus-5       ok        2m ago
cursor   model   gpt-5.6-sol  unprobed  —
claude   effort  xhigh        refused   2m ago
```

## `check`

Asks. Each row is one non-interactive run of that harness with a fixed the-loop prompt —
**never any text from a work item** — plus the arguments the choice resolves to.

```console
$ the-loop models check
Harness  Kind    Name         Verdict  Checked
claude   model   opus-5       ok       0s ago
cursor   model   gpt-5.6-sol  ok       0s ago
claude   effort  xhigh        refused  0s ago
```

| Verdict | Means | Effect on a work item |
|---|---|---|
| `ok` | the harness accepted it | offered on the phase-selection checklist |
| `refused` | the harness itself said no | **not offered**, and never spawned onto |
| `unknown` | the run could not start at all (no binary, no network) | still offered |

`unknown` staying offerable is deliberate: a machine with no harness installed must not
silently lose a capability you declared. Only a harness *refusing* withholds one.

Verdicts are cached for 24 hours under
[`<root>/local/model-verdicts.json`](/cli/state#availability-verdicts-root-local-model-verdicts-json),
keyed by the argv probed — so a changed flag, or a changed adapter mapping, asks again
rather than standing for something nobody tested. `--refresh` re-probes everything.

::: warning `check` runs your harness, which may cost tokens
Each probe is one real invocation. It is the cheapest one that still proves the arguments
were accepted, and it runs only here, at daemon start, and on a single stale-verdict
re-probe — never on the delivery path.
:::

## Exit codes

| Code | Meaning |
|---|---|
| `0` | every declared combination is `ok` or `unknown` |
| `1` | at least one is `refused` |
| `2` | the declaration itself is wrong (two default harnesses, say) |

Configuration problems are printed as findings beneath the table, which is where they
belong: a spawn should never be the thing that discovers a config mistake.

## What it is not

It does **not** enumerate what models exist. the-loop discovers nothing — it validates
what you declared. There is no stable machine-readable catalogue across harnesses,
accounts and CLI versions, and a fetched list would go stale between the fetch and the
spawn anyway.
