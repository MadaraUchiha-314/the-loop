# `critic`

The seam by which the harness doing the work hands it to a **different** harness for a
critic round, and reads back what it said.

```bash
the-loop critic list [--root .] [--format table|json]
the-loop critic run <name> (--prompt TEXT | --prompt-file PATH)
                    [--root .] [--cwd DIR] [--work-item ID] [--spec-dir PATH]
                    [--timeout SECONDS] [--output-file PATH]
```

A review is worth more when it comes from a model that did not write the code. This command
is how that happens without either harness knowing about the other.

## Where critics come from

`critics[]` in **your** [CLI config](/config/cli/critics-options) — not any repository's
harness config, since [issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352):
a critic is a harness and a model installed on the machine that runs the round. The same
file says how many rounds to run — its [`reviews`](/config/cli/critics-options#review-rounds)
block, printed by [`policy`](#policy) — and, with `critics[]`, with what. Each entry is
either:

- a **`harness`** the-loop has an adapter for — `claude`, `cursor` — where the invocation is
  derived; or
- an explicit **`command`** (argv[0]) plus **`args`**, with element-wise placeholders:
  `{prompt}`, `{promptFile}`, `{model}`, `{workItem}`, `{specDir}`, `{cwd}`.

`env` overlays the inherited environment, and `outputFormat`, `timeoutSeconds`, `cwd` and
`enabled` complete the entry.

::: danger This is executable config
A critic entry becomes an argv the CLI spawns, with your credentials in scope. Review one
the way you would review code, and **never** put a secret in `env`.
:::

## `list`

Every configured critic with its executable and whether that executable is available.

| Flag | Default | Meaning |
|------|---------|---------|
| `--root` | `.` | Project root — the default working directory for a round. |
| `--format` | `table` | `table` or `json`. |

## `policy`

The review-round policy the skill follows — the CLI config's `reviews` block with every
key defaulted, so the output is the same shape whether or not the block exists.

| Flag | Default | Meaning |
|------|---------|---------|
| `--root` | `.` | Project root (kept for the route's shape; the policy is the operator's, not the repository's). |
| `--format` | `text` | `text` (one `key: value` per line) or `json`. |

```json
{
  "selfReviewCount": 3,
  "criticReviewCount": 3,
  "stopOnNoNewFindings": true,
  "escalateOnRepeatFinding": true
}
```

A harness with no CLI installed follows these same defaults; the skill's
[reviewing reference](/operating-model/reference/reviewing) is the procedure they drive.

## `run`

Run **one** named critic round.

| Flag | Default | Meaning |
|------|---------|---------|
| *(positional)* | — | The `critics[]` entry to run, by name. |
| `--prompt` | — | The review prompt, inline. |
| `--prompt-file` | — | File holding the prompt. **Preferred** — review prompts are long. |
| `--root` | `.` | Project root. |
| `--cwd` | the critic's `cwd`, else `--root` | Directory to run in. |
| `--work-item` | `""` | Work item id, e.g. `issue-117` — fills `{workItem}`. |
| `--spec-dir` | `<specDir>/<work item>` | Fills `{specDir}`. |
| `--timeout` | the critic's `timeoutSeconds` | Override for this round. |
| `--output-file` | — | Also write the JSON envelope to this path. |

`--prompt` and `--prompt-file` are mutually exclusive, and one is required.

::: tip One critic per invocation
There is deliberately no run-all mode. A critic round is a decision about *which* second
opinion you want, not a batch job.
:::

## Safety

The critic is spawned as an **argv list, never through a shell**, under its timeout. So
untrusted review material can be **data** but never a **command** — a prompt containing
`; rm -rf /` is a string the critic reads, not something the shell expands.

## Output

stdout is exactly **one JSON envelope**; diagnostics go to the log stream, so stdout stays
parseable:

```json
{
  "critic": "cursor-gpt",
  "harness": "cursor",
  "model": "gpt-5.5",
  "attribution": "…",
  "ok": true,
  "exitCode": 0,
  "durationSeconds": 42.1,
  "output": "…",
  "error": null,
  "usage": {}
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | The round ran |
| `1` | The round failed — absent CLI, non-zero exit, timeout. **The envelope is still printed.** |
| `2` | Misconfigured — nothing was spawned |

The `1`-with-an-envelope behaviour is deliberate: a failed round is still a fact the calling
harness needs to record, not an absence of output.

## Scope

Repo-scoped, like [`check`](/cli/commands/check) and
[`scenarios`](/cli/commands/scenarios): it runs in the project it is invoked in, reads only
the operator's CLI config, and is no part of the daemon
([decision-032](/decisions/decision-032)).

The review **loop** itself — round counts, convergence, posting findings — stays with the
harness following the
[reviewing reference](/operating-model/reference/reviewing). `run` runs one round;
`policy` says how many there may be.

## See also

- [review-loop](/capabilities/review-loop) — the capability doc.
- [decision-043](/decisions/decision-043) — why the critic is a spawned argv.
