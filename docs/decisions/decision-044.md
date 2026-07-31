# Decision 044: a repository's harness config configures work on that repository, never the daemon itself

- **Status:** proposed
- **Date:** 2026-07-30
- **Deciders:** @MadaraUchiha-314 (issue #121)
- **Work item:** issue-121
- **Spec:** `docs/specs/issue-121/`
- **Refines:** [decision-032](decision-032.md) — which split the config in two. Its
  consequence was written as "the plugin config never feeds the CLI daemon", which reads
  as a statement about *processes*. This records what it actually constrains: a
  *direction*. Nothing in decision-032 is reversed.
- **Bounded by:** [decision-043](decision-043.md) — `reviews.critics[]` is executable
  configuration, spawned only by an explicit `the-loop critic run <name>`, never
  implicitly. That gate is unchanged and is what keeps the ⟶ direction below safe for the
  one key that could otherwise be abused.

## Context

[Issue #121](https://github.com/MadaraUchiha-314/the-loop/issues/121), on one sentence of
the CLI docs — *"Repo-scoped — reads the repo's `harness-config.yaml`"*: **why** is the
CLI reading the harness config, **should** it be, and if not, can the settings **move** to
`cli-config.yaml`?

A fair question, because the rule the documentation stated was the wrong shape and had
become false. It said, in four places, that the two files partition by *process*: daemons
read `cli-config.yaml`, repo-scoped commands read `harness-config.yaml`, and *"the daemon
never reads a repository's harness config … not for anything"*.

That has not been true since [issue-113](../specs/issue-113/). `graphlink.py` is
constructed by `webhook/dispatcher.py`, which **both** ingresses share, and
`GraphLinkConfig.enabled` defaults to true — so on every spawn and every routed event with
a spec directory, the daemon calls `build_runtime(root)` and reads the checkout's
`workflow.phaseLabelPrefix`, `workflow.specDir` and `notifications`. Deliberately: the
`loop:<phase>` labels the coupling exists to write are named by the repository, and the
daemon cannot know that name for each of the N repositories it watches without asking each
one.

The state of the read surface made the question hard to answer, too. Three modules read
the file — `graph/bootstrap.py`, `critics.py`, `commands/scenarios.py` — each with its
own copy of the `harness-config.yaml` → pre-rename `config.yaml` fallback and its own
behaviour for an unparseable file. With no single place that read the config, there was
nowhere for the rule to live and nothing for a test to hold it to.

## Decision

**A repository's harness config may configure work done *on that repository*. It may
never configure the daemon itself.**

Both directions, stated explicitly:

| Direction | Verdict | Why |
|---|---|---|
| ⟶ A checkout's harness config configures work the-loop does **on that checkout** — which phase label to write, where its specs are, which critics to run, where its integration tests are | **Allowed**, including from the daemon | The blast radius is that same repository. The values are the repository's own policy, and the plugin and skill read them too. |
| ⟵ A checkout's harness config configures **the daemon** — who may trigger it, what it watches, which port it binds, how sessions are hosted, where the log goes | **Forbidden, no exceptions, no fallbacks** | A checkout is untrusted input to an operator's machine. This is decision-032's actual content, and it is unchanged: `authorizedUsers` and `polling.sources[].repos` are CLI-config-only and fail closed when unset. |

Consequences:

- **One reader.** `the_loop.harness_config` is the CLI's only reader of the file:
  `FILENAMES` (the rename fallback, expressed once), `config_path`, best-effort `load`,
  and `load_strict` for the one caller that must not degrade. `graph/bootstrap.py`,
  `critics.py` and `commands/scenarios.py` delegate to it and keep their existing public
  names. No behaviour changes — same keys, same paths, same defaults.
- **The read surface is declared, not discovered.** `harness_config.READS` names every key
  the CLI reads, the command that reads it, and *why that key is the repository's to
  declare*. An entry that cannot state the third probably belongs in `cli-config.yaml`.
  `cli/tests/test_harness_config.py` asserts each key resolves in
  `.the-loop/harness-config.schema.json`, that no module outside the reader opens the
  file, and that the declaration and `docs/config/harness-config.md` agree in both
  directions.
- **Today's surface, in full:**

  | Key | Read by | Repository's to declare because |
  |---|---|---|
  | `workflow.phaseLabelPrefix` | `check`, `graph`, the daemon | the label namespace is the repository's own convention |
  | `workflow.specDir` | `check`, `graph`, the daemon | where this project keeps its specs is a fact about its layout |
  | `notifications` | `check`, `graph`, the daemon | recipients resolve against the repository's own `collaborators.yaml` |
  | `reviews.critics[]` | `critic` | the review bar is a property of the project, and the skill reads the same entries |
  | `testing.integrationTestGlobs` | `scenarios` | where the integration tests live is part of the layout |

- **The daemon's read stays gated.** `graphlink._checkout_belongs_to` proves via the
  checkout's `origin` remote that the directory really is the work item's repository
  before anything there is read, and fails closed when it cannot tell (issue-113, A6).
  Writing the rule down makes that gate's purpose legible; it does not relax it.
- **`.the-loop/graph.yaml` / `pdlc.yaml` already obey the same rule.** `graph/model.py`
  reads a repository's process-graph override the same way, for the same reason. It is
  the second instance of this pattern, not an exception to it.
- **The documentation is corrected, not softened.** The four pages that claimed "never"
  now state the direction rule and keep the part that was load-bearing:
  `authorizedUsers` and a poll source's `repos` have no fallback and fail closed.

## Alternatives considered

- **Move the five keys to `cli-config.yaml`** — issue #121's own third question, and the
  reason this record exists. Rejected on four counts:
  1. **Wrong cardinality.** They are per-repository. `cli-config.yaml` is one
     machine-scoped file for a daemon watching N repositories, so it would need a
     hand-maintained `OWNER/REPO →` map that drifts from the repository it describes the
     moment someone edits one and not the other.
  2. **Two sources of truth for one value.** The skill reads `reviews.critics[]` and
     `workflow.specDir` from the harness config. Sourcing the CLI's copy elsewhere would
     let `the-loop critic run` and the agent following `reference/reviewing.md` disagree
     about what the critics *are* — the fork decision-043 refused.
  3. **It breaks the checkout-only cases.** `the-loop check` is a CI gate: it runs in a
     bare checkout, in a job with no operator home directory and no `cli-config.yaml`
     anywhere. `scenarios` is the same. Both would become unconfigurable exactly where
     they are used.
  4. **The trust argument only runs one way.** Decision-032 removed the plugin → daemon
     fallback because a checkout must not tell an operator's machine who may trigger it.
     A repository saying "my specs live in `docs/specs`" can only affect work on that same
     repository.
- **Keep the per-process framing and fix only the false sentences** — rejected. The
  framing itself is what produced the false sentences: it has no way to describe the
  daemon reading a work item's own checkout, so anyone stating it precisely states
  something wrong. It would also break again at the next coupling.
- **Let `cli-config.yaml` *override* a repository's harness policy** (an operator who
  wants a different critic than the repository declares) — rejected. It buys one real use
  case at the cost of making every value's provenance ambiguous, and the harness config
  already has a per-work-item override mechanism (spec front-matter `overrides`) that
  lives next to the work it changes.
- **Fix the documentation without consolidating the readers** — rejected. Three readers
  are *why* the rule was never stated: with no single place that reads the file, there is
  nowhere to declare the surface and nothing for a test to pin. The consolidation is a net
  removal of code.
- **Enforce the "one reader" rule at runtime** (an `open()` shim, an import hook) rather
  than by scanning the source — rejected. It would only catch a read on a path some test
  happens to execute, which is precisely not the failure mode: a new command with no test
  yet. The defect is visible in the diff, so the diff is where it is checked.
