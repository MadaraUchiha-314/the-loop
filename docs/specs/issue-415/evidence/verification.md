---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#415"
---

# Verification: the `/the-loop:init` onboarding a person can finish

> The `verification` node's captured output. The results table lives in
> [`testing-plan.md`](../testing-plan.md) § Verification results, against the matrix rows
> it planned; this file is the raw evidence those rows point at.
>
> Every command was run from the repository root. `uv` is invoked as `python3 -m uv`
> because the container's `uv` (0.8.17) predates this repo's `required-version` pin
> (`>=0.12,<0.13`) and could not self-update behind the proxy; `pip install uv` supplied
> 0.12.17 and everything below ran on that. No behaviour of the repo's tooling changed.

## T1 / T8 — the onboarding-metadata tests

First **red** — the module was written before the schema block it asserts, and failed on
all seven assertions:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py
E   AssertionError: cli-config.schema.json carries no x-onboarding block —
E   /the-loop:init has nothing to drive its walkthrough with.
FAILED cli/tests/test_onboarding_schema.py::test_a1_both_schemas_speak_one_ask_level_vocabulary
FAILED cli/tests/test_onboarding_schema.py::test_a2_every_group_names_keys_the_schema_defines
FAILED cli/tests/test_onboarding_schema.py::test_a3_every_configurable_block_is_in_exactly_one_group
FAILED cli/tests/test_onboarding_schema.py::test_a4_every_profile_value_names_a_real_key_with_a_legal_value
FAILED cli/tests/test_onboarding_schema.py::test_a5_no_profile_value_reaches_a_key_that_guards_a_human_gate
FAILED cli/tests/test_onboarding_schema.py::test_a6_the_first_rung_is_the_shipped_defaults
FAILED cli/tests/test_onboarding_schema.py::test_a7_every_rung_is_complete_and_the_recommendation_resolves
7 failed in 0.15s
```

Then **green**, after `x-onboarding.groups` and `x-onboarding.profiles` landed:

```text
$ python3 -m uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py
.......                                                                  [100%]
7 passed in 0.05s
```

A5 — the mechanical form of requirement 3, that no autonomy rung can reach a key guarding
a human gate — is among them.

## T10 — parity, the keyword guard, and config validation

```text
$ python3 -m uv run --project cli python -m pytest -q \
    cli/tests/test_configschema.py cli/tests/test_config_schema_parity.py \
    cli/tests/test_docs_parity.py cli/tests/test_manifest_schemas.py
...........................................................              [100%]
59 passed in 3.29s
```

```text
$ python3 -m uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## T12 — documentation parity

Covered by the run above (`test_docs_parity.py`). The root-level `x-onboarding` adds no
schema **leaf** — `_schema_leaves` walks `properties` only — so P3 and P4 are unaffected
and no `docs/config/cli/` options page needed an entry. This was the prediction in
`design.md` § Testing strategy; the run confirms it.

## Lint, format, typecheck

```text
$ python3 -m uv run ruff check cli hooks
All checks passed!

$ python3 -m uv run ruff format --check cli hooks
347 files already formatted

$ python3 -m uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
```

## The full suite

```text
$ python3 -m uv run --project cli python -m pytest -q cli
4 failed, 4450 passed, 1 skipped in 232.79s (0:03:52)
```

**The four failures are pre-existing on `main` and are not this work item's.** All four
are in `cli/tests/test_instance.py` and concern the argv a tmux spawn is built with
(`-e` per-session environment, which issue-410 introduced); this work item changes no
spawn path. Confirmed by stashing the entire change and re-running the module on a clean
tree:

```text
$ git stash -u -q && python3 -m uv run --project cli python -m pytest -q cli/tests/test_instance.py
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 59 passed in 0.22s
```

Identical set, identical assertions, with none of this change applied. The visible cause
is in the captured log — `instance.name does not fit …; treating the instance as unnamed`
alongside an argv carrying no `-e` — which points at the container's tmux being older
than `TMUX_ENV_MIN_VERSION` (3.2), so the spawn omits `-e` by design. That is an
environment fact, not a regression. Recorded as an observation rather than fixed here:
it is outside this work item's scope, and widening the PR to chase it would be the wrong
call.

## T8 — the credential-value static check

No instruction added by this work item expands a credential's value. Every reference is
to the variable's **name**, in prose:

```text
$ grep -nE '(THE_LOOP_SLACK|THE_LOOP_GH_WEBHOOK|GH_TOKEN|GITHUB_TOKEN)' \
    commands/init.md skills/the-loop/reference/onboarding.md
commands/init.md:169:      name `channels.slack.botTokenEnv` (default `THE_LOOP_SLACK_BOT_TOKEN`).
commands/init.md:172:      `THE_LOOP_SLACK_APP_TOKEN`). This is what Socket Mode connects with, and Socket Mode
skills/the-loop/reference/onboarding.md:197:   about `THE_LOOP_SLACK_APP_TOKEN`; a deployment on polling is not told about the webhook
```

And no shell expansion of any of them anywhere:

```text
$ grep -nE '\$\{?(THE_LOOP_SLACK|THE_LOOP_GH_WEBHOOK|GH_TOKEN|GITHUB_TOKEN)' \
    commands/init.md skills/the-loop/reference/onboarding.md
(no output)
```

Three mentions, all naming a default variable name. No `$VAR`, no `${VAR}`, and no
instruction anywhere to read, print, hash or store a value — the procedure says
*presence only* in both files.

## T11 — the dry-run walkthrough

Walked on a throwaway git repository with **every credential variable unset**, so the
behaviour under test is what the preflight reports when a credential is missing. Nothing
is redacted because nothing secret existed; the scratch path is a temporary directory.

```text
# /the-loop:init --dry-run  (scratch repo: init-dryrun-336i556m)

## step 3 — posture

Q1 deployment shape: (a) a machine I close  (b) an always-on host  (c) nowhere yet
    -> (a) proposes polling.enabled=true + routing.workspace.root
    -> (b) proposes webhooks.ghWebhook.enabled=true + secretEnv as a credential

Q2 autonomy profile — recommended: watch-and-ask

  [commands-only] Commands only — the-loop is the slash commands in my editor
      still human: Everything. You start each work item yourself, in a session you are
                   sitting in front of.
      values: {"routing.enabled": false, "routing.spawnOnUnmatched": "never",
               "webhooks.ghWebhook.enabled": false, "polling.enabled": false,
               "channels.slack.enabled": false, "selfDiagnosis.enabled": false}

  [watch-and-ask] Watch and ask — notice my work items, but wait for me to say go  <- recommended
      still human: Starting each item, and merging every pull request. Plus everything
                   below: the phase-selection checklist, the requirements and design
                   approvals, the pull-request approval, and a named security sign-off
                   at risk tier 4 and above.
      values: {"routing.enabled": true, "routing.spawnOnUnmatched": "labeled",
               "routing.control.requireStartCommand": true,
               "routing.mergeOnApproval": false, "selfDiagnosis.enabled": false}

  [armed] Armed — the labels are the go-ahead
      still human: Every gate. … Autonomy here changes who STARTS the work, never who
                   APPROVES it.
      values: {"routing.enabled": true, "routing.spawnOnUnmatched": "labeled",
               "routing.control.requireStartCommand": false,
               "routing.mergeOnApproval": true, "selfDiagnosis.enabled": true}

## steps 4-5 — the CLI config walkthrough

  [always  ] posture     How much of this do you want running?
             keys: (none — establishes the posture above)
  [confirm ] deployment  Where this instance lives
             keys: state, env, instance
  [confirm ] ingress     What is watched, and how events arrive
             keys: repositories, webhooks, polling
  [confirm ] execution   What happens when an event matches
             keys: routing, harnesses, models, effort
  [confirm ] channels    Slack
             keys: channels
  [advanced] review      Critics & review rounds
             keys: critics, reviews
  [advanced] operations  Service, logs & integrations
             keys: service, eventLog, integrations, standingSessions, selfDiagnosis

  coverage: 18/18 blocks, uncovered=[]

## step 10 — credential preflight (presence only)

  THE_LOOP_SLACK_BOT_TOKEN     unset  <- channels.slack.botTokenEnv
                                         gates: posting/reading/reacting in Slack
  THE_LOOP_SLACK_APP_TOKEN     unset  <- channels.slack.appTokenEnv
                                         gates: Socket Mode: buttons, /the-loop, live replies
  THE_LOOP_GH_WEBHOOK_SECRET   unset  <- webhooks.ghWebhook.secretEnv
                                         gates: verifying webhook deliveries
  GH_TOKEN                     unset  <- integrations.github.api.tokenEnv
                                         gates: the-loop's own GitHub API calls

  env.file proposed: <scratch>/.env — holds secrets; .gitignore covers it: False
  -> needs-user: add ".env" to .gitignore  (offered, not written under --dry-run)

  the-loop CLI on PATH: NO -> channels status/doctor slack reported UNVERIFIED,
                              command printed for the user

## step 11 — report

  created:    (none — --dry-run writes nothing)
  needs-user: autonomy profile unanswered; deployment shape unanswered;
              4 credentials unset; routing.authorizedUsers empty;
              routing.workspace.root empty; .env not git-ignored
  profile applied: none -> NO AUTOMATION IS ENABLED; re-run init to change that

  scratch repo untouched: ['.gitignore', 'CONTRIBUTING.md']
```

What this proves, row by row against the requirements:

| Observed | Requirement |
|---|---|
| Seven groups in schema order, every ask level rendered, 18/18 blocks covered | R1.1, R1.3, R1.5 |
| The whole ladder shown with `stillHuman` on each rung and the recommendation marked | R2.1, R2.2, R2.6 |
| Every credential reported by **name** and `set`/`unset`, no value anywhere in the output | R6.1, R6.2 |
| Each unset variable names what it gates | R6.3 |
| `.gitignore` gap detected and **offered**, not written | R6.5, abuse case 1 |
| CLI absent → **unverified**, command printed, never reported as working | R5.6 |
| Scratch repo unchanged; no config, no `.gitignore` line | `--dry-run` contract |
| "no profile applied → no automation is enabled" stated outright | R3.4, `--defaults` contract |

## What was NOT executed

- **A live Slack probe** (`the-loop channels status --probe`, `the-loop doctor slack`).
  No Slack workspace, no app and no tokens exist in this environment, and manufacturing
  them to tick a line would prove nothing about the walkthrough. The path the walkthrough
  takes when the CLI or a token is absent **was** exercised (T11 above, reported as
  *unverified*), and the probe commands themselves are unchanged by this work item and
  covered by `test_channels*.py` and `test_doctor_slack.py`.
- **A live end-to-end `/the-loop:init`** against a real repository with a user answering.
  That is T4, marked `n/a` in the plan for the reason given there: automating an agent's
  side of a conversation tests the script, not the walkthrough.
