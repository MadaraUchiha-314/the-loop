---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#412"
---

# Documentation: four `test_instance.py` tests read the machine they run on

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Updated in this PR

**[`docs/capabilities/testing-and-contracts.md`](../../../capabilities/testing-and-contracts.md)**
— the organized view of how a work item is proved, and the capability that already carries
this repository's standing test conventions (issue-251's "asynchronous tests wait on the
state they depend on" is the neighbouring section, and the same shape of rule).

- A new section, *A test reads no ambient machine state, and `make` runs what CI runs*:
  the rule that a test pins or controls a cwd- or home-relative resolution; the CLI config
  named as the standing instance, with both acceptable answers (pin `$THE_LOOP_CLI_CONFIG`
  under the test's own `tmp_path`, or `chdir` and write the config it means to read); the
  correction that a cwd-relative lookup is **not** ambient in itself and must not be pinned
  wholesale, because the config path anchors the state root; that a green CI is one row of
  the table rather than evidence of hermeticity; and that a `Makefile` parity claim
  includes the working directory.
- A history row for issue-412, above issue-365.

**[`Makefile`](../../../../Makefile)** — the header RULE and the `test:` target carry the
parity claim, so they are documentation as much as configuration. The header is narrowed
from "all scripts run from the project root" (which the fix makes untrue) to invocation,
and now says that a target needing another working directory changes into it *and says so*.
The `test:` target gains a `# CI parity:` comment naming the hook it mirrors, why the `cd`
is part of the command rather than an accident, and "change both or neither".

## Not affected

- [`skills/the-loop/reference/testing.md`](../../../../skills/the-loop/reference/testing.md)
  — it is the *shipped* guidance the plugin gives a consuming project about planning and
  proving work. The rule added here is about this repository's own suite and its own task
  runner; generalizing "pin `$THE_LOOP_CLI_CONFIG`" into the plugin would be advice about
  the-loop's internals for projects that have none. The capability doc is where this
  repository's conventions live, and where issue-251's comparable rule sits.
- [`docs/capabilities/cli.md`](../../../capabilities/cli.md) and
  [`docs/capabilities/observability.md`](../../../capabilities/observability.md) — the
  config resolution order and the state root they describe are **unchanged**. The bug was
  in what the tests assumed about that order, not in the order itself; documenting a fix
  here would misdescribe a behaviour that did not move.
- `docs/api-specs/openapi/the-loop.v1.yaml` — no route, parameter or response changed.
- `.github/workflows/ci.yml` — deliberately untouched: the parity was restored by moving
  the local target onto CI's command, so CI itself runs exactly what it ran before.
- `README.md` / `CONTRIBUTING` — they point contributors at `make check`, which is what it
  always was, only now honest. No instruction a contributor follows has changed.
- No decision record: nothing here overturned a recorded decision, and the one judgement
  worth writing down — module-scoped rather than suite-wide pinning, and why the suite
  itself rejected the wider variant — is argued in
  [`bugfix.md`](../bugfix.md) § Defect 1 and evidenced in
  [`verification.md`](verification.md), where a reviewer of this change will look for it.
