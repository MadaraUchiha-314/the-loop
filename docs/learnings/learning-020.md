# Learning 020: Run a critic with absolute paths, and scope its prompt to fit its timeout

- **Date:** 2026-11-18
- **Source:** system-feedback
- **Work items:** issue-540 (also hit in issue-538)

## What happened

The issue-540 critic round took three attempts:

1. A prompt that asked codex to review the whole 123-file diff hit the 900 s
   `criticTimeouts.codex` ceiling and returned nothing.
2. A narrower prompt run with `the-loop critic run codex --root . --cwd .` from the
   worktree's root ran in 29 s, in the operator's `devbox` workspace instead of the
   worktree ("no `cli/` directory"). It reviewed nothing. issue-538's critic hit the same
   wrong-checkout problem.
3. Absolute `--root`/`--cwd` and the checkout path stated in the prompt worked: a real
   review in 48 s.

## Learning

- Pass `--root` and `--cwd` as **absolute** paths to the worktree, and name the checkout
  path in the critic prompt too. `.` does not reliably reach the critic process from a
  daemon-spawned worktree session.
- Scope the critic prompt to the code that carries the risk (new modules and the call-site
  diff), not to generated or data files. A big diff of data files spends the timeout on
  reading.
- Check what a "successful" critic envelope actually says (`ok: true` with "Unable to
  review…" is not a review) before recording a round.

## Action

Second occurrence of the wrong-workspace problem. Recorded here; the cwd resolution in
`the-loop critic run` is worth its own work item if it recurs.
