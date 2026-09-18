---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#377"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a released work item is launched with the arguments the operator declared

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `interactive-sessions.md` | Three clauses in Current behaviour: every session launches on the harness's **launch arguments** resolved once by `modelchoice.launch_args` from either home (new wins, never the union, conflict reported); the session spawned by the gate-answering reply is resolved **after** the gate and from the checkout, so it carries the frozen choice; the choice path starts from the adapter. The bypass-acceptance sentence names the launch arguments rather than `harnessArgs`; the record clause says the spawn events carry the argv | yes (issue-377) |
| `standing-sessions.md` | The inheritance clause: an entry that omits `harnessArgs` inherits the harness's launch arguments through the same resolver a work item's session uses | yes (issue-377) |
| `observability.md` | `session.spawned` / `session.respawned` carry `harness_args`, `model`, `effort`; `session.pr_spawned` carries `harness_args` — the catalogue in `eventlog.EVENT_TYPES` says so | yes (issue-377) |
| `webhook-triggers.md` | The bypass-acceptance sentence names both homes | no — a wording change inside an existing clause, not a behaviour change of this capability |
| `process-graph.md` | **unaffected** — the gate, the nodes and the edges are unchanged; only *when* the daemon resolves the adapter relative to `on_arm` moved, which `interactive-sessions.md` owns | n/a |
| `cli.md` | **unaffected** — no verb changed shape; `the-loop models check` gained no flag, only a correct probe argv, documented on its config page | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/harnesses-options.md` | `harnesses[].args` now says *every* session means every one — first spawn, released, respawn, PR endpoint, standing, and the probe — with the issue-377 history in one sentence; the conflict rule; and the two `the-loop diagnose` claims (one pre-existing) corrected to `the-loop models list\|check`, which is the one command that runs `config_findings` |
| `docs/config/cli/routing-options.md` | `harnessArgs.claude` / `.cursor` marked **deprecated** since 16.0.0 with a pointer to the new home; a paragraph on the one resolver and what happens when both declare; the `acceptBypassPermissions: auto` bullet and the warning below it name the launch arguments rather than `harnessArgs` |
| `docs/config/cli/standing-sessions-options.md` | The example's `harnessArgs` comment and `sessions[].harnessArgs`'s default name both homes |
| `skills/the-loop/reference/automation.md` | The bypass-acceptance sentence names the launch arguments |
| `skills/the-loop/templates/cli-config.yaml` | `harnesses[].args` comment says it reaches every session and the probe; `routing.harnessArgs` marked deprecated with the precedence rule; the trust comment and both standing-session comments name the new home |
| `.the-loop/cli-config.yaml` | Same two comments (this repository declares no `harnesses`, so the deprecated block points at "a top-level `harnesses[].args`") |
| `docs/api-specs/openapi/the-loop.v1.yaml`, `cli/the_loop/api/routes.py` | The `harnessArgs` description of the standing-session create body names both homes (a description string only; the contract's surface is unchanged, which the parity test pins) |
| `README.md`, `docs/guide/*` | **unchanged, deliberately** — neither mentions harness arguments; the front page describes the loop, not the daemon's argv |

## Not documented, deliberately

**No decision record.** The one choice worth stating — one resolver, adapters built from
it, the choice path deriving from the adapter rather than from a second config read — is
argued with its alternatives in `design.md` § Alternatives considered, and it restores a
rule issue-358 already made (`harnesses[].args` is the home; the deprecated key still
works) rather than making a new one. If the deprecated key is ever removed, that is the
decision to record.
