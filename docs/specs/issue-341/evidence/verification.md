# Verification — issue-341

> Executed at `verification` on 2026-09-11, head of `claude/github-issue-341-k4mghj`,
> from the repository root with the configured tooling (`uv`, `pytest`, `ruff`,
> `pyright`, `markdownlint`). Nothing here is a credential: every token, member id,
> channel id and repository name in the tests is a fixture, and the twelve repositories
> named in the ticket are the reporter's own public list.

## Red → green

The unit suite was written first. Against `cd1ae94` (13.11.1) it did not collect:

```text
E   ImportError: cannot import name 'kickoff' from 'the_loop.channels'
```

After tasks 1–9 every row below passed. One pre-existing assertion changed:
`test_bus.py::test_kickoff_needs_the_grant_and_a_repo` pinned the precondition this work
item deliberately removes, and is now
`test_kickoff_needs_the_grant_not_a_repo` — the grant and a channel open the read; the
target is the message's to name. No other existing assertion moved.

## T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py
...............................................                          [100%]
47 passed in 0.15s
```

Covers the declared set (order, the operator's own slug preserved, dedup by key, a
malformed entry, a non-`github` source, an unreadable `polling`), the prefix grammar
(three shapes, case, prose, metacharacters, a four-segment path, a prefix on line two),
every row of the resolution table, stripping, the four refusal wordings and the
candidate cap, the `kickoff_enabled` precondition, and the three `channels status` lines.

## T2 — integration scenarios

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "kickoff"
.......                                                                  [100%]
7 passed, 30 deselected in 0.09s
```

The five new Gherkin scenarios — a prefixed kickoff opening in the repository it named
(not the fallback), an ambiguous prefix refused in the thread with nothing created or
bound, a prefix-less message still opening in `kickoff.repo` with its text untouched, a
message asked for a prefix when there is no fallback, and an unlisted member told
nothing — plus the two pre-existing kickoff scenarios (issue-312's thread binding,
issue-337's Start button), which are unchanged.

## T8 — abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py -k "unauthorized or undeclared or metachar or host or leak or malformed or grant or told_nothing"
............                                                             [100%]
12 passed, 35 deselected in 0.11s

$ uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "told_nothing"
.                                                                        [100%]
1 passed, 36 deselected in 0.07s
```

One test per abuse case A1–A7; the dispositions are in `evidence/security-review.md`.

## T10 — migration / upgrade

```text
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_channels_commands.py cli/tests/test_channels_buttons.py cli/tests/test_channels_integration.py cli/tests/test_bus.py
.............................................................            [100%]
277 passed in 7.89s
```

Both schema copies stay byte-identical (only three descriptions changed; no key added,
removed or renamed), docs parity holds in both directions, the event catalog documents
the four new `kickoff-` drop reasons, and the slash command's own suite passes unchanged
against the shared repository-set builder it now delegates to.

## T12 — lint / format / typecheck / config validation / full suite

```text
$ make check
uv run ruff check cli hooks
All checks passed!
npx markdownlint-cli2 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
293 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   (7 files)
uv run --project cli python -m pytest -q cli
3418 passed, 1 skipped in 145.18s (0:02:25)
EXIT=0
```

## T13 — security review

`evidence/security-review.md` — A1–A7, each closed by a named test; tier 3, so no human
security sign-off is required.

## Requirement coverage

| Requirement | Proved by |
|-------------|-----------|
| R1.1, R1.2, R1.3, R1.4 | T1 (grammar, resolution, stripping), T2 (the prefixed scenario) |
| R1.5 | T2 (`labels == ["the-loop: auto-execute"]` on the prefixed create) |
| R2.1 | T1 (the declared-set tests), T10 (`test_channels_commands.py` on the shared builder) |
| R2.2, R2.3, R2.4 | T1 (undeclared qualified, ambiguous bare, unmatched bare), T8 (A2) |
| R2.5 | T1 (the four wordings, the cap), T2 (the ambiguous scenario) |
| R2.6 | T2 + T8 (A1 — no reaction, no reply, no disclosure) |
| R3.1, R3.4 | T2 (the fallback scenario), T10 (schema parity) |
| R3.2, R3.3 | T1 (`no-target`, `kickoff_enabled`), T2 (the no-fallback scenario) |
| R4.1 | unchanged code path, pinned by the pre-existing kickoff scenarios in T2 |
| R4.2 | T10 (`test_eventlog.py`) |
| R5.1 | T1 (the `channels status` tests), T10 (`test_docs_parity.py`) |
