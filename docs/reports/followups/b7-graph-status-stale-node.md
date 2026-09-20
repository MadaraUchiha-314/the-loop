# `the-loop graph status <ref>` reports a stale node for a daemon-run item

**Kind:** bug · **Source:** e2e Slack test 2026-09-19 (B7, and O6 — same cause) · **Not fixed in issue-393**

> Filed as [#396](https://github.com/MadaraUchiha-314/the-loop/issues/396) and fixed
> there ([`docs/specs/issue-396/`](../../specs/issue-396/)). Root cause: the command
> took the ref as a spec-directory id (`docs/specs/github:…#1/`, never there) and
> defaulted `--repo` to the working directory, then fell back to the graph's start
> node in silence. It now translates the ref, resolves the session's checkout through
> the session registry, and prints the state file it read.

## What happens

After the event log had recorded `graph.advanced` through brainstorming,
requirements-definition and requirements-approval, `the-loop --config <daemon
config> graph status github:…#<n>` still printed
"at phase-selection · waiting for an authorized user to choose the phases" — run
both from the daemon's config directory and from inside the work item's own
checkout, where `docs/specs/<id>/work-item-state.json` exists and is current.

O6 is the same symptom seen from the daemon's config directory: `graph status`
reported "at phase-selection" after the item had already advanced to
brainstorming.

## Impact

`graph status` is the one read-only CLI view of "where is this item", and it is
wrong for a daemon-run item — so an operator debugging from a shell is misled.

## Suggested fix (from the report)

Find out which state file `graph status` resolves (the portable record? the
daemon's `state.root`? a different checkout than the session's?) and make it read
the same `work-item-state.json` the runtime writes — or, at minimum, print the
path it read from so the mismatch is visible.

## Acceptance

- WHEN a daemon-run item has advanced THEN `graph status <ref>` reports the node
  the runtime last wrote, from whichever directory it is run, OR prints the state
  path it resolved so a wrong answer is diagnosable.
