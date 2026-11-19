Record a pull request as delivering a work item, so its comments,
reviews and CI results route to that work item's session. Call this in
the same step as opening the pull request: a pull request the-loop
authored carries none of the linkages the router can otherwise infer.
`pull_request` is its number in the work item's own repository, or a
full ref (github:OWNER/REPO#16) for one in another repository. With
`discover` and a `branch` instead, every open pull request whose head is
that branch (in `repository`, default the work item's) is recorded.
A newly recorded pull request also gets every routing.autoExecuteLabels
label, so the poller lists it. A pull request opened with
`create_pull_request` is already recorded.
