---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#248"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: a repository may bring its own graph hooks

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

**the-loop's process is extensible by design and closed in practice.** Ticket
[#248](https://github.com/MadaraUchiha-314/the-loop/issues/248) — *"allow user's of the-loop
to provide their own hooks — users of the-loop's CLI should be able to point to their own
hooks as well"*.

A **hook** is the-loop's one unit of work at a node boundary: `(HookContext) -> HookResult`,
named in the graph, resolved from a registry
([process-graph](../../capabilities/process-graph.md) § The hook contract). Ten ship with
the CLI. A project that wants an eleventh — *"every design.md must carry our architecture
board's sign-off"*, *"no implementation node passes while the licence header is missing"*,
*"tell our own change-management system when a work item reaches `needs-review`"* — has
nowhere to put it. [issue-109](https://github.com/MadaraUchiha-314/the-loop/issues/109)
listed *"user-defined graphs and user-authored hooks"* as out of scope precisely so this
could arrive later:

> the declarative form and the registry exist so it can arrive safely

This work item delivers the **hooks** half of that, and only that half. The process graph
stays the-loop's — a repository still cannot redefine the PDLC, reorder it, or drop a gate
out of it. What a repository gains is the ability to **add** a check at a boundary the
shipped graph already declares, in code it writes, reviews and ships in its own tree.

The direction rule ([decision-044](../../decisions/decision-044.md)) puts the declaration in
the repository's harness config: a hook that gates *this project's* design artifacts is a
property of this project, not of the operator's machine, and the same rule already puts
`reviews.critics[]` there. That entry is the precedent in every other respect too — it is
**executable configuration in a repo-tracked file, reviewed like code**
([decision-043](../../decisions/decision-043.md)).

## Requirements

### Requirement 1 — a repository declares hook modules and where they attach

**User story:** As an engineer whose project has a rule the-loop does not ship, I want to
write that rule as a hook in my own repository and name the boundary it runs at, so that the
loop enforces it without my forking the-loop.

#### Acceptance criteria (EARS)

1. WHEN a repository's harness config declares `graph.hooks.modules[]` THEN the-loop SHALL
   load each declared module and register the hooks it defines for that repository.
2. THE system SHALL accept two ways to name a module: `path`, a `.py` file relative to the
   repository root, and `module`, an importable dotted name installed alongside the CLI.
3. WHEN a repository declares `graph.hooks.attach[]` THEN each entry SHALL name a `hook`, a
   `node` of the loop being walked, and optionally a `boundary` (`entry` | `exit`, default
   `exit`) and a `with` parameter mapping, and the-loop SHALL run that hook at that boundary.
4. THE system SHALL pass an attached hook the same `HookContext` and accept the same
   `HookResult` as a shipped hook — one contract, not two.
5. WHEN a work item's node has repository hooks attached THEN `the-loop check`,
   `the-loop graph` and the daemon SHALL all evaluate the same chain, because all three
   compile the graph through one loader.
6. WHEN a repository declares no `graph.hooks` block THEN the-loop's behaviour SHALL be
   byte-for-byte what it is today, loading and importing nothing.

### Requirement 2 — a repository hook may add a constraint, never remove one

**User story:** As the owner of the-loop's process, I want a repository's hooks to be
strictly additive, so that adopting them cannot become a way to opt out of the PDLC.

#### Acceptance criteria (EARS)

1. THE system SHALL **append** attached hooks to the end of a node's shipped chain, and
   SHALL provide no way to remove, reorder or replace a shipped hook.
2. WHERE a shipped hook does not pass, the chain's short-circuit SHALL mean the attached
   hooks after it do not run — a repository hook SHALL NOT be able to turn a shipped
   `block` into a `pass`.
3. THE system SHALL ignore an `outcome` declared in an attached hook's `data`, so a
   repository hook SHALL NOT be able to classify a human gate (e.g. `approved`) or select an
   edge; its influence on movement is confined to its `status`
   (`pass` | `block` | `wait` | `skip`).
4. WHEN an attached hook declares an outcome THEN the-loop SHALL log that it was ignored,
   naming the hook — a silently dropped value is a defect report nobody receives.
5. THE system SHALL NOT let a repository attach to a node the loop being walked does not
   declare, nor to a boundary other than `entry` or `exit`.

### Requirement 3 — a repository hook is named in a reserved namespace

**User story:** As an engineer reading a chain, I want to know at a glance which hooks are
the-loop's and which are my repository's, so that a failure lands on the right maintainer.

#### Acceptance criteria (EARS)

1. THE system SHALL require every repository-provided hook name to begin with `x-`.
2. THE system SHALL refuse a shipped hook registered under an `x-` name, so the namespace
   cannot be colonised from the other side.
3. WHEN a repository module registers a name without the `x-` prefix THEN the load SHALL
   fail, naming the module and the offending name.
4. THE system SHALL resolve an `x-` name from the **repository's own** table, so two
   repositories served by one daemon SHALL NOT see each other's hooks even when both use the
   same name.

### Requirement 4 — every failure is a load failure, and it names the file

**User story:** As an operator, I want a broken hook declaration to stop the loop with a
message, so that a compliance gate can never quietly stop running.

#### Acceptance criteria (EARS)

1. WHEN a declared module is missing, unreadable, raises on import, or registers no hook
   THEN loading the graph SHALL fail with `GraphConfigError` naming the declaration.
2. WHEN an `attach[]` entry names a hook no declared module registered THEN loading the graph
   SHALL fail, listing the names that were registered.
3. WHEN an attached hook raises at run time THEN it SHALL be treated as `block` with
   `retriable=False`, exactly as a shipped hook is (issue-109, R2.6).
4. THE system SHALL NOT degrade a broken `graph.hooks` block to "no hooks" — an absent gate
   that the repository asked for is a false green.

### Requirement 5 — the operator can see, and refuse, what a repository would run

**User story:** As the operator running the daemon, I want to inspect a repository's hook
declarations without executing them, and to switch the whole mechanism off for my machine, so
that adopting a repository is a decision I make with the facts.

#### Acceptance criteria (EARS)

1. THE CLI SHALL provide `the-loop graph hooks`, which reports the registered shipped hooks
   and the repository's declared modules and attachments **without importing any of them**.
2. WHEN `routing.graph.repoHooks` is `false` in the operator's CLI config THEN the-loop
   SHALL load no repository hooks on any path that reads that config, and SHALL say so when
   a repository declared some.
3. THE system SHALL resolve a `path:` module inside the repository root — an absolute path,
   a `..` escape, a symlink leaving the tree, or a non-`.py` file SHALL be refused.

## Non-functional requirements

- **No new runtime dependency.** Module loading is `importlib`, stdlib
  ([decision-038](../../decisions/decision-038.md)).
- **Loaded once per process.** A module is imported once and its hooks cached by source, so a
  daemon walking N work items in one repository pays for one import. Editing a hook module
  therefore takes effect on the next process, which the documentation states.
- **Observable.** The event log records that a repository's hooks were loaded, with the
  module count and the attachment count — never the module's contents.

## Security considerations

> Threat-model-lite, captured with the requirements (`security.threatModel.required`).

- **Actors & trust.** *Trusted:* the-loop's shipped graph and hooks; the operator; the
  repository's reviewed, committed code. *Untrusted:* the agent as a writer of files inside a
  checkout; ticket and webhook payload text; any repository the operator has not adopted.
- **Boundary 1 — configuration → code execution.** issue-109's Boundary 2 said hooks are
  registered code and never argv-from-configuration, so the *graph* could safely become
  user-authored. This work item does not weaken that: the YAML still names hooks, and the
  code still arrives as code. What changes is **whose** code — and that is a trust decision
  the repository's own reviewers make, in a repo-tracked file, exactly as
  `reviews.critics[]` already is (decision-043).
- **Boundary 2 — the CLI process.** An attached hook runs **in the-loop's process**, with its
  environment. That process holds credential *handles* (env var names, R2.7) but its
  environment holds the values, so a repository hook can read them. This is not a new grant
  in the daemon's own threat model — the daemon already spawns a harness in that checkout
  with permissions bypassed (`the_loop.trust`), and that session inherits the same
  environment — but it is a **new route** to that place, and one an *agent* can open by
  writing a hook module and a `graph.hooks` block into a checkout it can already write. That
  is why R5.2's kill switch and R5.1's no-import inspection exist, and why the answer to "who
  authorises this?" is a repo-tracked file whose diff a reviewer sees.
- **Boundary 3 — repository hook → process movement.** A hook the agent could write must not
  be able to *advance* a work item. Confined by R2.1 (append-only), R2.2 (short-circuit) and
  R2.3 (no outcome), so the strongest thing a repository hook can do to the loop is stop it.
- **Abuse cases (EARS):**
  1. WHEN a repository hook returns `pass` at a gate whose shipped hook blocked THEN the node
     SHALL stay blocked, because the shipped hook short-circuited before it ran.
  2. WHEN a repository hook declares `data["outcome"] = "approved"` at a human gate THEN the
     outcome SHALL be ignored and the gate SHALL stay waiting.
  3. WHEN a repository declares a module outside its own tree (`/etc/…`, `../other-repo/…`,
     a symlink out) THEN the load SHALL be refused.
  4. WHEN a repository module registers a name that shadows a shipped hook THEN the load
     SHALL fail rather than the shadow taking effect.
  5. WHEN two repositories register the same `x-` name THEN each work item SHALL run its own
     repository's implementation.
  6. WHEN an attached hook raises or hangs the chain THEN it SHALL be a `block`, never a
     `pass`.
  7. WHEN the operator sets `routing.graph.repoHooks: false` THEN no repository module SHALL
     be imported on that machine.
- **Fail closed.** A malformed declaration, an unresolvable module, an unknown hook name, an
  unknown node, an escaping path — each stops the load and reports. Nothing degrades to
  "no hooks".
- **New surface, stated.** Repository-supplied Python executes inside the CLI process at node
  boundaries. Risk tier **4** — `security.review.humanSignOffMinTier` is 4, so this work item
  needs a **named human security sign-off** before it completes, and the schema and config
  files it touches are in `autonomy.sensitivePaths`.

## Out of scope

- **User-authored graphs.** A repository still cannot declare nodes, edges or a loop of its
  own; `_warn_on_repo_graph` stands unchanged. Only the hook half of issue-109's deferred
  item is delivered.
- **Removing, replacing or reordering shipped hooks.** Additive only, by decision (R2).
- **Sandboxing repository hooks.** They run in-process, trusted as the repository's own code.
  A sandbox is a different work item with a different threat model.
- **Distributing hooks as a plugin/entry-point ecosystem.** `module:` accepts an installed
  dotted name, which is enough for a team to `pip install` a shared package; discovery,
  versioning and a registry are not built here.
- **Hot reload.** A hook module is imported once per process (see non-functional).

## Open questions

None outstanding. The two judgement calls — where the declaration lives (harness config, by
decision-044) and whether repository hooks may route (they may not, R2.3) — are answered in
`design.md` § Trade-offs & decisions and recorded as a decision record.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
