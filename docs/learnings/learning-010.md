# Learning 010: An approval gate's vocabulary must cover the ways people say yes

- **Date:** 2026-10-18
- **Source:** user-feedback (the author's reply at a gate)
- **Work item:** issue-496

## What happened

At `requirements-approval` the author replied with the single word **"approval"**. The
gate's `classify-feedback` hook locks only on `approved`, `lgtm`, `looks good` and
`ship it` (`cli/the_loop/graph/hooks/feedback.py`, `_classify`), so it classified the
reply as indecisive and kept waiting. The session could not lock the file itself (the
gate is the only locker, issue-281) and had to ask the author to say it again with a
word on the list. One human decision cost two round trips.

## Learning

A gate that asks a human for a yes must accept the yes however they phrase it, or
say up front which words count. The cost of a missed yes is not a wrong lock, it is a
human asked twice for the same decision, which is what the gate exists to avoid. The
inverse risk, locking on a word that was not meant as approval, is the one to guard,
so widen the vocabulary to the plain forms of *approve* (`approve`, `approval`,
`approving`) and keep refusing anything hedged, rather than guessing at intent.

## Action

- Extend `_classify`'s approval set with the stem forms of *approve*, with a test
  for each and a negative test for `not approved` and `approval pending`.
- Have the gate's `request-review` comment name the words it accepts, so the first
  reply can be the one that locks.
