---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#464"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a Slack app from one click, named by its operator

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (naming) | yes | `--name` sets the two name fields and nothing else; the handle rule; every refused name exits 2 and writes nothing | `cli/tests/test_channels_commands.py -k manifest` |
| T2 | Unit (formats, link) | yes | no option prints the packaged file verbatim; `--format json` parses back to the built manifest; `--link` decodes back to the same manifest | same |
| T3 | Unit (kept file) | yes | `--write` defaults beside the resolved CLI config; creates, reports unchanged without rewriting, reuses the kept name, reports the scope and event delta and the reinstall line; refuses an unreadable file without `--name` and leaves it untouched | same |
| T4 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint | `make check` equivalents |
| T5 | Security | yes (review) | name only through the serializers, nothing but the name read back, no network, no token | `evidence/security-review.md` |
| T6 | Manual (Slack) | no, not runnable here | the link opens Slack's create dialog prefilled | see below |
| T7 | Integration / contract / UI / accessibility / migration / performance | n/a | no service route, no API contract, no UI, no stored data beyond one file the command owns, no hot path | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1, R1.5 | T2 |
| R1.2, R1.3, R1.4 | T1 |
| R2.1, R2.2 | T2, T5 |
| R3.1–R3.6 | T3 |
| R4, R5 | review of the walkthrough diff (`evidence/documentation.md`) |
| Security considerations | T1, T3, T5 |

## Verification environment

This repository's own checkout. No service, fixture or credential: the verb is local
and the tests point `$THE_LOOP_CLI_CONFIG` at a temporary directory.

## Not covered by an automated test

Slack's handling of the link (T6). This cloud session has no Slack workspace or browser
login. The test decodes the link back to the manifest, and Slack documents the
`new_app=1&manifest_json=` parameters. The live check is the next operator who runs
`/the-loop:init`.
