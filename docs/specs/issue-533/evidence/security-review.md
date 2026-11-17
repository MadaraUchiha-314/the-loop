---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#533"
---

# Security review: opt-in session credentials, never on argv

> Risk tier 4 (credential handling; touches `**/*schema*` and `.the-loop/**`). A named
> human security sign-off is required before completion.

## Security review (gate)

- **Mechanism:** the-loop checklist (below), verified against the diff and the tests. A
  second pass with the built-in `security-review` skill was started and **had not
  returned** when this record was written. Its result is appended under § Security-review
  skill round, and any finding from it blocks completion until dispositioned.
- **Outcome:** pass on the checklist. Every security finding raised earlier was fixed
  with a negative test, listed below.
- **Findings:**

  | ID | Finding | Disposition |
  |----|---------|-------------|
  | SR1-1 | a name in both `sessionPassthrough` and `sessionCredentials` rode `tmux -e` (argv) | fixed `047ecc8c` + test |
  | SR2-1 | a failed write left a partial `0600` file holding the value | fixed `aa1095bb` + test |
  | CR1-1 | a credential named `f` redirected the loader's `rm` (value on argv) | fixed `67447284` + test |
  | CR1-2 | a skipped entry's names were not stripped (fail-open) | fixed `376cce97` + test |
  | CR1-3 | the sweep ran only on writing spawns | fixed `025530d5` + test |

- **Human sign-off:** **pending.** Tier 4 requires a named human. Requested on PR #535.

## Checklist

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Every trust boundary in `design.md` § Security design is enforced where stated | pass | daemon↔session: `for_work_item` is the only place `inherit` is filled (`envstate.py`). tmux: client env drops `remove ∪ inherit`, the loader argv carries a path only (`runner.py`). disk: `O_EXCL\|O_NOFOLLOW`, `0600`/`0700`, owner check. outbound: route `scrubbed()` + `EventLog.emit`. All asserted by T2 on real tmux |
| 2 | Untrusted inputs validated at ingress; injection surfaces covered | pass | names `^[A-Za-z_][A-Za-z0-9_]*$`; values single-quoted with `'` → `'\''` (test with `'`, `$()`, backticks, newline); the loader is a constant with the path in `$1`; the filename is `<tmux target>.<16 hex>.env`, and tmux targets are minted by `tmux_session_name` (no `/`) |
| 3 | Untrusted content cannot steer privileged behaviour | pass | the agent cannot change `sessionCredentials` (operator config). The routes still require the service (issue-482 R3.2 unchanged). Text from the agent is scrubbed, never interpreted |
| 4 | No secrets in code, config, logs or fixtures | pass | warnings and events name variables only (caplog tests assert the value is absent). Values are masked in the event log. Test fixtures are dummies |
| 5 | AuthZ fails closed | pass | unset source, malformed entry, unmatched scope, unwritable directory, missing `credentials_dir`, or a provider error: nothing inherited, names stripped (tests A7, CR1-2, symlink, no-dir) |
| 6 | Least privilege | pass | default off. `from` exists to hand sessions a narrower token, with a warning when it names the daemon's own. `repositories` scopes per work item |
| 7 | Every abuse case A1–A7 has a passing negative test | pass | A1/A2/A3 `test_tmux_runner.py` + `test_session_credentials_integration.py`. A4 `test_api_session_credentials.py`, `test_sessioncreds.py`. A5 `…passthrough_still_refuses…`, `sr1_1`. A6 `…daemon_credential_source_warns`. A7 `…repositories_scope…` |
| 8 | New dependencies justified | pass | none added (`sh` only) |

## Residual risk (needs the human's acceptance)

An agent that holds a token can leak it where no scrubber sees: `gh`/`git push`/`curl`
with the token itself, a transformed value (base64, split), or a verb run with
`THE_LOOP_SERVICE_LOCAL=1`. This is inherent in holding a token and is documented in the
config reference (`danger` block) and the schema. Accepting it is the security sign-off's
decision.

## Security-review skill round

*Running. Result to be appended here.*
