# Evidence — the ticket's own scenario, against the shipped code (issue-183)

A work item in `acme/app` needing contributions in `acme/app` **and** `acme/infra`, walked
through the shipped router, runtime and hooks — no test doubles for anything under test.
Re-run after the PR #184 review round, so step 2 shows what actually shipped: the origin
repository comes from the harness config, and the **surface** comes from the work item's
own `phase-selection` answer, defaulting to the work item. The script is reproduced under
the transcript.

Two notes on the output:

- The `403 Forbidden` lines are the `force` hook's **best-effort** audit comment reaching
  for a GitHub API that this scratch repository does not have (and `acme/app` does not
  exist). Best-effort by contract: it is reported and the transition still stands, which is
  exactly what the transcript shows. No credential was used and none appears here.
- Nothing here needed redaction: the only names are the invented `acme/app`, `acme/infra`
  and `acme/docs`, and a `tmp` working directory that is not printed.

## Transcript

```console
$ uv run python scenario.py

--- 1. the ticket lives in acme/app; a PR in acme/infra closes it 
routed to: ['github:acme/app#42', 'github:acme/infra#7']

--- 2. the origin repo is config; the SURFACE is the work item's own choice 
originRepo: acme/app | surface in config: False
checklist parses to → skips: ['requirements-definition'] | surface: work-item
...and with the box ticked → surface: pull-request

[surface=unset → default]
the-loop assignment for issue-42:
  you are now at node: design (phase: design)
  produce: design.md
  iterate it on: the work item itself (the default) — comment on the ticket, and do not open a pull request just to carry the spec chain
  when this node's work is done, report back: `the-loop graph complete issue-42`
  (assigned by the-loop's graph — not part of any event payload)

[surface=pull-request]
the-loop assignment for issue-42:
  you are now at node: design (phase: design)
  produce: design.md
  iterate it on: a pull request in the repository the ticket was created in — the surface this work item chose at phase-selection
  when this node's work is done, report back: `the-loop graph complete issue-42`
  (assigned by the-loop's graph — not part of any event payload)

--- 3. two pull requests, both #7, one per contributing repository 
pr-loops/acme__infra/pr-7/graph-state.json → implementation
pr-loops/pr-7/graph-state.json → implementation

--- 4. the outer implementation gate, with acme/infra still in flight 
FORCED github:acme/app#7: implementation → complete (pull request github:acme/app#7 merged)
  warning: implementation → complete is not a declared edge; you are deliberately outside the model
could not post the force audit comment: github api POST /repos/acme/app/issues/7/comments failed: 403 Forbidden
wait | waiting for 1 inner loop(s) to finish: acme__infra/pr-7 — each pull request completes its pdlc-pr-loop (docs/specs/<id>/pr-loops/) before the work item moves past implementation

--- 5. …and once acme/infra's pull request merges -------------
FORCED github:acme/infra#7: implementation → complete (pull request github:acme/infra#7 merged)
  warning: implementation → complete is not a declared edge; you are deliberately outside the model
could not post the force audit comment: github api POST /repos/acme/infra/issues/7/comments failed: 403 Forbidden
pass | data: {'inner_loops': 2, 'declared': 2}

--- 6. a declared repository nobody opened a PR for -----------
wait | 1 declared repository(ies) have no inner loop yet: acme/docs — each pull request completes its pdlc-pr-loop (docs/specs/<id>/pr-loops/) before the work item moves past implementation

--- 7. the inner-loop session is told how to claim ITS loop ---
the-loop process state for pull request #7's pdlc-pr-loop on issue-42:
  node: complete — status: in-progress
  iterate on: this pull request (the inner loop always runs on its PR — no setting moves it)
  when this node's work is done, run: `the-loop graph complete issue-42 --pr 7 --pr-repo acme/infra`
  (this block is the-loop's own state, not part of the event payload)

--- 8. a hostile repository name never resolves a path --------
'../../etc': refused — unusable repository segment '..' in '../../etc'
'acme//app': refused — unusable repository segment '' in 'acme//app'
'acme': refused — repository must be <owner>/<repo>: 'acme'

legitimate: acme__infra → docs/specs/issue-42/pr-loops/acme__infra/pr-7
```

## What each step proves

| Step | Shows | Requirement |
|---|---|---|
| 1 | a PR in `acme/infra` closing `acme/app#42` routes to the work item in the **origin** repository, before the PR's own ref | R1.5 |
| 2 | the origin repository is read from config; the **surface is not** — it is parsed from the checklist, defaults to the work item, and the session is told which either way | R2.2, R2.3, R2.5, R2.7, R2.9 |
| 3 | two pull requests both numbered #7 keep separate state — `pr-loops/pr-7/` for the origin repository, `pr-loops/acme__infra/pr-7/` for the contributing one — under the one spec chain | R1.3, R1.4 |
| 4 | the outer `implementation` gate holds while a contributing repository's loop is unfinished, naming it | R4.1 |
| 5 | …and passes once every declared repository has finished | R4.1 |
| 6 | a declared repository nobody opened a pull request for holds the gate rather than passing it | R4.2 |
| 7 | the inner-loop session's claim command addresses **its** loop: `--pr 7 --pr-repo acme/infra` | R2.8 |
| 8 | a hostile repository name is refused at the path boundary, never sanitized | R1.6, abuse case 1 |

## The script

```python
"""issue-183's own scenario, scripted against the SHIPPED router, runtime and hooks."""
import json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, "cli")
from the_loop.control import ControlConfig
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.assignment import render_assignment
from the_loop.graph.hooks.selection import _parse_selection, _parse_surface
from the_loop.graph.hooks.loops import await_inner_loops, inner_loop_state_dir, repo_state_key
from the_loop.graphlink import GraphLink, GraphLinkConfig, render_graph_context
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import extract_work_items

WI = WorkItemRef.parse("github:acme/app#42")
PR_APP = WorkItemRef.parse("github:acme/app#7")
PR_INFRA = WorkItemRef.parse("github:acme/infra#7")

root = Path(tempfile.mkdtemp())
subprocess.run(["git", "init", "-q", str(root)], check=True)
subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                "https://github.com/acme/app.git"], check=True)
spec = root / "docs" / "specs" / "issue-42"
spec.mkdir(parents=True)
(root / ".the-loop").mkdir()
(root / ".the-loop" / "harness-config.yaml").write_text(
    "ticketing:\n  github:\n    owner: acme\n    repo: app\n"
    "workflow:\n  specDir: docs/specs\n")
(spec / "execution-log.md").write_text(
    "---\ntype: execution-log\nworkItem: issue-42\nrepos:\n"
    "  - acme/app\n  - acme/infra\n---\n\n# Execution Log\n")

def show(title):
    print(f"\n--- {title} " + "-" * (58 - len(title)))

show("1. the ticket lives in acme/app; a PR in acme/infra closes it")
payload = {"repository": {"full_name": "acme/infra"},
           "pull_request": {"number": 7, "body": "Closes acme/app#42",
                            "head": {"ref": "feature/multi-repo"}}}
print("routed to:", [r.ref for r in extract_work_items("pull_request", payload)])

show("2. the origin repo is config; the SURFACE is the work item's own choice")
rt = build_runtime(root)
print("originRepo:", rt.config["originRepo"],
      "| surface in config:", "outerLoopSurface" in rt.config)
checklist = ("- [x] design\n"
             "- [ ] requirements-definition\n"
             "- [ ] outer-loop-on-pull-request\n")
print("checklist parses to → skips:", _parse_selection(checklist, ["requirements-definition"], [])[0],
      "| surface:", _parse_surface(checklist))
print("...and with the box ticked → surface:",
      _parse_surface(checklist.replace("- [ ] outer-loop", "- [x] outer-loop")))
for surface in ("", "pull-request"):
    ctx = HookContext(work_item=WorkItem(ref=WI.ref, id="issue-42", spec_dir=spec),
                      node={"id": "design", "phase": "design", "produces": ["design.md"]},
                      boundary="entry", repo=root, surface=surface, config=dict(rt.config))
    print(f"\n[surface={surface or 'unset → default'}]")
    print(render_assignment(ctx))

show("3. two pull requests, both #7, one per contributing repository")
link = GraphLink(GraphLinkConfig(enabled=True), control=ControlConfig(enabled=False))
link.on_pr_spawn(WI, PR_APP, str(root), session_id="s-1", runner="tmux")
link.on_pr_spawn(WI, PR_INFRA, str(root), session_id="s-2", runner="tmux")
for path in sorted((spec / "pr-loops").rglob("graph-state.json")):
    print(path.relative_to(spec), "→", json.loads(path.read_text())["currentNode"])

show("4. the outer implementation gate, with acme/infra still in flight")
gate_ctx = HookContext(work_item=WorkItem(ref=WI.ref, id="issue-42", spec_dir=spec),
                       node={"id": "implementation"}, boundary="exit", repo=root,
                       config=dict(rt.config))
link.on_pr_close(WI, PR_APP, str(root), merged=True)
r = await_inner_loops(gate_ctx)
print(r.status, "|", r.messages[0].text)

show("5. …and once acme/infra's pull request merges")
link.on_pr_close(WI, PR_INFRA, str(root), merged=True)
r = await_inner_loops(gate_ctx)
print(r.status, "| data:", r.data)

show("6. a declared repository nobody opened a PR for")
(spec / "execution-log.md").write_text(
    "---\ntype: execution-log\nworkItem: issue-42\nrepos:\n"
    "  - acme/app\n  - acme/infra\n  - acme/docs\n---\n\n# Execution Log\n")
r = await_inner_loops(gate_ctx)
print(r.status, "|", r.messages[0].text)

show("7. the inner-loop session is told how to claim ITS loop")
print(render_graph_context(link.pr_context(WI, PR_INFRA, str(root)), "issue-42",
                           pr_number=7, pr_repo="acme/infra"))

show("8. a hostile repository name never resolves a path")
for hostile in ("../../etc", "acme//app", "acme"):
    try:
        repo_state_key(hostile)
        print(f"{hostile!r}: RESOLVED (should not happen)")
    except ValueError as exc:
        print(f"{hostile!r}: refused — {exc}")
print("\nlegitimate:", repo_state_key("acme/infra"),
      "→", inner_loop_state_dir(Path("docs/specs/issue-42"), 7, "acme/infra"))
```
