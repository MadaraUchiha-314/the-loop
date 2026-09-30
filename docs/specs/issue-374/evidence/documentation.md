# Documentation (issue-374)

Capability docs updated in this PR — the organized view of the specs, never left to rot:

| Doc | What changed |
|-----|--------------|
| `docs/capabilities/instances.md` | subtitle; a *The manager* section under Current behaviour (the role and registry, the worker half kept, the identical surface and the `instance` parameter, trust by name, the `instances` family and its writers, the stream fan-in, the dashboard); *What it does not do* rewritten (ticket-managed instance still reserved; nested managers and the fleet-wide Slack channel as follow-ups #438 and #437); Design links; a history row |
| `docs/capabilities/control-plane.md` | the facade seam bullet (one router, two facades; the `instance` parameter; `409`/`502`; the partial header; the `instances` family on every role); a history row |
| `docs/capabilities/cli.md` | a history row for `the-loop instances`, the `status` fleet lines and the boot refusal |
| `docs/capabilities/capabilities.md` | the `instances` row's description |

User-facing docs:

| Doc | What changed |
|-----|--------------|
| `docs/config/cli/instance-options.md` | `role`, the registry (`manager.instances`, `[].name`, `[].url`), `manager.timeoutSeconds`, `manager.probeIntervalSeconds`; the example block |
| `docs/cli/instances.md` | a *Running a manager* section: the config, reach, the operation table, the name check, registering, the `instance` parameter; the last "does not do" bullet updated; Next links |
| `docs/cli/commands/instances.md` (new), `docs/cli/commands/index.md`, `docs/.vitepress/config.mts` | the command page, its index row and sidebar entry |
| `docs/cli/commands/status.md` | the fleet lines on a manager |
| `docs/cli/state.md` | a tip: a manager stores none of its members' state |
| `docs/sdk/reference.md` | `loop.instances()`, `loop.facade()` |
| `docs/api-specs/openapi/the-loop.v1.yaml` | the `instance` parameter on 13 `GET` operations and 19 body schemas; the three `instances` routes and their two body schemas |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | `role: worker` and a commented `manager` block |
| `ui/README.md` | the two new surfaces, "One URL, many instances", the routes |
| `docs/decisions/decision-138.md`, `docs/decisions/decisions.md` | accepted |
| `docs/specs/issue-374/design.md` | the as-built note on the facade (one class per role) |

Parity: `test_docs_parity.py` (P1–P5) and `test_sdk_docs_parity.py` pass.
