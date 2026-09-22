---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#422"
---

# Security review: the suite writes into the checked-in `.the-loop/` when run from the repo root

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)). The
> checklist below was run against the branch diff, file by file.

## Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `cli/the_loop/channels/slack.py` | `probe_subscription` / `report_subscription` take an optional `cli_config`, passed to `SlackDirectory`; the listener passes its frozen config | the directory cache's **path** only |
| `cli/the_loop/commands/channels_cmd.py`, `diagnose_cmd.py` | pass the config they already hold | same |
| `cli/tests/conftest.py` | audit hook + autouse fixture + `pytest_sessionfinish` | none (test process only) |
| `cli/tests/test_*.py` (5 files) | state roots under `tmp_path`; one new module | none |
| `.the-loop/portable/*.json` (2 files) | deleted | none: nothing reads them |
| `.gitignore` | comment reworded | none |
| `docs/**` | prose | none |

## Findings

**None.**

## Checklist

- **Secrets.** No token, credential or host is read, written, logged or committed by any
  changed line. `SlackDirectory` reads its token from `token_env`, which the probe still
  passes explicitly (`config.bot_token_env`). The new `cli_config` argument reaches only
  `_default_path()`, and the token is chosen before the config is consulted
  (`directory.py`: `self.token_env or SlackChannelConfig.from_mapping(...)`). The cache
  file holds conversation and user names and ids, which it held before. Only its
  directory moves.
- **Where the cache lands.** It moves from `./.the-loop/local/` of whatever directory the
  command ran in, possibly a shared one, to `<state.root>/local/`. That is the documented
  location and the operator's own tree. This is a small reduction in exposure, not an
  increase.
- **Abuse case restored.** `test_no_declared_value_reaches_any_output_on_any_path`
  (R5.1, R5.3 of the restart spec) asserts that neither the retired nor the new token
  appears in any output, the event log included. Its log half searched a file that was
  never written. It now searches the log the code actually writes, asserts that log is
  non-empty, and still passes on all four paths. The assertion is strictly stronger.
- **No weakened assertion.** Every changed test asserts what it did before, plus one
  line. The health test's lock assertion now watches the poller's real pidfile. The
  doctor test additionally asserts the cache location. Nothing was skipped, marked or
  loosened.
- **The guard.** It inspects path arguments of audit events and appends to an in-memory
  list. It opens no file, touches no network, and cannot be triggered by input from
  outside the test process. It never raises inside the hook, so it cannot turn a
  diagnostic into a crash in code under test.
- **Sensitive paths.** `.the-loop/**`: two files deleted. They are test debris for a
  repository that does not exist (`octo/repo`), and nothing in code, config or docs
  reads them. This is why the item is tier 3 rather than the ticket's 1–2. No schema,
  workflow, auth, secret or credential path is touched.
- **Supply chain.** No dependency added, removed or re-pinned; `uv.lock` is untouched.
- **Risk tier.** 3. Below the tier-4 threshold, so no named human security sign-off is
  required. The PR approval is the human gate.
