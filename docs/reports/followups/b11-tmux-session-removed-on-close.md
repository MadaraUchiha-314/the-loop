# The tmux session is removed on close despite `keepSessionOnClose: true`

**Kind:** bug · **Source:** e2e Slack test 2026-09-19 (B11) · **Not fixed in issue-393**

## What happens

The close path logged `session.retained tmux_target=…` and then, 300 ms later,
`session.cleaned removed=["tmux","session"]` from the `close-event` source; the
pane is gone (`can't find pane`). The instance's config has
`routing.tmux.keepSessionOnClose: true`, and the session-started comment had
promised "The session is kept after the work completes, so this transcript stays
readable."

## Impact

The transcript the ticket points a reader to no longer exists — the one place to
see *why* a long phase (the 55-minute critic round in the test) took as long as it
did is gone.

## Suggested fix (from the report)

The issue-closed cleanup path should honour `keepSessionOnClose` the way the
graph-complete path does — or the two paths should share one retention decision,
so a session cannot be both retained and cleaned on the same close.

## Acceptance

- WHEN a work item closes AND `routing.tmux.keepSessionOnClose: true` THEN the
  tmux session (and its transcript) survives the close, matching the
  graph-complete path.
