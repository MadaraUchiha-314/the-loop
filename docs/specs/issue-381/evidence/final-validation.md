---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#381"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: a work item is armed by a set of labels, all of which must be present

> The `verification` node's proof: every activity in `testing-plan.md` ticked, with the
> command, the outcome and the committed artifact.

## Red → green

The new tests were written before any production code. The first run
(`pytest cli/tests/test_routing.py cli/tests/test_migrations.py -x`) failed at import:

```text
    from the_loop.webhook.router import (
E   ImportError: cannot import name 'event_carries_labels' from 'the_loop.webhook.router'
ERROR cli/tests/test_routing.py
```

With the router and config in place and the poller still single-label, the poller and
migration suites failed on the seams the design names — verbatim tail:

```text
FAILED cli/tests/test_poller.py::test_gh_listings_pass_one_label_flag_per_label
FAILED cli/tests/test_poller.py::test_provider_drops_a_listed_item_missing_one_label
FAILED cli/tests/test_poller.py::test_provider_from_source_reads_labels_and_falls_back_to_routing
FAILED cli/tests/test_poller.py::test_a_presence_event_is_labeled_only_when_every_label_is_present
E       TypeError: GitHubPollProvider.from_source() got an unexpected keyword argument 'default_label'
FAILED cli/tests/test_configschema.py::test_the_schemas_use_no_keyword_the_validator_ignores
E       assert not {'minLength'}
FAILED cli/tests/test_migrations.py::test_an_un_migrated_label_key_is_refused[config0-routing.autoExecuteLabel-autoExecuteLabels]
```

The first two are the poller seams; the third caught a schema keyword the hand-written
validator does not implement (removed); the fourth was the test's own assertion against
the message's spelling (tightened to the replacement name). After the change every one of
them passes (below).

## Results

| # | Command | Outcome | Artifact |
|---|---|---|---|
| T1 | `pytest cli/tests/test_routing.py -k carries_labels or empty_label_list` | pass — subset, wrong added label, empty list all `False`; the last missing label arms | three tests |
| T2 | `pytest cli/tests/test_routing.py -k normalize_labels or reads_the_label_list` | pass — default list, order kept, empties and repeats dropped, a string is one label | two tests |
| T3 | `pytest cli/tests/test_routing.py -k flags_labeled_only` | pass | `test_router_flags_labeled_only_when_every_label_is_present` |
| T4 | `pytest cli/tests/test_poller.py -k one_label_flag_per_label` | pass — `--label` per entry on both listings | the test |
| T5 | `pytest cli/tests/test_poller.py -k drops_a_listed_item or reads_labels_and_falls_back or presence_event_is_labeled_only` | pass | three tests |
| T6 | `pytest cli/tests/test_migrations.py` | pass (59 tests) — refusal of each old key, the wrap, the empty source label, the empty routing label flagged, the half-migrated file, idempotence, another provider's key untouched, version `0.10.0` | the file |
| T7 | `pytest cli/tests/test_webhook_routing_integration.py -k only_some_of_the_labels or last_missing_label` | pass — no spawn on a subset; a spawn when the last label is added | two scenarios |
| T8 | `pytest cli/tests/test_poller_integration.py -k missing_one_label` | pass — nothing tracked or spawned on a subset; a spawn once the second label is applied | `test_the_poller_drops_a_listed_item_missing_one_label` |
| T9 | `pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py` + `scripts/validate_config.py` | pass — the parity suite **caught** the two documented-but-removed headings before the docs were rewritten | the suites; `VALID ×6` |
| T10 | `make check` | pass | below |
| T11 | as named in `security-review.md` | pass | see that file |
| T12–T14 | — | n/a, as planned | — |

## Gates

```text
$ uv run ruff check cli hooks                → All checks passed!
$ npx markdownlint-cli2@0.18.1 "**/*.md"     → Linting: 1220 file(s)  Summary: 0 error(s)
$ uv run ruff format --check cli hooks       → 317 files already formatted
$ uv run pyright cli                         → 0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py   → VALID ×6
$ uv run --project cli python -m pytest -q cli
3957 passed, 1 skipped in 192.30s (0:03:12)
```
