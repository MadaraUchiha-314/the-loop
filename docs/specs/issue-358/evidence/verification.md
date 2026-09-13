# Verification: per-work-item model and effort choice, and spawning after the gate

Every activity of [`testing-plan.md`](../testing-plan.md), with the command that ran it and
its outcome. Run on the work item's branch at `3c14f33`.

Nothing here contains a credential: this work item reads and writes none, and the only
rendered output is a checklist body, a verdict matrix and a session table over fixtures.

## T1 — unit

```console
$ make test            # uv run --project cli python -m pytest -q cli
3603 passed, 1 skipped in 176.89s (0:02:56)
```

Outcome: **pass.** The suite was 3539 tests before this work item and is 3603 after, so the
change carries 64 new tests and broke none of the existing ones.

## T2 — integration (scenario)

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_spawn_gate_integration.py cli/tests/test_dispatcher_choice.py
19 passed in 0.16s
```

Outcome: **pass.** The four Gherkin-documented scenarios the plan named:

| Scenario | File |
|---|---|
| an armed work item gets no session until its gate is answered | `test_spawn_gate_integration.py` |
| the arming event still reaches the first gate | `test_spawn_gate_integration.py` |
| an unparked work item spawns exactly as before | `test_spawn_gate_integration.py` |
| a mid-graph work item still respawns | `test_spawn_gate_integration.py` |

The plan also named *"a work item that chose a model and an effort is respawned on both"* and
*"a model the harness refuses is never spawned"*. Both are asserted, in
`test_dispatcher_choice.py`, at the resolution seam (`_adapter_for`) rather than through a
full respawn — the argv is what the scenario is about, and asserting it there fails more
usefully than asserting it through two layers of stubs.

## T3 — contract

```console
$ make validate        # uv run python scripts/validate_config.py
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Plus `test_api_contract_parity.py` and `test_config_schema_parity.py`, both passing inside T1.

Outcome: **pass, and the row changed meaning.** The plan expected an OpenAPI edit adding
`model`/`effort`/`harnessArgs` to a session schema. There is none to make:
`/api/v1/sessions` types its response as an array of untyped objects and
`core.list_sessions` returns the registry record verbatim, so the three fields flow through
and contract parity still holds. Recorded in `design.md` § The session record and in the
plan's matrix rather than left as a surprise.

## T8 — security / abuse case

```console
$ uv run --project cli python -m pytest -q cli -k abuse
38 passed, 3566 deselected in 6.76s
```

Outcome: **pass.** The seven abuse cases of `requirements.md` § Security considerations, each
against the real parse and resolution path:

| Case | Test |
|---|---|
| A1 unauthorized reply freezes nothing | `test_selection_choices.py::test_abuse_an_unauthorized_reply_freezes_nothing` |
| A2 a flag, a path or a metacharacter | `test_selection_choices.py::test_abuse_a_reply_naming_a_flag_or_a_path_resolves_to_nothing` |
| A2 (the interesting half) a shell fragment after a real name | `test_selection_choices.py::test_abuse_a_shell_fragment_after_a_real_name_is_not_smuggled_through` |
| A3 the argv holds only config + adapter output | `test_dispatcher_choice.py::test_abuse_the_argv_contains_only_what_config_and_the_adapter_produced` |
| A4 a hand-edited frozen record | `test_dispatcher_choice.py::test_abuse_a_forged_frozen_choice_is_ignored` |
| A4 (second form) a withdrawn declaration | `test_dispatcher_choice.py::test_abuse_a_declaration_withdrawn_stops_reaching_the_argv` |
| A4 (third form) a model narrowed to another harness | `test_dispatcher_choice.py::test_abuse_a_model_narrowed_to_another_harness_cannot_be_forced_onto_this_one` |
| A5 a label named after a model | `test_dispatcher_choice.py::test_abuse_a_label_named_after_a_model_selects_nothing` |
| A6 an unreadable checklist | `test_selection_choices.py::test_abuse_an_unreadable_checklist_keeps_the_operators_arguments` |
| A7 a forged availability verdict | `test_modelprobe.py::test_abuse_a_forged_verdict_cannot_introduce_a_choice` |
| (also) a choice row read as a phase | `test_selection_choices.py::test_abuse_a_choice_row_is_never_read_as_a_phase` |

**A4's third form was found by writing these tests, not by the design.** `harnesses:` on a
model was enforced only where the checklist is rendered, so a hand-edited frozen record could
have put a cursor-only model onto claude. It is now enforced where the argv is built too.

## T10 — migration / upgrade

```console
$ uv run --project cli python -m pytest -q cli/tests/test_dispatcher_choice.py \
    -k "before_this_feature or declared_nothing or deprecated"
3 passed, 12 deselected in 0.46s
```

Outcome: **pass.** An install that declared nothing resolves to the shared adapter untouched;
a session recorded before this feature is not treated as drifted; the deprecated
`routing.harnessArgs` still launches a session. `test_routing.py` adds the record-level half
(a pre-change session record still parses, and a session with no choice writes none of the
three keys).

## Tooling parity

```text
uv run ruff check cli hooks           ->  All checks passed!
uv run ruff format --check cli hooks  ->  301 files already formatted
uv run pyright cli                    ->  0 errors, 0 warnings, 0 informations
npx markdownlint-cli2 "**/*.md"       ->  Summary: 0 error(s)
```

Outcome: **pass.** Same commands CI runs.

## What did not run, and why

| Planned | Why not |
|---|---|
| T4 end-to-end | `n/a` in the plan, and it stayed `n/a`: a real harness with real model access, a real tmux server and a real repository. T2 stands in at the same seams. |
| A live `models check` against a vendor | Deliberately not part of verification. The probe spends real tokens, and a suite that depends on an account is a suite that fails for reasons unrelated to the change. `test_modelprobe.py` decides each outcome with a stub adapter instead. |

## One thing an operator should know

Running `the-loop models check` in this container reported `claude model opus-5 → refused`,
because the `claude` binary is present but this environment cannot complete the call. That is
the mechanism behaving correctly — the harness said no, so the model is withheld — and it is
also the failure mode to be aware of: a **transient** environment problem can withhold a model
for up to 24 hours. `--refresh` re-probes immediately, and `unknown` (no binary at all) stays
offerable precisely so that a machine which cannot probe does not lose its declarations.
