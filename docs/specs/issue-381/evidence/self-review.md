---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#381"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a work item is armed by a set of labels, all of which must be present

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Can an empty list arm everything? | It would have: `all([])` is `True`. `event_carries_labels` returns `False` on an empty list before the `all`, and `_carries_every_label` guards the same way on the poller. Both are pinned (`test_an_empty_label_list_arms_nothing`; the provider filter's `bool(self.labels) and …`) |
| 2 | Can a string reach a reader as a list of characters? | The first draft did exactly that: `normalize_labels(list(labels))` turned `"the-loop: auto-execute"` into 22 one-character labels, and the poller unit suite caught it (`--label` argv assertions). `normalize_labels` now reads a bare string as one label, and the readers pass the value through unchanged |
| 3 | Does a `labeled` action for the *wrong* label arm an item that is one label short? | No: the added label is read together with the item's current set per label, so the missing one is still missing. Pinned in `test_event_carries_labels_counts_the_label_being_added` |
| 4 | Does the poller's tracking depend on `gh`'s multi-label semantics? | No. `_carries_every_label` re-checks the returned label set, and `test_provider_drops_a_listed_item_missing_one_label` feeds a listing that returns too much. GitHub's filter is all-of anyway, so nothing is fetched that the filter would not have returned |
| 5 | Is the hot-reload path still right? | `router.auto_execute_labels` is replaced with the new list and the log line names it; `test_webhook_routing_integration.py` runs the reload path with the renamed argument |
| 6 | Does a config that never set the key change behaviour? | No: the default is `["the-loop: auto-execute"]` and every existing suite that spawned on the single label passes with `[LABEL]` — a one-entry list is the old string |
| 7 | Can the old key be read by accident? | `RoutingConfig.from_mapping` reads only `autoExecuteLabels`, and `load_cli_config` refuses `autoExecuteLabel` before `from_mapping` sees it; a github source's `label` is refused the same way. Both refusals name the key, the replacement and the command |
| 8 | Is the migration lossless and idempotent? | Wrap, drop an empty source label, keep an already-declared list, flag an empty routing label; a second run reports no change. All four are tests |
| 9 | Does the schema change survive the hand-written validator? | The first draft used `minLength`, which `configschema.SUPPORTED` does not know; `test_the_schemas_use_no_keyword_the_validator_ignores` caught it and the keyword is gone. The packaged copy is byte-identical |
| 10 | Does the self-diagnosis label guard still hold? | It was documentation, not code, before this change and still is; the wording now says *none of* the list. A self-filed issue carries no arming label at all, so all-of makes it strictly harder to arm by accident |

## What I changed after re-reading

- **`normalize_labels` on a bare string** (question 2) — one label, never its characters.
- **`minLength` removed from both schema copies** (question 9).
- **The splice-refusal test** in `test_core_config.py` spliced `autoExecuteLabel`, which
  the schema now refuses before the splicer runs; it splices a scalar the schema accepts.
- **The refusal-message assertion** in the migration test compared against a
  backticked replacement that the message spells with its `routing.` prefix; the test now
  asserts the replacement name itself.
