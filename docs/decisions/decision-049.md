# Decision 049: an instruction registration is verified by a command, not by a graph gate

- **Status:** proposed
- **Date:** 2026-08-03
- **Deciders:** @MadaraUchiha-314 (issue #132)
- **Work item:** issue-132
- **Spec:** `docs/specs/issue-132/`
- **Builds on:** [decision-029](decision-029.md) — the `customInstructions` contract this
  makes observable — and [decision-044](decision-044.md), whose directional rule the new
  read has to satisfy.

## Context

Issue #132 asked whether the-loop lets a project declare its own rules and guidelines.
It does, and has since issue-59: `customInstructions.docs` is an ordered list of the
operator's own convention files, read at the start of every work item, with documented
precedence and an `onMissing` policy.

The question is still the useful artifact here, because of **who asked it**. The
repository's owner — who merged the feature — could not find it, and had no way to confirm
the docs were being read. Both halves of that are defects:

- **Nothing advertised it.** The README never named `customInstructions`, and its
  enumeration of the skill's reference docs omitted `instructions` entirely.
- **Nothing observed it.** `onMissing` was honoured by the agent's good behaviour and by
  nothing else. A mistyped or moved path contributed no guidance and produced no signal;
  a run against a broken registration was indistinguishable from a correct one.
  `onMissing: error` was a setting that never errored.

The second is the interesting one. the-loop already had a name for this failure mode —
an obligation it places on the agent that nothing can observe drifts — and already had an
answer to it: `the-loop scenarios` exists so the Gherkin obligation is queryable rather
than aspirational. Custom instructions had no counterpart.

The obvious alternative was a **process-graph hook**. `pdlc.yaml` is where the-loop's
gates live, `validate-instructions` names itself, and issue-109 established that the
process is a graph and the graph is executable.

Two things rule it out, and they are worth writing down because the hook is the answer a
reader will reach for first:

1. **The obligation is per-work-item, not per-node.** `reference/instructions.md` says the
   docs are read once, when work on an item starts — "right after loading the config and
   before any phase work". A per-node gate would attach a node-shaped check to a duty that
   is not node-shaped, and would then have to be replicated across five nodes to
   approximate it.
2. **The semantically correct placement would be invisible.** "Were the instructions
   available when this node began?" is an *entry*-chain question, and `Runtime.evaluate`
   runs only **exit** chains — that is what keeps `the-loop check` honest about artifacts.
   So an entry hook would never be reported by `check` and never gate CI: precisely the
   silence being fixed, relocated.

## Decision

**`customInstructions` is verified by `the-loop instructions`, a pure repo-scoped command
in the shape of `the-loop scenarios` — not by a node in the process graph.** The
process graph is unchanged.

- The command resolves every entry of `customInstructions.docs`, in configured order, and
  reports its configured path, resolved absolute path, `notes` and state:
  `present` / `missing` / `unreadable` / `invalid`.
- **Everything that is not `present` counts as unresolved — `invalid` included.** A
  registration the-loop could not understand is guidance that is not reaching the agent,
  and dropping it silently is the very defect this closes.
- `onMissing` decides the exit code (`error` → 1, `warn` → 0 with a warning naming each
  one, `ignore` → 0), independently of `--format`. The setting finally means what it says,
  and CI can gate on it.
- The skill and the granular commands tell the agent to run it alongside reading the docs,
  which is where the per-work-item obligation actually lives.
- `customInstructions` becomes the **sixth** entry in `harness_config.READS`, satisfying
  decision-044's direction: which conventions govern work on this repository is a fact
  about this repository, and it configures work done *on* the repository, never the daemon.
- **The report carries facts about a doc, never its contents.** Absolute and out-of-repo
  paths are supported on purpose (decision-029), so path confinement is not the boundary
  — output is. The byte count is reported instead of a preview for exactly this reason.

## Consequences

**Positive.**

- A broken registration is a signal instead of silence, at the moment work starts and in
  CI, without any change to the config shape a project already wrote.
- `onMissing: error` becomes enforceable, which retroactively makes decision-029's policy
  a real one.
- The verification is cheap to reach for: no work item, no graph state, no spec directory
  — it runs in a bare checkout like `scenarios` and `check`.
- Globs, directory registration and phase-scoped applicability — all deferred as YAGNI —
  are now cheap to add against a shape that is finally observable.

**Negative / accepted costs.**

- **It is advisory unless someone runs it.** A command is not a gate: an agent that skips
  it is not stopped by the graph. Accepted, because the alternative gate would sit at a
  boundary `check` cannot see, and because the same is already true of the *reading* it
  verifies. If evidence shows it being skipped, a `pdlc.yaml` hook calling this same
  domain module is a small follow-up — the split between `instructions.py` and its command
  exists so that hook has something to call.
- **A sixth CLI read of the harness config.** Each one has to argue for itself under
  decision-044; this one does, and `test_harness_config.py` pins it in both directions.
- **"Present" is not "obeyed".** The command proves availability, not comprehension.
  Comprehension is not mechanically checkable; availability was the half that was silently
  failing.

## Alternatives considered

| Option | Why not |
|---|---|
| A `validate-instructions` hook in `pdlc.yaml` | The obligation is per-work-item, not per-node; and its correct placement (entry chain) is never evaluated by `the-loop check`, which runs exit chains only. The gate would be invisible exactly where it was supposed to be loud. |
| Fold it into `the-loop check` as a node-independent section | `check`'s report is node-shaped end to end (`StatusReport.nodes`); a section belonging to no node would need its own rendering, its own exit-code rule and its own place in the JSON contract — a new concept inside an existing command, to avoid adding a command. |
| Extend the schema instead (globs, directories, phase scoping) | #132 asks for "a list of files", which `docs[]` already is. Extending an unobservable shape adds ways for a registration to be wrong before adding any way to find out. Deferred, deliberately, to a follow-up. |
| Have the agent simply report which docs it read | Self-reported, unverifiable, and absent exactly when it matters — a session that never resolved the doc is the session least likely to notice. |
| Show a content preview instead of a byte count | More informative, and it hands an instruction doc a channel into the operator's terminal for no requirement. "Did it resolve" is answered by the size. |
| Treat a malformed entry as absent and skip it | Restores the silence. The operator believes a doc is registered; nothing says otherwise. |
