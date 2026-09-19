---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Unit tests (T1): the grammar, the input table, the records, the frames

> Row T1 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. Run at the PR's head
> on 2026-09-19, in this repository's `cli/` with `uv`.

## Command

```bash
cd cli && uv run python -m pytest -q tests/test_channels_mentions.py tests/test_channels_verbs.py tests/test_collaborators.py tests/test_workchannels.py tests/test_channels.py
```

## Outcome

| Files | Result | Duration |
|-------|--------|----------|
| `test_channels_mentions.py` (manifest, probe, the two record shapes, the two frames, the status lines, the threads column), `test_channels_verbs.py` (`strip_mention`, `parse_verb`, `compose_keyword`, `help_text`), `test_collaborators.py` (`CollaboratorRecord.slack`, `parse_subjects`, `slack_ids`, fail-closed `from_dict`), `test_workchannels.py` (`listen`, the two-value guard, `add(listen=)`), `test_channels.py` (the channel, the ledger, `channels threads`) | **234 passed** | 0.84 s |

The whole suite under `make check` (T12, [`checks.md`](checks.md)): 4127 passed,
1 skipped.
