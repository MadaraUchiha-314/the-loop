---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#415"
---

# Self-review: the `/the-loop:init` onboarding a person can finish

> The `self-review` node's proof, per `reference/reviewing.md`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) | new findings | 4 found, 4 fixed — below |
| 2 | self (this session) | zero (converged) | re-read the whole diff against the requirements; no new finding |

## Round 1 findings

**F1 — the keyword guard would have gone red, and quietly for the wrong reason.**
`test_configschema.py::test_the_schemas_use_no_keyword_the_validator_ignores` walks every
keyword of the two *packaged* schemas. `harness-config.schema.json` has carried
`x-onboarding` since issue-49 and never tripped it only because it is not packaged. Adding
the block to `cli-config.schema.json` would have reported `explain`, `ladder`, `stillHuman`
and every config path inside a rung's `values` as unimplemented JSON-Schema keywords.
**Fixed** by declaring `x-onboarding` documentation-only in `configschema.SUPPORTED` and
adding it to the test's `_DATA_KEYWORDS` beside `examples`/`default`/`enum` — the same
treatment, for the same reason, with the reason written down in both places. The guard is
not weakened: a new *constraining* keyword still fails it.

**F2 — the first rung has to be the defaults, or "not yet" is a lie.** The draft ladder
began at `watch-and-ask`, which would have meant a user answering "I don't want any of
this yet" still got `routing.enabled: true` written. **Fixed** by making `commands-only`
the first rung, declaring it as exactly the six shipped defaults, and asserting the
equality in test A6 so it cannot drift.

**F3 — `mergeOnApproval` defaults to `true`, and a rung flipping it needs saying.**
`watch-and-ask` proposes `false` (stop at approved; a person merges), which is a *change*
from the shipped default, not an inheritance of it. Left as designed — it is the right
value for the rung whose whole promise is "every irreversible act is still yours" — but
the rung's `summary` now states it in so many words, and R2.3's "show the resolved values
before writing them" means the user sees it.

**F4 — the docs link in `commands/init.md` pointed at a domain that does not exist.**
The draft wrote `https://the-loop.dev/guide/slack`. The site is published at
`madarauchiha-314.github.io/the-loop`. **Fixed.** A dead link in the one step whose whole
job is "link rather than restate" would have been the worst place for it.

## Round 2 — the re-read

Checked every requirement against what shipped, and every abuse case against the
instructions as written. Three things I deliberately left as they are, with the reasoning
rather than a silent pass:

- **`docs/config/cli/` gained no page for `x-onboarding`.** It is metadata about the
  walkthrough, not an operator-settable option, and `test_docs_parity.py` walks
  `properties` only. Documenting it as a config option would invite someone to edit it in
  their own `cli-config.yaml`, where `additionalProperties: false` would reject it.
- **The deployment shape is not stored.** Tempting to persist, but a stored copy becomes a
  second source of truth for "is the webhook enabled" that nothing reads and that drifts
  the first time someone edits the config by hand.
- **No decision record was opened.** Every judgement here renders a rule already decided
  (issue-352, issue-220, decision-032, issue-281). The one new judgement — three rungs,
  and `spawnOnUnmatched: always` excluded from the ladder — lives in `design.md` §C2 and
  is enforced by test A5, which is a stronger record than a file nothing reads.

## Requirement trace

| Requirement | Where it landed | Proved by |
|---|---|---|
| R1 — the CLI config is onboarded from its own schema | `cli-config.schema.json` §`x-onboarding.groups`; `reference/onboarding.md` §Two configs, one procedure; `commands/init.md` step 4 | A1–A3, T11 |
| R2 — one question sets the automation threshold | `x-onboarding.profiles`; `reference/onboarding.md` §The autonomy ladder; init step 3 | A4, A6, A7, T11 |
| R3 — autonomy never buys away a human gate | the `PROFILE_BLOCKS` confinement; each rung's `stillHuman`; init step 3's stated invariant | **A5** |
| R4 — init knows what kind of machine it is on | `reference/onboarding.md` §The deployment shape; init steps 1 and 3 | T11 |
| R5 — Slack is explained, configured and proved | the `channels` group's `explain`; init step 5; verification in step 10 | T11 (the CLI-absent path) |
| R6 — every credential is checked | `reference/onboarding.md` §The credential preflight; init step 10 | T8 static check, T11 |
| R7 — explained, not narrated | `reference/onboarding.md` §How to present a group, items 1, 6 and 7 | T11, review |

## Unresolved

The four pre-existing `test_instance.py` failures documented in
[`verification.md`](verification.md). Not this work item's, not fixed here, and raised in
the PR so they are not mistaken for one of ours.
