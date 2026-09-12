---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#354"
status: draft
approvedBy: []
collaborators: [architect, engineer]
riskTier: 2
overrides: {}
---

# Requirements: survey — the architecture of the-loop (CLI)

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). A **tier 2, documentation-only** work item: the
> deliverable is a report, so the design, testing-plan and tasks artifacts are not
> authored (the skill's risk tiers — tiers 1–2 are autonomous-complete and need no full
> spec chain). This record exists so the survey has a ticket, a spec directory and an
> execution log like every other work item.

## Introduction

[Issue-354](https://github.com/MadaraUchiha-314/the-loop/issues/354) asks five questions
about how the-loop's CLI is put together:

> - I want to know how the-loop is architected internally
> - What's the exact flow that happens when user says `the-loop start` and `the-loop execute`
> - Main Question: How does the-loop make sure that it doesn't proceed to design phase
>   before completion of requirements phase? What are the guardrails that exist that
>   prevent this? Are these enforcement programmatic?
> - Does the agent harness (claude/cursor) come back to the-loop to ask what to do next
>   and does the-loop reply with the next step?
> - Can you explain the architecture using sequence and component diagrams?

The answer is a **report** under `docs/reports/` — the home of investigations that do not
belong to one work item's spec — written from the code as it stands at v15.0.0, with
file references a reader can follow.

## Requirement 1 — One report answers every question the issue asks

**User story:** As the owner, I want a single document that answers the five questions
with references into the code, so that I can check each claim against the source rather
than take a narrative on trust.

### Acceptance criteria (EARS)

1. THE report SHALL have one section per question in the issue, in the issue's order,
   and each section SHALL cite the module (and where useful the function) that
   implements what it describes. (AC1.1)
2. WHEN the report describes the `the-loop start` and `the-loop execute` flows THEN it
   SHALL trace them end-to-end — ingress, authorization, control record, workspace,
   session, graph entry, phase selection, freeze, first assignment — as a numbered
   sequence and as a sequence diagram. (AC1.2)
3. WHEN the report answers the main question (requirements before design) THEN it SHALL
   list every guardrail, mark each one **programmatic** or **prose**, say where it lives,
   and state honestly what is *not* prevented (a session may write `design.md` early;
   the pointer, the label and the gate are what it cannot move). (AC1.3)
4. WHEN the report answers the harness-interaction question THEN it SHALL state the
   direction of control (the daemon spawns and resumes the harness; the harness calls
   the CLI at node ends and from its Stop hook) and SHALL name the three touchpoints —
   the assignment prompt, `the-loop graph complete`, and `the-loop check` from the Stop
   hook. (AC1.4)
5. THE report SHALL carry at least one **component diagram** and at least two
   **sequence diagrams**, as Mermaid fences the docs site renders. (AC1.5)

## Requirement 2 — The report is registered and lint-clean

**User story:** As a reader of the docs site, I want the survey listed where the other
reports are, so that it is discoverable without knowing its path.

### Acceptance criteria (EARS)

1. THE report SHALL be listed in `docs/reports/index.md` and in the docs sidebar
   (`docs/.vitepress/config.mts`), and linked from `docs/architecture/architecture.md`.
   (AC2.1)
2. THE report SHALL pass the repository's markdownlint configuration. (AC2.2)

## Security considerations

**No new attack surface.** This work item adds documentation only: no code, no
configuration, no hook, no workflow changes. The report describes existing trust
boundaries (the `authorizedUsers` allowlist, the self-authored-comment marker, the
recompute rule on `graph-state.json`) and introduces none.

- **Untrusted actors:** none new. The report quotes no secrets and no private data.
- **Trust boundaries:** unchanged. The report documents where the existing ones are
  enforced (`control.py`, `graph/hooks/feedback.py`, `graph/state.py`).
- **Abuse cases:** a reader could misread the report as a claim that every guardrail is
  programmatic; AC1.3 requires the prose/programmatic split to be explicit so the
  document cannot be used to over-claim.
- **Fail-closed expectations:** n/a — no runtime behaviour changes.
