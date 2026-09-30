# Verification (issue-374)

Executed at the `verification` node on 2026-09-30, head `HEAD` of PR #436, in the
work item's cloud checkout (`uv 0.12.21`, Python 3.11, `bun` 1.x). One section per
activity of `testing-plan.md`; raw summaries as the runner printed them.

## T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_instance_role.py cli/tests/test_instance.py \
    cli/tests/test_manager_fleet.py cli/tests/test_manager_stream.py cli/tests/test_instances_core.py \
    cli/tests/test_instances_cmd.py cli/tests/test_lifecycle_cmd.py cli/tests/test_api_config_integration.py
164 passed in 11.34s
```

Re-run after self-review round 3 (`0b2cd86`), which added six regression tests here.
Red → green: `test_instance_role.py` was written first and failed on import
(`ImportError: MANAGER`); `test_manager_fleet.py` went red on the fan-out's unbounded
wait and the probe's detail text before the implementation was corrected;
`test_manager_stream.py` went red on the upstream count before the fixture and the
reconcile loop were fixed. Outcome: **pass**.

## T2 — integration (scenario)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_manager_integration.py \
    cli/tests/test_api_instances_integration.py cli/tests/test_manager_stream_integration.py
15 passed in 9.37s
```

Ten Gherkin scenarios over two worker apps and a manager app joined in-process; four on
a worker; one socket-level scenario with three real `python -m the_loop.api.serve`
processes on ephemeral loopback ports (the manager's stream fans two workers' streams in
and resumes per member). Outcome: **pass**.

## T3 — contract

```text
$ uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py \
    cli/tests/test_mcp_integration.py cli/tests/test_sdk_docs_parity.py
15 passed in 2.70s
```

The parity test is parametrised over a worker app and a manager app; one MCP tool list
on both roles with `list_instances` and without the registry writers. Outcome: **pass**.

## T5 / T9 — UI, visual and accessibility

```text
$ cd ui && bun run lint && bun run typecheck && bun run test && bun run build
$ oxlint --type-aware
$ tsc --noEmit
 Test Files  21 passed (21)
      Tests  324 passed (324)
✓ built in 1.27s
```

Screenshots of the built bundle (`bun run preview`) pointed at the live manager of the
manual walk-through, light and dark, under `ui/`: `instances-*.png` (the fleet table,
the not-live banner, the Register card), `instance-laptop-a-*.png` (the pane: identity,
daemons with verbs, the config editor mounted with `instance=laptop-a`),
`instance-cloud-1-*.png` (every control disabled with the reason),
`board-*.png` (chips on rows, the filter, the session panel naming the instance).
State words beside every dot, the filter a native `<select>`, actions as buttons: checked
by eye against the locked prototype. Outcome: **pass**.

## T7 — performance, bounded

```text
$ uv run --project cli python -m pytest -q cli/tests/test_manager_fleet.py cli/tests/test_manager_stream.py \
    -k "hung_member or upstream_per_live_member"
2 passed, 28 deselected in 2.46s
```

A hung member costs at most the timeout (`elapsed < 4 s` with `timeoutSeconds: 1`);
four subscribers hold exactly one upstream per live member. Outcome: **pass**.

## T8 — security / abuse cases

```text
$ uv run --project cli python -m pytest -q cli/tests -k "foreign_url or mismatched_member or malformed_member \
    or hung_member or ambiguous_ref or unknown_instance or foreign_instance or proxied_config \
    or overwrites_a_members_claim or nothing_of_the_caller or refuses_to_boot \
    or stamp_origin or hand_edited_entry"
16 passed, 4968 deselected in 6.47s
```

One negative test per abuse case A1–A9; the mapping is in `security-review.md`. The two
selectors added last cover self-review round 3's C9 (the subject of a fleet event is
kept, never confused with its origin) and C14 (a hand-edited registry entry is refused by
index before a write). Re-run after round 3 (`0b2cd86`).
Outcome: **pass**.

## T10 — migration / upgrade

```text
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py \
    cli/tests/test_migrations.py cli/tests/test_instance_integration.py cli/tests/test_api_routers_integration.py \
    cli/tests/test_eventlog.py
104 passed in 3.50s
```

A config without `role` is a worker and every pre-existing suite passes unchanged (T12
below); the packaged schema is byte-identical to the authored one;
`CURRENT_CONFIG_VERSION` is unchanged (`0.10.0`); a member without `role` in its
document probes as live (`test_a_member_with_no_role_field_probes_as_a_worker`); the
docs↔schema and SDK↔docs parity tests pass. Outcome: **pass**.

## T11 — manual exploratory

The procedure and its output: [`manual.md`](manual.md). Outcome: **pass**.

## T12 — the repository's own gates

```text
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
388 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
$ python scripts/validate_config.py
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
$ cd cli && uv run python -m pytest -q          # the CI form of `make test`
4965 passed, 1 skipped, 2 warnings in 189.92s (0:03:09)     # before the review rounds
4983 passed, 1 skipped, 1 warning in 196.41s (0:03:16)      # after self-review round 3
$ uv run --project cli python -m pytest -q cli/tests   # from the repository root
4965 passed, 1 skipped, 1 warning in 213.81s (0:03:33)
```

`make validate` and `make test` are run through their underlying commands: the
container's `uv` on `PATH` is 0.8.17 and the Makefile pins `>=0.12`; a 0.12.21 `uv`
from PyPI ran every command above. Outcome: **pass**.

## T13 — the security review gate

[`security-review.md`](security-review.md): the abuse-case table with verdicts, the
harness's security-review skill run over the diff, and the tier-4 sign-off line for the
owner.
