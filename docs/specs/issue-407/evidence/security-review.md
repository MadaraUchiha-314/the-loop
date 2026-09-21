---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#407"
---

# Security review: the release leaves `uv.lock` a version behind (issue-407)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Permissions and credentials:* unchanged. `release.yml` keeps `contents: write` on
    the release job and `id-token: write` on the publish job; no secret, token or
    environment is added, read or logged. The new step uses the checkout the job
    already authenticated.
  - *`git tag -f`:* moves one tag, in the runner's own checkout, created seconds
    earlier by `cz bump` in the same job, never yet pushed — the push step below it is
    the first time that ref leaves the runner. No published tag or release is
    rewritten. The `concurrency: release, cancel-in-progress: false` group still means
    one release at a time, so no second job can be holding the same ref.
  - *`git commit --amend`:* `git add uv.lock` names exactly one path, so the amend can
    only extend the bump commit by the lockfile. The runner's checkout is otherwise
    the merge commit the job started from, and `actions/checkout` gives it a clean
    tree.
  - *Supply chain:* `uv lock` re-resolves against the same index the job already used
    to run `cz` at all, and the pinned resolver makes that resolution deterministic —
    strictly more predictable than the unpinned status quo. The published artifact is
    still built by `uv build --package the-loopy-one` from `cli/`, and the lockfile is
    dev tooling, not a dependency of the wheel.
  - *New failure modes are fail-closed:* `uv sync --locked` turns a silent in-runner
    mutation into a failed check; `required-version` turns an unknown resolver into a
    refusal. Neither widens what runs.
  - *Trust boundary:* unchanged — nothing here reads event text, channel input or any
    other untrusted source; the inputs are the repository's own files and
    `steps.bump.outputs.version`, which commitizen computes from the repository's tags.
- **Risk tier:** 3 — raised by the sensitive path `.github/workflows/**`
  (`reference/workflow.md`). Below the tier-4 threshold that requires a named human
  security sign-off, so the autonomous review suffices; the PR approval is the human
  gate.
- **Human sign-off:** not required at tier 3.
