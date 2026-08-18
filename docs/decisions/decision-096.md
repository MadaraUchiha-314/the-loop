# Decision 096: a repository may append its own hooks to the-loop's graph, and may do nothing else to it

- **Status:** proposed
- **Date:** 2026-08-18
- **Work item:** [issue-248](https://github.com/MadaraUchiha-314/the-loop/issues/248)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (proposal)
- **Refines:** [decision-041](decision-041.md) (two concepts: nodes and hooks),
  [decision-042](decision-042.md) (hooks are registered code, edges route on outcomes),
  [decision-043](decision-043.md) (`reviews.critics[]` is executable configuration),
  [decision-044](decision-044.md) (which config a setting belongs in)

## Context

issue-109 shipped ten hooks and deferred *"user-defined graphs and user-authored hooks"*,
stating that "the declarative form and the registry exist so it can arrive safely". Issue-248
asks for the hooks half: *"users of the-loop's CLI should be able to point to their own hooks
as well"*.

A project with a rule the-loop does not ship — a licence header, an architecture board's
sign-off, a ping to its own change-management system — had two options: fork the-loop, or
keep the rule outside the loop where nothing gates on it. Both are worse than the third,
provided the third cannot become a way to opt *out* of the PDLC.

## Decision

| Sub-decision | What was chosen | Why |
|--------------|-----------------|-----|
| D1 | Declared in the **repository's harness config** (`graph.hooks`), not the operator's CLI config | decision-044's direction rule: a hook gating this project's artifacts is this project's policy, and the code it names lives in this project's tree. It is where `reviews.critics[]` already is, and it carries the same label — executable configuration, reviewed like code (decision-043). |
| D2 | **Append-only.** An attachment goes at the end of the node's shipped chain; nothing can be removed, reordered or replaced | The chain short-circuits at the first hook that does not pass, so a shipped gate always decides first. This single property is what makes the feature safe to have on by default: a repository hook can add a constraint and never relax one. |
| D3 | A reserved **`x-` namespace**, required for repository hooks and refused for shipped ones | A chain reads honestly (`validate-artifacts, lint-artifacts, x-arch-signoff`), a repository module cannot shadow a shipped hook, and the collision rule needs no resolution logic. |
| D4 | A repository hook **cannot route**: `data["outcome"]` is dropped, with a warning | An outcome is how a gate is classified (`approved`) and how an edge is chosen. Honouring one from repository code would make "add a check of your own" a way to approve your own work item. Status only — so the strongest thing a repository hook can do to the loop is stop it. |
| D5 | Hooks are resolved from a **per-repository table on the compiled `Graph`**, not the process-global registry | A daemon walks several repositories in one process; two of them may legitimately define `x-house-rules`. A global registry would silently run one repository's code for another. |
| D6 | The same `@hook` decorator, redirected by a **collector** during the module's execution | One authoring API. A repository hook is written exactly like a shipped one, which is what the documentation can then say in a sentence. |
| D7 | Every declaration failure is a **load failure**, naming the file — nothing degrades to "no hooks" | The repository asked for the gate. A compliance check that silently stopped running is the failure mode worth being strict about; a repository *graph* file is still merely ignored, because the-loop never promised to honour that. |
| D8 | An operator kill switch (`routing.graph.repoHooks: false`) plus a no-import inspection command (`the-loop graph hooks`) | The modules execute in the-loop's own process, with its environment. That is not a new grant on the daemon path — it already spawns a permissions-bypassed harness in the same checkout — but it is a new statement, and an operator gets both a way to read what a repository would run and a way to refuse all of it. |
| D9 | **Graphs stay the-loop's.** No nodes, no edges, no loops from a repository | Only the hook half of issue-109's deferred item is delivered; `_warn_on_repo_graph` stands unchanged. The process is the product. |

## Consequences

**Good.** A project can enforce its own rules through the loop instead of beside it, in code
its reviewers see, with one hook API and one contract. The extension point is exactly one
function (`load_graph(repo=…)`), so `the-loop check`, every `graph` verb and the daemon get
it identically. A repository that declares nothing imports nothing and behaves as before.

**Costs, accepted.** Repository code runs in the-loop's process — mitigated by D2/D4, the
kill switch and the inspection command, not by a sandbox (deliberately out of scope, and said
so in the requirements). A hook module is imported once per process, so a daemon needs a
restart to pick up an edited one. The compiled-graph cache is now keyed per repository. And
attaching is per loop: an attachment names a node of the loop being walked, so a hook wanted
on both the outer and the inner loop is declared twice.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Let a repository supply a whole graph | Much larger surface (nodes, edges, gates, authorization) and it lets a repository delete gates. The hooks half is what the ticket asked for. |
| An insertion index (`before: validate-artifacts`) | Buys ordering, costs the guarantee that no repository hook can pre-empt a shipped gate. |
| Register repository hooks in the global registry | Simplest code, wrong for the daemon: two repositories with one name silently share an implementation. |
| Namespace by module instead of an `x-` prefix | Names become `house_rules:check`, chains stop being readable, and shadowing is prevented by machinery rather than by a rule you can state in one line. |
| Shell/`exec` hooks from configuration | Refused in issue-109 and still refused: argv from configuration is the thing the hook registry exists to avoid. |
| Warn-and-continue on a broken declaration | The failure mode is a gate that stopped running and told nobody. |
| Default the kill switch to `false` | Repository hooks would then work under a local `the-loop check` and silently not under the daemon — the same gate, two answers. |
