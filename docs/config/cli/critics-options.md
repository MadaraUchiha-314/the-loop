# Critic options

Options under the top-level `critics` key — the **critic harnesses** a session may hand its
work to for a second opinion ([issue-108](https://github.com/MadaraUchiha-314/the-loop/issues/108),
[decision-043](/decisions/decision-043)), run by [`the-loop critic`](/cli/commands/critic)
and read by the [review loop](/capabilities/review-loop).

Declared **here**, in the operator's config, since
[issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352)
([decision-123](/decisions/decision-123)): a critic is a harness and a model installed on
the machine that runs the round, and executable configuration belongs in a file no pull
request to a repository can edit. How **many** rounds run is the [`reviews`](#review-rounds) block beside this one (moved
here from the harness config in the same change); **which**
critics exist is yours.

```yaml
critics:
  - name: cursor-gpt          # a harness the-loop has an adapter for needs nothing else
    harness: cursor           # built-in: claude | cursor
    model: gpt-5.5
  - name: aider-review        # any other CLI: the executable and its argv, spelled out
    harness: aider
    model: gpt-5.5
    command: aider            # argv[0] — NOT a shell line
    args: ["--message-file", "{promptFile}", "--model", "{model}", "--no-auto-commits"]
    outputFormat: text
    timeoutSeconds: 900
```

::: danger This is executable config
A critic entry becomes an argv the CLI spawns, with your credentials in scope. Review one
the way you would review code, and **never** put a secret in `env` — name a variable and
keep its value in [`env.file`](/config/cli/#env-file) or the ambient environment.
:::

## Each entry's keys

### `critics[].name`

- **Type:** `string`
- **Default:** none — required, unique across the list

The critic's id: `the-loop critic run <name>` runs it, and the review loop records rounds
under it.

### `critics[].harness`

- **Type:** `string`
- **Default:** `""`

The critic harness/CLI. Free-form so any harness works — it is also the
`[<harness>/<model>]` attribution prefix on every finding. When it names a harness
the-loop has an adapter for (`claude`, `cursor`), the invocation is derived from that
adapter and `command`/`args` may be omitted entirely.

### `critics[].model`

- **Type:** `string`
- **Default:** `""`

The model the critic runs. Passed via the harness's own model flag for a built-in
harness, or wherever `{model}` appears in `args`.

### `critics[].command`

- **Type:** `string`
- **Default:** `""`

The **executable** to spawn (argv[0]) — not a shell line: arguments go in `args`, and
nothing is ever run through a shell. Required for a harness the-loop has no adapter for;
wins over `harness` when both are set.

### `critics[].args`

- **Type:** `array` of `string`
- **Default:** `[]`

argv after the executable. Placeholders are substituted element-wise, never via a shell:
`{prompt}`, `{promptFile}`, `{model}`, `{workItem}`, `{specDir}`, `{cwd}`. With an explicit
`command` the list **must** carry `{prompt}` or `{promptFile}` — otherwise the critic is
handed nothing to review. With a built-in `harness`, these are appended as extra flags to
the derived invocation.

### `critics[].env`

- **Type:** `object` of `string`
- **Default:** `{}`

Environment overlaid on the inherited environment for this critic. Never a secret's
value — name the variable; the child inherits the ambient environment.

### `critics[].cwd`

- **Type:** `string`
- **Default:** the checkout the round is run from (`--root`)

Directory to run the critic in.

### `critics[].outputFormat`

- **Type:** `string` — `text` | `json`
- **Default:** `text`

How to read the critic's stdout. `json` extracts the reviewer's text from the payload
(falling back to raw stdout when it is not JSON); `text` uses stdout verbatim.

### `critics[].timeoutSeconds`

- **Type:** `number`, at least `1`
- **Default:** `900`

Hard bound on one critic round, so a hung critic CLI cannot wedge the review loop.

### `critics[].enabled`

- **Type:** `boolean`
- **Default:** `true`

Set `false` to keep the entry but refuse to run it.

## Review rounds

The top-level `reviews` block — the **review-round policy** the skill follows before it
escalates to a human. Moved here from the repository's harness config in
[issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352): the operator who
runs the rounds sets how many. Every key has a default, so the block may be omitted;
[`the-loop critic policy`](/cli/commands/critic#policy) prints the effective values, and a
harness with no CLI installed follows the same defaults.

```yaml
reviews:
  selfReviewCount: 3
  criticReviewCount: 3
  stopOnNoNewFindings: true
  escalateOnRepeatFinding: true
```

### `reviews.selfReviewCount`

- **Type:** `integer`, at least `0`
- **Default:** `3`

Cap on self-review rounds. The loop stops early when a round yields zero new actionable
findings.

### `reviews.criticReviewCount`

- **Type:** `integer`, at least `0`
- **Default:** `3`

Cap on critic-review rounds, run with the `critics[]` above. Also stops early on zero new
findings; a critic that could not run does not count toward it.

### `reviews.stopOnNoNewFindings`

- **Type:** `boolean`
- **Default:** `true`

Stop the review loop as soon as a round surfaces no new actionable finding.

### `reviews.escalateOnRepeatFinding`

- **Type:** `boolean`
- **Default:** `true`

Diminishing-returns guard: when two consecutive rounds surface the same finding, escalate
to a human instead of looping.
