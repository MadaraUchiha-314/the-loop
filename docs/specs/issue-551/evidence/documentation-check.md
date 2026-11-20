# Skill and docs check (T12)

Run on 2026-11-20 at `a0b978dd`, after the review fixes, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T12 | `grep -rnE "next session starts fresh\|ending the session at a phase" skills/ commands/ docs/capabilities/` (run from the repository root, with a plain pipe) | no output, exit 1 |
| T12 | `uv run python -m pytest -q tests/test_docs_parity.py` | 5 passed in 0.22s |

`tests/test_interaction.py` also asserts that neither phrase appears under
`skills/` or `commands/`, and that the interaction prompt names `--after` and
`the-loop wait`.
