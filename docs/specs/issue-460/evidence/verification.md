---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#460"
---

# Verification (issue-460)

Run on 2026-10-03 on branch `claude/pensive-brown-2oo6yk`, using uv 0.12.17 (the
version `release.yml` pins) and Python 3.11. `$S` is the session scratchpad. The
replays use a bare clone of this repository as the "remote" and run the job's git and
commitizen commands verbatim.

## What PyPI and the remote held before the fix

```text
$ curl -sS https://pypi.org/pypi/the-loopy-one/json | jq -r .info.version
19.21.0
$ git tag -l 'v19.2*' --sort=-v:refname | head -2
v19.22.0
v19.21.0
$ git branch -r --contains v19.22.0        # (empty: the tag is not on main)
$ git log --oneline -1 v19.22.0
95bfe36 bump: version 19.21.0 → 19.22.0
```

Run #189 log: `! [rejected] HEAD -> main (non-fast-forward)`. Run #191 log:
`fatal: tag 'v19.22.0' already exists` / `cz bump failed (exit 7)`.

## T1: red, then green

Against the pre-fix `release.yml`:

```text
FAILED cli/tests/test_release_workflow.py::test_release_builds_on_the_tip_of_main_not_the_event_sha
FAILED cli/tests/test_release_workflow.py::test_bump_commit_and_tag_are_pushed_atomically
  AssertionError: non-atomic push in step 'Push bump commit + tag to main'
```

After the fix: `2 passed`.

## T2: lockstep guard

`cli/tests/test_version_lockstep.py` passes, so every `version_files` target and
`uv.lock` carry 19.22.0. `uv lock --check` exits 0.

## T3 / T4: the race, replayed

Setup: the remote's `main` is at `3fdd80a` (#457). Check out `3fdd80a` and run
`cz bump --yes` (→ 19.22.0). Then move the remote's `main` to `250dc97` (#458 lands
mid-run) and push.

```text
[plain]  ! [rejected] HEAD -> main (non-fast-forward)
         remote tag v19.22.0: 0de6d84…   remote main: 250dc97     ← the bug: orphan tag
[atomic] error: atomic push failed for ref refs/heads/main. status: 2
         ! [rejected] HEAD -> main (non-fast-forward)
         remote tag v19.22.0: ABSENT     remote main: 250dc97     ← fixed: nothing lands
```

## T5: recovery

Setup: the remote's `main` is this branch's head, and the orphan `v19.22.0` (on `95bfe36`)
is present.

```text
$ cz bump --yes --changelog
bump: version 19.22.0 → 19.22.1
tag to create: v19.22.1
increment detected: PATCH
$ head CHANGELOG.md
## v19.22.1 (2026-10-03)
### Fix
- **issue-452**: a completed work item stays completed after normal cleanup (#459)
## v19.22.0 (2026-10-03)
### Feat
- **issue-453**: a parked work item is owned by the instance that accepted it (#457)
```

In the replay, the branch head was a `wip` commit, so only #459 is listed. On `main`,
this PR's squash commit, `fix(release): …`, adds a second Fix line. #458 is a `test:`
commit, which commitizen leaves out of the changelog.

## T6: no-op from the tip

A second `cz bump --yes --changelog` on the new bump commit prints
`[NO_COMMITS_FOUND] No new commits found.` and exits 3. The job treats that as
`released=false`.

## T7: full suite

```text
$ uv run pre-commit run --all-files
ruff (lint + autofix)....................................................Passed
ruff (format)............................................................Passed
pyright (type check cli).................................................Passed
pytest (cli unit tests)..................................................Passed
markdownlint (all markdown, incl. docs)..................................Passed
validate .the-loop config against schema.................................Passed
```

## Live check (after merge)

The first release run on `main` should publish **19.22.1** to PyPI.
