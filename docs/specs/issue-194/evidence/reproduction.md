# Evidence — the ticket's symptom, before and after

Work item: issue-194 · captured 2026-08-10.

## What was run

The ticket's reproduction, made offline and deterministic: a work item at the start of
`pdlc-work-item-loop` in a repository whose harness config declares `ticketing.github`,
entered with **no `--ref`**. The stand-in transport parses the ref with the shipped
`_split_ref` before recording the call, which is exactly what `GitHubApi` and `GitHubCli`
do first — so a ref no provider could use fails here too.

```python
"""The ticket's reproduction, offline: a work item at phase-selection, no --ref."""
import sys, tempfile, pathlib, copy
sys.path.insert(0, "cli")
from the_loop.graph import hooks  # noqa
from the_loop.graph.bootstrap import build_runtime
import the_loop.graph.integrations as integrations

root = pathlib.Path(tempfile.mkdtemp())
(root / "docs/specs/issue-123").mkdir(parents=True)
(root / ".the-loop").mkdir()
(root / ".the-loop/harness-config.yaml").write_text(
    "ticketing:\n  github:\n    owner: octo\n    repo: repo\n"
    "workflow:\n  specDir: docs/specs\n"
)

sent = []
from the_loop.graph.integrations.github import _split_ref
class Fake:
    """A stand-in transport that parses the ref exactly as the real ones do."""
    def call(self, op, **params):
        _split_ref(str(params.get("ref")))   # what GitHubApi/GitHubCli do first
        sent.append((op, str(params.get("ref"))))
        return {"comments": []}
integrations.resolve = lambda target, config: Fake()

rt = build_runtime(root)
report = rt.start("issue-123")            # exactly what the daemon/CLI does
print(f"123: {report.node} -> {report.status}")
for m in report.messages:
    print(f"  . {m}")
print(f"GitHub calls made: {sent or 'NONE'}")
```

## Before (the 9.5.0 source, restored with `git stash`)

```text
123: phase-selection -> pass
GitHub calls made: NONE
```

`GitHub calls made: NONE` is the defect: the checklist the gate is waiting on never
reached the ticket, and the phase label was never set. The node still reports `pass`, and
its report carries no messages — so `the-loop graph advance` prints a clean answer.

The two `could not …` lines above come from Python's last-resort logging handler on
**stderr**, and are the only trace that existed. They are not on stdout, not in the
`NodeReport` the CLI prints, and not in the event log — so a piped invocation, a CI step,
a `--format json` consumer and the daemon all see nothing at all.

## After (this branch)

```text
123: phase-selection -> pass
GitHub calls made: [('set-labels', 'github:octo/repo#123'), ('list-comments', 'github:octo/repo#123'), ('add-comment', 'github:octo/repo#123')]
```

All three calls now reach `github:octo/repo#123`, derived from `ticketing.github` plus the
`issue-123` id. No warning is printed, because there is nothing to warn about — the
warning path is exercised separately by
`test_a_failing_hook_is_reported_without_changing_the_edge` and
`test_cli_advance_prints_the_warning` (see [`integration.md`](integration.md)), where the
same run produces:

```text
issue-194: phase-selection → wait
  · waiting for an authorized user to choose the phases and reply `the-loop execute`
  · warning: post-phase-selection did not complete: github is down
```
