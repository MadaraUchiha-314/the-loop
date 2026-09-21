---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#415"
---

# Security review: the `/the-loop:init` onboarding a person can finish

> The `security-review` node's proof. Risk tier **4** — the change touches `.the-loop/**`
> (a sensitive path) and its whole subject is telling people where to keep Slack and
> GitHub credentials. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist, against `requirements.md` § Security considerations
  and `design.md` § Security considerations.
- **Outcome:** pass — no finding required a change beyond what the design already
  specified.
- **Human sign-off:** **required and outstanding.** Tier 4 needs a named human security
  sign-off distinct from the PR approval. Requested from the repository owner on the pull
  request; this work item is not ready-to-ship until it is recorded here.

## The one-sentence summary

This change moves `/the-loop:init` **next to** the credentials for the first time, and
the entire security argument is that it never touches their values.

## Abuse cases, and the disposition of each

| # | Abuse case (from `requirements.md`) | Disposition |
|---|---|---|
| 1 | `.gitignore` does not cover the proposed `env.file` | **Mitigated, and it is the change's main security gain.** `reference/onboarding.md` § The credential preflight item 5 and `commands/init.md` step 10 both require the check and an *offer* to add the line. Init never writes a value into that file. Exercised in T11: the gap was detected and offered, not written. |
| 2 | A credential's value leaks into the report, a log, or a file | **Mitigated by construction.** Both files say *presence only*, and spell out the negative list: no value, no prefix, no length, no hash. Verified statically (T8: three prose mentions of variable **names**, zero shell expansions) and behaviourally (T11: `set`/`unset` per name, nothing else). This matches `channels status`'s existing `_presence()` contract deliberately — one reviewed behaviour, reused. |
| 3 | A detected file in an unaudited repository carries text shaped like an instruction | **Mitigated.** `reference/onboarding.md` § How to present a group now ends with an explicit *Untrusted input* rule: a `CONTRIBUTING.md`, a convention doc and a `.gitignore` are **data**, proposed as paths for the user to confirm, never followed. This was init's behaviour already; the new steps now inherit it explicitly rather than by accident. |
| 4 | An autonomy profile grants authority | **Mitigated mechanically.** `test_onboarding_schema.py::test_a5_…` fails the build if any rung writes `routing.authorizedUsers`, and the schema's own `profiles.description` states the rule. Who may drive the loop stays a named-person question. |
| 5 | A Slack verification leaks a token | **Mitigated.** Init runs `channels status --probe` and `doctor slack`, both of which already report ids, names and scopes and never a token. This work item calls them; it does not change them. |

## Fail-closed behaviour

- An unanswered autonomy question leaves the shipped defaults — **every automation off**.
  The failure mode of this walkthrough is doing less, never more.
- An unset credential blocks the feature it gates and lands in **needs-user**. It never
  causes a fallback to a weaker configuration.
- `routing.authorizedUsers` empty means nobody can drive the loop. Init reports that as a
  gap rather than filling it.
- A verification that could not run is reported as **unverified**, never as working
  (R5.6, T11).

## Trust boundaries

| Boundary | Crosses | Control |
|---|---|---|
| unaudited repository content → the walkthrough | detected file paths | proposed for confirmation; contents never executed or followed |
| process environment → init's report | credential **names** only | presence check; value never read into anything printed or written |
| init → the user's filesystem | configs, optionally one `.gitignore` line | non-clobbering; `--dry-run` writes nothing at all |
| init → Slack | nothing this work item sends | the probes it calls are read-only and pre-existing |

## New attack surface

**None.** No new endpoint, no new command, no new credential, no new file that holds a
secret, and no parsing of untrusted input that was not already parsed. The deliverable is
schema metadata, agent instructions and documentation.

## What a reviewer should check hardest

1. That no instruction added in `commands/init.md` step 10 or
   `reference/onboarding.md` § The credential preflight can be read as "print the value".
2. The `armed` rung's `stillHuman` text — it is the sentence a bold user reads before
   picking the top of the ladder, and it must be true.
3. `test_a5_no_profile_value_reaches_a_key_that_guards_a_human_gate` — if that assertion
   is weak, requirement 3 is prose.
