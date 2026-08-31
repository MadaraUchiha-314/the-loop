# Evidence: per-work-item collaborators

Captured 2026-08-31 on `claude/github-issue-307-wuv951`, from `cli/` unless stated.

## The suites (T1–T11)

```console
$ uv run pytest -q tests/test_collaborators.py          # T1 grammar, T2 store, T8 gates
32 passed in 0.11s

$ uv run pytest -q tests/test_control.py                # T3 the parser and the keywords
57 passed in 0.14s

$ uv run pytest -q tests/test_control_integration.py    # T4 the control seam, T13
31 passed in 0.34s

$ uv run pytest -q tests/test_webhook_routing_integration.py   # T6 end to end
33 passed in 18.20s

$ uv run pytest -q tests/test_poller.py                 # T7 the poll seam
148 passed in 0.48s

$ uv run pytest -q tests/test_routing.py                # the router seam, T5's vocabulary
166 passed in 1.55s

$ uv run pytest -q tests/test_collaborators_cli.py      # T10 the two CLI verbs
10 passed in 0.24s

$ uv run pytest -q tests/test_reset.py                  # T9 lifecycle
27 passed in 0.14s
```

## The whole suite (T14)

```console
$ uv run pytest -q
2770 passed, 1 skipped in 150.05s (0:02:30)
```

2701 → 2771 collected (**+70**): 42 in the two new files, 28 added to the six existing
suites. One pre-existing skip, unchanged.

## Lint, format, types, configs, markdown (T14)

```console
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
263 files already formatted

$ uv run pyright
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py            # from the repo root
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ npx markdownlint-cli2@0.18.1 "**/*.md"              # from the repo root
Linting: 908 file(s)
Summary: 0 error(s)
```

The documentation-parity gate (`tests/test_docs_parity.py`) is what forced the two new
command pages and the two new option headings; it passes with the rest of the suite.

## Every new test was run against the unfixed tree first

The seams were stashed (`git stash push -- webhook/router.py webhook/dispatcher.py
webhook/daemon.py poller/poller.py reset.py`) and the new tests run against a tree that
still had the store, the parser and the CLI but none of the enforcement:

```console
$ uv run pytest -q tests/test_webhook_routing_integration.py -k collaborator \
      tests/test_routing.py -k collaborator
4 failed, 195 deselected

$ uv run pytest -q tests/test_poller.py -k "collaborator or grant" \
      tests/test_reset.py -k "collaborator or roster" \
      tests/test_control_integration.py -k collaborator
6 failed, 1 passed, 199 deselected

$ uv run pytest -q tests/test_poller.py::test_a_grant_on_another_work_item_does_not_carry \
      tests/test_control_integration.py::test_a_grant_that_names_nobody_is_refused \
      tests/test_control_integration.py::test_closing_the_work_item_forgets_its_roster \
      tests/test_reset.py::test_a_work_item_known_only_by_its_roster_is_still_enumerated
3 failed, 1 passed
```

**The two that passed are the two that should have.** Both are *negative* assertions —
"a grant on another work item does not carry", "a collaborator's comment on issue 16
delivers nothing" — and on a tree where no grant is honoured anywhere, nothing is
delivered for any reason. They earn their place as regression guards on the finished
behaviour, not as proof of it; the positive halves of both (`…comment_is_forwarded…`,
`…reaches_the_session`) are in the failing lists above.

## Manual walk-through (the CLI, against a scratch state root)

```console
$ uv run the-loop add-collaborator @Dana --work-item github:octo/repo#15 \
      --portable-dir "$SCRATCH" --no-comment
@dana is now a collaborator on github:octo/repo#15: their comments on it reach the
session as input (they cannot start, stop or approve anything)   # exit 0

$ uv run the-loop add-collaborator @dana …                       # exit 1
@dana is already a collaborator on github:octo/repo#15; nothing changed

$ uv run the-loop add-collaborator "bad login" …                 # exit 2
error: not a GitHub login: 'bad login' (expected @login — letters, digits and single
interior hyphens, at most 39 characters)

$ uv run the-loop remove-collaborator @DANA …                    # exit 0
@dana is no longer a collaborator on github:octo/repo#15
```

The record written by the first call, showing the section, the canonicalised login and
the provenance:

```json
{
  "ref": "github:octo/repo#15",
  "url": "https://github.com/octo/repo/issues/15",
  "collaborators": {
    "users": [
      {"login": "dana", "addedBy": "…", "addedAt": "2026-08-31T16:18:15Z",
       "source": "cli", "note": ""}
    ]
  }
}
```

The last call left no file at all: a record whose sections are all gone is deleted
rather than kept as an empty husk, which is the work-item store's existing rule.

## Not run

- **T12 (OpenAPI contract), T15 (UI):** no route, request shape, response shape or
  dashboard surface is touched. `tests/test_api_contract_parity.py` passes unchanged as
  part of the full suite, which is the assertion that they were not touched.
- **T16 (performance):** one extra JSON read per event, on the path that already reads
  that record for the control section. No measurement taken, and none is claimed.
