---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#397"
---

# Evidence: automated tests (issue-397)

Run from the repository root on 2026-09-20, on the branch of the delivering PR.

## T1 + T2 — the touched files

```
$ cd cli && uv run pytest -q tests/test_workchannels_integration.py \
    tests/test_channels_mentions_integration.py tests/test_channels_verbs.py \
    tests/test_workchannels_cli.py
73 passed in 0.77s
```

New tests (all Gherkin-docstringed where they are scenarios):

- `tests/test_channels_verbs.py::test_help_public_is_read_from_the_first_line_only` (T1 — R2.1, R3.1, R3.2)
- `tests/test_workchannels_integration.py::test_a_new_declaration_confirms_the_room_through_the_opener` (T2 — R1.1, R1.2, R1.4)
- `tests/test_workchannels_integration.py::test_a_failing_confirmation_never_undoes_the_declaration` (T2 — R1.3)
- `tests/test_workchannels_cli.py::test_add_confirms_the_room_when_channels_are_configured` (T2 — R1.1, R1.3)
- `tests/test_channels_mentions_integration.py::test_help_public_answers_as_a_reply_everyone_can_see` (T2 — R2.1, R2.4)
- `tests/test_channels_mentions_integration.py::test_a_connectors_signature_line_does_not_change_help` (T2 — R2.2, R3.2)

The two dispatcher tests and the mentions `help public` test were written first and
failed for the expected reason (no opener call; an ephemeral instead of a post) before
the production change landed — the red→green transition of the TDD rule.

## Full suite, lint, format, typecheck

```
$ cd cli && uv run pytest -q
4282 passed, 1 skipped in 189.51s (0:03:09)

$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
337 files left unchanged
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

T8 (abuse case 1) is `tests/test_channels_mentions_security.py`, unchanged and green in
the full suite: an unauthorized member's `help` — `public` or not — is dropped before
the help branch.
