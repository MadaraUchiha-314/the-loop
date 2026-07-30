# `migrate-config`

Migrate a `cli-config.yaml` to the current schema version. Deterministic, idempotent, and
previewable.

```bash
the-loop migrate-config [--path ~/.the-loop/cli-config.yaml] [--dry-run]
```

## Why it exists

Some changes are breaking, and the owner's call was to make them breaking properly rather
than carry a shadow override forever — *"Let's make breaking changes. `/upgrade` should be
able to handle it."*

A breaking change is only as good as its migration, so four properties hold:

1. **Version the schema; do not sniff for keys.** Detection is exact.
2. **Fail closed and loudly.** A config still carrying a removed key makes the runtime
   refuse to start, naming the key, its replacement and the exact command. Silently ignoring
   a value you deliberately set would change your behaviour without telling you — much worse
   than an error.
3. **The migration is a deterministic key move**, idempotent and previewable, that *reports*
   what it changed rather than rewriting the file quietly.
4. **It is tested both ways** — an old config migrates to the expected new one, and the
   runtime refuses an un-migrated one.

## What it migrates today

Current version: **`0.2.0`**.

The per-feature `ghBinary` keys — declared separately under `routing.control`,
`routing.reactions` and `routing.announce` — move to a single
[`integrations.github.cli.binary`](/config/cli/integrations-options#github-cli-binary).
Three copies of one setting is exactly the duplication the `integrations` block exists to
remove.

```text
$ the-loop migrate-config --dry-run
migrated the CLI config:
  · webhooks.ghWebhook.routing.control.ghBinary → integrations.github.cli.binary ('gh')
  · webhooks.ghWebhook.routing.reactions.ghBinary → integrations.github.cli.binary ('gh')
  · webhooks.ghWebhook.routing.announce.ghBinary → integrations.github.cli.binary ('gh')
  · version '0.1.0' → '0.2.0'

--- /home/you/.the-loop/cli-config.yaml (preview, not written) ---
version: 0.2.0
…
```

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--path` | the resolved CLI config | Which file to migrate. |
| `--dry-run` | off | Print the report and the migrated YAML without writing. |

`--path` defaults to whatever the normal
[resolution order](/config/cli/#where-the-file-is-found) finds.

## Behaviour

- **Reads with the raw loader, on purpose.** The normal loader refuses an un-migrated
  config — and refusing to load the very file you are trying to migrate would be a locked
  door with the key inside.
- **Keeps a backup.** The pre-migration file is written to `<path>.bak` before the new one
  replaces it. A breaking migration you cannot walk back from is a worse trade than one
  stray `.bak`.
- **Idempotent.** Running it twice produces the same file and reports no second change:
  `config is already current; nothing to migrate`.
- **Reports, then acts.** The report is printed either way; `--dry-run` stops there.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Migrated, or already current |
| `2` | File not found, or it could not be parsed |

## When the runtime refuses

```text
this CLI config still declares webhooks.ghWebhook.routing.control.ghBinary. That key
was removed in favour of `integrations.github.cli.binary`, so transport is declared
once instead of three times. It is NOT being ignored — ignoring a value you set would
change behaviour silently. Run `/the-loop:upgrade-the-loop` to migrate.
```

`/the-loop:upgrade-the-loop` shells out to this command, so an upgrade never hand-edits a
config the runtime already knows how to move. Running `migrate-config` directly does the
same job.

::: tip An unset `version` is not refused
The gate refuses exactly two things: a **removed key still present**, and a config that
**declares** a version older than the current one. A config with no `version` at all and no
removed keys is accepted — there is nothing to move and nothing to lose, and a gate that
stops a daemon over a missing bookkeeping key is a gate operators learn to route around.
:::

## See also

- [Versioning and migration](/config/cli/#versioning-and-migration)
- [Integrations options](/config/cli/integrations-options) — where the moved key now lives.
