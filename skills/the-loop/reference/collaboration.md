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

## Working with other tools (MCP / CLIs / plugins)

the-loop is allowed to freely interact with the MCP tools, skills and plugins available
in the harness. The user declares which ones to be aware of in
`.the-loop/external-tools.md` (free-form) or `config.externalTools.notes`. Examples:
Jira via MCP, GitHub via `gh`, plugins such as ponytail or superpowers. Always check
this registry before assuming a capability is or isn't available.
