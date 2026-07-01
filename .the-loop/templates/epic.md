---
type: epic
id: ""                       # ticket id, e.g. issue-12 or PROJ-12
title: ""
status: draft                # draft | ready | in-progress | in-review | done
collaborators: []            # roles/handles required up-front, e.g. [product-manager, architect]
# --- per-task overrides of .the-loop/config.yaml (optional) ---
overrides: {}
  # reviews:
  #   selfReviewCount: 1
---

# Epic: <title>

## Summary

One-paragraph description of the outcome this epic delivers.

## Goal (detailed)

What does "done" look like for the whole epic? Why does it matter?

## Acceptance criteria

- [ ] Criterion 1 (observable, testable)
- [ ] Criterion 2

## Child work items

Break the epic down into stories / bugs. Capture dependencies (blocked-by / depends-on)
so the-loop can build the task DAG.

| Work item | Type | Depends on | Status |
|-----------|------|------------|--------|
|           |      |            |        |

## Collaborators

Who is required and for what. (RULE: identify collaborators up-front; more can be added later.)

## Out of scope

What this epic explicitly does not cover.
