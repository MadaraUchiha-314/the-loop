# Decision 124: a work item picks its model at the gate; the harness is asked what it can run

- **Status:** proposed
- **Date:** 2026-09-13
- **Work item:** [issue-358](https://github.com/MadaraUchiha-314/the-loop/issues/358)
- **Deciders:** jc1993 (the ask); MadaraUchiha-314 (four rounds of review on
  [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359) — *"label is an insecure
  mechanism"*, *"keep model and effort as 2 separate inputs"*, *"putting it under routing key
  doesn't make any sense"*, *"Let's not tie model to harness"*, *"implement in this same PR"*);
  the-loop (design)
- **Refines:** [decision-067](decision-067.md) (phase selection is answered by an authorized
  comment — this adds two questions to that one reply), [decision-120](decision-120.md) and
  [decision-123](decision-123.md) (nothing is inferred from prose; executable configuration
  lives in the operator's file)
- **Spec:** `docs/specs/issue-358/`

## Context

`routing.harnessArgs.<harness>` was one list applied to every spawn, so the model a session
runs on was a property of the *machine*, not of the work. An operator wanting five of
eighteen work items on a different model had no supported path and typed `/model` into each
tmux pane by hand — invisible to the-loop, unrecorded, lost on the next respawn.

The ticket proposed a label→args map. That is where the first decision had to be made, and
three more followed from it.

## Decision

**1. The choice is a question at `phase-selection`, not a label.** A label rides GitHub's
`triage` permission, not `routing.authorizedUsers`, and the payload does not attribute a
label to a person. Accepting one would let anyone with triage rights choose the argv of an
unattended agent — decision-067's argument, with a command line at the end of it. The model
and effort rows are answered by the same signed `the-loop execute` that already freezes the
phases, the outer-loop surface and `sessionPerPr`.

**2. The declarations are top-level, not `routing`.** `routing` configures how an event
*reaches* a session; `harnesses`, `models` and `effort` configure what a session *is*. They
sit beside `repositories` and `critics`, which are the same kind of fact about a machine.

**3. A model name is the provider's; an effort level is the-loop's.** Opposite answers to
"who owns the name", each for its reason. A model name (`opus-5`, `fable-5.1`, `gpt-5.6-sol`)
is an identifier the-loop neither normalises nor parses for a vendor — it is copied verbatim
into the harness's own model flag. An effort level is a the-loop concept that harnesses spell
differently, so the-loop owns the vocabulary and each adapter translates it. The enum is the
**union** of what the known harnesses express — and the two interesting rows are why:

| the-loop | Claude Code | Codex |
|---|---|---|
| `xhigh` | xhigh *(its default)* | **Extra high** |
| `ultra` | — | Ultra |

`xhigh` is one concept with two spellings, which is the case for normalising at all. `ultra`
is a level only one harness has, which is the case for a union rather than an intersection: it
is offered where it exists and silently absent where it does not. An operator writing a per-harness effort flag is how two
configs come to disagree about what `high` means.

**4. A model is not tied to a harness: the relation is measured.** `models` is a flat list of
names. Which harness can run which name is answered by `the-loop models check`, which asks
each harness and caches the verdict. A `harnesses:` list on a model may **narrow** where it is
offered and probed; only a verdict may confirm one. The whole rule is: *a declaration may
narrow, only the probe may confirm.*

**5. The session is spawned after the gate is answered, not before.** The checklist is posted
by the daemon, not by an agent, so nothing about the gate needs a session. Entering the graph
when the work item is armed and deferring the spawn until the pointer leaves its first human
gate means the first session already carries the frozen model.

## Consequences

**What this buys.** A per-work-item model and effort, set from a phone, needing no config edit
and no daemon restart; surviving every respawn; visible in `the-loop sessions list`; and a
model the harness would refuse never offered in the first place, so a work item cannot die in
a pane nobody is watching.

**What it costs.**

- **A behaviour change for every work item, not only those choosing a model** (point 5): an
  armed work item has no tmux session until its first gate is answered. It is followed with
  `the-loop check` rather than `sessions list`.
- **A probe that runs the harness.** One cheap non-interactive call per declared combination
  per 24 hours, off the delivery path — the first time the-loop runs a harness to *learn*
  something rather than to do work.
- **A second place where argv is assembled**, contained by keeping the merge itself in one
  function both callers use.

**What was deliberately not done.** the-loop does not enumerate what models exist: there is no
stable machine-readable catalogue across harnesses, accounts and CLI versions, and a fetched
list would go stale between the fetch and the spawn. It validates what you declared instead.
Nor does it accept operator-written args on a model, or parse a name for its vendor
(`gpt-*` → OpenAI → cursor) — a guess dressed as a convention, which breaks the first time a
provider renames.

**The open edge.** No adapter the-loop *ships* has an effort mapping yet, because neither
`claude` nor `cursor-agent` exposes a thinking-effort flag on its CLI. Declaring `effort`
therefore offers nothing today, even though the vocabulary is now known to be right: the level
names came from the two harnesses' own pickers, not from a guess. A mapping is added when a
harness exposes one — read from that CLI's `--help`, then probe-validated like any other claim
about a CLI. Codex has the richest set and no adapter at all yet; adding one is an adapter plus
a `_EFFORT_ARGS` table, and this feature then works for it with no further change.
