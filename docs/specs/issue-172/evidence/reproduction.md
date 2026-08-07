# Evidence — the ticket's reproduction, before and after

> Work item: [issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172) ·
> Testing plan row **T11** (manual exploratory) · captured 2026-08-07.
>
> The ticket's five reproduction steps, driven through a real `Dispatcher` with an injected
> `FakeTmux` (the same seam the integration tests use). The harness is not checked in as a
> script — it is reproduced verbatim at the end of this file, because a throwaway that exists
> to produce one capture belongs with that capture rather than in the repository.
>
> `--prefix` restores the pre-issue-172 behaviour by rebinding two methods —
> `SessionRegistry.session_for` back to a bare `find_by_work_item`, and
> `Dispatcher._record_pr_binding` to a no-op — so both columns run the *same* code path
> everywhere else. No redaction was needed: the output holds two `github:octo/repo#N` refs
> and two file names.

## Before — the defect

```text
# BEFORE the fix (pre-issue-172 resolver)

## step 2 — a session is registered against the issue
registry: ['github-octo-repo-15.json']

## step 3 — a comment on PR #16, whose description says 'Closes #15'
routed refs: ['github:octo/repo#15', 'github:octo/repo#16']
delivered to: ['github:octo/repo#15']
registry: ['github-octo-repo-15.json']

## steps 4+5 — the link is removed; another comment on PR #16
routed refs: ['github:octo/repo#16']
delivered to: ['github:octo/repo#15']
spawned: []
```

Two lines carry the whole ticket:

- After step 3 the registry still holds **one** file. That is the ticket's own observation —
  *"Note that `sessions/` contains no file for the PR."* The routing decision was made and
  discarded.
- After step 5 `delivered to` has **not grown**. The second comment was routed to
  `github:octo/repo#16`, which has no session, and dropped. The issue's session is still
  running and still owns the work.

`spawned: []` here is the configuration talking, not a second safety net: with
`spawnOnUnmatched: always` the same event would have started a *duplicate* session against
the PR while the issue's session kept running. Dropped or duplicated, the event never reaches
the agent that has the context.

## After — the binding is recorded, and used

```text
# AFTER the fix

## step 2 — a session is registered against the issue
registry: ['github-octo-repo-15.json']

## step 3 — a comment on PR #16, whose description says 'Closes #15'
routed refs: ['github:octo/repo#15', 'github:octo/repo#16']
delivered to: ['github:octo/repo#15']
registry: ['github-octo-repo-15.json', 'github-octo-repo-16.link.json']

## steps 4+5 — the link is removed; another comment on PR #16
routed refs: ['github:octo/repo#16']
delivered to: ['github:octo/repo#15', 'github:octo/repo#15']
spawned: []
```

The same two lines, inverted:

- Step 3 now leaves `github-octo-repo-16.link.json` behind — the decision, written down.
- Step 5's `routed refs` is **identical** to the run above (`['github:octo/repo#16']`):
  derivation still fails, exactly as the ticket describes. What changed is that the failure
  is no longer the end of the line — the second delivery lands in the issue's session.

## The record on disk

```json
{
  "ref": "github:octo/repo#16",
  "sessionRef": "github:octo/repo#15",
  "createdAt": "2026-08-07T00:00:00Z",
  "updatedAt": "2026-08-07T00:00:00Z",
  "url": "https://github.com/octo/repo/issues/16"
}
```

(Timestamps normalised for this document; the run's real values are the capture time.)

## The harness

```python
"""The ticket's reproduction, driven through a real Dispatcher.

Usage: repro.py [--prefix]   (--prefix restores the pre-issue-172 resolver)
"""

import sys, tempfile, time
from pathlib import Path

sys.path.insert(0, "cli")
sys.path.insert(0, "cli/tests")

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

PREFIX = "--prefix" in sys.argv
if PREFIX:
    SessionRegistry.session_for = lambda self, item: self.find_by_work_item(item)
    Dispatcher._record_pr_binding = lambda self, routed, target: None

ISSUE, PR = "github:octo/repo#15", "github:octo/repo#16"


def pr_comment(body, pr_body):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {
            "number": 16,
            "body": pr_body,
            "pull_request": {"html_url": "https://github.com/octo/repo/pull/16"},
        },
        "comment": {"body": body, "user": {"login": "octocat"}},
        "sender": {"login": "octocat"},
    }


def routed(body, pr_body, delivery):
    payload = pr_comment(body, pr_body)
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


tmp = Path(tempfile.mkdtemp())
local = tmp / "local"
registry = SessionRegistry(local)
tmux = FakeTmux()
dispatcher = Dispatcher(
    registry=registry,
    adapters={"claude": StubInteractiveAdapter()},
    config=RoutingConfig(control=ControlConfig(require_start_command=False)),
    tmux_runner=tmux,
)

print(f"# {'BEFORE the fix (pre-issue-172 resolver)' if PREFIX else 'AFTER the fix'}")
print()
print("## step 2 — a session is registered against the issue")
item = WorkItemRef.parse(ISSUE)
registry.register(
    Session(
        work_item=item,
        harness="claude",
        harness_session_id="sess-1",
        cwd=str(tmp),
        tmux_target=f"loop-{item.slug}",
    )
)
print("registry:", sorted(p.name for p in local.iterdir()))
print()

print("## step 3 — a comment on PR #16, whose description says 'Closes #15'")
event = routed("please rerun CI", "Closes #15", "d-1")
print("routed refs:", [r.ref for r in event.work_items])
dispatcher.handle(event)
time.sleep(0.5)
print("delivered to:", [ref for ref, _ in tmux.delivers])
print("registry:", sorted(p.name for p in local.iterdir()))
print()

print("## steps 4+5 — the link is removed; another comment on PR #16")
event = routed("and again please", "", "d-2")
print("routed refs:", [r.ref for r in event.work_items])
dispatcher.handle(event)
time.sleep(0.5)
print("delivered to:", [ref for ref, _ in tmux.delivers])
print("spawned:", [ref for ref, *_ in tmux.spawns])
dispatcher.stop()
```

Run as `uv run python repro.py [--prefix]` from the repository root. Two log lines about a
missing `gh` binary and a workspace that is not a checkout of `octo/repo` are filtered from
the captures above; both are the fixture's environment, not the behaviour under test.
