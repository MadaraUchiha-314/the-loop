# CLAUDE.md — working in the-loop's own repository

**This repository *is* `the-loop`, and it dogfoods its own PDLC.** the-loop is a
product-development-lifecycle harness (shipped as a Claude Code / Cursor plugin). When you
work in *this* repo you are both **building** the harness and expected to **use** it: build
the-loop *through* the-loop.

## Why this file exists

the-loop's operating rules normally reach an agent through the plugin's **SessionStart
hook** (`hooks/hooks.json`) or, in Cursor, the always-applied rule (`rules/the-loop.mdc`).
Those only fire when the-loop is **installed as a plugin in a consuming project** — they do
**not** fire in the-loop's *own* sessions, because a fresh Claude Code **cloud / web**
checkout doesn't self-install the plugin. This `CLAUDE.md` is the in-repo equivalent: it is
auto-loaded in every session here and carries the same reminder, so cloud/web sessions run
the loop instead of shipping plain one-off PRs. (This is the gap
[issue #73](https://github.com/MadaraUchiha-314/the-loop/issues/73) surfaced — the phase
labels sit unused precisely because past work bypassed the loop.)

## What to do

1. **Read the operating model first.** [`.the-loop/harness-config.yaml`](.the-loop/harness-config.yaml)
   (this project's config) and the bundled skill
   [`skills/the-loop/SKILL.md`](skills/the-loop/SKILL.md) are the source of truth for how
   work is done here; [`skills/the-loop/reference/workflow.md`](skills/the-loop/reference/workflow.md)
   has the phase-by-phase detail. Follow them — don't re-derive the process.
2. **Every change is a work item with a ticket.** Nothing is worked without a GitHub issue.
   Create and lock the Kiro 3-phase spec (`requirements → design → tasks`) under
   `docs/specs/<id>/` before writing code, **scaling rigor to the change** per
   `config.autonomy` tiers: a trivial (tier 1–2) change is autonomous-complete and needs no
   full spec; a tier 3+ change does. When unsure which, follow the skill.
3. **Keep the phase label in sync.** Apply and advance the `loop:<phase>` label on the
   ticket at every transition (`loop:not-started → … → loop:complete`), mirrored in
   `docs/specs/<id>/execution-log.md`. Using the loop is what keeps these labels populated
   (see [`docs/reports/labels-and-dashboards.md`](docs/reports/labels-and-dashboards.md)).
4. **Follow the skill's remaining rules, don't restate them here:** self/critic-review
   before escalating, a paper trail for every human decision, and updating the affected
   capability docs (`docs/capabilities/`) in the same PR as the change. See
   [`skills/the-loop/SKILL.md`](skills/the-loop/SKILL.md) and its `reference/`.

**Prime directive: when you build the-loop, run the loop.**
