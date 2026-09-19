---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Snapshots (T6): the modal, the manifest, the help text, the status lines

> Row T6 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. Run at the PR's head
> on 2026-09-19.

## Command

```bash
cd cli && uv run python -m pytest -q tests/test_channels_commands.py tests/test_channels_dm.py tests/test_channels_shortcuts.py
```

**101 passed** in 0.26 s. The manifest's fenced copy in `docs/guide/slack.md` is
byte-equal to the packaged `slack-app-manifest.yaml` (`test_docs_parity.py`, T10); the
`help` text and the `channels status` lines `mentions:` / `shortcuts:` / `rooms:` are
pinned in `test_channels_verbs.py` and `test_channels_mentions.py` (T1).

## The decision modal, as committed

`decision_view("keep poll mode", '{"channel": "C0TMP389", "ts": "1800.2", "thread_ts": "1800.1"}')`
(`cli/the_loop/channels/slack.py`), pinned by `test_channels_shortcuts.py`:

```json
{
  "type": "modal",
  "callback_id": "the-loop:record-decision",
  "private_metadata": "{\"channel\": \"C0TMP389\", \"ts\": \"1800.2\", \"thread_ts\": \"1800.1\"}",
  "title": {
    "type": "plain_text",
    "text": "Record a decision"
  },
  "submit": {
    "type": "plain_text",
    "text": "Record"
  },
  "close": {
    "type": "plain_text",
    "text": "Cancel"
  },
  "blocks": [
    {
      "type": "input",
      "block_id": "decision",
      "label": {
        "type": "plain_text",
        "text": "What was decided"
      },
      "element": {
        "type": "plain_text_input",
        "action_id": "text",
        "multiline": true,
        "initial_value": "keep poll mode"
      }
    },
    {
      "type": "input",
      "block_id": "kind",
      "optional": true,
      "label": {
        "type": "plain_text",
        "text": "Kind"
      },
      "element": {
        "type": "static_select",
        "action_id": "select",
        "placeholder": {
          "type": "plain_text",
          "text": "product, design or tech"
        },
        "options": [
          {
            "text": {
              "type": "plain_text",
              "text": "product"
            },
            "value": "product"
          },
          {
            "text": {
              "type": "plain_text",
              "text": "design"
            },
            "value": "design"
          },
          {
            "text": {
              "type": "plain_text",
              "text": "tech"
            },
            "value": "tech"
          }
        ]
      }
    },
    {
      "type": "input",
      "block_id": "rationale",
      "optional": true,
      "label": {
        "type": "plain_text",
        "text": "Why"
      },
      "element": {
        "type": "plain_text_input",
        "action_id": "text",
        "multiline": true
      }
    }
  ]
}
```

The `private_metadata` is composed by the-loop from the shortcut's coordinates, never
from the member's text, and is validated again on submission (A3).
