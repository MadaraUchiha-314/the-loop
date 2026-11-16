---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#532"
---

# Security review: graph notifications on a gateway consumer post first time

> The `security-review` node's proof (`reference/security.md`). Risk tier **2**: a
> two-key change to an in-process config dict plus tests and docs. No route, schema,
> credential path, authorization check or untrusted input changes. Under tier 4, so no
> named human sign-off is required.

## Security review (gate)

- **Mechanism:** the-loop's checklist (`reference/security.md`), applied to
  `git diff origin/main...HEAD`, plus the codex critic's trust-boundary question
  (`critic-review.md`, no findings).
- **Outcome:** clean, no findings.
- **Checklist:**
  - *Untrusted input:* none. The two keys come only from the operator's CLI config
    (`load_cli_config_best_effort`). The work-item thread, the PR and the agent-writable
    `work-item-state.json` can't set them.
  - *Secrets:* neither key holds one. `gateway` holds a URL and timing knobs, and
    `instance` holds a name. The bot token stays an env-var reference, read only by
    `posting_path`, unchanged.
  - *AuthN/AuthZ:* unchanged. The gateway call is the same one the outbox retry
    already made, and it now carries the instance's real name rather than the default,
    which is what the gateway's lease check expects.
  - *Fail-closed:* unchanged. An absent, `null`, non-mapping or URL-less block resolves
    to `none` and the post still raises. Negative tests:
    `test_no_usable_gateway_block_still_resolves_no_gateway` (four cases).
  - *Logging:* no new log fields. The fix removes one false ERROR line.
- **Human sign-off:** not required (tier 2).
