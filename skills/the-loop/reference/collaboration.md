# Collaboration reference

How the-loop works with humans and other personas. The governing rule: **every decision
or opinion taken from a human MUST have a paper trail** on the ticketing system or the
PR.

## Paper-trail rules

- **Planning questions/opinions/decisions** → asked and recorded as **comments in the
  ticketing system** (GitHub issue / Jira), not resolved silently in files.
- **PR reviews** → happen **on the PR** as comments and replies.
- **Self & critic reviews** → also as PR/ticket comments.
- **Notifications/escalations** when a human action is pending → sent through configured
  **messaging channels** (`messaging.channels`: slack / whatsapp / email) if configured.
  Messaging is for notification only; the decision itself still lands as a comment.

## Personas, roles and groups

- The full list of available collaborators is defined up-front in the repo:
  `.the-loop/collaborators.yaml` and/or `config.personas`.
- A collaborator may be an **individual** or a **group** (e.g. a GitHub team
  `@org/team`). A single user may hold **multiple roles**.
- Supported roles: `product-manager`, `architect`, `designer`, `engineer`, `qa`,
  `reviewer`, `approver`.

## RULE: identify collaborators up-front

Every work item MUST clearly identify the collaborators it needs at the start (in its
spec front-matter `collaborators`). More collaborators can be added later as needed.

## Not every task needs every persona

Match personas to the work:

| Work type | Typical collaborators |
|-----------|----------------------|
| Architecture-significant change | architect (+ PM, engineer) |
| UI/UX change | designer (+ engineer) |
| Product/requirements work | product-manager (+ architect) |
| Simple bug fix | engineer only |
| Content/copy fix | reviewer (often no engineer) |
| Release/QA sign-off | qa, approver |

Pull required reviewers/approvers for each phase from `collaborators.yaml` by role.

## User-interaction principles (reviewing AI-authored work)

The human often did not write the code and their familiarity with the codebase keeps
dropping, so how the-loop communicates is a first-class concern. Driven by
`config.userInteraction`.

- **Give enough context to decide.** Whenever user input is requested (a planning
  question, a design opinion, a review), include enough context that the user can make
  the right judgement call without digging.
- **Condensed, prioritized PR summaries.** Every PR the-loop raises tells the reviewer
  **where to focus and in what order** — reviewing a huge AI-authored PR top-to-bottom
  is not realistic. Lead with the highest-priority items to scrutinize.
- **RULE: all diagrams are mermaid.** PR summaries, design docs and educational snippets
  use mermaid diagrams to explain low-level details (`diagramFormat: mermaid`).
- **Document insights & decisions in the PR description.** Capture the insights from
  taking the spec to implementation and every low-level decision the harness had to make,
  so the user sees the reasoning, not just the diff.
- **RULE: educate the user (mandatory, not optional).** As the user's familiarity with
  the code drops, use every opportunity to teach them the low-level design decisions.
  This is intentional and required (`educateUser: true`), not a nicety. *How to hard-
  enforce this is an open question (see `automation-and-roadmap.md`); today it is a
  standing rule + config flag.*

## Working with other tools (MCP / CLIs / plugins)

the-loop is allowed to freely interact with the MCP tools, skills and plugins available
in the harness. The user declares which ones to be aware of in
`.the-loop/external-tools.md` (free-form) or `config.externalTools.notes`. Examples:
Jira via MCP, GitHub via `gh`, plugins such as ponytail or superpowers. Always check
this registry before assuming a capability is or isn't available.
