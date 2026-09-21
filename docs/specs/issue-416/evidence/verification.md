---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#416"
---

# Verification: multi-modal messages are forwarded to the session, never parsed by the loop

> The `verification` node's captured output. The results table lives in
> [`testing-plan.md`](../testing-plan.md) § Verification results, against the matrix rows
> it planned; this file is the raw evidence those rows point at.
>
> Every command was run from the repository root. `uv` is invoked as `python3 -m uv`
> (and `make` with `/usr/local/bin` first on `PATH`) because the container's own `uv`
> (0.8.17) predates this repo's `required-version` pin (`>=0.12,<0.13`); `pip install
> "uv>=0.12,<0.13"` supplied 0.12.17. No behaviour of the repo's tooling changed. No
> network call was made by any test: every fetch goes through an injected fake, and the
> credential variables the tests set are the literals in the test source.

## T1 / T8 — the unit module, red then green

Red — the test module was written before the module it asserts:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_attachments.py
    from the_loop.channels import attachments as mod
E   ImportError: cannot import name 'attachments' from 'the_loop.channels'
ERROR cli/tests/test_attachments.py
1 error in 0.18s
```

Green, after `cli/the_loop/channels/attachments.py` landed:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_attachments.py
.......................                                                  [100%]
23 passed in 0.06s
```

The abuse-case selection (T8), across both new modules:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_attachments.py \
    cli/tests/test_attachments_integration.py \
    -k "off_host or redirect or cap or hostile or untrusted or stranger or permalink"
13 passed, 26 deselected in 0.12s
```

## T2 — the integration scenarios, red then green

Red — the scenarios were written before the pipeline, the dispatcher and the probe
learned about files:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_attachments_integration.py
E   ImportError: cannot import name 'attachment_findings' from 'the_loop.channels.slack'
ERROR cli/tests/test_attachments_integration.py
1 error in 0.19s
```

Green, after the wiring; the sixteen scenarios, by their Gherkin titles:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_attachments.py \
    cli/tests/test_attachments_integration.py
.......................................                                  [100%]
39 passed in 2.27s
```

| Scenario | Row |
|---|---|
| a Slack image reaches the session as a path and the ticket as a link | T2 |
| a voice note reaches the session and the ticket as Slack's transcript | T2 |
| a transcript Slack is still producing is re-read before delivery | T2 |
| a message that is only an image is delivered | T2 |
| a file that cannot be fetched is still named, and the message is delivered | T2 |
| a stranger's file is never fetched | T8 |
| a poll-read reply carries its files | T2 |
| a gate answer with a file names it on the record | T2 |
| a recorded thread names the files its messages carried | T2 |
| a kickoff with a file links it from the issue body | T2 |
| a GitHub comment's screenshot reaches the pane as a path after the excerpt | T2 |
| a private asset with no token is named, not fetched | T2 |
| an asset seen again is reused from disk | T2 |
| a prompt whose event carries no attachment is byte-identical to before | T10 |
| the manifest declares files:read | T2 |
| a missing files:read is one finding; unreadable scopes are none | T2 |

Two scenarios were corrected between red and green for the **test's** shape, not the
code's: the kickoff's issue body ends with the ledger's own attribution footer, so the
📎 line is asserted present after the message rather than last; and the pipeline's drop
record for a stranger is `{"outcome": "unauthorized-actor"}`, not a `dropped` wrapper.

## T10 / T12 — the touched suites, parity and the event catalog

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_state_portability.py \
    cli/tests/test_channels_mentions.py cli/tests/test_channels_dm.py \
    cli/tests/test_doctor_slack.py cli/tests/test_interaction_integration.py \
    cli/tests/test_channels.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py
231 passed in 2.96s
```

Four tests in that set went red first and were made honest rather than green:
`test_channels_dm.py` (two probe tests), `test_channels_mentions.py` (the mention
finding) and `test_doctor_slack.py` (the clean app) pin an exact findings count against
a fake app whose granted scopes predate `files:read`; each fixture now grants the scope,
so a "clean" app is one that can fetch a file, and the absence is pinned as issue-416's
own finding in the integration module. `test_eventlog.py` caught the two new event types
before they were catalogued (self-review F1).

```text
$ python3 -m uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## The full `make check`

```text
$ PATH=/usr/local/bin:$PATH make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
uv run ruff format --check cli hooks
350 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   … (all six, as above)
uv run --project cli python -m pytest -q cli
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 4489 passed, 1 skipped in 196.81s (0:03:16)
```

**The four failures are pre-existing and not this work item's.** All four are in
`cli/tests/test_instance.py` and concern the argv a tmux spawn is built with (the `-e`
per-session environment, issue-410); this work item touches no spawn path. Reproduced on
an untouched checkout of `origin/main` in a separate worktree:

```text
$ git worktree add <scratch>/main-tree origin/main
$ cd <scratch>/main-tree && PYTHONPATH=cli python -m pytest -q cli/tests/test_instance.py
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 59 passed in 0.26s
```

Identical set, none of this change applied — the same four issue-415 recorded, with the
same visible cause (this container's tmux behaviour around `-e`). Recorded, not fixed:
outside this work item's scope.

One side effect of the full suite worth naming: a test rewrites the timestamp inside the
tracked fixture `.the-loop/portable/github-octo-repo-15.json`. It was restored with
`git checkout` after each run and is not part of this change.

## T11 — the operator's first-use check (not executed here)

No Slack workspace, app or token exists in this environment, and a private-repository
asset needs a token with access; neither can be faked into meaning anything. The check
is the operator's, on first use after re-installing the app with `files:read`:

1. In a work item's bound thread, mention the-loop with a **screenshot** attached. Expect:
   👀 then ✅ on the message; a `📎 <name> (image/png, …) — <permalink>` line on the
   ticket's record; the session's pane ends with `Attachments (1)` naming a path under
   `<state.root>/local/attachments/<slug>/`, and the session reads it.
2. Record a **voice clip** in the same thread and mention the-loop. Expect: the same 📎
   line plus `> Slack's transcript: …` on the ticket; the pane's line quotes the same
   transcript. If Slack was still transcribing, the pane says so and names the saved
   clip.
3. On a **private repository**, comment on the work item with an image. Expect: the
   session's next prompt ends with an `Attachments (1)` section naming a saved path —
   or, with no `GH_TOKEN`/`GITHUB_TOKEN` in the daemon's environment, the URL with *the
   transfer failed* and the offer to try it.
4. `the-loop channels status --probe` on an app that was **not** re-installed. Expect:
   the `files:read` finding, and step 1's file named with *the transfer failed* rather
   than a path.
