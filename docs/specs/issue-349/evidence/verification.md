# Verification evidence — issue-349

> The testing plan, executed. Every row that `testing-plan.md` marks *applies* has its
> command, its outcome and its raw output here. Commands are run from the project root.
> Date: 2026-09-11. Base: `9dcb4a1` (14.0.0).

## Red before green

The two new suites do **not collect** against the base commit — the behaviour they
describe did not exist:

```console
$ git stash push -- cli/the_loop/
$ uv run --project cli python -m pytest -q \
    cli/tests/test_channels_kickoff_picker.py \
    cli/tests/test_channels_kickoff_integration.py \
    cli/tests/test_channels_kickoff.py
E   ImportError: cannot import name 'KICKOFF_REPO_ACTION' from 'the_loop.channels.slack'
ERROR cli/tests/test_channels_kickoff_picker.py
ERROR cli/tests/test_channels_kickoff_integration.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.34s
$ git stash pop
```

## T1 — the resolver (`askable`, one meaning for `text`, `question_text`)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff.py
...........................................................              [100%]
59 passed in 0.17s
```

Sixteen of those 59 are new (43 on the base, 59 now — eight test functions, several
parametrized). They pin: `ok` and `askable` partition all six outcomes with
`empty-message` alone outside both; `text` carries the stripped message wherever a prefix
was *read* and the raw message where none was (including the fallback arm of
`unknown-repo`, which reads no prefix at all); a message that is nothing but an ambiguous
or unknown prefix resolves to `empty-message`; `question_text` quotes the prefix, teaches
`<repo>:` and renders nothing of the member's message; `refusal_text` is unchanged on
every outcome.

## T2–T5, T11 — the picker suite

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py
...................................................                      [100%]
51 passed in 0.25s
```

The whole file, because its sections map one-to-one onto rows T2–T5, T11 and the
`channels status` half of T14 — a `-k` filter over shared words (`option`, `press`)
selected most of it anyway, which was a filter that only looked precise. What each
section pins:

### T2 — the pending record

Covers R3.1–R3.4: written, read back, claimed exactly once; expiry read as absence
without a write and swept on the next write; an **undateable** record treated as expired
rather than eternal; `PENDING_CAP` dropping the oldest; `restore` putting a claimed
record back; a pre-issue-349 `slack.json` loading with an empty map and saving with the
key; a malformed `options` contributing nothing.

### T3 — rendering and the payload read

Buttons at or below `BUTTON_CHOICE_LIMIT` with unique `action_id`s (Slack requires it),
a `static_select` above; every option's **text and value** the declared slug; the
`OPTION_LIMIT` cap with the overflow named in the prose; `action_value` reading
`selected_option.value` for a select and `value` for a button; `kickoff_picker` true only
for socket **and** the grant.

### T4 — the fork

Each askable outcome asks and creates nothing; `ambiguous-repo` offers only the matched
candidates and strips the prefix it read; `resolved` and `fallback` create immediately
and ask nothing; `empty-message` refuses; `poll` mode and an empty declaration both
refuse with today's text and **no blocks**; a second read of the same message does not
re-ask; a question that could not be posted is forgotten rather than left suppressing the
next one.

### T5 — the answer

A pick opens the work item the question was holding — the issue composed from the
**held** text, in the **picked** repository, with `kickoff.labels`, the thread bound with
origin `kickoff` and the "Opened …" reply posted; the ledger receives
`DeclaredRepo.declared` and never the pressed string; a select-menu pick is read from
`selected_option`; a landed press is reported with ✅ and the picker removed, a failed one
with ⚠️, the picker kept and the record restored; a press on any other `action_id` still
takes the pre-issue-349 path. The channel's own permission is **re-read at press time**,
so a `work-item.create` revoked (or Socket Mode left) while a question was outstanding
refuses the answer — the one gate a pending record could otherwise have carried a member
past. An accepted press is acknowledged 👀 then ✅ on the question, per issue-325 R1.5.

### T11 — security / abuse cases A1–A10

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py \
    -k "abuse or mark or revoked or socket_mode"
................                                                         [100%]
16 passed, 35 deselected in 0.11s
```

One negative test per abuse case, plus the two halves of the disclosure line: an
authorized refusal is answered on the question, an unauthorized one edits, reacts and
posts nothing. Scenarios 96 and 97 cover A6 and A7 end to end. The full trace is in
[`security-review.md`](security-review.md).

## T8 — integration (Gherkin scenarios)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_integration.py
.....                                                                    [100%]
5 passed in 0.11s
```

Through `handle_socket_event`, `handle_socket_action` and `poll_once` as they are
actually composed. The scenarios are queryable, as `testing.gherkinDocstrings` requires:

```console
$ uv run --project cli the-loop scenarios --format markdown | grep 349
| 94 | a Slack kickoff asks which repository instead of refusing | a member who has never used the-loop files from their phone | github issue #349 (R1.1, R2.1, R3.4, R4.1, R4.3, R4.4) | cli/tests/test_channels_kickoff_integration.py:173 |
| 95 | a Slack kickoff asks which repository instead of refusing | a member who already knows the prefix is not asked again | github issue #349 (R1.5) | cli/tests/test_channels_kickoff_integration.py:214 |
| 96 | a pending kickoff is answered exactly once | a member double-taps, or Slack redelivers the press | github issue #349 (R3.4; abuse case A6) | cli/tests/test_channels_kickoff_integration.py:231 |
| 97 | a pending kickoff expires | nobody answers for a day | github issue #349 (R3.2; abuse case A7) | cli/tests/test_channels_kickoff_integration.py:247 |
| 98 | the question is only asked where a press can be received | the operator runs the channel in poll mode | github issue #349 (R5.1; decision-122 D1) | cli/tests/test_channels_kickoff_integration.py:265 |
```

Scenario 94 is the whole shape end to end: the question goes out with the three declared
repositories and creates nothing; the pick opens `github:jchou2/devbox#1` from exactly
the text that was written; the thread is bound; and **a reply in that thread then reaches
the work item** — the thing that proves a picked kickoff is indistinguishable from a
prefixed one.

## T14 — migration, compatibility and `channels status`

```console
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py \
    cli/tests/test_docs_parity.py cli/tests/test_eventlog.py
......................                                                   [100%]
22 passed in 0.86s
$ uv run --project cli python scripts/validate_config.py
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
$ uv run --project cli python -m pytest -q cli/tests/test_channels_kickoff_picker.py -k status
...                                                                      [100%]
3 passed, 42 deselected in 0.13s
```

No config key, no schema change, no `CURRENT_CONFIG_VERSION` bump — asserted by the
parity suite rather than assumed. `channel.kickoff_asked` is in the event catalog. The
`kickoff:` status line says whether the question can be asked and, when it cannot, which
of the two reasons applies.

## T16 — the repository's own gate

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1073 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
295 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
…
uv run --project cli python -m pytest -q cli
3537 passed, 1 skipped in 169.81s (0:02:49)
```

## T17 — security review

[`security-review.md`](security-review.md) — nine abuse cases, nine closed, two residual
risks stated.

## Pre-existing assertions that changed

**None.** Every test that passed on `9dcb4a1` still passes unchanged; the 72 new ones
(16 in `test_channels_kickoff.py`, 51 in `test_channels_kickoff_picker.py`, 5 in
`test_channels_kickoff_integration.py`) are additive. That is not luck — it is D1 doing its job. The existing
channel suites run at `read.mode: poll` (the default), where `kickoff_picker` is false
and the refusal path is byte-for-byte what it was, so the backward-compatibility claim in
`requirements.md` § NFR is asserted by the whole pre-existing suite rather than by one
test written to say so.

The one behaviour change a reviewer should look for on purpose is the `text`/
`empty-message` shift described under T1: an `ambiguous-repo` or qualified `unknown-repo`
message consisting of **nothing but the prefix** now resolves to `empty-message`. No
pre-existing test covered that combination, which is why nothing went red; the new
`test_a_message_that_is_nothing_but_a_prefix_has_nothing_to_open` covers it now, and
`decision-122` § Consequences records it as the change's one neutral cost.

## Unrelated file in the diff

`uv.lock` carries a one-line change (`the-loopy-one` `13.12.0` → `14.0.0`): the lockfile
was not regenerated by the version bump in `9dcb4a1`, and any `uv run` corrects it.
Reverting it only has it come back on the next command.
