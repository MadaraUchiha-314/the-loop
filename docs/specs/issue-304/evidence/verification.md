---
type: evidence
workItem: "issue-304"
phase: verification
---

# Verification evidence: one Slack surface, two identity allow-lists

Every row of [`testing-plan.md`](../testing-plan.md) that is in scope, with what was run
and what came back. Nothing here carries a token, a secret, or a path outside the
checkout — the whole matrix is filesystem and in-process checks.

## Every new test was run against the unfixed tree first

The source changes were stashed (schemas, `configschema.py`, `migrations.py`, the packaged
copies, the templates and this repo's configs), leaving only the new tests, and the two
touched test modules were run:

```text
$ git stash push -- .the-loop/*.schema.json cli/the_loop/configschema.py \
    cli/the_loop/migrations.py cli/the_loop/schemas/ .the-loop/*.yaml \
    skills/the-loop/templates/{cli-config,collaborators}.yaml
$ uv run pytest -q tests/test_configschema.py tests/test_migrations.py
…
15 failed, 61 passed in 2.29s
```

All fifteen failures are the new assertions — every retired-key refusal, the guidance
messages, the `RETIRED`-vs-schema cross-check, the differential run over the collaborators
corpus, and each of the six migration cases. None of the pre-existing tests failed there,
which is the other half of the claim: the new tests fail for the reason they were written,
not because the stash broke the module.

## T1, T2, T5, T8 — the schema refusals and the drift guards

```text
$ cd cli && uv run pytest -q tests/test_configschema.py
40 passed in 1.63s
```

Covering: `notificationChannel` and `collaborator.notifications` gone (R1.1); a
collaborator carrying `notifications` refused with `channels.slack` **and**
`the-loop migrate-config` in the message (R1.2); `handle`/`kind`/`roles` still validating
(R1.3); neither `collaborators` nor `notifications` a leaf of the CLI config schema, and
each refused with the same guidance (R2.1, R2.2); an ordinary typo still getting plain
`unknown key` and no invented advice; both identity allow-lists still schema leaves and
still accepting a real value (R2.4); every `RETIRED` row asserted absent from the schema it
names, so a row that could never fire fails the build.

The **keyword guard** and the **differential test against real `jsonschema`** both pass,
and the differential now runs the collaborators corpus too — that schema carries every
`$ref` left in the tree since the CLI config's one cross-schema reference was retired.

## T3, T4 — the migration

```text
$ cd cli && uv run pytest -q tests/test_migrations.py
36 passed in 0.15s
```

A 0.5.0 config carrying both filled-in blocks migrates to a clean `0.6.0`; both removals
are reported; `state`, `routing` (with its `authorizedUsers`) and `channels` come out
byte-identical to what went in, and the input mapping is never mutated (A3). A second run
reports no change and produces an identical config (R3.3). A config that stamps the
current version while still carrying `collaborators` is still detected and still refused
(A1). The refusal names the key, `channels.slack`, `routing.authorizedUsers` and the
upgrade command (R2.2, A2). A filled-in block gets the "here is what to configure instead"
note; the shipped empty default gets the removal and no lecture (R3.4).

The command-level round trip, as an operator sees it:

```text
$ the-loop migrate-config --dry-run   # 0.5.0 config with both blocks
migrated the CLI config:
  · collaborators removed — nothing read it (issue-304); Slack is declared once under `channels.slack`
  · notifications removed — nothing read it (issue-304); Slack is declared once under `channels.slack`
  · version '0.5.0' → '0.6.0'
  note: what you had declared there was never delivered on. To be notified, set
        `channels.slack`'s `botTokenEnv` and `channel` and subscribe its `events` list to
        the event names you want — one channel for the daemon, not one list per person;
        per-person routing is not built

$ the-loop migrate-config --dry-run   # the same file, second run
config is already current; nothing to migrate
```

## T6, T7, T11 — the whole suite, unchanged behaviour

```text
$ cd cli && uv run pytest -q
2698 passed, 1 skipped in 147.89s
```

**2679 → 2698**, nineteen added, none removed and none weakened. The channel suite
(`test_channels.py`, `test_channels_integration.py`,
`test_standing_channels_integration.py`) is green untouched — no channel code was
modified — and the pinned harness-config read-surface test still holds: `notifications`
remains a harness-config key and still gates the graph's `notify` hook (R2.5, NFR1, NFR2).

Six test fixtures that hard-coded `"0.5.0"` now read `CURRENT_CONFIG_VERSION`. That is the
fix rather than six new literals: a fixture pinned to a version the code is about to bump
fails on every future migration for a reason that has nothing to do with what it tests.

```text
$ cd cli && uv run ruff check . && uv run ruff format --check .
All checks passed!
258 files already formatted
$ cd cli && uv run pyright
0 errors, 0 warnings, 0 informations
$ npx markdownlint-cli2@0.18.1 "docs/**/*.md" "skills/**/*.md" "commands/**/*.md"
Linting: 876 file(s)
Summary: 0 error(s)
```

## T8, T9 — the shipped configs and the docs

```text
$ uv run --project cli python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

All seven validate under real `jsonschema`, with the retired shapes gone from both
templates and both of this repo's own configs, commented examples included (R4.1). The
schema/docs parity tests pass in both directions — no doc heading survives for a removed
key (P3), and no schema leaf is undocumented (P4) — as do the `.the-loop/` ↔
`the_loop/schemas/` byte-parity and manifest assertions.

## T10 — no doc promises what no code delivers

```text
$ grep -ri "channel-list" docs/ skills/ commands/
docs/config/harness-config.md: transport and a `channel-list` — and **no code ever read it**, …
```

The one live hit is the sentence that says the shape is gone. The others are under
`docs/specs/issue-82/`, `docs/specs/issue-245/` and `docs/decisions/decision-035.md` —
the per-work-item record and the decision log, which are **history and are not rewritten**.
decision-035 instead carries a `superseded in part by` marker naming this work item, the
convention decision-005, decision-021 and decision-030 already set.

```text
$ grep -rn "delivered on each recipient" . --exclude-dir=.git
(only this work item's own requirements/testing-plan, quoting the sentence that was removed)
```

`skills/the-loop/reference/collaboration.md` now says a notification is gated by
`notifications.events` and delivered to a **channel**, and names the two allow-lists as the
only places identity is declared (R4.2, R4.4).
[`docs/capabilities/channels.md`](../../capabilities/channels.md) carries two new
behaviour bullets and a History row (R4.3).
