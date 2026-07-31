---
type: bugfix
phase: requirements-definition
workItem: issue-124
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: a bugfix-shaped work item cannot clear the gate its own process ships

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

the-loop documents two names for the phase-1 spec artifact — `requirements.md`, **or
`bugfix.md` for a bug** — in the skill, the workflow reference, the manifest, two command
docs and a bundled template. The process graph that *gates* phase 1 knows only one:

```yaml
# cli/the_loop/graph/pdlc.yaml
- id: requirements-definition
  produces: [requirements.md]
```

`validate-artifacts` resolves `produces` literally. An agent that follows the documented
process therefore authors `bugfix.md` and is then blocked by the same process for not
having written `requirements.md`. Ticket: #124.

This spec is itself authored as a `bugfix.md`, deliberately: the-loop's own gate runs on
every spec folder a PR touches, so this file passing CI *is* the regression test for the
headline defect.

## Steps to reproduce

Any bug spec in the tree that followed the documented shape reproduces it. On `main`:

```console
$ uv run the-loop check issue-104 --recompute
issue-104: UNMET (at requirements-definition)
  BLOCK  requirements-definition
         · required artifact is missing (docs/specs/issue-104/requirements.md)
  ····   5 node(s) not reached yet
```

`docs/specs/issue-104/` contains `bugfix.md`, `design.md`, `tasks.md` and
`execution-log.md` — a complete, merged, shipped work item. It is blocked at phase 1
for the absence of a file the process told it not to write.

## Expected vs actual

- **Expected:** a work item whose phase-1 artifact is named `bugfix.md` — the name the
  skill, the reference, the manifest and the bundled template all bless — clears the
  `requirements-definition` node.
- **Actual:** `BLOCK requirements-definition · required artifact is missing
  (docs/specs/<id>/requirements.md)`. There is no way to satisfy the gate while following
  the documentation.

## Root cause (confirmed)

One naming disagreement, and **three** places it bites. Each was found by walking the
gate's own code rather than by reading the prose, and the second and third are not in the
ticket — they are what the missing parity test would have surfaced alongside the first.

### RC1 — `produces` cannot express an alternative

`Node.produces` is a flat tuple of names, and both hooks that read it resolve every entry
to exactly one path:

```python
# cli/the_loop/graph/hooks/artifacts.py — and, identically, hooks/lint.py
def _artifact_paths(ctx: HookContext) -> List[Path]:
    produces = ctx.node.get("produces") or []
    ...
    return [ctx.work_item.spec_dir / str(p) for p in produces]
```

There is no syntax for "this node produces one of these", so the graph could not have
been written to accept both names even if #109 had known to try.

### RC2 — the security-boundary check silently skips for every bug

The `design` node's second exit hook names its upstream by the same literal:

```yaml
- {hook: enforces-boundaries-from, with: {upstream: requirements.md, markers: [...]}}
```

For a bug, `requirements.md` does not exist, so `enforces_boundaries_from` takes its
`not up.is_file()` branch and returns **skip**, not block:

```python
if not up.is_file() or not downs:
    return HookResult.skipped(name, "upstream or downstream artifact absent")
```

A skip passes the chain. So for every `bugfix.md` work item, the check that every trust
boundary raised in phase 1 is answered in `design.md` — a `security.design.required`
gate — has never run, and reported success while not running. That is strictly worse
than RC1: RC1 fails loudly, RC2 passes quietly.

### RC3 — the bundled bugfix template cannot satisfy the sections the node requires

The `requirements-definition` node demands two headings:

```yaml
exit:
  - {hook: validate-artifacts, with: {locked: true, sections: ["Requirements", "Security considerations"]}}
```

`skills/the-loop/templates/requirements.md` has `## Requirements`.
`skills/the-loop/templates/bugfix.md` does not — it has `## Acceptance criteria (EARS)`.
So fixing only the filename leaves a bugfix.md authored from the shipped template blocked
on `required section is missing: Requirements`. The headline claim of this ticket stays
true until the template is fixed too.

This is also what #119's undocumented workaround actually consisted of: not just naming
the file `requirements.md`, but *also* retitling its acceptance criteria to
`## Requirements`. Both halves were needed, and neither was written down.

### Why nothing caught it

The graph landed in #109, after every existing `bugfix.md` (issues 36, 78, 80, 93, 104),
so no work item exercised the combination until #119 — which hit it in CI on #120 and
worked around it. **Nothing asserts that the artifact names and section headings the
shipped templates offer are the ones the shipped graph accepts.** That parity gap is the
real defect; the naming disagreement is only what it let through.

## Requirements

### Requirement 1 — `produces` can name alternatives

The graph gains a way to say "this node produces one of these names".

#### Acceptance criteria (EARS)

1. WHEN a `produces` entry contains alternatives separated by `|` THEN the graph SHALL
   treat every listed name as an accepted name for that one artifact.
2. WHEN the graph is compiled AND a `produces` entry has an empty alternative (`a||b`,
   `|a`, `a|`) THEN compilation SHALL fail with a `GraphConfigError` naming the offending
   node and entry — a structural fault is a startup failure, per the graph's own thesis.
3. WHEN a `produces` entry names a single artifact THEN behaviour SHALL be unchanged from
   today, byte for byte.

### Requirement 2 — the phase-1 node accepts both documented names

#### Acceptance criteria (EARS)

1. WHEN a work item's spec folder holds `bugfix.md` and no `requirements.md` THEN
   `validate-artifacts` at `requirements-definition` SHALL validate `bugfix.md` and,
   if it holds up, pass.
2. WHEN the folder holds `requirements.md` and no `bugfix.md` THEN the node SHALL behave
   exactly as it does today.
3. WHEN the folder holds **neither** THEN the node SHALL block with a message naming
   **every** accepted name, so the agent knows what it may write.
4. WHEN the folder holds **both** THEN the node SHALL block as ambiguous. Two phase-1
   artifacts in one folder have no defined source of truth, and a gate that silently
   picks one is how a stale spec gets approved. Fail closed.

### Requirement 3 — the security-boundary check runs for bugs

#### Acceptance criteria (EARS)

1. WHEN `enforces-boundaries-from` is given an `upstream` naming alternatives THEN it
   SHALL resolve it the same way `produces` is resolved.
2. WHEN a work item's phase-1 artifact is `bugfix.md` AND it names a trust boundary that
   `design.md` does not answer THEN the `design` node SHALL **block** — not skip.

### Requirement 4 — a bugfix spec authored from the bundled template passes

#### Acceptance criteria (EARS)

1. WHEN a bugfix spec is authored from `skills/the-loop/templates/bugfix.md` and filled in
   THEN every section the `requirements-definition` node requires SHALL be present in it.
2. The template SHALL keep the reproduction / expected-vs-actual / root-cause structure
   that makes it worth having as a separate template at all.

### Requirement 5 — the parity gap is closed by a test

This is the acceptance criterion the ticket calls the actual defect.

#### Acceptance criteria (EARS)

1. WHEN a bundled template declares a phase whose node's `produces` does not accept that
   template's filename THEN the test suite SHALL fail.
2. WHEN a node's `produces` accepts a name that no manifest work-item artifact declares
   THEN the test suite SHALL fail.
3. WHEN a node's `validate-artifacts` requires a section that a template for that node's
   phase does not offer as a heading THEN the test suite SHALL fail.
4. The test SHALL fail on the tree as it stands **before** the fix — a parity test that
   was green on the broken tree would prove nothing.

### Requirement 6 — regression coverage and documentation

#### Acceptance criteria (EARS)

1. The fix SHALL include tests that fail before it and pass after, for RC1, RC2 and RC3.
2. `bugfix.md` SHALL remain documented as a first-class phase-1 artifact name in the
   skill, the workflow reference, the manifest and the command docs — Option 1 keeps both
   shapes working, so no documentation retires the name.
3. The `produces` alternation syntax SHALL be documented where the graph is documented,
   and the choice recorded as a decision.

## Out of scope

- **Retiring `bugfix.md`** (the ticket's Option 2). Declined by the maintainer: it would
  change documented plugin behaviour for consuming repos on upgrade. Recorded on the
  ticket.
- **Renaming the five existing bug specs** (issues 36, 78, 80, 93, 104). Left as a
  historical record by the maintainer's call — they are closed work items and nothing
  re-runs their gates. They are *not* retro-fitted with a `## Requirements` heading
  either; RC3's fix is to the template, for specs authored from here on.
- **The review nodes' unenforced sections.** `self-review`, `critic-review`,
  `security-review`, `evidence`, `capability-docs` and `reviewer-briefing` each declare
  `sections:` but no `produces:`, so `validate-artifacts` returns
  `skipped("this node declares no artifacts")` and those section requirements are never
  checked against `execution-log.md`. Same family as RC2 — a gate reporting success
  without running — but a distinct defect with its own blast radius, and folding it in
  here would bury this fix. Filed as **#125**.
- Generalising alternation to `sections:`. RC3 is fixed by making the template match the
  one section vocabulary the graph already uses; a second alternation mechanism would be
  cost without a second use.

## Security considerations

**Threat-model-lite.** The change is to a gate's resolution logic, so the security
question is not "what new input arrives" but "what can now pass that should not".

- **Untrusted actors / inputs.** None new. `produces` and `upstream` come from
  `pdlc.yaml`, which **ships with the CLI**; a repository cannot define or override the
  graph (a repo-supplied one is ignored with a warning, R1.4). The alternation syntax is
  therefore authored only by the-loop's own maintainers, and every value it can take is
  reviewed as code. No payload text, no network input, no user-supplied path reaches this
  code path.
- **Trust boundary: the filesystem.** Alternatives are resolved by joining a name to
  `work_item.spec_dir`, exactly as the single-name path is today. The set of names is
  fixed at graph-compile time, so alternation adds no way to reach a path an operator
  did not already grant. It cannot widen the resolution surface beyond the spec folder.
- **Abuse case: weakening a gate to get green.** The one real risk. Accepting "any one of
  N names" is, by construction, easier to satisfy than "this exact name". Two decisions
  hold the line: **ambiguity fails closed** (Requirement 2.4 — both present is a block,
  not a lucky pick, so nobody clears a gate against a stale artifact while the live one
  sits beside it), and every alternative still runs the **full** validation — `locked`,
  `frontMatter`, `sections`, `checkmarks` — unchanged. The name is what becomes flexible;
  the standard the artifact is held to does not move.
- **Fail-closed, and a gate that gets stricter.** Net, this change *closes* an open hole
  rather than opening one: RC2 means the trust-boundary check has been silently skipping
  for every bug work item, and Requirement 3 makes it run and block. A bug spec that names
  a boundary its design ignores will now fail where it previously passed. That is the
  intended direction, and it is why "no new attack surface" is the accurate claim here
  rather than a formality — the attack surface is unchanged and one existing gate goes
  from advisory to enforced.
- **Human sign-off.** Risk tier 3, below `security.review.humanSignOffMinTier: 4`, so no
  named security sign-off is required; the security review at the ready-to-ship gate still
  runs.

## Open questions

None. The one open decision this ticket carried — Option 1 versus Option 2, and whether to
rename the existing bug specs — was put to the maintainer and answered before the spec was
written; the paper trail is on #124.
