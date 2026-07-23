# Onboarding reference (the guided `/init` config walkthrough)

`/the-loop:init` does not dump a config file on the user and walk away — it
**establishes the config with the user**, group by group, so that by the end of init
they know what they configured and why. This file is the procedure that drives it.

## Sensible defaults: the precedence

Every key gets a proposed value before the user is ever asked. Resolve it in this
order — first hit wins:

1. **Existing answer** — the value already in the project's `.the-loop/config.yaml`
   (re-runs never re-ask or overwrite what was already established).
2. **Detected signal** — what init's project detection found (lock files, manifests,
   CI config, git remote — see `commands/init.md` step 1 and
   `reference/tooling.md` → "Tooling detection").
3. **Schema default** — the `default` in `.the-loop/config.schema.json` (the config
   template mirrors these).

The user is only *asked* where the answer genuinely needs them: keys with no
default and no signal (e.g. `personas`), or groups whose proposal they should
confirm before the harness relies on it.

## The schema drives everything

The single source of truth for the walkthrough is `config.schema.json`:

- **`x-onboarding.groups`** — the ordered list of config groups: which top-level keys
  are clubbed together (because they interact and should be decided together), the
  group's title, a one-paragraph `explain`, and its `ask` level.
- **Per-property schemas** — each key's `description` (what it does and the RULE it
  encodes), `default`, `enum` (ALL legal values), and `examples`.

Never hardcode the group list or key explanations in a command or in conversation
from memory — read them from the schema, so the walkthrough can never drift from
what the config actually accepts.

## Ask levels

Each group carries one of three `ask` levels (`x-onboarding.askLevels`):

| Level | Meaning |
|-------|---------|
| `always` | No sensible default exists. Init MUST establish the group with the user. Non-interactive runs report it under **needs-user** instead. |
| `confirm` | Init proposes values (precedence above) and asks the user to confirm or adjust the group **in one pass** — one interaction per group, not per key. |
| `advanced` | Sensible defaults are applied silently. Walked through only when the user asks for the full tour. |

## How to present a group

For each group, in `x-onboarding.groups` order:

1. **Say what it is.** The group title and its `explain` text — what this part of the
   config controls and why it matters to the loop. Educating the user here is
   mandatory, not optional (`userInteraction.educateUser`).
2. **Show the proposal.** The resolved value for each key in the group, marking where
   it came from: *detected*, *default*, or *already configured*. Detected values name
   their signal (e.g. "`packageManager.ts: pnpm` — from `pnpm-lock.yaml`").
3. **Enums show every possibility.** When a key is an `enum`, list ALL its values with
   a one-line meaning each (from the schema descriptions), and mark the proposed one.
   The user should never have to guess what the alternatives are.
4. **Free-form keys show examples.** Use the schema's `examples` (e.g.
   `ticketing.github.owner: "MadaraUchiha-314"`,
   `sensitivePaths: ["**/auth/**", "**/*secret*"]`) so the expected shape is obvious.
5. **Ask once per group.** Collect the whole group's answers in a single interaction.
   Where the harness has a structured-question UI (e.g. Claude Code's
   `AskUserQuestion`), use it — one question per key that needs deciding, enum values
   as the options, the proposal as the recommended option. Otherwise ask in plain
   chat, compactly.
6. **Offer the fast path.** At any point the user may say "accept defaults for the
   rest" — apply the remaining proposals silently and report them in the final
   summary.

Keys that interact are decided together, never in isolation — e.g.
`repository.monorepo` with `monorepoTool`; `testing.gherkinDocstrings` with
`linkRequirements`; `reviews.*` counts with `autonomy.tiers`. That is exactly what
the grouping encodes.

## Modes

- **Interactive (default).** Run the walkthrough: `always` and `confirm` groups are
  presented; `advanced` groups are defaulted silently and summarized at the end, with
  an offer to tour them too.
- **`--defaults` (non-interactive).** No interaction at all: apply the precedence for
  every key, write the config, and put every un-defaultable gap (the `always` groups'
  empty keys, plus any `# TODO: verify` tooling lines) in the **needs-user** section
  of the final report.
- **`--dry-run`.** Never interacts and never writes: print the report, including what
  the walkthrough *would* ask.

## Re-runs (idempotence)

Onboarding is as idempotent as the rest of init. On a re-run, only **gaps** are
raised: required keys still empty (e.g. `personas: []`), lines still carrying a
`# TODO: verify` marker, and keys newly added by a schema upgrade. Everything already
established is left untouched and never re-asked.

## After the walkthrough

Validate the resulting `.the-loop/config.yaml` against `config.schema.json` and fold
the outcome into init's final report: answered keys under **created/updated**,
untouched ones under **skipped**, and anything still unresolved under **needs-user**
with a pointer to the exact key and an example value.
