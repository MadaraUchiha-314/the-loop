# Decision 086: the event excerpt is a field allow-list, and the constant text stays put — for now

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-243](https://github.com/MadaraUchiha-314/the-loop/issues/243)
- **Deciders:** maintainer (via ticket); harness (proposal)

## Context

Everything the-loop forwards into a session ends as one rendered prompt, and the part of it
that describes *what happened* was a subset of GitHub's raw payload: nine container keys,
copied whole, JSON-dumped, cut at 4,000 characters.

Measured on an ordinary `issue_comment` webhook
([`evidence/baseline.md`](../specs/issue-243/evidence/baseline.md)), a 61-character
instruction arrived inside a 4,014-character excerpt — 0.9% signal — and the cut landed
mid-string inside `issue.user.gists_url`, so the delivered "JSON" did not parse. Two
`user` objects with eighteen API URLs each, two `reactions` blocks, the label objects and
the whole `issue` body travelled with every comment on that item.

The ticket asks two things: strip the metadata, and say whether the-loop's *own* constant
per-event text (another 2,290 characters) should move into a system prompt instead.

## Decision

1. **The excerpt is a field allow-list per container, not a payload subset.** Each
   container the-loop carries (`comment`, `review`, `issue`, `pull_request`, `label`,
   `workflow_run`, `check_run`, `check_suite`) names the fields it contributes, in
   emission order, and everything else is dropped. A deny-list of noisy keys was rejected:
   GitHub adds fields to these objects routinely, so a deny-list silently re-inflates
   while an allow-list does not move.
2. **A comment is its body and its address.** An `issue_comment` carries `body`,
   `html_url` and the author's login — not the `issue` object, whose identity the
   comment's own URL already contains, and not the `sender`. An inline comment keeps
   `path`/`line` **before** the body (issue-246's rule, now structural rather than
   incidental); a review keeps its `state`.
3. **Free text is capped per field, before the dump.** The rendered excerpt stays
   parseable JSON no matter how long a body is, and a cap can no longer take a URL, an
   anchor, or the document's structure. The whole-excerpt limit is enforced by shortening
   prose (halving the text budget until it fits), not by cutting the document in half.
4. **An unknown shape costs context, never a delivery.** An event with no rule distils
   whichever containers it carries; a payload with nothing recognisable renders `{}`; a
   wrong-typed container contributes nothing rather than raising. By the time the excerpt
   is rendered the event has already passed routing and authorization, so failing *closed*
   here would drop an instruction a human authorized — the wrong trade.
5. **The excerpt is prompt text and nothing else.** Routing, authorization, the
   self-comment marker check, control-keyword parsing, reaction targeting and head-ref
   resolution keep reading the full `RoutedEvent.payload`. Asserted by test, not by
   convention.
6. **The `$payload_excerpt` placeholder, its position and its UNTRUSTED framing do not
   change.** They are a contract with operator-authored templates.
7. **The constant per-event text stays where it is, and the question is escalated rather
   than answered.** Four options were analysed
   ([`design.md` § The constant text](../specs/issue-243/design.md#the-constant-text-the-tickets-second-question)):
   status quo; a harness system prompt; stating it once at spawn; and a two-line
   restatement per event with the full text at spawn. The last is recommended and is
   **not** implemented here, because it weakens a stated invariant — decision-051: *every*
   rendered prompt says where the session takes its answers from — which is the owner's to
   relax. The system-prompt option is not recommended at all: `HarnessAdapter` has no
   system-prompt channel, only one adapter implements interactive sessions at all, a
   system prompt cannot follow a `Dispatcher.reload`, and it is invisible in the tmux
   scrollback a human debugs from.

## Consequences

- **Measured:** the excerpt for the baseline event drops 4,014 → 203 characters and the
  whole prompt 6,676 → 2,865 (−57%), and the excerpt parses for the first time
  ([`evidence/after.md`](../specs/issue-243/evidence/after.md)).
- **The trust boundary narrows.** Two attacker-controlled surfaces stop reaching an
  agent's prompt entirely — the `sender`/`user` objects and the `issue` object that
  travelled with every comment — and what remains is a fixed, named, individually capped
  few.
- **A field the-loop stopped carrying is one a session must fetch.** Every carried object
  keeps its `html_url`, so the cost is one lookup, and the failure mode is a session
  asking rather than acting wrongly. Adding a field back is a one-line table edit.
- **The tables are now the thing to review.** What a session learns about an event is
  legible in two dicts instead of implied by what GitHub happens to send.
- **The bigger remaining share of the prompt is the-loop's own text**, and that is stated
  in the evidence rather than left to be rediscovered — with the options costed for
  whoever decides.

Spec: [docs/specs/issue-243/](../specs/issue-243/requirements.md)
