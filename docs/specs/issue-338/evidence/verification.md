# Verification — issue-338

> Executed at `verification` on 2026-09-11, head of `claude/github-issue-338-lk8282`,
> from the repository root with the configured tooling (`uv`, `pytest`, `ruff`,
> `pyright`, `markdownlint`). Nothing here is a credential: every URL, path, comment
> and token name in the tests is a fixture.

## Red → green

The new tests were written first. Against `3b7563c` (13.10.0) the unit module did not
import (`ImportError: cannot import name 'digest' from 'the_loop.channels'`) and the
three scenarios failed on the raw section text (the fence and the traceback still in
it, the marker literal); after tasks 1–5 every row below passed. Two pre-existing pins
moved: `test_bus.py::test_render_blocks_caps_text_and_points_at_the_link` now names
`long_messages="truncate"` (and pins the digest beside it), and
`test_channels.py::test_config_defaults_match_the_schema` gained the new key. The
self-review's six findings each landed with a test before the fix
(`test_code_is_drawn_as_written`, `test_a_text_that_grows_past_the_cap_when_drawn_is_digested`,
`test_a_question_in_a_heading_leads_and_leaves_no_empty_heading`, the `<` case inside
`test_absolute_paths_are_shortened_and_urls_untouched`'s design, the trace-start
tightening covered by `test_fences_tables_and_traces_become_pointers`).

## T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py cli/tests/test_channels.py::test_config_defaults_match_the_schema
..........................................                               [100%]
42 passed in 0.23s
```

## T2 — integration scenarios

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py -k "digest or untouched or excerpt"
....                                                                     [100%]
4 passed, 28 deselected in 0.08s
```

The four: the three issue-338 scenarios (a long agent comment reaches Slack as a digest
that leads with the ask; a short comment reaches Slack untouched; a notification's
artifact excerpt is digested too) plus the issue-337 scenario the selection also
matches (an unlisted member's press leaves the message untouched).

## T7 — the pathological input

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py -k pathological --durations=1
0.05s call     tests/test_channels_digest.py::test_a_pathological_comment_digests_in_linear_time
1 passed in 0.08s
```

A 64 KB comment of unclosed `**`, `<!--`, `[`, fence openers, list markers and pipes:
three digests, three drawings and three cuts in 0.05 s against the test's 5 s bound.

## T8 — abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests/test_channels_digest.py -k "pathological or broadcast or footer_links or foreign_comment or reads_the_digest"
....                                                                     [100%]
4 passed, 37 deselected in 0.09s
```

A1–A5 each closed by a named test — the table is in [`security-review.md`](security-review.md)
(A5 is closed by `test_a_foreign_html_comment_is_removed_too` together with
`test_html_comments_never_reach_slack`).

## T10 — migration, parity, config validation, the existing suites

```text
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_configschema.py cli/tests/test_channels.py cli/tests/test_channels_buttons.py cli/tests/test_channels_integration.py cli/tests/test_bus.py cli/tests/test_channels_commands.py
...............                                                          [100%]
303 passed in 8.95s
```

Both schema copies are byte-identical (`cmp` clean; `test_the_packaged_schema_is_the_authored_schema`);
`channels.slack.longMessages` is documented with type and default
(`test_p4_every_schema_leaf_is_documented`, `test_p5_…`); a 13.10.0 configuration
parses unchanged and resolves `long_messages == "digest"`
(`test_long_messages_is_parsed_and_defaults_to_digest`); the issue-309/325/334/337
channel suites are green on the new renderer.

## T12 — `make check`

The repository's own gate — ruff, ruff format, markdownlint over every markdown file,
pyright, `validate_config`, the full suite — as pre-commit and CI run it, on the tree
the PR carries (this file was pasted in after the run and linted on its own).

```text
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1040 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
287 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
3341 passed, 1 skipped in 148.94s (0:02:28)
exit=0
```

## `channels status`, as printed

With `maxChars: 900` and no `longMessages` key (the default):

```text
  verbosity:    normal
  maxChars:     900
  longMessages: digest — above maxChars: the ask first, choices numbered, code and traces as pointers, cut at a sentence, the link for the rest
  read:         poll every 30s
```
