---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#344"
---

# Security review: programmatic hooks around the lifecycle of a work item's delivery

> The `security-review` gate's record (`reference/security.md`). **Risk tier 4**: the
> change imports operator Python into the-loop's process, adds outbound HTTP carrying work
> item facts and a bearer token, and adds a CLI config schema key. Tier 4 requires a
> **named human security sign-off** before completion; it is requested on the pull request
> and is not claimed here.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`) over the requirements'
  threat model, the design's Security design table and the diff.
- **Outcome:** pass — every abuse case has a named negative test; two hardening findings
  fixed during the review (below).
- **Findings:** H1, H2 — fixed. None open.
- **Human sign-off:** requested on the pull request (tier 4); not claimed here.

## What the change introduces

1. A new operator-owned configuration list (top-level `hooks`) naming Python modules or
   files on the operator's machine, or URLs — **executable configuration**, the third such
   list after `critics[]` and `routing.graph.hooks` (decision-043, decision-096,
   decision-123).
2. Outbound HTTP from the daemon and from one-shot commands to operator-declared URLs,
   carrying work item facts (ref, actor, harness, model, node, the boot prompt, an agent's
   question) and, when `tokenEnv` is set, a bearer token from the environment.
3. Decisions a hook's answer may set: refuse a start or a launch, replace the prompt a
   harness boots on, replace an agent's question, silence three announcements.
4. A new section (`lifecycle`) on the portable record and five `hooks.*` event types.

No new dependency, no new credential in any file, no new permission.

## Abuse cases

| # | Abuse case (requirements) | Mechanism | Test |
|---|---|---|---|
| 1 | A repository carries a file at the path a `path:` entry names relative to a checkout | `Entry.resolved_path(config_base_dir(config_path))` — the config file's directory, never the cwd or a checkout | `test_a_path_resolves_against_the_config_file_not_the_cwd` |
| 2 | A remote returns a fact, an unknown key, a wrong-typed decision | `Context.apply` copies decision fields only after type-checking every one; `DecisionTypeError` is that hook's failure and nothing is applied | `test_apply_copies_decisions_only`, `test_a_wrong_typed_decision_is_refused_not_coerced`, `test_a_refused_apply_leaves_the_context_untouched`, `test_a_result_may_change_decisions_only` (live server) |
| 3 | A remote is unreachable, slow, or answers an error | `HookFailure` → `hooks.failed`, context unchanged, chain continues; `required` at a `proceed` point → `proceed=False` | `test_an_unreachable_remote_is_a_recorded_failure_not_a_stop`, `test_a_timeout_is_bounded`, `test_an_unreachable_required_remote_refuses_a_proceed_point`, `test_a_remote_error_is_a_recorded_failure_not_a_stop` |
| 4 | `http://` to a non-loopback host with a `tokenEnv` | `_check_url` refuses at parse | `test_a_bearer_token_over_cleartext_http_is_refused_at_load` |
| 5 | `tokenEnv` unset at call time | `RemoteExecutor.call` raises `HookFailure` before building the request | `test_the_bearer_token_travels_only_when_its_variable_is_set` |
| 6 | A module raises on import or construction | `HooksConfigError` naming the entry; daemons exit 1 before taking their lock; a one-shot command installs an empty runner and records `hooks.load_failed` | `test_a_module_that_raises_fails_the_load`, `test_a_constructor_that_raises_fails_the_load`, `test_a_daemon_refuses_to_start_on_a_bad_declaration`, `test_a_lazy_load_failure_installs_no_hooks_and_records_it` |
| 7 | An executor raises inside a point | `Runner._run` catches per executor; `Runner.run` catches the rest | `test_a_raising_hook_never_reaches_the_caller`, `test_the_runner_never_raises_even_when_the_context_is_odd` |
| 8 | `on` names an event type | `_read_on` accepts `POINTS` only | `test_on_may_name_only_catalog_points` |

## Hardening found during the review

**H1 — a credential in `headers`.** The design allowed arbitrary non-secret headers; a
literal `Authorization: Bearer …` in the config would have been a token in a tracked file.
**Fixed**: `_read_headers` refuses an `Authorization` header, naming `tokenEnv`
(`test_authorization_may_not_be_a_plain_header`).

**H2 — the suite loading a developer's hooks.** See self-review S3: the hermetic fixture now
installs an empty runner, so no test process ever imports a module from a developer's home
config.

## Further checks made over the diff

- **The hooks never see a secret.** Every context field is a fact of the work item or the
  launch; no environment value, token or config document is a field. `hooks.failed`
  carries `urllib`'s error text, which names the URL and the status, never a header.
- **A hook cannot steer the graph.** No decision names a node, an edge, an outcome, a
  loop or a path. `phase_changed` and `waiting_for_input(kind=gate)` are told after the
  graph moved; `notify` gates a channel publish and nothing else.
- **A refused start leaves nothing standing.** `_start_permitted` clears the control record
  and the `lifecycle` mark before settling, so the item is disarmed exactly as an
  unauthorized start is; the comment carries the hook's `reason` verbatim, marked
  `<!-- the-loop:agent-comment -->` so the daemon never re-reads it as a human's.
- **A refused launch is not a retry loop.** The event is settled (`hook-refused`) and
  `session.spawn_failed` carries `will_retry=False`; a later event asks the hook again,
  which is stated in the docs as the reason to refuse at `work_item_start` when the
  refusal is meant to hold.
- **The reworded prompt.** A `session_spawn` hook's `prompt` reaches the harness argv the
  way the operator's own `promptTemplate` does — the same trust level, the operator's code.
  The prompt carries the triggering comment (untrusted text) and travels to a remote hook
  the operator chose, over HTTPS unless loopback. Stated in the requirements as an
  accepted risk and in the docs under *Before you adopt one*.
- **A session runs the same hooks as its daemon.** `the-loop ask` inside a session resolves
  the daemon's exported config path (issue-393 B6) and loads the same declaration; the
  session can add nothing to it. A session's environment is what the hook runs with, which
  is true of every command a session runs.
- **Portable record.** The new `lifecycle` section holds one timestamp; it is classified
  `operator-ledger` in `ATTRIBUTES` and documented in `docs/cli/state.md`
  (`test_every_attribute_is_classified`, `test_the_attribute_table_is_documented`).

## Residual risks, stated

1. A remote hook server the operator declares sees every work item's facts, including
   the boot prompt and an agent's questions. It is the operator's service; the transport
   rule (HTTPS, or loopback) is the-loop's part of the boundary.
2. A `required` remote that is down refuses every start until it is up. That is the
   operator's declared choice (`required: true`), recorded on every refusal.
3. A one-shot command whose declaration fails to load runs hookless. Accepted because the
   daemon holding the same file refuses to start; the command says so in its log and the
   event log records `hooks.load_failed`.
