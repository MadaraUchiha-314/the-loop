# Learning 008: A marker in a comment body is a claim, not an identity

- **Date:** 2026-10-15
- **Source:** system-feedback (self-review and critic review)
- **Work item:** issue-488

## What happened

The quiz gates' design treated "the comment carries the-loop's self-marker and the quiz
marker" as proof that the-loop wrote the comment. Review found three ways that was not
enough:

- **S1.** Anyone who can comment can copy both markers. A look-alike could force the
  spec quiz back to the explainer on demand, or hide the real tick.
- **S8.** Jira's format silently dropped the marker, so the gate never found its own
  comment and re-posted it on every event.
- **C1.** The GraphQL edit history names who edited a comment, never what each edit
  changed. So "the latest editor is authorized" did not prove that person made the tick.

Each fix had to ground the claim in something the service attests:

- the comment's **author** (the-loop posts as the operator, who is authorized);
- Jira's `isSelf`, meaning the service account wrote it;
- **every** editor in the history.

## Learning

A marker in text is a loop-prevention device, and it does only that job well: it stops
the-loop from treating its own words as a human's. It is not an authentication
mechanism. When a gate's decision depends on *who wrote* or *who changed* something,
read that from a field the platform itself attests (author, account id, edit history),
and check what that field does **not** say. Then check the marker's spelling survives
every format it passes through.

## Action

- The quiz gates now require authorship and a fully authorized edit history
  (`cli/the_loop/graph/hooks/quiz.py`), and use a colon-shaped marker Jira keeps.
- When reviewing a new gate, ask: "which of its inputs could a non-authorized commenter
  write?", and "does every marker it relies on survive the Jira round trip?"
