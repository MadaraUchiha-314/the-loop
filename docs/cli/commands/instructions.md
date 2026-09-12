# `instructions`

Which of the custom instruction docs your project registers actually resolve — so
"is the-loop really reading my conventions?" is a question you can answer, and
`onMissing: error` is a setting that errors.

```bash
the-loop instructions [--root .] [--doc PATH | --doc '{"path": …, "notes": …}']...
                      [--on-missing warn|error|ignore] [--format table|markdown|json]
```

## What it reads

The docs you hand it. `customInstructions.docs` in the repository's
[harness config](/config/harness-config) is the ordered list of your own rule and
guideline files the **agent** reads before working an item
([instructions reference](/operating-model/reference/instructions)); the CLI reads no
harness config ([issue #352](https://github.com/MadaraUchiha-314/the-loop/issues/352)),
so the agent — or you — passes each entry as `--doc`, and the policy as `--on-missing`:

```yaml
customInstructions:
  docs:                                       # ordered; later docs win on conflict
    - path: docs/team-conventions.md          # repo-relative …
      notes: House TS style, naming, PR etiquette.
    - path: /home/me/company-wide-rules.md    # … or absolute (per-machine)
      notes: Org-wide security & dependency policy.
  onMissing: warn                             # warn | error | ignore
```

```bash
the-loop instructions \
  --doc '{"path": "docs/team-conventions.md", "notes": "House TS style, naming, PR etiquette."}' \
  --doc /home/me/company-wide-rules.md \
  --on-missing warn
```

It reports each entry in the order given — order matters, because later docs win on
conflict — with its configured path, the absolute path it resolved to, your `notes`, and
its state. A `--doc` is a path, or a JSON object carrying `path` and `notes`; a value
that starts like JSON and is not is refused (exit 2) rather than read as a path.

## States

| State | Meaning |
|-------|---------|
| `present` | The file is there and readable. Its guidance reaches the agent. |
| `missing` | Nothing resolves at that path (including a broken symlink). Usually a typo or a moved file. |
| `unreadable` | Something is there, but it is not a readable text file — a directory, a device node, an unpermitted file, or binary content. |
| `invalid` | The entry itself is unusable: no `path`, a blank one, or not a mapping. |

`missing` and `unreadable` are kept apart on purpose: "your path is wrong" and "your path
is right but the target is not a doc" send you to different places.

## Exit code

Everything that is not `present` counts as unresolved — `invalid` included, because a
registration the-loop could not understand is guidance that is not reaching the agent.
What happens then is `--on-missing` (the harness config's `customInstructions.onMissing`, carried over by the caller):

| `onMissing` | Unresolved docs | Exit |
|-------------|-----------------|------|
| `error` | any | **1**, naming each one |
| `warn` (default) | any | 0, with a warning naming each one |
| `ignore` | any | 0, silently — still reported in the output |
| any | none | 0 |

The exit code never depends on `--format`, so a CI job can pick whichever output it wants
to archive:

```bash
the-loop instructions --format markdown >> pr-briefing.md
```

A run with **no** `--doc` reports an empty list and exits 0 — registering nothing is not
an error.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--root` | `.` | Repository root that relative paths resolve against. |
| `--doc` | — | A registered doc (repeatable): a path, or `{"path": …, "notes": …}`. |
| `--on-missing` | `warn` | `warn`, `error` or `ignore` — the policy that grades the report. |
| `--format` | `table` | `table`, `markdown` or `json`. |

## What it does *not* print

The **contents** of your instruction docs — only facts about them (path, resolved path,
state, byte count). Absolute and out-of-repo paths are supported on purpose, so what keeps
a doc inert to this command is that its body has no channel into the output. The byte
count is there instead of a preview for exactly that reason.

## Why it exists

`customInstructions` shipped in
[issue-59](https://github.com/MadaraUchiha-314/the-loop/tree/main/docs/specs/issue-59),
and for a long time nothing could observe it. A mistyped path contributed no guidance and
no signal; a run against a broken registration looked exactly like a correct one. This is
the same move [`scenarios`](/cli/commands/scenarios) makes for the Gherkin obligation: an
obligation nothing can observe is an obligation that drifts.

## See also

- [instructions reference](/operating-model/reference/instructions) — when the docs are
  read, and what they can and cannot override.
- [harness config](/config/harness-config) — the `customInstructions` block the agent reads and passes here.
- [`scenarios`](/cli/commands/scenarios) — the same shape, for test coverage.
