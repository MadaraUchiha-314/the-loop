# Learning 019: A CLI config schema change goes in both copies

- **Date:** 2026-11-17
- **Source:** system-feedback
- **Work item:** issue-533

## What happened

`env.sessionCredentials` was added to `cli/the_loop/schemas/cli-config.schema.json`
(the packaged copy) only. CI failed twice:

- `test_config_schema_parity` failed because the authored copy at
  `.the-loop/cli-config.schema.json` differed;
- `test_docs_parity` failed because it reads the authored copy, and an array of objects
  is documented per item key (`### \`env.sessionCredentials[].name\``), not by the
  array's own heading.

## Learning

`.the-loop/*.schema.json` is the authored home and the packaged file is a `cp` of it.
Edit the authored file and copy it. A new array-of-objects option needs one
`- **Type:**` / `- **Default:**` heading per item key under `docs/config/cli/`.

## Action

First occurrence. The parity tests already catch it; recorded so the next schema change
starts in the right file.
