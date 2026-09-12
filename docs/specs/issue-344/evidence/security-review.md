# Security review — issue-344

> The ready-to-ship security gate. **Risk tier 4**: a CLI-config schema key
> (`**/*schema*`, `.the-loop/**`), a second surface that imports operator-declared Python
> into the-loop's process, and a shipped hook that makes outbound HTTP calls. Tier 4
> requires the owner's PR approval **and a named human security sign-off**; this document
> is the autonomous review that sign-off reads. Date: 2026-09-12.
> **Sign-off status: outstanding** — recorded in the execution log and the PR.

## What actually changed, from a security point of view

One sentence: **the operator's CLI config can now name Python that runs on every event
the-loop records, and one shipped hook sends those records over HTTP with a bearer
token.** The trust model for the first half is the one decision-096 and decision-123
already set — the CLI config is executable configuration, reviewed like code, editable by
no pull request. The second half is new and bounded below.

Four properties carry the whole review:

1. **Only the CLI config declares.** `read_declaration` reads `cli_config["hooks"]` and
   nothing else. No code path scans a checkout for hook modules or opens a harness
   config. A `path` resolves against the config file's own directory and is refused
   outside it.
2. **A hook cannot stop, feed or steer the-loop.** It runs on a worker thread the emitter
   never waits on; a raise or a `block` becomes one `hooks.failed`; the `hooks.*` domain is
   never an attach point and a record emitted on the worker thread is never re-dispatched;
   it receives no `HookContext` and nothing reads an `outcome`.
3. **Secrets by name, at call time.** `forward-event` carries `tokenEnv` — a variable
   name — and reads the value when the hook runs. The config, the record, the failure
   event and the log never hold the value; an unset variable sends nothing.
4. **Every fault fails closed.** A declaration that cannot be honoured fails the entry
   point (no silent "no hooks"); a URL outside `http`/`https` is refused at parse; a full
   queue drops for hooks only and says so.

## Abuse cases, and what closes each

| # | Abuse case | Control | Test |
|---|---|---|---|
| A1 | A checkout carries `.the-loop/hooks/evil.py` that nobody declared | Only `cli_config["hooks"]` is read; the checkout is never scanned | `test_a_checkout_module_nobody_declared_never_runs` (integration, with the checkout as cwd) |
| A2 | `modules[].path` is absolute, contains `..`, or is a symlink out of the config directory | `extensions._contained` with the config directory as root: all three refused at load, naming the path | `test_a_path_escaping_the_config_directory_is_refused` (three shapes) |
| A3 | A hook raises, returns `block`, or hangs | Raise/block → `hooks.failed`, next hook runs; a hang stalls the worker only — `dispatch` is a `put_nowait`, `drain` times out honestly | `test_a_raising_hook_is_recorded_and_the_next_one_runs`, `test_a_blocking_result_is_a_failure_not_a_veto`, `test_a_hung_hook_stalls_only_the_worker` |
| A4 | A hook emits events (directly or through the-loop) to trigger itself or another hook | `hooks.*` never in the attach-point universe (cannot even be named); a record arriving on the worker thread is written and not queued | `test_hooks_events_are_never_attach_points` (three patterns), `test_a_hook_that_emits_does_not_recurse` |
| A5 | A hook returns `data["outcome"]`, `wait` or `block` to move or park the graph | No `HookContext`, no chain, no pointer; the runtime reads `status` only | `test_an_outcome_a_lifecycle_hook_declares_is_ignored`, `test_a_blocking_result_is_a_failure_not_a_veto` |
| A6 | A bearer token in config, in a record, or in a log line | `tokenEnv` is a name; the value is read from `os.environ` at call time; the failure message names the variable; the record sent is the log's own line | `test_forward_event_reads_the_token_at_call_time_and_sends_nothing_when_unset`, `test_the_failure_event_names_the_variable_not_the_value` (asserts the value is absent from the whole log), `test_forward_event_end_to_end_with_the_token_from_the_environment` (asserts absent from config and log) |
| A7 | `forward-event` pointed at `file://`, `ftp://` or a bare host | `validate_forward` at parse: scheme must be `http`/`https`; `urllib` never sees anything else | `test_forward_event_refuses_bad_params_at_load` (three URLs), `test_forward_event_refuses_a_non_http_url_at_load` |
| A8 | A malformed block, a missing module, a typo'd pattern | `HooksConfigError` at parse or load; `configure_from_file` propagates it; the daemon refuses to start and a command exits with the message | `test_seam_a_broken_declaration_fails_configure_from_file`, `test_a_broken_declaration_fails_the_entry_point`, `test_a_pattern_matching_nothing_fails_the_load`, `test_a_missing_raising_empty_or_misnamed_module_fails_naming_it`, `test_hooks_exits_2_on_a_malformed_block` |
| A9 | A flood of events with a slow hook | `queue.Queue(maxsize=1024)`, `put_nowait`; drops counted; one `hooks.dropped` per episode; the log loses nothing | `test_overflow_drops_for_hooks_only_and_says_so_once` (asserts all five records reached the log and one announcement was made) |

Nine raised, nine closed.

## The checklist

| Item | Verdict |
|---|---|
| New attack surface | Two, both operator-declared: the `hooks` block (Python imported into the process — the same shape and trust as `routing.graph.hooks` and `critics[]`) and `forward-event`'s outbound POST. Neither is reachable from a repository, a comment, or a Slack message. |
| New authority | **None.** No new grant, no new scope. The block is read from the file `authorizedUsers` is read from, by the same loader. |
| Untrusted input reaching a command argument | No. Nothing in a record becomes a path, an argument or a URL. `forward-event`'s URL is the operator's declaration. A record's fields (some carry excerpts of comment text) reach a hook as data. |
| Authentication / authorization | Unchanged. `forward-event` adds an `Authorization: Bearer` header from an environment variable the operator names; an unset variable fails closed. |
| Secrets | Never in config (a name, not a value), never in a record, never in `hooks.failed` (the variable name), never in the log — asserted by three tests that grep the whole log/config for the placeholder value. |
| New data at rest | None. The queue is in-memory and bounded. |
| Injection (command, path, template) | Path: containment enforced with the graph loader's rule. Command: nothing is executed via a shell; the module is imported. Template: none. |
| Denial of service | The emitter never waits (`put_nowait`); one worker; 1024-record bound; drops announced once per episode. A hung hook costs the worker, not the daemon. |
| Logging / disclosure | `hooks.loaded` carries counts; `hooks.failed` carries the hook name, the event type and the error text (the hook author's or the exception's); `hooks.dropped` carries the event type and the capacity. No record contents are re-logged. |
| Fail closed | Every parse/load fault raises to the entry point. Every runtime fault is recorded and contained. Asserted, not asserted-to. |

## Residual risks

1. **A hook module runs with the operator's environment**, including every token the
   daemon can read. This is exactly the exposure `routing.graph.hooks` and `critics[]`
   already carry, stated in the same words in the config page's danger block. What is
   new is *when* such code runs — on every recorded event rather than at node boundaries
   — which is more often, not more privileged.
2. **`forward-event` sends the event record as-is.** The event log already carries
   handles rather than secrets (observability capability), but a few event types carry
   excerpts of human-authored text (comment bodies, reasons). An operator forwarding
   `*` to a third party is forwarding those excerpts; the attach points are the
   operator's choice, and the docs say the body is the log's own line.
3. **A slow hook drops silently after the first announcement of an episode.** The
   log records one `hooks.dropped` per episode and the runtime counts every drop
   (`dropped`), but a long episode is one warning line. A reviewer wanting a per-record
   trail can attach nothing to high-frequency types (`api.request`, `poll.cycle`) or
   raise the one constant.
4. **The named human security sign-off tier 4 requires is outstanding.** This document
   is the input to it; the PR approval is where it lands.
