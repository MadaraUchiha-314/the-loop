# Evidence: automated tests (issue-393)

The logic gate for the five bugs and the room rework. Run from `cli/` with
`uv run pytest`. The one failure noted below is pre-existing and environmental
(a critic CLI installed on the build machine), not a regression from this work.

## T1 — unit rows

```
$ cd cli && uv run pytest tests/test_room_policy.py tests/test_voice.py \
    tests/test_channels_digest.py tests/test_channels_buttons.py \
    tests/test_selection_control.py tests/test_channels_upgrade.py \
    tests/test_channels_directory.py tests/test_workchannels.py \
    tests/test_critics.py tests/test_doctor_slack.py \
    tests/test_graph_hooks.py tests/test_graph_drive.py -q
386 passed, 1 failed
```

The one failure is `tests/test_critics.py::test_list_reports_availability`, which
asserts `cursor-agent` is *not* installed ("not installed in CI"); it is installed
on this build machine, so the assertion is false here and passes in CI. It predates
issue-393 and is unrelated (confirmed by running it against the base branch).

Covers: RoomPolicy's seven rules (one test each); the voice table (emoji, first
person, no room header, single signature, short channel id); the summary
sanitizer (mention/broadcast defused, capped) and summary-leads-the-gate render;
membership-first channel resolution and the truncated-vs-exhausted refusal; the
critic `--timeout` threading regression and the policy timeout surfacing;
phase-selection checkbox render and typed skip-grammar; `set-phase-label`
create-and-retry and the non-missing-error degrade; the doctor's probe/verdict.

## T2 — integration rows (Gherkin-docstringed)

```
$ cd cli && uv run pytest tests/test_channels_integration.py \
    tests/test_channels_declared_integration.py tests/test_bus_integration.py \
    tests/test_ask_reply_integration.py tests/test_graph_drive.py \
    tests/test_graph_refs_integration.py tests/test_control_integration.py -q
169 passed
```

Covers the scenarios the design named: the first authorized answer after a gate
publishes advances the gate (B8); a spawned session inherits the daemon's config
and `ask` warns on a channel-less bus (B6); a gate's mirror and lifecycle lines
are suppressed after its pending message, and an intermediate transition is
collapsed (R6); the session's question reaches the room and a template for a node
the session spoke for is suppressed (R12); the checkbox Execute composes the
signed execute (R9); the PR-review gate names the pull request (B7/O8); an ignored
Socket Mode envelope is logged and a refused keyword explains itself (B3/B2).

## T8 — abuse cases

Run within the suites above (markers/scenario names): an unauthorized gate answer
or checkbox submit changes nothing and freezes nothing; a hostile summary is
escaped, capped and its mentions/broadcasts defused (it can page no one); a
skip-grammar naming an unknown or protected phase refuses the whole reply rather
than freezing a different selection; label-ensuring never touches an undeclared
repository.

## T10 — config / state compatibility

`channels.slack.room.style` round-trips through the schema (both copies kept
identical) and defaults to `agentic`; a pre-issue-393 `ChannelState` file loads the
delivery map empty (no crash, no migration) and a lost record degrades that item's
room to classic delivery, never to silence.

## T5a — mockup

`design/slack-room-redesign.html` is self-contained (inline CSS/JS, system fonts,
emoji glyphs, no network) and renders the before/after room at phone (~400 px,
stacked) and desktop (side-by-side) widths, with requirement-mapped callouts.

## Not executed — blocked on deployment

T4 (the live re-run of the report's timeline against the operator's daemon), T5b
(redacted live-room screenshots) and T11 (the operator's readability verdict)
require the patched build deployed to the operator's cloud-workspace daemon, which
is outside the build environment's reach. They are the final confirmation that the
room *reads* right to a person; the rows above prove every fix and every rework
rule at the logic level. Bring-up is in `testing-plan.md` § Verification environment.
