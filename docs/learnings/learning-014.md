# Learning 014: an option a procedure writes after the verb must live on every verb's parser

- **Date:** 2026-10-19
- **Source:** system-feedback
- **Work item:** issue-496

## What happened

The testing plan wrote `the-loop gateway start --config …`, as an operator would. The
`gateway` command declared `--config` on its own parser and nested one subparser per
verb; argparse resolved `start` first and then refused `--config` as unrecognised. The
CLI's global `--config` has the same constraint ("must precede the subcommand"), and the
plan's `the-loop start --config …` failed for the same reason.

## Learning

With nested subparsers an option is accepted only where it is declared. When a documented
procedure places an option after the verb, a shared parent parser (`parents=[common]`)
on every verb is the fix; and the manual checklist is where such mismatches between the
written procedure and the parser surface — run it.

## Action

`commands/gateway_cmd.py` puts `--config` and `--format` on every verb through a parent
parser and also honours the global flag; the bring-up in `testing-plan.md` for the
instance uses the global form (`the-loop --config … start`).
