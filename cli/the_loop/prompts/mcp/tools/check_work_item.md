Evaluate a work item's process-graph gates against its checked-in
artifacts (pure read; the same report `the-loop check` prints).

A `repo` that is not a directory on this machine comes back as
`{"repoResolved": false, "nodes": [], "currentNode": ""}` rather than an
error. That is "this checkout is not here", NOT "this work item has no
phases" — do not report progress from it; check the path instead.

`work_item` is an id (`issue-7`) or a ref (`github:OWNER/REPO#7`). The
report's `statePath`/`stateFound` say which `work-item-state.json` it
was read from; `stateFound: false` means the position is the graph's
start node by default, not a recorded one — check the path. `pointer`
is the node that file records (`""` when none); with `recompute`,
`currentNode` is the first node the artifacts leave unmet, and can be
ahead of where the work item actually is. A report carrying `archived`
is an ENDED work item whose checkout is gone, answered from the record
its closure kept (issue-452): read `archived.outcome` for how it ended,
and do not report a position or missing artifacts from it.
