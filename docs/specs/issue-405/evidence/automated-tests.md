---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#405"
---

# Evidence: automated tests (issue-405)

Run on 2026-09-21, on the branch of the delivering PR, from the repository root unless
noted. Nothing in the output names a token, a host or a person.

## Red first — P1, the pre-fix clause reader

With the four production modules stashed (`git stash push cli/the_loop/channels/…
cli/the_loop/eventlog.py`) and the new tests present, the two suites **fail at
collection** (`ImportError: cannot import name 'EMPTY_CLAUSE' from
'the_loop.channels.slack'`). The behaviour itself, on the pre-fix reader:

```
$ cd cli && uv run python -c "…without_clause / apply_without on the live shapes…"
BEFORE without_clause -> ['design', '*Sent', 'using*', '@Claude']
BEFORE apply_without  -> that name is not a phase this checklist offers, so nothing was recorded. The phases you may leave out: 1. `bra
BEFORE numeric        -> that name is not a phase this checklist offers, so nothing was recorded. The phases you may leave out: 1. `bra
BEFORE bold           -> ['*2*'] that name is not a phase this checklist offers, so nothing w
BEFORE zwsp           -> ['design\u200b']
```

— the run-3 refusal, reproduced: a same-line signature is read as three more "phases",
the first non-name of which refuses the reply as *that name*, for a valid name and a
valid number alike; a bolded number and a zero-width space do the same.

## Red first — P2, the pre-fix close path

```
$ cd cli && uv run python -m pytest -q tests/test_finish_grace.py -x
tests/test_finish_grace.py:32: TypeError   (GraphContext.__init__() got an unexpected keyword argument 'terminal')
1 failed
```

## T1 + T2 + T9 — the grammar, the pipeline, the hostile names

```
$ cd cli && uv run python -m pytest -q tests/test_channels_verbs.py tests/test_selection_control.py
52 passed in 0.46s
```

New or changed tests:

- `test_strip_signature_removes_a_connectors_signature_wherever_it_sits` (T1 — R1.1)
- `test_without_clause_ignores_a_connector_signature_and_slack_markup` (T1 — R1.1, R1.2)
- `test_a_non_token_word_is_refused_by_its_position_never_echoed` (T1 — R1.3)
- `test_abuse_an_unknown_or_unskippable_phase_refuses_the_whole_reply` (re-parametrised
  with the reason family — R1.4)
- `test_abuse_a_hostile_name_is_named_never_echoed` (+ `read_summary` — T9)
- `test_a_signed_execute_without_freezes_the_selection` (T2 — R1.1, R1.5)
- `test_a_non_token_word_drops_as_unknown_phase_and_the_record_says_what_was_read`
  (T2 — R1.3, R1.4, R1.5)
- the two existing pipeline refusal tests now expect `unknown-phase` (R1.4)

## T3 + T4 + T9 — the held closure, over the real dispatcher

```
$ cd cli && uv run python -m pytest -q tests/test_finish_grace.py
12 passed in 0.16s
```

Scenarios: held at the terminal node (R2.1); the claim ends the grace early, the
deadline ends it regardless, the sweeper thread finishes on its own (R2.2); a pointer
off the terminal node, an already-exited terminal node, a dead pane, an unreadable
graph and `finishGraceSeconds: 0` close at once (R2.3, T9); a reopen cancels, a second
close is a no-op (R2.4); `merged: true` for an issue whose recorded PR merged, `false`
otherwise (R2.5); `TmuxConfig.from_mapping` reads the knob (T4).

## T5 — the graph context from a real runtime

```
$ cd cli && uv run python -m pytest -q tests/test_graph_drive.py
25 passed in 2.27s
```

`test_the_context_names_the_terminal_node_and_the_merge_that_delivered_it` (R2.1, R2.5).

## T13 — the full suite and the repository's checks

```
$ uv run --project cli python -m pytest -q cli
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 4335 passed, 1 skipped in 188.07s
```

The four `test_instance.py` failures are **pre-existing and environmental**: they fail
identically with every production change of this work item stashed (`4 failed, 59
passed`), and their assertion shows why — the spawn environment carries
`THE_LOOP_CLI_CONFIG=<checkout>/.the-loop/cli-config.yaml`, this repository's own
checked-in CLI config, resolved from the working directory. No file this work item
touches is on that path.

```
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
340 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-405/**/*.md" "docs/reports/**/*.md" "docs/capabilities/*.md" "docs/config/cli/routing-options.md" "commands/finish-tasks.md" "skills/the-loop/SKILL.md"
Summary: 0 error(s)
$ uv run python scripts/validate_config.py
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
