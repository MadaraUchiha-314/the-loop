---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#407"
---

# Verification: the release leaves `uv.lock` a version behind (issue-407)

> The matrix is [`testing-plan.md`](../testing-plan.md); this file carries the
> transcripts for the rows a test file cannot hold — the release step replayed on a
> real `cz bump`, and the two tool-level contracts.

## Verification results

| Row | What was verified | Command | Outcome |
|-----|-------------------|---------|---------|
| T1 | `check_uv_lock`: stale member, in-step member beside registry packages, no member | `cd cli && uv run pytest tests/test_version_lockstep.py -q` | pass (4 passed) |
| T2 | the shipped guard against this repository, red before / green after | `python3 scripts/check_version_lockstep.py` | pass |
| T3 | the fold-in step on a real `cz bump` | replay, below | pass |
| T4 | the step's no-op path | replay, below | pass |
| T5 | `uv sync --locked` red on the pre-fix lockfile, green on the committed one | `uv sync --locked` | pass |
| T6 | `required-version` refuses uv 0.8.17, admits uv 0.12.17 | `uv lock --check` on both | pass |
| T7 | full hook suite | `uv run pre-commit run --all-files` | pass (6 hooks) |

## T2 / T5 — the guards against the pre-fix lockfile (red first)

`main` at `46c684b` (`bump: version 19.9.0 → 19.9.1`) is the reported state: the
lockfile still names `19.9.0`.

```console
$ git stash push -q uv.lock && python3 scripts/check_version_lockstep.py
DRIFT   uv.lock: the-loopy-one locked at 19.9.0, expected 19.9.1 — run `uv lock`
versioned artifacts out of lockstep with .cz.toml version 19.9.1 — `cz bump` would
silently skip the drifted lines, and a stale uv.lock dirties the next checkout that
resolves it.
exit=1

$ uv sync --locked
The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
hint: To update the lockfile, run `uv lock`.
exit=1

$ git stash pop -q && uv sync --locked
Checked 66 packages in 0.54ms
exit=0
```

## T3 / T4 — the release step replayed on a real `cz bump`

A scratch copy of the working tree (the fix as it is committed here), tagged
`v19.9.1` to stand in for the last release, then one releasable commit, then the
release job's own `uv run cz bump --yes`, then the step's script **verbatim**.

```console
### after cz bump, before the fold-in step
HEAD=1cb49a6  tag v19.9.2 -> 1cb49a6
bump commit touches uv.lock? 0          ← the defect: the commit that will be pushed
                                          does not carry the lockfile

### the fold-in step
Folded uv.lock into 1639ac8; tag v19.9.2 moved with it.
HEAD=1639ac8  bump: version 19.9.1 → 19.9.2
tag v19.9.2 -> 1639ac8   (equal to HEAD: yes)          ← R1.2
bump commit now touches:
  .claude-plugin/marketplace.json
  .claude-plugin/plugin.json
  .cursor-plugin/marketplace.json
  .cursor-plugin/plugin.json
  .cz.toml
  cli/pyproject.toml
  uv.lock                                              ← R1.1
uv lock --check: clean
uv sync --locked: ok
lockstep guard:
  LOCKSTEP all 5 version_files and uv.lock carry 19.9.2

### the step re-run with nothing to fold
uv.lock already carries 19.9.2 — nothing to fold in.
HEAD unchanged: yes   tag unchanged: yes                ← R1.3
```

Noted while replaying: the bump step's own `uv run cz version --project` already
leaves the lockfile dirty in the runner's checkout, because `uv run` re-resolves after
`cz bump` has rewritten `cli/pyproject.toml`. The fold-in step commits that same
result, and its `uv lock` is then a no-op — it is there so the step does not depend on
that incidental side effect, and the no-op guard is there so the step does not amend
when there is genuinely nothing to fold.

## T6 — the resolver window

```console
$ /root/.local/bin/uv lock --check          # uv 0.8.17, outside the window
error: Required uv version `>=0.12, <0.13` does not match the running version `0.8.17`.
Update `uv` by running `uv self update`.

$ uv lock --check                            # uv 0.12.17, inside it
Resolved 70 packages in 1ms
```

Before the window, the same two uv versions re-rendered the same resolution
differently — uv 0.8.17 emitted the reported `exceptiongroup` /`typing-extensions`
marker hunk on top of the version hunk, uv 0.12.17 emitted the version hunk alone.
That is the second half of the reported diff, and it is what the pin removes.

## T7 — the full hook suite

```console
$ uv run pre-commit run --all-files
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```
