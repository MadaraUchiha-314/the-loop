# Codex support: implementation contract

This document records the implementation added to PR #450 for the operator's
A1–A7 and B1–B4 findings on issue #449. It supersedes the brainstorm's proposed
per-session `CODEX_HOME` and resume-by-recency approach. Codex keeps the operator's
normal home, authentication, settings and sandbox policy.

| Finding | Result |
| --- | --- |
| A1: resume identity | Put a unique conversation marker in the initial user prompt. Match the rollout's marker and exact working directory, then bind the native UUID in the registry. Resume only that UUID; missing, ambiguous or mismatched rollouts refuse resume. |
| A2: stop gate | Install a native Stop command that returns Codex's JSON continuation protocol, including the existing bounded retry cap. Preserve unrelated hooks and explicit operator choices. |
| A3: instructions | Preserve existing `AGENTS.md` or `AGENTS.override.md` and maintain an identified block pointing to the bundled skill, command procedures and graph verbs. Native plugins also expose the shared skill. |
| A4: harness trace | Locate the identified native rollout and normalize text, tool calls, tool results, reasoning summaries and compaction for the existing transcript API and UI. Retain original event payloads. |
| A5: MCP delegation | Use the selected adapter's actual binary, one-shot arguments and configured defaults. Unknown harnesses block instead of running Claude. Extract Codex's final JSON agent message. |
| A6: critic output and accounting | Run `codex exec --json`; extract the final completed agent message and latest usage record. Account for cached input without counting it twice. Do not invent dollar costs. |
| A7: distribution | Add the Codex installer component, native plugin manifest and hook definitions. Bundle shared instructions, command procedures and hooks in both wheels and source distributions. |
| B1: required labels | Keep the ALL-of semantics established by decision-381. Emit `poll.item_filtered` with the missing labels and repository-qualified work item when this gate excludes an item. |
| B2: retired arguments | Migrate `routing.harnessArgs` into `harnesses[].args`, including current-version configs. Preserve explicit modern arguments, report conflicts and leave a repeat migration unchanged. |
| B3: default fallback | Log and emit `session.default_harness_bypassed` when a declared default cannot host the session. Include the declared and effective harness and reason. |
| B4: stale connection | Retry a disconnected GraphQL read once. Never replay mutations or semantic API failures. |

## Codex integration details

Codex 0.160.0's interactive CLI does not accept a preassigned conversation ID.
Rollout discovery validates UUIDs, explicit absolute working-directory metadata and
filesystem containment. A launch marker may resolve only one conversation.
The loop does not copy authentication into a separate home or select the most
recent conversation. A live endpoint binds its native ID on subsequent delivery;
transcript reads and respawns can also resolve the marker before that binding.

The daemon installs its Stop hook in the operator's Codex home so the definition
is shared across worktrees. Project installation uses `.codex/hooks.json`;
user installation respects `CODEX_HOME`. Codex requires the operator to review
and trust a new non-managed hook definition through `/hooks`. The loop reports
that step and does not bypass Codex's hook trust policy. Disabling
`routing.harnessPlugins.enabled` disables automatic instruction and hook setup;
workspace trust preparation has its own independent switch.

The current native plugin surface is documented by OpenAI's
[plugin documentation](https://developers.openai.com/plugins/build/plugins).
Stop continuation and hook trust follow OpenAI's
[hook documentation](https://learn.chatgpt.com/docs/hooks).
Custom prompt copies are optional in the issue comment; shared procedures are
available through the installed skill and managed instruction block instead.

## Verification

Regression tests cover exact conversation recovery after an unrelated chat,
ambiguous markers, mismatched directories, unsafe IDs, escaping symlinks,
native trace normalization, JSONL critic output and usage, native Stop results,
MCP adapter selection, installer behavior, argument migration, default fallback,
label diagnostics and read-only connection retries.

The bundled instructions include both the operating skill and its required
sibling writing skill, including each skill's references.

Build verification must include a wheel built from the checkout and a wheel
rebuilt from an extracted source distribution, with the shared resources present
in each. Static checks include Ruff, Pyright, configuration validation, version
lockstep and Markdown lint. Local execution evidence and environmental limits
are recorded in `evidence/codex-verification.md`.
