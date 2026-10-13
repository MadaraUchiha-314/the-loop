---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#482"
---

# Security review: spawned sessions never receive a secret (issue-482, issue-485)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff
  and against the abuse cases in [`requirements.md`](../requirements.md).
- **Outcome:** pass, pending the named human sign-off tier 4 requires.

## Abuse cases → proof

| Case | Defence | Test |
|------|---------|------|
| A1 token readable from a pane's argv in `ps` | `-e` carries only the three identifiers and the passthrough; a credential is never forwarded | `test_abuse_482_a1_no_credential_value_reaches_the_argv` |
| A2 a spawn starts the tmux server, which keeps the token in its name for days | nothing secret is in that argv; on a real tmux the server's `/proc/<pid>/cmdline` holds no value (red on the old code) | `test_issue_485_a_spawned_server_and_its_pane_hold_no_secret` |
| A3 a pane inherits the token from the server's environment | `env -u NAME …` before the harness; tmux run with the names removed from its environment | `test_abuse_482_a3_…`, the real-tmux test (pane `/proc/<pid>/environ`) |
| A4 an operator lists `GH_TOKEN` in the passthrough | refused with a warning naming the variable | `test_abuse_482_a4_a_credential_in_the_passthrough_is_refused` |
| A5 a steered agent falls back to an in-process call on a token | a daemon-spawned session never falls back; it exits 2 naming the service | `test_abuse_482_a5_a_daemon_session_never_falls_back_in_process` |

## Findings

- **Fail closed.** The credential names come from the config and built-in defaults, not
  from the env file, so an unreadable file still strips them. A provider that raises
  still strips the defaults (`test_a_provider_that_raises_still_strips_the_default_credentials`).
- **No value in output.** `status`, `sessions restart` and every warning name a variable;
  a forwarded value is shown only as a fingerprint, a kept-out one as "held". Tests assert
  the dummy token is absent from rendered output and JSON.
- **`env -u` argument safety.** Only names matching the env-file name grammar reach
  `env -u`, so a malformed config value cannot become an option or fail the spawn.
- **The new route.** `POST /api/v1/sessions/ask` adds no authority a caller lacked: it does
  what `POST /work-items/comments` already does on the same loopback service (a marked
  comment on a work item), plus the `session.awaiting_input` event. `actor` is recorded,
  never trusted as authentication (decision-059).
- **Residual.** A passthrough value is visible in `ps`; the docs and the schema say only
  non-secret names belong there, and credentials are refused. A pane spawned by an
  earlier version keeps its token until it is relaunched, and a tmux server one of them
  started keeps it in its name until it exits; the upgrade note says how to clear both and
  to rotate the exposed token.
- **Not changed.** `git` in a session still uses the operator's git credential helper or
  SSH key; that is not an API token and is not in `env.file`.

## Sign-off

Tier 4: a named human security sign-off is required on the PR, distinct from its approval.
