---
type: requirements
phase: requirements-definition
workItem: issue-164
status: approved              # draft | in-review | approved
approvedBy: []                # recorded on the PR review (paper trail)
collaborators: [product-manager, architect, engineer, reviewer]
overrides: {}
---

# Requirements: the module structure a work item will produce

> Phase 1. Ticket: [issue #164](https://github.com/MadaraUchiha-314/the-loop/issues/164).

## Introduction

`design.md` tells a reviewer what the components are and how they interact. It never tells
them **where the code will land**. Nothing in the bundled template or the `design` node's
gate asks for the files, modules and packages the work item will create, change or remove,
so a reviewer who wants that has two options: read `tasks.md`, which describes work rather
than layout, or wait for the diff — after the design is already approved.

This work item adds a **Module structure** section to `design.md`: the tree of paths the
delivered code will occupy, each marked new, changed or removed, each with a one-line
responsibility and the requirement it serves. It is gated at the `design` node beside
`Architecture`, `Security design` and `Testing strategy`, because a section that only prose
asks for is a section that goes missing — that is what issue-124 and issue-148 both cost.

## Requirements

### Requirement 1 — `design.md` states where the code will land

**User story:** As a reviewer approving a design, I want to see the module layout the work
item will produce, so that I can judge placement before the code exists rather than after.

#### Acceptance criteria (EARS)

1. WHEN `design.md` is authored from the bundled template THEN the template SHALL provide a
   `## Module structure` section.
2. WHEN the module structure is authored THEN it SHALL show the modules the work item
   creates, changes or removes as a tree of repository-relative paths, each entry marked
   new, changed or removed.
3. WHEN a module appears in the tree THEN the section SHALL state its responsibility in one
   line and name the requirement(s) it serves.
4. WHERE three or more modules depend on one another THEN the section SHALL carry a mermaid
   diagram of the dependency direction (`userInteraction.writingStyle.diagramFirst`).
5. The section SHALL be scoped to the modules the work item touches and SHALL NOT restate
   the repository's whole layout — `docs/architecture/architecture.md` holds the standing
   view, and this section is the delta the work item adds to it.
6. WHERE a work item changes no code (a docs-only or process-only item) THEN the section
   SHALL say so in one sentence and name the files it does change, rather than being
   deleted.

### Requirement 2 — the gate enforces it, not the prose

**User story:** As the harness, I want the section to be a gate condition, so that a design
missing it blocks instead of reaching a human as a surprise.

#### Acceptance criteria (EARS)

1. WHEN the `design` node's exit hooks run THEN `validate-artifacts` SHALL require a
   `Module structure` section in `design.md`.
2. WHEN that section is missing or empty THEN the node SHALL block with a finding naming
   the section, and SHALL NOT report the gate as passed.
3. WHEN the shipped graph and the bundled templates are checked against each other THEN the
   parity test SHALL confirm the template can satisfy the new gate condition.

### Requirement 3 — the operating model names the section once

**User story:** As an agent authoring a design, I want one statement of what belongs in the
section, so that four documents cannot drift into four rules.

#### Acceptance criteria (EARS)

1. WHEN `/the-loop:create-design` runs THEN its steps SHALL name the module structure among
   the sections it derives.
2. WHEN the skill and `reference/workflow.md` describe `design.md` THEN they SHALL list the
   section among its contents.
3. WHEN the capability doc for the spec workflow describes the design phase THEN it SHALL
   record the section as current behaviour with a history row.
4. The rules for **how** to author the section SHALL live in the bundled template, and the
   documents above SHALL reference rather than restate them.

### Requirement 4 — the section educates rather than duplicates

**User story:** As a reviewer, I want the section to answer a question I would otherwise
ask, without re-reading it in three other places.

#### Acceptance criteria (EARS)

1. WHEN a reviewer reads the section THEN they SHALL be able to name the directories and
   modules the delivered code will occupy without opening `tasks.md` or the diff.
2. WHEN the section is authored THEN it SHALL NOT duplicate `Components & interfaces` —
   that section carries responsibility and contract, this one carries **placement**.
3. WHERE the implementation ends up diverging from the planned structure THEN the divergence
   SHALL be recorded in the PR briefing, so the section stays a claim a reviewer can check.

## Security considerations

**Threat-model-lite.** This work item adds no runtime path, no network call and no new
input to any executable code. The change is one template section, one entry in the shipped
process graph's existing `sections:` list, documentation, and tests. The gate mechanism
itself (`validate-artifacts` reading headings through `graph.frontmatter`) is untouched.

- **Untrusted actors:** none new. The section is authored by whoever authors the design,
  who already writes the rest of the file.
- **Trust boundaries:** one, and it is pre-existing — the `design` node's exit gate reads
  the spec file from the work-item directory. This change adds a required heading to that
  read; it adds no parser, no new file, and no new source of input.
- **Abuse cases:**
  1. *A path listing leaks something it should not* — an internal hostname, a credential
     file path, a private repository name pasted into the tree. Mitigation: the tree holds
     repository-relative source paths only, and the existing redaction rule for committed
     artifacts applies unchanged. Negative expectation: nothing in this change causes a path
     to be read, resolved or fetched — the gate matches a heading and checks it is non-empty.
  2. *The section becomes a box to tick* — a heading with "TBD" under it clearing the gate.
     Mitigation: `validate-artifacts` treats an empty required section as a finding, and
     content quality stays a review judgement, deliberately (the density test is not a gate,
     decision-061).
  3. *The gate blocks a work item that legitimately changes no code.* Mitigation: R1.6 — the
     section records that in one sentence, which is non-empty and clears the gate. A gated
     section is never deleted to shorten a document.
- **Fail-closed behaviour:** a missing or empty section blocks the node. The failure mode
  this repository has actually paid for is the opposite one — a gate reporting success
  without running (issue-124) — so the new condition is added to an existing
  `validate-artifacts` list rather than to any new code path that could skip.
- **No new attack surface**, and here is why that is not merely asserted: the diff adds no
  executable statement to the CLI. The only non-markdown file it touches is `pdlc.yaml`,
  and only to append a string to a list the hook already iterates.

**Effective risk tier: 3** (`autonomy.defaultTier: 3`, `human-approves-pr`). No path in
`autonomy.sensitivePaths` is touched — the harness config, its schema and
`.github/workflows/` are all unchanged — so `inferFromChange` does not raise the tier, and
no named human security sign-off is required
(`security.review.humanSignOffMinTier: 4`).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
