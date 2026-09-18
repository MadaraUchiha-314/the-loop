---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#377"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a released work item is launched with the arguments the operator declared

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Is the diagnosis the only mechanism that produces the report's table, or the most convenient one? | The only one found. With `routing.harnessArgs` alone the shared adapters carry the flag on every path, so the released sessions would have had it; the report's flag-less sessions therefore came from a config that declares under `harnesses[].args` — which is where the deprecation warning sends every operator. The 13-vs-6 split is dated on either side of v16.0.0, which introduced both the key and the spawn-after-the-gate rule. Stated as an assumption in `bugfix.md`, because the config is not in the report; the fix does not depend on it |
| 2 | Can the fix ever make a session wider than the config says? | No. `launch_args` reads only `cli-config.yaml`; the choice path appends only `(model_flag, <declared name>)` and `effort_args`; the two homes are never merged. `test_abuse_a_forged_model_in_the_state_file_buys_nothing_on_the_post_gate_spawn` asserts the newly reachable path, and the issue-358 abuse table runs unmodified against the rewired fixture |
| 3 | Does an install that declares nothing launch exactly as before? | Yes: `launch_args({}) == {}`, `build_adapters({})` gives every adapter `extra_args=[]`, and `test_an_install_that_declared_nothing_behaves_exactly_as_before` still passes. `critics.py` keeps calling `build_adapters()` bare |
| 4 | Did moving `_adapter_for` after `on_arm` change any refusal's place? | The "no adapter for defaultHarness" refusal stays first, as a membership check, so a config error still fails before a conversation is opened or a clone is made. The deferral, the workspace failure and the tmux failure are untouched; `test_spawn_gate_integration.py`'s four issue-358 scenarios pass unchanged |
| 5 | Could the second `_resolved_choice` in `_spawn_tmux` disagree with the adapter's? | It reads the same checkout (`cwd`) the adapter was resolved from, milliseconds later, with no write in between. Both are best-effort reads that fall back to `("", "")`; a disagreement would need the state file to change between them, and nothing on this thread writes it |
| 6 | Does the respawn path still leave a pre-fix record alone? | Yes — `_choice_drifted` is unchanged and returns `False` on empty `harnessArgs`. The respawned record now carries `model`/`effort`/`harnessArgs`, so a session relaunched by the drift net is compared on its *new* launch next time, which is what `test_the_respawned_event_names_the_argv_it_was_relaunched_on` pins (record model `fable-5.1`) |
| 7 | Is `launch_args` the resolver for every reader, or most? | All eight in `design.md` §2: both daemons, `reload`, `models_cmd` twice, `standing.py`, `core/standing.py`, and `_adapter_for` (via the adapter). `grep -rn "harnessArgs\|harness_args" cli/the_loop` after the change finds no reader of the deprecated key outside `RoutingConfig.from_mapping`, `launch_args`, `harness_args`, `config_findings` and the two standing sessions' own per-entry `harnessArgs` |
| 8 | Import cycles? | `modelchoice` imports only the standard library, so `standing.py` and `core/standing.py` importing it is safe; the daemons import it inside the builder function, as they import `build_adapters` |

## What I changed after re-reading

- **The conflict finding's `where`.** The first draft put it at `harnesses` (the whole
  section); it now names `harnesses[<h>].args`, the key that wins, so an operator reading
  `the-loop models list` knows which line to keep.
- **`config_findings` without `routing_args`.** `models_cmd._emit` never passed the
  deprecated block, so the "already carries `--model`" check could not see it. The
  function now reads `routing.harnessArgs` from the document when the caller passes none.
- **`the-loop diagnose`.** Three sentences (two mine, one pre-existing in
  `harnesses-options.md`) said `diagnose` reports these findings. It does not —
  `config_findings` has one caller, `models_cmd` — so they now say
  `the-loop models list|check`.
- **This repository's own `cli-config.yaml`.** It declares no `harnesses` section, so
  the comment on its deprecated `harnessArgs` block says "declare a top-level
  `harnesses[].args`" rather than pointing "above" at a key that is not there.

## Round 2 — zero new findings

A second pass over the final diff (after the docs and the evidence were written) found
nothing new: every code change is covered by a row of the testing plan, every doc
sentence that changed names issue-377, and the two regression tests were watched go red
(`bugfix.md` § Root cause, `final-validation.md` § Red → green) before the fix. Converged.
