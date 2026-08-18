# Evidence: security review (gate)

Risk tier **4** (`autonomy.inferFromChange`: the change touches
`.the-loop/*schema*` and adds a code-execution path), so
`security.review.humanSignOffMinTier: 4` applies: this review is the agent's, and a
**named human security sign-off is still required before the work item completes**.

Reviewed: the working-tree change set of this work item — `cli/the_loop/graph/extensions.py`
(new), `registry.py`, `model.py`, `chain.py`, `bootstrap.py`, `commands/graph_cmd.py`,
`harness_config.py`, and the two schemas. The bundled `/security-review` skill was invoked
first; its diff range resolved to the whole branch history (hundreds of files from earlier
work items), so the review below was run inline against this work item's diff instead.

## The central fact, stated plainly

This work item adds a way for a **repository** to have its Python executed **inside
the-loop's own process**, at graph node boundaries. That is the feature, not a bug in it. The
review's question is therefore not "is there code execution?" — there is, by design — but
"what can that execution reach, who authorises it, and what can it do to the loop?"

## Trust boundaries and what holds them

| Boundary | Mechanism | Verified by |
|---|---|---|
| Configuration → code execution | The YAML still only *names* hooks; there is no argv, no shell, no `eval`. The code arrives as code, from a repo-tracked file reviewed like `reviews.critics[]` (decision-043). | Read of `extensions.py`; no `subprocess`/`shell`/`eval` in the diff. |
| Repository → files outside it | `_contained()` refuses an absolute path, resolves through symlinks and requires containment in `repo.resolve()`, then requires a `.py` suffix and an existing file. | `test_a_module_outside_the_repository_is_refused`, `test_a_symlink_leaving_the_repository_is_refused`, `test_a_module_that_is_not_python_or_not_there_is_refused` |
| Repository hook → process movement | Append-only chains, short-circuit at the first shipped hook that does not pass, and `data["outcome"]` dropped for any `x-` hook. | `test_a_repository_hook_cannot_rescue_a_blocked_chain`, `test_a_repository_hook_cannot_declare_an_outcome` |
| Repository A → repository B | Hooks resolve from a per-graph table, never the process registry; the registry itself refuses `x-` names. | `test_two_repositories_keep_their_own_implementations`, `test_collector_takes_the_registration_instead_of_the_global_registry` |
| Shipped namespace → repository | `@hook` refuses `x-` outside the collector and requires it inside; a module registering `validate-artifacts` fails the load. | `test_a_shipped_hook_may_not_take_an_extension_name`, `test_a_module_registering_a_shipped_name_fails_to_load` |
| Broken declaration → silent absence | Every failure raises `GraphConfigError` at load. Nothing degrades to "no hooks". | `test_a_broken_declaration_fails_the_load_rather_than_degrading`, `test_a_module_that_cannot_be_imported_stops_the_loop` |

## Finding 1 — an agent that can write a checkout can reach the daemon's process (accepted, documented)

- **Severity:** medium · **Category:** privilege escalation · **Status:** accepted with
  mitigations, and named here rather than left implicit.
- **Path.** the-loop's own threat model treats the agent as an untrusted *writer* of files in
  a checkout. An agent could therefore write `.the-loop/hooks/evil.py` plus a `graph.hooks`
  block, and the next graph load in that checkout would import it **into the daemon's
  process**, whose environment holds real credential values (the webhook secret, a bot
  token) even though `HookContext` deliberately carries only handles.
- **Why it is accepted.** The daemon already spawns a harness in that same checkout with
  permissions bypassed (`the_loop.trust`), and that session already inherits the environment;
  the new path is a second route to a place the design already grants. The alternative —
  sandboxing repository hooks — is a different work item with a different threat model, and
  the requirements say so out loud rather than implying a protection that does not exist.
- **Mitigations shipped.** `routing.graph.repoHooks: false` refuses the mechanism
  machine-wide (nothing imported, and the refusal is logged naming the repository);
  `the-loop graph hooks` reports a repository's declarations **without importing any of
  them**; the declaration lives in a repo-tracked file whose diff a reviewer sees; and
  `graph.hooks` is covered by this repository's existing `autonomy.sensitivePaths` entry for
  the harness config.
- **Residual risk for the human sign-off.** An operator running the daemon over repositories
  they do not review should set `repoHooks: false`. That sentence is in the config schema, the
  routing-options page and `docs/cli/hooks.md`.

## Finding 2 — `importlib.reload` on an already-imported dotted module (accepted, low)

A `module:` declaration naming something already in `sys.modules` is reloaded so its
decorators run under the collector. A repository could name an unrelated installed module and
have it re-executed. This grants nothing a repository does not already have (it can declare a
`path:` module that does anything), and the documented contract is that a hook module defines
hooks and does nothing else. No change made; recorded for the sign-off.

## Checked and clear

- **No new network, subprocess, shell or `eval`.** The diff adds `importlib` and `hashlib`
  only.
- **No secret reaches a new place.** `HookContext.config` is unchanged; nothing in the diff
  logs a config value. The new log lines carry hook names, module labels and counts.
- **No new deserialization surface.** The declaration is read from the harness config through
  `yaml.safe_load` in the existing single reader; the new parser walks a mapping.
- **Fail-closed on ambiguity.** Both `path` and `module` set, neither set, a bare string, an
  unknown boundary, an unknown node, a duplicate name, an unattached hook (warned) — each is a
  refusal or a warning, never a quiet default.
- **The synthetic module name** used for `path:` modules is `the_loop_repo_hooks_<sha256[:16]>`
  and is not inserted into any package namespace, so it cannot shadow an import.

## Human sign-off

*Pending.* Name and date to be recorded here and in `execution-log.md` § Security review
(gate) before this work item can be marked complete.
