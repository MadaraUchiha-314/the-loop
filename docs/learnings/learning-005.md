# Learning 005: Practice what you preach — use your own prescribed tooling

- **Date:** 2026-07-01
- **Source:** user-feedback
- **Work item:** issue-1

## What happened

the-loop prescribes `uv` as the Python package manager and a "same tooling local & CI"
rule, yet its own `Makefile`/CI used raw `pip`. The maintainer called it out on PR #2:
"why are we not using uv...?" / "practice what you preach."

## Learning

A harness that prescribes tooling loses credibility (and misses its own dogfooding
signal) when it doesn't use that tooling itself. the-loop's repo is also a reference
project with the-loop initialized in it, so it must exemplify every rule it enforces —
package manager, lockfile-pinned versions, CI parity. When we add a config knob or a
RULE, the very next check is: *does this repo itself obey it?*

## Action

- Converted the repo to a uv workspace (root `pyproject.toml` + committed `uv.lock`);
  `make install-dev` = `uv sync`; hooks and CI run tools via `uv run` (`decision-009`).
- Going forward, treat the-loop's own repo as conformance test #1: every prescribed
  practice must be visibly applied here before we consider a requirement delivered.
