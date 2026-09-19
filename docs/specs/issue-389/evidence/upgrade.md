---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Upgrade (T10): an installation from before this change reads as it did

> Row T10 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. Run at the PR's head
> on 2026-09-19.

## Command

```bash
cd cli && uv run python -m pytest -q tests/test_channels_upgrade.py tests/test_config_schema_parity.py tests/test_docs_parity.py tests/test_graph_parity.py tests/test_bus.py
```

**64 passed** in 0.28 s.

## The pre-change fixtures

Each is written by the test as the file was before the change — the store's own writer,
then the new key stripped — so the shape is the real one, not a guess
(`cli/tests/test_channels_upgrade.py`):

| Fixture | Reads as |
|---------|----------|
| a `collaborationChannels` declaration without `listen` | a `mentions` room; `ChannelStores.listen_mode` answers `mentions` for it and for an undeclared channel |
| a declaration with an unknown `listen` | `mentions` (the two-value guard) |
| a roster entry without `slack` | still a collaborator by login; `slack_ids()` empty; `is_collaborator_slack` false |
| a roster entry with neither id, or a malformed one | skipped whole (`from_dict` → `None`) |
| a `channels/slack.json` without `snapshots` | loads with none; the first `record-context` writes the map |
| an app whose granted scopes lack `app_mentions:read` | one finding naming the scope and the consequence from `status --probe` and at connect; none when the scopes cannot be read |

The two `cli-config.schema.json` copies stay byte-equal (`test_config_schema_parity.py`);
the docs pins — the manifest's fenced copy, the options page's grant rows, the command
pages — pass (`test_docs_parity.py`); the graph and the catalog pins pass
(`test_graph_parity.py`, `test_bus.py`). No config version bump: nothing is renamed.
