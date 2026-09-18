---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#381"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a work item is armed by a set of labels, all of which must be present

> The `security-review` node's record, against `requirements.md` § Security
> considerations. See `skills/the-loop/reference/security.md`.

## The boundaries this work item touches

1. **The arming gate** — which items an instance looks at. It becomes a set; the set can
   only narrow what is armed. Who may *start* an armed item (`authorizedUsers`,
   `control.requireStartCommand`) is untouched.
2. **The upgrade** — a custom single label read under the wrong key would fall back to the
   shared default and arm *more* than the operator set. The old keys are refused at load.
3. **`gh` argv** — labels reach `gh` as separate argv entries, never a shell string.

Risk tier stays **3**: a configuration rename with a migration, no new route, grant,
scope or credential path, and nothing that widens who may speak.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| A1 | An item carrying a subset of the labels is armed | `event_carries_labels` requires every label; the provider re-checks the listing | `test_event_carries_labels_requires_every_label`, `test_an_item_carrying_only_some_of_the_labels_is_not_armed`, `test_the_poller_drops_a_listed_item_missing_one_label` |
| A2 | A `labeled` action for another label arms an item one label short | the added label is read per configured label against the item's set | `test_event_carries_labels_counts_the_label_being_added` |
| A3 | An empty list arms everything | explicit `False` before `all()` on both ingresses | `test_an_empty_label_list_arms_nothing`, `_carries_every_label` |
| A4 | An un-migrated config runs on the shared default | `assert_current` refuses both old keys; `load_cli_config` calls it before any reader | `test_an_un_migrated_label_key_is_refused` (both keys) |
| A5 | A label name is interpolated into a shell | `_label_flags` appends argv entries; `_run_json` runs a list, no shell | `test_gh_listings_pass_one_label_flag_per_label` |

## Fail-closed checks

- Empty list → nothing armed, nothing listed.
- Old key present → the daemon does not start; the message names the fix.
- A source `labels` the operator left empty → the routing list, never "any label".

## Verdict

**Pass.** No finding open; no security-relevant decision needed from a human; below the
tier-4 named sign-off threshold.
