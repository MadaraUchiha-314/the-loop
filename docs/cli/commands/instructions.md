# `instructions`

Which of the custom instruction docs your project registers actually resolve — so
"is the-loop really reading my conventions?" is a question you can answer, and
`onMissing: error` is a setting that errors.

```bash
the-loop instructions [--root .] [--format table|markdown|json]
```

## What it reads

`customInstructions.docs` in the repository's
[harness config](/config/harness-config) — the ordered list of your own rule and
guideline files the loop reads before working an item
([instructions reference](/operating-model/reference/instructions)):

```yaml
customInstructions:
  docs:                                       # ordered; later docs win on conflict
    - path: docs/team-conventions.md          # repo-relative …
      notes: House TS style, naming, PR etiquette.
    - path: /home/me/company-wide-rules.md    # … or absolute (per-machine)
      notes: Org-wide security & dependency policy.
  onMissing: warn                             # warn | error | ignore
```

It reports each entry in configured order — order matters, because later docs win on
conflict — with its configured path, the absolute path it resolved to, your `notes`, and
its state.

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
What happens then is `customInstructions.onMissing`:

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

A repository that registers **no** docs reports an empty list and exits 0 — configuring
nothing is not an error. So does a repository whose harness config is absent or
half-edited: reading it is best-effort by contract, and a broken YAML file should fail
your build for its own reasons, not this one.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--root` | `.` | Repository root to read the harness config from. |
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
- [harness config](/config/harness-config) — the `customInstructions` block.
- [`scenarios`](/cli/commands/scenarios) — the same shape, for test coverage.
