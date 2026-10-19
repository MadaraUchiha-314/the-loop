# Learning 013: Node 22+ ships an experimental `localStorage` that shadows jsdom's in vitest

- **Date:** 2026-10-19
- **Source:** system-feedback
- **Work item:** issue-496

## What happened

`bun run test` in `ui/` failed 61 view tests with `Cannot read properties of undefined
(reading 'clear')` on `globalThis.localStorage`, in files this work item never touched.
Node 26 defines `globalThis.localStorage` as an experimental Web Storage global that is
`undefined` unless `--localstorage-file` is given, and that definition wins over the jsdom
environment's.

## Learning

A suite's environment can change under it with the runtime version alone. The failure
pattern — every view test, one error, untouched files — is the tell; check the runtime
before the code.

## Action

Run vitest with `NODE_OPTIONS=--no-experimental-webstorage` on Node 22 or newer (recorded
in `docs/specs/issue-496/evidence/ui.md`). A `.nvmrc`/`engines` pin or the flag in
`ui/package.json`'s `test` script is the durable fix for a follow-up.
