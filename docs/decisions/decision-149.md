<!-- Written per the `the-loop:writing` skill. -->

# Decision 149: `/the-loop:init` is split into `/init`, `/init-cli` and `/init-gateway`

- **Status:** accepted (the owner approved the requirements and the design, 2026-10-21)
- **Date:** 2026-10-21
- **Deciders:** MadaraUchiha-314 (the ask and both approvals), the-loop (the split)
- **Work item:** [issue-514](https://github.com/MadaraUchiha-314/the-loop/issues/514)
- **Spec:** [`docs/specs/issue-514/`](../specs/issue-514/)
- **Refines:** [decision-032](decision-032.md) (the harness config and the CLI config are
  independent files) — they now have independent commands too.

## Context

One command walked all three of the-loop's configs: the repository's harness config, the
operator's CLI config and, when asked, a gateway's config. Only one repository in a
deployment is the operator repository. Every other repository that uses the-loop needs
just the plugin, the harness config and the `docs/` trees, yet `/init` opened there with
*"where will the daemon run?"* and *"how much should it do unattended?"*.

## Decision

Each config gets its own command:

| Command | Owns |
|---|---|
| `/the-loop:init` | harness config, `collaborators.yaml`, manifest, the `docs/` trees, the `loop:<phase>` labels, hooks and CI parity |
| `/the-loop:init-cli` | the posture questions, the CLI config and where it lives, Slack, Jira, the `routing.autoExecuteLabels` labels, the credential preflight |
| `/the-loop:init-gateway` | `gateway-config.yaml` and its own secrets' preflight |

Four defaults, confirmed at the requirements gate:

1. `collaborators.yaml` stays with `/init`: every repository's agent reads it.
2. Phase labels stay with `/init`. Arming labels move to `/init-cli`, because they exist
   only when a daemon routes the repository.
3. There is no `--only-harness` flag: repository-only is what `/init` does.
4. `/init-cli` needs no harness config, and does not run `/init`.

The walkthrough rules stay in one place, the skill's `reference/onboarding.md`. The
commands own their steps.

## Consequences

- A repository that only uses the-loop runs `/init` and is asked nothing about a daemon.
  The operator repository runs `/init` and `/init-cli`.
- `/init`'s report always names the other two commands, so nobody misses them.
- `/init-cli` still asks whether an instance *reads from* a gateway, because that is its
  own ingress block. *Hosting* one is `/init-gateway`'s.
- No alias keeps the old all-in-one behaviour. Nothing was removed, only moved, so an
  old habit still gets a correct, smaller result and a pointer to the rest.
