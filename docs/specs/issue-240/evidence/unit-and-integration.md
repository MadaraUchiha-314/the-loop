# Evidence — automated tests (issue-240)

Testing plan rows: T2, T3, T4, T5, T6, T15. Every command was run from the project root
with the configured tooling (`uv`, `pytest`, `ruff`, `pyright`).

The red run that preceded all of this is [`red.md`](red.md).

## T2 + T5 — the delivery argv, unit and through the real dispatch pipeline

```console
$ uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py \
    cli/tests/test_tmux_runner_integration.py
132 passed in 3.76s
```

The two assertions that carry the fix:

- `test_deliver_pastes_bracketed_then_submits_without_send_keys` — the exact four-command
  sequence, `-p` on the prompt paste and not on the submit, `-d` on both, distinct buffer
  names, and `"send-keys" not in verbs`.
- `test_deliver_removes_both_temporary_files` — both `mkstemp` paths gone, including when
  the second paste fails.

## T3 + T6 — the notice, and the abuse case

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poller.py \
    -k "notice or giveup or given_up"
10 passed, 112 deselected in 0.24s
```

Covering: the body carries the marker and the attribution line, names the comment and the
attempt count, states the recovery and `the-loop sessions list`; it falls back to the id
when the provider gave no URL; its **signature** admits no parameter that could carry a
comment body (R2.6 as a property of the function, not of its prose); and a hostile comment
body reaches none of the posted text.

## T4 — the poller end to end

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poller.py \
    cli/tests/test_poller_integration.py
140 passed in 1.57s
```

`test_an_abandoned_comment_is_reported_on_the_work_item` drives the real
`GitHubPollProvider` and the real `Dispatcher` with tmux delivery failing, and asserts:
one notice, posted to `repos/octo/repo/issues/15/comments`, marked as the-loop's own, and
**not** repeated on the next cycle. Its siblings in `test_poller.py` cover a `gh` that
refuses (`returncode=1`) and a runner that raises — in both, `summary.failures == 1` and
the comment is baselined exactly as before, so R2.4 holds.

## T15 — the whole suite

```console
$ uv run --project cli python -m pytest -q cli
2116 passed, 1 skipped in 96.17s (0:01:36)
```

One failure was found on the way there and fixed: `test_every_emitted_event_type_is_documented`
rejected `poll.giveup_reported` / `poll.giveup_report_failed` until both were described in
`eventlog.EVENT_TYPES`. The repository's own guard, doing its job.

## Lint, format and types (CI parity)

```console
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
223 files left unchanged
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

`pyright` initially rejected the new poller construction in the tests (an in-process
double is not a `Dispatcher`, and a fake `gh` is not `subprocess.run`). Routed through the
existing deliberately-unannotated `make_poller` helper rather than adding casts — the
convention that file already documents.

## Scenario coverage

```console
$ uv run --project cli the-loop scenarios --format table
319 lines
```

The two integration tests this work item touched keep their Gherkin docstrings, and the new
one carries a `Requirement:` link to `bugfix.md`'s Requirement 2.
