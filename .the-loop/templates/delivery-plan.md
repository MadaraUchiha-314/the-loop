---
type: delivery-plan
workItem: ""                 # ticket id this plan delivers
status: draft                # draft | in-review | approved
approvedBy: []               # handles/roles who approved (paper trail)
overrides: {}                # per-task overrides of .the-loop/config.yaml
---

# Delivery Plan: <work item title>

> A delivery plan MUST be created for every work item, reviewed and approved by the
> appropriate collaborators BEFORE execution begins. This file is checked in as
> `docs/delivery-plans/<id>-delivery-plan.md`.

## Context
Link to the work item. Summary of goal and acceptance criteria.

## Collaborators required
| Role | Handle | Needed for |
|------|--------|------------|
|      |        |            |

## Approach
The intended technical approach and the key trade-offs considered.

## Step-by-step plan
1.
2.
3.

## Checkpoints & self-checks
At which logical points will the-loop run tests / validations to verify progress?

- [ ] Checkpoint 1 — what is validated, how
- [ ] Checkpoint 2

## Risks & open questions
Anything that needs a human decision is raised as a ticket comment and linked here.

## Definition of done
How the-loop will present validated evidence that acceptance criteria are met.

## Approvals
Record approvals here (and as ticket comments) before moving to execution.
