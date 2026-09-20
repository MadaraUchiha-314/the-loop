---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#395"
---

# Security review: the hosted ingress set follows the config (issue-395)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Trust boundary:* unchanged. The input is the CLI config file, already the
    operator's control surface and already acted on by every daemon on each change;
    it is read through the same strict loader (`load_cli_config(strict=True)`) the
    service's `ConfigHolder` uses, so the schema-adjacent gates (version, removed keys)
    stand between an edit and a reconcile exactly as between an edit and a request.
  - *Authorization / new surface:* none. The reconcile composes the starters
    `the-loop start` composes, with their refusals intact: the single-instance lock is
    taken (a standalone daemon is skipped, not fought), the missing-token refusal names
    the **variable** and never a value (pinned by
    `test_a_refused_start_on_reconcile_is_recorded_and_the_supervisor_survives`).
  - *Untrusted input:* the two events' `reason` is one of two fixed strings the-loop
    composes; `config.reloaded`'s `detail` carries ingress names only.
  - *Fail-closed:* an unloadable edit changes nothing; a reconcile that raises is
    caught per tick and the service keeps serving; a flapping edit stops or starts at
    most once per tick and a failed start is not retried until the file changes again.
  - *Secrets / logging:* none new.
- **Human sign-off:** n/a (risk tier 3).
