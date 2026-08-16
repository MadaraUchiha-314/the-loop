---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#243"
status: approved             # draft | in-review | approved
approvedBy: ["@MadaraUchiha-314"]  # issue #243 states the wanted behaviour; PR carries the chain
collaborators: [engineer]
overrides: {}
---

# Requirements: a forwarded event carries the instruction, not GitHub's metadata

> Phase 1 of 3 (requirements → design → tasks). This phase MUST be reviewed and approved
> before the design is derived from it.

## Introduction

Every event the-loop forwards into a session carries a 4,000-character JSON excerpt of
GitHub's raw payload. Almost none of it is the message. Measured on a realistic
`issue_comment` webhook for a 61-character instruction
([`evidence/baseline.md`](evidence/baseline.md)):

| Part of the delivered prompt | Chars | Share |
|---|---:|---:|
| The instruction itself (`comment.body`) | 61 | 0.9% |
| The rest of the payload excerpt — two copies of a `user` object, 18 API URLs each, `reactions`, `labels`, the whole `issue` object | 3,953 | 59.2% |
| the-loop's own constant text (template shell + interaction directive) | 2,290 | 34.3% |
| Graph context (this item's live process state) | 372 | 5.6% |

The excerpt is capped at 4,000 characters, and this ordinary comment **hits the cap** —
the JSON is chopped mid-string inside `issue.user.gists_url`, so what the session receives
is not even parseable JSON (`json.loads` fails with *Invalid control character at char
4000*). A comment needs its **body** and its **URL**; the URL already
names the issue or pull request it lives on. Everything else in the excerpt is either
metadata the agent never reads or a duplicate of something the prompt header already
states.

The same is true of PR reviews and review-thread comments, which is where the cost bites
hardest: [issue-246](../issue-246/bugfix.md) had to emit the inline anchor **before** the
body precisely because the cap could otherwise swallow it.

Ticket: [#243](https://github.com/MadaraUchiha-314/the-loop/issues/243). The ticket's
second half — whether the-loop's constant per-event text (34.6% above) should move into a
system prompt instead — is a **question**, answered as an analysis with a recommendation
in [`design.md` § The constant text](design.md#the-constant-text-the-tickets-second-question);
it changes no behaviour here, and R6 states the deliverable.

## Requirements

### Requirement 1 — a comment arrives as its body and its address

**User story:** As the session working a work item, I want a forwarded comment to be the
comment, so that the instruction is not buried in — or truncated by — GitHub's metadata.

#### Acceptance criteria (EARS)

1. WHEN an `issue_comment` event is rendered into a prompt THEN the payload excerpt SHALL
   carry the comment's `body`, its `html_url` and its author's login, and SHALL carry no
   other field of the comment object.
2. WHEN an `issue_comment` event is rendered THEN the excerpt SHALL NOT carry the `issue`
   object, the `sender` object, the `repository` object, or any API (`api.github.com`) URL.
3. WHEN a `pull_request_review_comment` event is rendered THEN the excerpt SHALL carry
   `path` and `line` **before** `body`, followed by `html_url` and the author's login.
4. WHEN a `pull_request_review` event is rendered THEN the excerpt SHALL carry the
   review's `state`, `body`, `html_url` and the author's login, and nothing else.
5. WHILE the excerpt is rendered for any event the author's login SHALL be a bare login
   string, never GitHub's `user` object.

### Requirement 2 — every other routed event keeps what makes it actionable

**User story:** As the session, I want a non-comment event distilled rather than dropped,
so that a closed issue, a merged PR or a red check still tells me what happened and where
to look.

#### Acceptance criteria (EARS)

1. WHEN an `issues` or `pull_request` event is rendered THEN the excerpt SHALL carry the
   entity's `number`, `title`, `state`, `html_url`, plus `merged` and `draft` for a pull
   request, and no other field.
2. WHEN the action is `labeled` or `unlabeled` THEN the excerpt SHALL carry the label's
   `name` — the label is the event.
3. WHEN a `workflow_run`, `check_run` or `check_suite` event is rendered THEN the excerpt
   SHALL carry the run's identity (`name` where the object has one), its `status`,
   its `conclusion`, its `html_url` where present and its `head_branch`, so the session
   can diagnose without a second lookup.
4. WHEN a `check_run` carries `output.title`/`output.summary` THEN the excerpt SHALL carry
   both, capped as free text (R3.1) — that summary is the failure message.
5. WHEN a `status` event is rendered THEN the excerpt SHALL carry `state`, `context`,
   `description` and `target_url`.
6. IF an event names no rule of its own — an operator added it to `routing.events` — THEN
   the excerpt SHALL distil whichever known containers the payload carries, and SHALL
   never fall back to the raw payload.
7. IF distillation yields nothing at all THEN the excerpt SHALL render `{}` and the
   prompt SHALL be delivered unchanged in every other respect: a shape the-loop does not
   recognise costs context, never delivery.

### Requirement 3 — truncation takes prose, never the address

**User story:** As the session, I want a 50 KB pasted log in a comment to cost me the tail
of that log and nothing else, so that the comment's URL, its anchor and the-loop's own
rules are always intact.

#### Acceptance criteria (EARS)

1. WHEN a free-text field (`body`, `description`, `summary`) exceeds the per-field text cap
   THEN that field alone SHALL be truncated, with a visible marker inside the field's
   value.
2. WHILE any field is truncated the rendered excerpt SHALL remain **parseable JSON**.
3. WHEN a comment's body is truncated THEN its `html_url` — and, for a review-thread
   comment, its `path` and `line` — SHALL still be present in the excerpt.

### Requirement 4 — both ingresses distil identically

**User story:** As an operator running the poller rather than the webhook receiver, I want
the same lean prompt, so that the two ingresses stay the parity pair issue-246 made them.

#### Acceptance criteria (EARS)

1. WHEN the poller synthesises a comment, review or review-comment event THEN its rendered
   excerpt SHALL contain the same fields as the webhook event for the same object.
2. WHEN either ingress renders a prompt THEN it SHALL use one distillation function —
   there SHALL be no second, ingress-specific excerpt path.

### Requirement 5 — nothing that *acts* on the payload changes

**User story:** As the operator, I want this to be a prompt-rendering change only, so that
routing, authorization, control keywords, reactions and workspace preparation behave
exactly as they did.

#### Acceptance criteria (EARS)

1. WHEN an event is dispatched THEN routing, authorization (`is_authorized`,
   `is_self_authored`), control-command parsing, reaction targeting and head-ref
   resolution SHALL continue to read `RoutedEvent.payload` — the full payload — and SHALL
   be unaffected by what the excerpt omits.
2. WHEN a prompt template declares `$payload_excerpt` THEN it SHALL keep working
   unchanged: the placeholder's name, position and UNTRUSTED framing are a contract with
   operator-authored templates and SHALL NOT change.

### Requirement 6 — the second question is answered, not silently decided

**User story:** As the ticket's author, I want the "can the constant text live in the
system prompt?" question answered with pros and cons, so that I can decide rather than
discover a decision.

#### Acceptance criteria (EARS)

1. WHEN this work item completes THEN `design.md` SHALL carry a section presenting the
   options for the constant per-event text with pros, cons, measured cost and a
   recommendation.
2. WHILE that question is unanswered by a human the loop SHALL NOT weaken the invariant
   that every rendered prompt states where the session takes its answers from
   ([decision-051](../../decisions/decision-051.md)) — the analysis is posted on the
   ticket for the owner's decision.

## Non-functional requirements

- **Cost.** The distilled excerpt for the measured `issue_comment` baseline is ≤ 400
  characters (from 4,014), and the whole rendered prompt drops below 3,100 characters
  (from 6,676). These are recorded as measurements in the evidence, not as gates.
- **Observability.** Nothing new is logged. The excerpt is prompt text; the event log
  already records what was delivered.
- **No new dependency.** Standard library only (`json`), per `reference/minimalism.md`.

## Security considerations

> Threat-model-lite. This change **narrows** an untrusted ingress rather than widening
> one, which is stated below rather than implied.

- **Actors & trust:** anyone who can comment on, review, or open an issue or pull request
  in a monitored repository is an untrusted actor. GitHub's webhook payload and the
  poller's `gh` reads are the untrusted inputs. The trusted side is the prompt an agent
  acts on.
- **Trust boundaries & data:** the excerpt is the crossing point — attacker-controlled
  text entering a prompt. This change **reduces** the crossing: the fields carried drop
  from "every key of four container objects" to a fixed, named list per container. Two
  attacker-controlled surfaces are removed outright — the `sender`/`user` objects (whose
  `avatar_url`, `html_url` and `*_url` values contain attacker-chosen login text repeated
  18 times) and the whole `issue` object (title and body, i.e. a second injection surface
  that arrives with every comment on the item). No secret, token or credential appears in
  any carried field; none appeared before either.
- **Abuse cases (EARS):**
  1. WHEN a comment body contains text shaped like the excerpt's own JSON — a forged
     `"html_url"`, a fake `"the-loop process state"` block — THEN the excerpt SHALL keep
     it inside the `body` string's JSON escaping, so it renders as data and not as a
     sibling field.
  2. WHEN a comment body is large enough to crowd out the prompt THEN the per-field cap
     SHALL bound it, and the comment's `html_url` SHALL survive that truncation.
  3. WHEN a hostile actor sets a field the distiller does not carry — a crafted
     `performed_via_github_app`, an injected `user.name` — THEN that field SHALL NOT reach
     the prompt at all.
  4. WHEN a payload arrives with a missing or wrong-typed container THEN distillation
     SHALL yield `{}` for it rather than raising, so a malformed payload cannot stop
     delivery of an event that already passed the routing and authorization gates.
- **Fail closed / fail safe:** the authorization decisions are made **before** rendering,
  on the full payload (R5.1), and are untouched here. The renderer itself fails *safe* on
  purpose: an unrecognised shape costs the session context, never the event. Failing
  closed at this point — refusing to render — would drop an event a human authorized,
  which is the worse outcome and is the same choice `payload_excerpt` made before.

## Out of scope

- Changing the interaction directive, the template shell or the graph-context block
  (R6 answers the question; any change waits for the owner's decision).
- Compressing `RoutedEvent.payload` itself, or what the event log records. The full
  payload is what the gates read (R5.1).
- The `$payload_excerpt` placeholder's name, or the templates' UNTRUSTED framing.
- Jira. The ticket mentions it; the-loop has no Jira ingress today, so there is nothing to
  distil there. When one lands it uses the same function or it repeats this bug.

## Open questions

None outstanding for R1–R5. R6 is itself the open question, and is posted on the ticket
with its analysis rather than being answered here.

## Review comments

*None yet.*
