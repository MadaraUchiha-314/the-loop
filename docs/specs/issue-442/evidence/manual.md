# Manual exploratory (issue-442, T10)

## Procedure

On a machine with **no** `gh` binary on `PATH`:

1. Build and install the wheel: `uv build --project cli` then
   `pip install dist/the_loopy_one-*.whl` into a fresh virtual environment.
2. Export a fine-grained token for a scratch repository (*Issues: read and write*,
   *Pull requests: read*, *Metadata: read*): `export GH_TOKEN=…`.
3. A minimal `cli-config.yaml` (version `0.11.0`): `repositories: [<you>/<scratch>]`,
   `polling.enabled: true`, `routing.enabled: true`, `routing.authorizedUsers: [<you>]`,
   no `integrations` block.
4. `the-loop start` — the pre-flight passes (no `missing credential` line); `the-loop
   status` shows the poller polling `github <you>/<scratch>`.
5. Label an issue `the-loop: auto-execute`, comment `the-loop start` — watch 👀 then 🎉 land
   on the comment, the session announcement and the control paper-trail comment appear,
   both carrying the marker.
6. Close the issue — the next cycle detects the closure and closes the session.
7. `the-loop stop`; `unset GH_TOKEN`; `the-loop start` — the pre-flight names the missing
   variables; with `polling.enabled: false` the daemon starts and the first reaction logs
   `no GitHub token: set GH_TOKEN or GITHUB_TOKEN — dispatch reactions are a no-op` once.

## Outcome

The work item's cloud checkout has no `gh` on `PATH` (steps 1, 4 and 7 were run there
against the loopback GitHub the daemon integration tests provide — `the-loop start` with
`GH_TOKEN` set polls and stops cleanly; without it, `start` names the variables). Steps 2,
3, 5 and 6 need a scratch repository and a real token, which the cloud session does not
hold; they are left for the owner to run on merge and are the one row of the testing plan
not executed by the agent. Recorded as **not run by the agent** rather than claimed.
