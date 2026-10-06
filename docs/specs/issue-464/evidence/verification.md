---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#464"
---

# Verification: a Slack app from one click (issue-464)

All automated rows of the [testing plan](../testing-plan.md) ran and passed. T6 (Slack
opening the link) could not run here; see the end.

## Activities

- [x] **T1–T3: unit tests, red then green.** `cd cli && uv run python -m pytest -q
      tests/test_channels_commands.py -k "manifest or name or link or write"`
- [x] **T4: regression.** ruff check, ruff format --check, pyright, the config
      validator, the full CLI suite, markdownlint on every changed file.
- [x] **T5: security review.** [`security-review.md`](security-review.md).
- [ ] **T6: manual, in Slack.** Not run: this cloud session has no Slack workspace.

## T1–T3 red (before `app_manifest.py` and the new options)

```text
FAILED tests/test_channels_commands.py::test_a_named_manifest_changes_the_two_name_fields_and_nothing_else
FAILED tests/test_channels_commands.py::test_the_link_opens_slacks_create_dialog_with_the_manifest
FAILED tests/test_channels_commands.py::test_write_keeps_the_manifest_beside_the_cli_config
FAILED tests/test_channels_commands.py::test_write_regenerates_under_the_kept_name_and_names_the_delta
FAILED tests/test_channels_commands.py::test_write_reports_no_reinstall_when_only_the_name_changed
FAILED tests/test_channels_commands.py::test_write_without_a_kept_file_uses_the_packaged_name
FAILED tests/test_channels_commands.py::test_write_leaves_a_file_it_cannot_read_untouched_without_a_name[not json]
…
17 failed, 8 passed, 54 deselected in 1.16s
```

All 17 new tests the filter selects failed. The 8 that passed are existing tests whose
names the filter also matches (the packaged manifest, the guide pin, the shortcut limit,
usage and help). The new `test_no_option_still_prints_the_packaged_file_and_json_parses_back`
is outside the filter. It runs green in the whole file (`79 passed`) and in the full suite.

## T1–T3 green

```text
25 passed, 54 deselected in 0.40s
```

## T4 regression

```text
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
414 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
$ cd cli && uv run python -m pytest -q
5409 passed, 1 skipped, 7 warnings in 233.07s (0:03:53)
$ npx --yes markdownlint-cli2@0.18.1 <changed markdown>
Summary: 0 error(s)
```

## The verb, run by hand

`$THE_LOOP_CLI_CONFIG` pointed at a scratch directory, shown here as `~/.the-loop`. The
link is cut after 60 characters.

```text
$ the-loop channels manifest --name "the-loop-dana" --write
wrote ~/.the-loop/slack-app-manifest.json (app "the-loop-dana")
create a new app from it: https://api.slack.com/apps?new_app=1&manifest_json=%7B%22display_information%22%3A%7B%22name%22%3A%22the-loop-d…

$ the-loop channels manifest --write
~/.the-loop/slack-app-manifest.json unchanged (app "the-loop-dana")
create a new app from it: https://api.slack.com/apps?new_app=1&manifest_json=%7B%22display_information%22%3A%7B%22name%22%3A%22the-loop-d…

# files:read removed from the kept file, as if it were written by an older release
$ the-loop channels manifest --write
wrote ~/.the-loop/slack-app-manifest.json (app "the-loop-dana")
  bot scopes: + files:read
  bot events: (unchanged)
  An app created from the old manifest: replace its manifest (api.slack.com/apps → your app → App Manifest) and reinstall it, since its scopes changed.
create a new app from it: https://api.slack.com/apps?new_app=1&manifest_json=%7B%22display_information%22%3A%7B%22name%22%3A%22the-loop-d…

$ the-loop channels manifest --name ""
the-loop channels manifest: the app name is empty
exit 2
```

The full link for the packaged manifest under a name is about 2,000 characters, well
inside what browsers and Slack accept in a URL.

## Not run: T6

Opening the link needs a Slack login and a workspace. The test decodes the printed link
back to the exact manifest. Slack documents the `new_app=1` and `manifest_json`
parameters for its create-app dialog. The first operator to run `/the-loop:init` with
Slack is the live check.
