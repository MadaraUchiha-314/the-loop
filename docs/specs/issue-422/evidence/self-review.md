---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#422"
---

# Self-review: the suite writes into the checked-in `.the-loop/` when run from the repo root

> The self/critic review before requesting human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). The
> branch diff was read adversarially, asking what would make CI or a reviewer reject it,
> and what the guard could get wrong in either direction.

## Found and fixed during review

1. **False positive: a name relative to a `dir_fd` was resolved against the cwd.**
   `shutil.rmtree` on Linux walks by file descriptor and removes an inner directory as
   `os.rmdir(".the-loop", dir_fd=<parent>)`. The first version of the hook turned that
   bare name into `<cwd>/.the-loop` and reported it. Any test removing a `tmp_path` tree
   that held its own `.the-loop/` would have failed for nothing. Reproduced with a new
   test before the fix (`AssertionError: [('os.rmdir', … '.the-loop')]`). The hook now
   pairs each path argument with its `dir_fd` argument and skips a relative one.
2. **False positive: a symlink's target was treated as written.** `os.symlink(src, dst)`
   writes `dst` only. The first version checked both, so a link *pointing into* a
   protected tree tripped the guard. Reproduced the same way; the hook now checks the
   destination of `os.link` / `os.symlink` only.
3. **The hook could raise.** An exception in an audit hook propagates into the audited
   call, so a guard bug would have become a failure in unrelated code. `_protected` now
   survives a deleted working directory (`os.getcwd()` raising inside `abspath`), and the
   `open` branch checks that `flags` is an int before masking it.
4. **The stack filter matched `/the_loop/`**, which never matches on Windows. It now
   filters on the `cli/` directory's absolute path.
5. **An overclaim in a docstring.** `pytest_sessionfinish` said it caught writes "at
   shutdown". It catches writes made after the last teardown and before session finish,
   not an `atexit` handler. The wording now says so.

## Checked and left as is

- **Scope of the runtime change.** The Slack probe fix touches code outside tests. It is
  kept here because the guard surfaced it and it is the same class of defect: a
  cwd-relative fallback where the state root was meant. The fix is also one optional
  argument passed by the three callers that already hold the config. Doing it as a
  separate ticket would have meant either leaving the doctor test tripping the guard or
  pinning its cwd, which hides the bug from the guard built to find it. It is flagged
  for the reviewer in the briefing.
- **Not changing `RoutingConfig.portable_dir` or `default_options()`.** Both
  resolve state the way an operator's daemon does. Anchoring either on the config would
  change daemon behaviour, and nothing in this ticket asks for that (bugfix § The fix).
- **Guarding the cwd's tree may fail a future test that deliberately writes
  `./.the-loop/` after `chdir`-ing somewhere.** It will not: `abspath` resolves at the
  moment of the write, so after `monkeypatch.chdir(tmp_path)` the write lands under
  `tmp_path/.the-loop/`, which is not protected. `_PROTECTED_STATE` is fixed at import,
  from the directory pytest started in. The issue-412 tests that write a real
  `./.the-loop/cli-config.yaml` in a `tmp_path` pass under the guard.
- **Thread attribution.** A write from a daemon thread that outlives its test is
  reported by the next test's teardown. That misattributes the failure but not the code:
  the stack names it. No test in the suite does this today (T1, T2 green).
- **Subprocesses are not covered.** The tracer run (T15) exported a `sitecustomize` to
  every child that inherits the environment and found no subprocess writer. The limit is
  stated in the hook's docstring and in the capability doc.
- **Cost.** The hook is one Python call per audited event. Measured in T7.
- **The `.gitignore` entry for `cli/.the-loop/`** is kept rather than deleted, so a
  checkout that still carries old residue does not suddenly show it as untracked.

## Verdict

No open finding. Ready for human review at tier 3.
