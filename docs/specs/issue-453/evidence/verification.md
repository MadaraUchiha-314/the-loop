# Verification (issue-453)

Executed at the `verification` node on 2026-10-02, on this work item's PR branch
(`claude/github-issue-453-eya3qe`), in the work item's cloud checkout: `uv 0.12.22`,
Python 3.11, no network for the tests. One section per row of `testing-plan.md`. The
summaries are as the runner printed them, from `cli/`.

## Red first (T5, negative control)

The new tests were written before the code was final. With `core/github_ops.py` restored
to `HEAD` and the tests kept:

```text
$ uv run python -m pytest -q tests/test_parked_closure_integration.py tests/test_github_ops.py \
    -k "453 or parked or unnamed or unreadable or session_backed or second_close or github_refuses"
FAILED tests/test_parked_closure_integration.py::test_a_parked_work_item_is_closed_and_cannot_launch_later
FAILED tests/test_parked_closure_integration.py::test_a_session_backed_work_item_closes_as_before
FAILED tests/test_github_ops.py::test_close_ticket_closes_a_work_item_this_instance_parked
FAILED tests/test_github_ops.py::test_closing_a_parked_work_item_cancels_its_pending_start
FAILED tests/test_github_ops.py::test_a_second_close_of_a_parked_work_item_is_a_no_op_with_exit_0
FAILED tests/test_github_ops.py::test_a_session_backed_close_records_no_stop
FAILED tests/test_github_ops.py::test_an_unnamed_instance_owns_the_records_it_wrote
FAILED tests/test_github_ops.py::test_a_parked_pull_request_work_item_may_be_acted_on
8 failed, 8 passed
```

The eight that stayed green on the old source are the refusals (an unrelated ref,
another instance's record, named/unnamed mismatches, an ended item, an unreadable store,
a stranger PR beside a parked work item, and the abuse case in the integration module):
they assert behaviour the old guard already had and must keep. Outcome: **pass**.

## T1–T3: unit, the guard and the closure

```text
$ uv run python -m pytest -q tests/test_github_ops.py
96 passed
```

Thirteen new cases (`issue-453` section): a parked item closes; the close records the
`stop` with this instance's name, clears the `work_item_start` mark and says
`startCancelled`; a second close is exit 0 with the record unchanged; a GitHub refusal
leaves the item armed; a session-backed close records no stop; another instance's
record, an unnamed record on a named instance, a named record on an unnamed instance, an
ended item and an unreadable store all refuse with nothing sent; an unnamed instance owns
its own records; a parked `--work-item` cannot merge a stranger PR; a parked PR work
item may be acted on. Outcome: **pass**.

## T4: integration, the real dispatcher

```text
$ uv run python -m pytest -q tests/test_parked_closure_integration.py
3 passed
```

The real `Dispatcher` + `SessionRegistry` + `ControlStore` over one state root and the
CLI's config for the same root: a parked item is closed through `close_ticket`, no
session is invented, and a labelled event **and** a synthesised `control-start` spawn
nothing afterwards; a record stamped by another instance is refused and its arming
stands; a session-backed item closes with no stop recorded, and the daemon's `closed`
event ends the session, forgets the arming and stamps `ended`. Outcome: **pass**.

## T6: regression, the full suite

```text
$ cd cli && uv run python -m pytest -q
5312 passed, 1 skipped, 1 warning in 221.91s
```

Outcome: **pass**.

## T7: static

```text
$ uv run ruff check cli hooks          → All checks passed!
$ uv run ruff format --check cli hooks → 408 files already formatted
$ uv run pyright cli                   → 0 errors, 0 warnings, 0 informations
$ npx markdownlint-cli2@0.18.1 docs/specs/issue-453/**/*.md docs/decisions/decision-141.md \
    docs/decisions/decisions.md docs/capabilities/cli.md docs/cli/commands/ticket.md
Summary: 0 error(s)
```

Outcome: **pass**.

## Not run here

T8–T11 are `n/a` with reasons in the plan. A live close against GitHub was not run:
the request is `GitHubClient.close_issue`, unchanged since issue-447, and this checkout
holds no token for the testing repository.
