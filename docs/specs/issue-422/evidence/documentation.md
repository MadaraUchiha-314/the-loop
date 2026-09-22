---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#422"
---

# Documentation: the suite writes into the checked-in `.the-loop/` when run from the repo root

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Updated in this PR

**[`docs/capabilities/testing-and-contracts.md`](../../../capabilities/testing-and-contracts.md)**
holds this repository's standing test conventions, and issue-412's neighbouring rule on
ambient state is the one this extends.

- A new section, *The suite never writes into a checked-in `.the-loop/`*. It covers: the
  rule (a test gives the code it runs a `tmp_path` state root); the two routes by which a
  default reaches this checkout's tree; the guard, what it covers and why it covers the
  working directory's tree too; why it records rather than raises; its subprocess limit;
  and the rule that a file assertion first establishes the file was written.
- A history row for issue-422, above issue-412.

**[`docs/capabilities/channels.md`](../../../capabilities/channels.md)** owns the Slack
name → id directory and the subscription probe.

- The name-resolution requirement now says the probe resolves names through the
  state-root cache too.
- A history row for issue-422, above issue-409.

**[`.gitignore`](../../../../.gitignore)**: the `cli/.the-loop/` entry's comment said a
test run leaves residue there on every hook run, which this change makes untrue. It now
says the suite fails such a write, and that the entry stays for old checkouts.

## Not affected

- [`docs/config/cli/channels-options.md`](../../../config/cli/channels-options.md) already
  documents the cache at `<state.root>/local/slack-directory.json`. The code now matches
  the page, so the page is unchanged.
- [`docs/cli/state.md`](../../../cli/state.md) uses `github-octo-repo-15.json` as a worked
  example of a portable record. It is an illustration of the layout, not a reference to
  the deleted file, and stays.
- [`skills/the-loop/reference/testing.md`](../../../../skills/the-loop/reference/testing.md)
  is the plugin's shipped guidance to consuming projects. The guard is about this
  repository's suite and its own `.the-loop/`, the same reasoning issue-412 recorded for
  its rule.
- `docs/api-specs/openapi/the-loop.v1.yaml`: no route, parameter or response changed.
- No decision record. Nothing overturns a recorded decision. The judgements worth keeping
  are argued in [`bugfix.md`](../bugfix.md) § The fix: an audit hook over a snapshot,
  guarding the working directory's tree, recording rather than raising, and leaving the
  daemons' defaults alone.
