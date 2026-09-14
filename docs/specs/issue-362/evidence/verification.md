---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#362"
---

# Verification: a DM is a channel like any other

Every row of [`testing-plan.md`](../testing-plan.md)'s matrix marked *yes*, run in this
container. No Slack credentials and no network: every Slack call is made through a
substituted client, as the rest of `cli/tests/test_channels*.py` does.

## Results

| # | What was verified | Command | Outcome |
|---|-------------------|---------|---------|
| — | The **red root**: the new assertions against the unfixed tree | `pytest -q cli/tests/test_channels_dm.py cli/tests/test_channels_dm_integration.py` | fail, as designed — [`red.md`](red.md) |
| T1–T4, T6, T7, T10 | The manifest, the kinds, the findings, the probe, `catchUpSeconds`, `channels status` and `--probe`, the abuse cases | `pytest -q cli/tests/test_channels_dm.py` | **39 passed** |
| T5 | The listener end to end: the `message.im` envelope through the unchanged filter, the start-up probe, a probe that raises, the reconcile deadline and a raising cycle, `0` = connect-only | `pytest -q cli/tests/test_channels_dm_integration.py` | **5 passed** |
| T1 (parity) | The guide's fenced manifest is byte-identical to the packaged file | `pytest -q cli/tests/test_channels_commands.py -k manifest` | **2 passed** |
| T7, T12 | The two schema copies are byte-identical; every schema leaf is documented; every documented option exists | `pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py cli/tests/test_docs_parity.py` | **53 passed** |
| T12 | The whole suite — nothing else regressed | `uv run --project cli python -m pytest -q cli` | **3674 passed, 1 skipped** |
| T12 | Every repository gate CI runs: ruff, markdownlint over 1144 files, ruff format, pyright, config validation, the suite | `make check` | **pass** |

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py cli/tests/test_channels_dm_integration.py
............................................                             [100%]
44 passed in 0.67s

$ uv run --project cli python -m pytest -q cli
3674 passed, 1 skipped in 170.45s (0:02:50)
```

## What the tests found

Two defects, both caught by an assertion before any reviewer saw the code:

1. **`scopes=None` meant two different things.** `subscription_findings` used `None` for
   both "nothing was probed" and "the probe ran but the header was unreadable", so an
   unreadable header produced the sentence *"run `--probe` to check"* — advice to do the
   thing that had just been done. `test_probe_with_unreadable_scopes_reports_none_and_finds_nothing`
   failed on it. Split into `subscription_findings` (measured; `None` scopes → no
   finding) and `unchecked_advice` (nothing probed; only a `D…` is called out). The
   design's D2/D3 were updated to match, and the split is the better shape: each function
   has one meaning and one test.
2. **The reconcile trusted `catch_up` not to raise.** The first draft called
   `catch_up(frozen_config)` bare on the strength of its internal `try/except` —
   `test_the_listener_reconciles_on_its_deadline_and_survives_a_raising_cycle` killed the
   listener. R3.3 is a requirement on the *listener*, not on `catch_up`, so the call is
   now guarded in its own right: `catch_up` swallows what `poll_once` raises, and the
   listener swallows everything around it (the event emit, any future refactor). A
   listener that dies on a reconcile is strictly worse than one that never reconciled.

## What this did NOT prove — T9

**No end-to-end run against a real Slack workspace.** It would need a workspace, an app
installed from the new manifest, and a real DM; this container has none, and CI has none.
So the following are verified by construction and by the operator's own import, not by an
observed round trip:

- that Slack actually delivers `message.im` to an app carrying `im:history` +
  `message.im` (Slack's documented behaviour, and the premise of the ticket's diagnosis);
- that `auth.test` returns `x-oauth-scopes` on a live call (documented, and the reporter's
  instance can confirm it in one command).

What *is* proved here: the manifest declares all four pairs, the listener's filter admits
a DM message unchanged, the probe makes exactly the two calls and turns their answers into
the right sentence, and the reconcile fires on its deadline. The end-to-end evidence for
the **defect** is the reporter's own event log in
[issue-362](https://github.com/MadaraUchiha-314/the-loop/issues/362) — 9.5 hours with
zero inbound events, then eight replies and one issue in a seven-second burst at restart.
The end-to-end evidence for the **fix** is one operator importing the manifest and typing
in their DM; `the-loop channels status --probe` is the one-command check that it took.
