# Collaboration reference

How the-loop works with humans and other personas. The governing rule: **every decision
or opinion taken from a human MUST have a paper trail** on the ticketing system or the
PR.

## Paper-trail rules

- **Planning questions/opinions/decisions** → asked and recorded as **comments in the
  ticketing system** (GitHub issue / Jira), not resolved silently in files.
- **PR reviews** → happen **on the PR** as comments and replies.
- **Self & critic reviews** → also as PR/ticket comments.
- **Notifications/escalations** when a human action is pending → driven by the
  `notifications.events` filters in `harness-config.yaml` (event → roles), with
  recipients resolved by role from `.the-loop/collaborators.yaml` and delivered on each
  recipient's enabled channels (issue-82, decision-035). Notification only; the
  decision itself still lands as a comment.

## Where questions go, and where artifacts are iterated (issue-134)

Two rules. The first is configurable, because only the operator knows where they are.
The second is not, because it is a property of the artifact.

### 1. The interaction channel is declared, not guessed

A session driven by the CLI daemon is **told** where its answers come from, via
`routing.interaction.mode` in the operator's `cli-config.yaml`
(rendered into every event/spawn prompt as `$interaction_directive` —
`reference/automation.md`):

- **`work-item` (default)** — do not assume a human is watching this terminal. Every
  question, clarification, decision or approval is asked as a **comment on the work item
  or its PR** (marked as the-loop's own, per the loop-prevention rule below), and the
  session then **stops and waits**: the reply reaches it as the next event. Never block
  on an interactive prompt, and never read silence as consent — if genuinely blocked, log
  the conflict, escalate once, and move to the next available work.
- **`cli`** — a human is attached to this session's terminal, so ask there. This does not
  waive the paper trail: the **outcome** of every human decision still lands on the work
  item as a comment.

When no daemon is involved (a human ran `/the-loop:work-on` themselves), the human is by
definition at the terminal — that is `cli` behaviour, with the same paper-trail obligation.

### 2. RULE: a generated artifact is iterated on a durable, reviewable surface

Once an artifact of the chain exists — `brainstorm.md`, `requirements.md`/`bugfix.md`,
`design.md`, `testing-plan.md`, `tasks.md` — iteration on it happens **only** through
comments on a surface that outlives the session: the **pull request** that carries it, or
the **ticket**. In both interaction modes. What is never permitted is iterating on it
interactively, where the reasoning vanishes with the scrollback — that is the invariant,
and it is not configurable (decision-051 §5, amended by decision-069).

Which of the two durable surfaces applies is **this work item's own choice**, made by its
author at `phase-selection` (issue-183) — and it applies to the **outer** loop only:

| The `outer-loop-on-pull-request` box | Outer loop's artifacts are iterated | Typical work item |
|---|---|---|
| unticked — **the default** | as comments on the work item, Jira-style | work whose code lands in *other* repositories, so a PR in the origin repo would only ever hold a discussion |
| ticked | as review comments on the PR carrying them, in the repository the ticket was created in | single-repo work, where that PR also carries the code |

- Commit and push the artifact either way, and link the checked-in file from the ticket;
  never paste its contents into a comment. The choice is where it is **discussed**,
  not whether it is checked in — every gate in the process graph reads files.
- It is deliberately **not** a setting in `harness-config.yaml` or `cli-config.yaml`: it
  is a property of the work item, and it is frozen by the same signed reply that freezes
  the phase selection.
- This is the *reference, don't duplicate* rule (`SKILL.md`) reaching its conclusion: the
  artifact is a checked-in file, and the file, the discussion and the approval belong in
  one place.
- The **inner** loop has no surface to choose. A pull request's `pdlc-pr-loop` is iterated
  on that pull request — review comments, review threads, its own approval.
- Planning questions asked *before* any artifact exists still follow rule 1.

See `docs/decisions/decision-051.md` for why the mode is a two-value enum, and
`docs/decisions/decision-069.md` for why the artifact rule now names two surfaces rather
than one.

## RULE: mark every comment/reply as the-loop's own (loop prevention)

The webhook/poller trigger paths react to their own repo's activity, but the harness
posts comments/reviews/replies under **your own credentials** (no separate bot token —
decision-023's operating model), so by author alone the-loop's own reply is
indistinguishable from something you typed. Left unmarked, it would re-enter the loop
as new input on the next poll/webhook cycle, resuming the session that just wrote it —
which may reply again, forever.

GitHub (and every ticketing system the-loop targets) attaches no queryable custom
metadata to a comment or review — the body text is the only channel available. So:

- **Every comment, PR review, and reply the-loop posts** (issue comments, PR
  conversation comments, PR review comments/replies, review submissions — anywhere
  this session writes a reply, not just review findings) **MUST end with two things**,
  appended after a blank line:
  1. The exact, invisible marker `<!-- the-loop:agent-comment -->` — an HTML comment,
     so it never clutters the rendered thread. This exact string is what
     `the_loop.authz.is_self_authored` matches on; do not paraphrase or omit it, and
     do not use it verbatim in a comment that is **not** the-loop's own.
  2. A short, **visible** attribution line so a human reading the thread also knows —
     reuse the round's `[<harness>/<model>]` prefix (`reviewing.md`) where one already
     applies; a plain `🤖 _the-loop, autonomous reply_` otherwise.
- This applies everywhere GitHub-style credentials post on your behalf — issues, PRs,
  and (once supported) Jira or any other ticketing system — not only GitHub.
- **It applies to both producers, not just this session.** The CLI daemon posts
  comments of its own (today: the interactive-session announcement,
  `the_loop.announce`) with the same credentials, so they carry the marker too — via
  `the_loop.authz.mark_self_authored`, the producer-side counterpart of
  `is_self_authored`. Any new daemon-side comment MUST go through that helper; an
  unmarked one is re-ingested on the next cycle and pasted into the session it was
  about (issue-104).
- **Only ever mark text the-loop composed.** `mark_self_authored` asserts authorship
  and the trigger paths silently drop whatever carries the marker — never apply it to
  payload-derived text or another author's words.
- **Do not rely on this for anything else.** It identifies authorship for loop
  prevention; it is not an authorization mechanism and does not replace the
  authorized-actor guard (`security.md`).

See `docs/decisions/decision-031.md` and `cli/the_loop/authz.py` for the CLI-side
enforcement (both the webhook router and the poller drop a marker-carrying event before
dispatch, regardless of who technically posted it) — the same module now holds the
marking helper, so what the-loop writes and what it recognises cannot drift apart.

## Conflicts & assumptions (keep unattended runs moving)

`docs/decisions/` captures *deliberate* decisions; unattended runs also hit **ambiguities
and conflicts** mid-flight (a missing field, contested ownership, an unexpected tool
failure, an assumption the agent had to make). Those must neither block the loop nor
vanish. Rule:

- **Resolvable with a reasonable default → assume and continue.** Record the assumption in
  the append-only conflict log and keep going; do not stall the whole run on one
  low-stakes ambiguity.
- **Genuinely blocked → log, escalate once, move on.** Record the conflict, escalate once
  via the paper trail (ticket/PR comment + a `conflict-escalated` notification), and proceed to the next
  available work rather than spinning.

The log is `docs/decisions/conflicts.md` (append-only). Each entry is one line:
**timestamp · phase · one-liner · status** (`assumed` / `escalated` / `resolved`). It
gives the human a precise, reviewable trail of every judgment call the agent made on their
behalf.

## Personas, roles and groups

- The full list of available collaborators is defined up-front in the repo, in
  **`.the-loop/collaborators.yaml`** — the SINGLE source of truth for people and their
  notification config, validated against `.the-loop/collaborators.schema.json`
  (issue-82, decision-035; the former `config.personas`/`config.messaging` keys are
  retired). CODEOWNERS-like: these are the stewards of the repository.
- A collaborator may be an **individual** or a **group** (e.g. a GitHub team
  `@org/team`). A single user may hold **multiple roles**.
- Supported roles: `product-manager`, `architect`, `designer`, `engineer`, `qa`,
  `reviewer`, `approver`.
- Each collaborator declares their **notification channels** — the primary way the
  harness notifies them that an action is pending (never where decisions land). Per
  user: `notifications.enabled`. Per channel: `enabled`, a `type` (only `slack` for
  now), `via` (how to interact with the channel — `mcp`/`cli`/`api`, the same
  primitives as `externalTools.kind`), and channel-specific `config` (slack:
  `channel-list`). Which events notify which roles is the harness config's
  `notifications.events`.
- The CLI daemon never reads this file (decision-032): the operator declares their own
  recipients, in the same collaborator structure, in `cli-config.yaml` — see
  `reference/automation.md`.

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

For **UI/UX work**, the `designer` reviews the **UI/UX design artifacts** produced in the
design phase (Figma links / self-contained HTML prototypes under `docs/specs/<id>/design/`)
— iterating on the *rendered* output until locked, with every opinion recorded as a ticket
comment (paper trail). See `reference/design-artifacts.md`.

## User-interaction principles (reviewing AI-authored work)

The human often did not write the code and their familiarity with the codebase keeps
dropping, so how the-loop communicates is a first-class concern. Driven by
`config.userInteraction`.

- **Give enough context to decide.** Whenever user input is requested (a planning
  question, a design opinion, a review), include enough context that the user can make
  the right judgement call without digging.
- **Condensed, prioritized PR summaries.** Every PR the-loop raises tells the reviewer
  **where to focus and in what order** — reviewing a huge AI-authored PR top-to-bottom
  is not realistic. Lead with the highest-priority items to scrutinize. This briefing is
  produced from the-loop's internal
  `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/pr-briefing.md` and **posted/updated in the PR
  BEFORE human review is requested** — a required item of the ready-to-ship gate
  (`userInteraction.prSummary.required`), so it triggers on every PR (see
  `workflow.md`).
- **RULE: all diagrams are mermaid.** PR summaries, design docs and educational snippets
  use mermaid diagrams to explain low-level details (`diagramFormat: mermaid`).
- **Document insights & decisions in the PR description.** Capture the insights from
  taking the spec to implementation and every low-level decision the harness had to make,
  so the user sees the reasoning, not just the diff.
- **RULE: educate the user (mandatory, not optional).** As the user's familiarity with
  the code drops, use every opportunity to teach them the low-level design decisions.
  This is intentional and required (`educateUser: true`), not a nicety. **Enforcement:**
  it is not left to chance — the reviewer briefing is a required item of the ready-to-ship
  gate (`workflow.md`), so "request human review" cannot happen without the education
  step having fired.

## Working with other tools (MCP / CLIs / plugins)

the-loop is allowed to freely interact with the MCP tools, skills and plugins available
in the harness. The user declares which ones to be aware of in `config.externalTools`
(the `externalTools.tools` list + `notes` in `.the-loop/config.yaml`). Examples:
Jira via MCP, GitHub via `gh`, plugins such as ponytail or superpowers. Always check
this registry before assuming a capability is or isn't available.
