---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#358"
status: draft
approvedBy: []
overrides: {}
riskTier: 4
---

# Design: per-work-item model and effort choice, answered at the phase-selection gate

> Phase 2 of 3 (requirements → design → tasks). Derives from
> [`requirements.md`](requirements.md). MUST be reviewed and approved before moving to tasks
> breakdown.
>
> **Revision 4** — the spawn-order change is now **in scope as R8** (§ *Spawning after the
> gate, not before*), on the owner's "implement in this same PR". Revision 3 moved the
> declarations out of `routing` into three top-level sections
> (`harnesses`, `models`, `effort`), `models` became a flat list whose rows name a harness, and
> **effort is normalized by the-loop** rather than described per harness by the operator — all
> three from the owner's second round of review on PR #359. Revision 2 split model from effort
> and added the availability requirement (R7); revision 1 was the label-to-args map's
> replacement. Still **presented for approval with the requirements**, and still nothing
> implemented: no authorized `the-loop execute` reaches a cloud session, so neither gate can be
> answered here.

## Overview

**Two independent questions — which model, and how much effort — are added to the
phase-selection checklist, resolved against two closed sets the operator declared, frozen by
the same signed reply, and read at spawn time by the dispatcher exactly as `sessionPerPr`
already is.**

The change reuses three mechanisms and adds one:

| Existing mechanism | What it already does | What this work item adds |
|---|---|---|
| `phase-selection` ([selection.py](../../../cli/the_loop/graph/hooks/selection.py)) | asks three per-work-item questions, freezes the answers on one authorized reply | a `model-*` section and an independent `effort-*` section |
| the frozen record (`control_store.frozen_graph`) | carries `surface` and `sessionPerPr` | carries `model` and `effort` |
| `_tmux_for` ([dispatcher.py](../../../cli/the_loop/webhook/dispatcher.py)) | overrides one operator default per work item | `_adapter_for` overrides `harnessArgs` the same way |
| — | — | **availability**: a cached verdict per declared choice, so a model the harness refuses is never offered (R7) |

The declarations are two per-harness lists in the operator's CLI config. They are the answer
to the owner's first question — the-loop discovers nothing; it validates what it is told.

```mermaid
flowchart LR
  subgraph operator["operator's machine — trusted"]
    cfg["cli-config.yaml<br/>harnesses[] · models[] · effort[]"]
    ad["harness adapter<br/>model_flag · effort_args(level)"]
    probe["availability cache<br/>(harness, id) → ok · refused · unknown"]
  end
  subgraph ticket["the work item — untrusted text"]
    chk["phase-selection checklist<br/>model-fable · model-opus<br/>effort-high · effort-low"]
    rep["authorized reply:<br/>the-loop execute"]
  end
  subgraph state["portable state"]
    frozen["frozen record<br/>surface · sessionPerPr<br/>model · effort"]
  end
  subgraph daemon["dispatcher"]
    res["_adapter_for()"]
    tmux["tmux + harness argv"]
    reg["session record<br/>model · effort · harnessArgs"]
  end
  cfg --> ad
  ad -->|"the argv for a normalized level"| res
  cfg --> probe
  cfg -->|"renders the rows"| chk
  probe -->|"withholds a refused row"| chk
  chk -->|"tick state at reply time"| rep
  rep -->|"two tokens, each matched against its declared set"| frozen
  cfg -->|"the argv itself"| res
  probe -->|"veto"| res
  frozen -->|"which entries"| res
  res --> tmux
  res --> reg
```

Read the arrows into `_adapter_for` together: the work item chooses **which declared
entries**, the cache may **veto** one, and the operator's config supplies **the argv**. No
string from a comment is ever part of a command line.

## Spawning after the gate, not before (R8)

**In scope, on the owner's instruction** ("implement in this same PR"). Today
`dispatcher._spawn_tmux` spawns the tmux session and *then* calls `graphlink.on_spawn`, which
enters the graph — whose start node is `phase-selection`, whose entry hook posts the checklist.
So a harness session exists, and has been told to wait, before anyone has said what the work
item should do.

The current order is deliberate, and its reason is in the code
([dispatcher.py:2466](../../../cli/the_loop/webhook/dispatcher.py)): *"a failed spawn must not
leave a labelled ticket pointing at a node nobody stands on."* That was sound when the graph was
entered nowhere else. It is load-bearing in one other way too: the arming comment rides into the
first gate (issue-199), which is how `the-loop contribute` carries its goal.

What makes the reorder possible is one fact: **the checklist is posted by the daemon, not by the
agent.** `selection.py` posts it through the CLI's own github integration
(`_resolve(ctx).call("post-comment")`). Nothing about phase selection needs a harness session.

```mermaid
flowchart TB
  subgraph today["today"]
    a1["authorized start"] --> a2["prepare workspace"] --> a3["spawn tmux + harness"] --> a4["on_spawn: enter graph"] --> a5["post checklist"] --> a6["session waits at the gate,<br/>already on the default model"]
  end
  subgraph proposed["proposed — R8"]
    b1["authorized start"] --> b2["prepare workspace"] --> b3["on_arm: enter graph"] --> b4["post checklist"] --> b5["NO spawn — pointer parked"] --> b6["authorized execute<br/>freezes the selection"] --> b7["spawn tmux + harness<br/>on the chosen model"]
  end
```

**One correction to what I claimed before folding this in.** The reorder saves the **harness
session**, not the checkout: `graphlink._guarded` verifies the checkout belongs to the work item
and the pointer is written to `graph-state.json` **under the checkout's spec directory**, so the
workspace must be prepared before the graph can be entered at all. That is no regression — the
checkout already happens before the checklist today — but "no checkout is spent" was wrong and is
struck. What is saved is a tmux session plus a harness process, per work item, for as long as the
gate goes unanswered.

### What changes

`graphlink.on_spawn` does two things today — *enter the graph* and *bind the session*. They
separate:

| Seam | When | What it does |
|---|---|---|
| `graphlink.on_arm(work_item, cwd, routed)` | after the workspace is prepared, before any spawn | `rt.start()`, evaluate a **start node that is a human gate** with the arming event attached (issue-199, unchanged), report whether the pointer is parked there |
| `graphlink.on_spawn(work_item, cwd, session_id, runner)` | after a session exists | `_bind_session` only — the re-bind a respawn already needs |

`_spawn_for` gains one early return: when `on_arm` reports the pointer parked at a
daemon-serviced start gate, it emits `session.spawn_deferred` and returns **without** spawning.
The work item is then visible in `the-loop check` (waiting at that node) and in the checklist
comment on the ticket; it has no session, which is the point.

**When the gate is answered**, the `execute` comment is routed as it is today, the gate freezes
the selection and the pointer advances — and because the work item now has no session, the
ordinary "no session for this work item" path spawns one, resolving the model through
`_adapter_for` from the record that was just frozen. The first spawn is therefore already on the
chosen model, and the drift re-launch (R4.3) becomes a safety net that no ordinary path
exercises.

### The narrow rule, and why it cannot strand a work item

A spawn is deferred **only** while both hold: the pointer has never advanced past the graph's
start node, **and** that start node is a human gate (`_entered_a_human_gate`, the predicate
`on_spawn` already uses). Everything else spawns exactly as today:

- a **mid-graph** work item — any pointer that has moved — always spawns and respawns;
- a **crashed** session on a mid-graph item respawns, because deferral cannot apply to it;
- graph linkage disabled (`routing.graph.enabled: false`), no spec-id convention, a foreign
  checkout, a spec dir outside the checkout — every existing `_guarded` skip path means `on_arm`
  reports nothing parked, so the spawn happens as it does now;
- an **inner (per-PR) loop**, whose start node is not a human gate, is untouched.

The original rationale survives: a pointer parked on `phase-selection` is standing on a node the
**daemon itself** services, so there is no labelled ticket pointing at a node nobody stands on.

### What it costs

The blast radius is the honest cost, and it is why I had proposed splitting this out: the arming
path, `on_spawn`'s idempotency contract, the issue-199 comment hand-off, the announce and
conversation-open side effects (announce moves with the spawn, conversations stay at arm time),
and every existing test that assumes a session exists once a work item is armed. The behaviour
change is also user-visible: an armed work item no longer has a tmux session until its gate is
answered, so `sessions list` shows nothing for it and `the-loop check` is where it is followed.
That is the line to document loudest.
**The safety net (R4.3).** The dispatcher compares the session record's recorded arguments with
the currently resolved ones and, on a difference, re-launches the session — resuming its
conversation — instead of delivering into it. With R8 in place no ordinary path reaches it: the
first spawn already carries the frozen choice. It still earns its keep for a choice changed after
the gate (an operator re-freezing, a declaration withdrawn, a verdict turning `refused`) and for
every session launched before this change, which carries no recorded arguments at all.

## Architecture

### Where each piece lives

| Component | File | Status |
|---|---|---|
| the vocabulary: declared models and efforts, resolution, merge | `cli/the_loop/modelchoice.py` | new |
| the availability probe and its cache | `cli/the_loop/modelprobe.py` | new |
| `the-loop models check` / `models list` | `cli/the_loop/commands/models_cmd.py` | new |
| the adapter's model and effort flags, asked by name | `cli/the_loop/harness/__init__.py`, `harness/base.py` | extended |
| an adapter copy carrying different args | `cli/the_loop/harness/base.py` | extended |
| the two checklist sections, the parse, the frozen keys | `cli/the_loop/graph/hooks/selection.py` | extended |
| seeding the hook's config | `cli/the_loop/graph/bootstrap.py` | extended |
| resolution at spawn / respawn / drift, and the deferred spawn (R8) | `cli/the_loop/webhook/dispatcher.py` | extended |
| the `on_arm` / `on_spawn` split (R8) | `cli/the_loop/graphlink.py` | extended |
| the three recorded fields | `cli/the_loop/sessions/registry.py` | extended |
| the `Model` column | `cli/the_loop/commands/sessions_cmd.py` | extended |
| the verdict report | `cli/the_loop/commands/diagnose_cmd.py` | extended |
| the JSON contract | `cli/the_loop/api/routes.py`, `docs/api-specs/openapi/the-loop.v1.yaml` | extended |
| the declarations' schema | `cli/the_loop/schemas/cli-config.schema.json` | extended |

`modelchoice.py` exists for the reason `prsessions.py` exists: its two readers cannot see each
other. The selection hook cannot import the dispatcher — `dispatcher → graphlink → graph` makes
that a cycle — and a second copy of the resolution rule is how the checklist and the daemon
come to disagree about what `fable` means. It imports no ingress and no graph; it asks
`the_loop.harness` for a flag by name (verified cycle-free: `the_loop.harness` pulls only
stdlib, `trust` and `harness_plugins`) and otherwise reads mappings.

`modelprobe.py` is separate because it is the only part that **runs a process**. Keeping the
pure resolution rules out of reach of a subprocess call is what lets every rule above be unit
tested without a harness installed.

### The life of one choice

```mermaid
sequenceDiagram
  participant H as authorized human
  participant G as phase-selection gate
  participant P as availability cache
  participant S as portable state
  participant D as dispatcher
  participant T as tmux session

  G->>P: which declared choices are offerable?
  P-->>G: fable ok · opus ok · o1-mini refused
  G->>H: checklist — two sections, refused rows withheld
  H->>G: ticks `model-fable` and `effort-high`, replies `the-loop execute`
  G->>G: authorize · parse each section · match against its declared set
  G->>S: freeze {phases, surface, sessionPerPr, model: "fable", effort: "high"}
  G->>H: confirmation — "this item will run on fable, at high effort"
  D->>S: read the frozen record
  D->>P: still offerable?
  D->>T: spawn (or re-launch, resuming) with harnessArgs + fable + high
  D->>S: record model, effort and effective args on the session
```

## Components & interfaces

### `modelchoice.py` — the vocabulary

```python
@dataclass(frozen=True)
class DeclaredChoice:
    """One pickable model or effort level, exactly as the operator declared it."""
    id: str                 # the token the checklist renders and a reply names
    kind: str               # "model" | "effort"
    harness: str            # which harness it is declared under
    args: Tuple[str, ...]   # resolved argv: the entry's own, else (flag, id)
    about: str = ""         # one line rendered beside the row

def declared_choices(cli_config: Mapping, harness: str, kind: str) -> List[DeclaredChoice]: ...
def resolve_choice(token: str, declared: Sequence[DeclaredChoice]) -> Optional[DeclaredChoice]: ...
def effective_args(base: Sequence[str], *chosen: Optional[DeclaredChoice]) -> List[str]: ...
```

- One type for both kinds, with `kind` on it, because they differ in exactly one rule — where
  `args` comes from: a **model** row resolves through `adapter.model_flag`, an **effort** level
  through `adapter.effort_args(level)`. Neither is ever read from the operator's file for a
  harness the-loop adapts. Two near-identical types would be two places to fix the next bug in.
- `declared_choices` is **fail-closed in the shrinking direction**, the rule `repos.py` already
  follows: a malformed entry contributes nothing, so a fault can only remove a choice — it can
  never invent one.
- `resolve_choice` matches on `id`, exactly, case-sensitively, and takes the declared list as an
  argument rather than re-reading config, so every caller is provably resolving against the same
  set it rendered.
- `effective_args` is `list(base) + …` in argument order and nothing else (R3.1, R3.2). Variadic
  so the call site reads `effective_args(base, model, effort)` and a `None` contributes nothing.

### `harnesses`, `models`, `effort` — three top-level sections

**Not under `routing`, and not nested.** `routing` answers *how an event reaches a session*.
Which harnesses this instance has, and what they can be asked to run, is a property of **the
machine's installed tooling** — the same kind of fact as `repositories` (this instance's scope)
and `critics[]` (this instance's harness+model combos). So three top-level keys, beside those:

```yaml
# ── top level, beside `repositories` and `critics` ──────────────────────────────
harnesses:                       # NEW — the harnesses this instance has
  - name: claude
    default: true                # the one an unmatched event spawns
    args: ["--dangerously-skip-permissions"]   # this harness's launch args
  - name: cursor

models:                          # NEW — a flat list; each row names its harness,
  - harness: claude              #   exactly the shape `critics[]` already uses
    id: opus
    about: the default for anything with real design in it
  - harness: claude
    id: fable
    about: fast and cheap — good for small, well-specified items
  - harness: cursor
    id: gpt-5.5

effort:                          # NEW — the-loop's OWN normalized vocabulary
  - low                          #   the levels this instance offers, drawn from
  - medium                       #   the loop's fixed enum. NO flags here: the
  - high                         #   mapping to each harness is the ADAPTER's job.
```

**`models` is a flat list whose rows name a harness**, which is the correction to revision 2's
nested map. My objection to a harness-independent list was that the-loop would have to
*attribute* an id to a harness — a guess. A `harness:` field removes the guess without nesting
anything: the operator states the association in the row, `critics[]` has worked exactly this
way since issue-108, and `the-loop models list` can print one table.

**`effort` is normalized by the-loop, not described by the operator.** Revision 2 had the
operator hand-writing `["--thinking-effort", "high"]`, which is worse than nesting: it makes
every operator restate a flag per harness, and it lets two configs disagree about what "high"
means. So the vocabulary is **fixed and the-loop's** — `low | medium | high`, one enum, the same
three words whatever harness runs — and the translation is the adapter's:

```python
class HarnessAdapter:
    #: This harness's own way of asking for more or less thinking. Empty tuple for a
    #: level this harness cannot express, and for a harness with no effort control at
    #: all — never a guess, and never the operator's problem.
    def effort_args(self, level: str) -> Tuple[str, ...]: ...
```

One consequence, stated plainly because it is the thing to check: **the per-harness mapping
table is the one fact this design cannot settle from the-loop's own codebase.** No adapter has
an effort flag today, and a spec must not invent one. So the table is filled in at implementation
from each harness CLI's own `--help`, every mapping is validated by the availability probe (R7 —
the same probe that validates a model, for the same reason), and a level a harness cannot express
is simply **not offered for that harness**. `the-loop models check` prints which levels each
harness actually supports. That is the honest version of "the-loop normalizes this": one
vocabulary for the human, per-harness truth underneath, and nothing asserted that has not been
probed.

**Where `harnesses[].args` leaves `routing`.** The merge in R3.1 is onto this harness's launch
args, which live in `routing.harnessArgs.<harness>` today. `harnesses[].args` is their new home:
read from there when present, from `routing.harnessArgs` otherwise with a deprecation warning —
the warn-never-fail shim this repository already used when `routing.runner` was removed
(issue-156) and when the repository list left `polling.sources[].repos` (issue-348). The other
three per-harness keys — `routing.harnessTrust`, `routing.harnessPlugins` and
`routing.defaultHarness` — belong in `harnesses[]` by exactly the same argument, and folding them
in is a **follow-up work item**, not this one: it is a breaking config migration with its own
tests, and `harnesses[].default` is included here only because `models[]` needs to know which
harness a work item will run on.

A **model** row resolves to `[<adapter.model_flag>, <id>]`. An explicit `args` on a model row is
accepted **only** when the named harness has no `model_flag` — a harness the-loop adapts is
normalized, never hand-written — and validation rejects it otherwise, so there is exactly one way
to do the ordinary thing.

### `modelprobe.py` — availability (R7)

The mechanism that answers *"what if the harness does not have that model?"*: **do not offer
it, and never spawn on it.**

```python
@dataclass(frozen=True)
class Verdict:
    harness: str
    kind: str
    id: str
    args_digest: str        # the declaration probed — a changed declaration invalidates
    verdict: str            # "ok" | "refused" | "unknown"
    checked_at: str

def probe(choice: DeclaredChoice, adapter: HarnessAdapter) -> Verdict: ...
def offerable(choice: DeclaredChoice, cache: VerdictCache) -> bool: ...
```

- **What it probes.** Every declared **model** row, and every **effort** level against every
  declared harness — the effort mapping is the-loop's own assertion about a harness CLI, so it is
  exactly the kind of claim that must be checked rather than trusted.
- **How it probes.** `adapter.oneshot_argv(PROBE_PROMPT, …)` plus the choice's resolved args — the
  harness's own cheapest non-interactive invocation, the same surface critics already use. The
  prompt is a fixed the-loop constant; **no text from a work item is ever sent** (the
  requirements' egress rule). A non-zero exit or an error envelope is `refused`; a binary that
  is not on PATH, or a run that could not start, is `unknown`.
- **When it probes.** `the-loop models check` (explicitly), at daemon start, and on the single
  stale-verdict path of R7.5 — never inline in a delivery. A verdict's lifetime is bounded
  (proposed 24h, open question 2) and any change to the declaration's args invalidates it
  through `args_digest`.
- **What `unknown` means.** Offerable. An operator on a machine with no harness binary, or no
  network at probe time, must not lose a capability they declared (R7.6).
- **Where it is stored.** The machine-local state beside the session registry, never the
  portable tree: a verdict is a fact about *this machine's* harness installation, and it must
  not travel in a repository or be writable by an agent session.
- **The one loop it closes.** A choice cached `refused` that still reaches resolution — a
  frozen record older than the verdict, or a hand-edited one — spawns on `harnessArgs`
  unchanged, posts one comment naming the refused choice and what ran instead, and is not
  retried until its verdict changes (R7.4). That is what stops the failure mode the owner
  named: a work item dying in a pane nobody is watching, forever.

### `selection.py` — the sections, the parse, the freeze

Four changes, each mirroring what `pr-sessions-*` does today:

1. **Tokens.** `MODEL_TOKENS = {f"model-{c.id}": c.id}` and `EFFORT_TOKENS = {f"effort-{c.id}":
   c.id}`, both added to `_NON_PHASE_TOKENS` so such a row is never read as a phase skip and
   never as a refusal.
2. **Rendering.** Two sections, each rendered only when its list has offerable entries (R1.7),
   each capped at `CANDIDATE_LIMIT` with an "…and N more" line (R2.7). "Leave it alone" is
   described in each section's prose rather than given a row, so there is nothing to tick for
   the default.
3. **Parse.** `_parse_choice(body, tokens) -> str`, called **once per section**: exactly one
   ticked row is a choice; zero, several, an unknown token, or an unreadable body is `""`
   (R1.5). Per-section resolution is what keeps an ambiguous model from discarding a valid
   effort.
4. **Freeze and confirm.** `_frozen_graph` gains `"model"` and `"effort"`, and the confirmation
   comment names both outcomes in both directions (R1.6).

`""` is the right literal for "no choice", and it is deliberately *not* the id of a default
entry: the frozen record then says "this item chose nothing", which is what makes a later change
to the operator's default apply to it.

### `dispatcher.py` — resolution, and the bridge

```python
def _adapter_for(self, work_item: WorkItemRef, harness: str) -> Optional[HarnessAdapter]:
    """The operator's adapter with THIS work item's own model and effort applied."""
```

The body is `_tmux_for`'s, two fields over: read `control_store.frozen_graph(work_item)`, take
`model` and `effort`, resolve each against its declared set, drop any whose cached verdict is
`refused`, and return `adapter.with_args(effective_args(adapter.extra_args, model, effort))` —
or the adapter itself when there is no choice, so the no-choice path allocates nothing and
behaves identically to today (R6.1). Every failure returns the adapter unchanged and logs once
(R4.5).

`HarnessAdapter.with_args(args)` returns a shallow copy sharing `trust` and `plugins`. A method
rather than a `replace()` at each call site, so an adapter subclass can never be rebuilt with
half its configuration.

Three call sites switch from `self.adapters.get(...)` to `self._adapter_for(...)`: `_spawn_for`,
`_spawn_endpoint` and `_respawn_tmux` — the whole of R4.1 and R4.2, because a respawn already
re-derives everything else from the record rather than from the dead session.

**The bridge** (R4.3) sits at the top of the deliver-into-a-live-session path: if the session
record's `harnessArgs` differ from the resolved ones, the delivery becomes a respawn (resume)
instead of a paste, and emits `session.choice_changed` with both values (R4.4). It compares
*recorded* against *resolved*, never against the config, so a session launched before this
change (no recorded args) is left alone until something else respawns it.

### The session record

```json
{
  "harness": "claude",
  "harnessSessionId": "…",
  "model": "fable",
  "effort": "high",
  "harnessArgs": ["--dangerously-skip-permissions", "--model", "fable", "<the adapter's args for high>"]
}
```

All three keys are **omitted when empty**, so every record written before this change
round-trips byte-identically and parses unchanged (R5.4) — the rule `pullRequests` already
follows. `the-loop sessions list` gains a `Model` column showing `-` when absent (R5.2), and the
fields appear in the JSON form, the control-plane API response and the OpenAPI contract (R5.3),
which this repository regenerates its API documentation from.

## UI/UX design

N/A — no product UI. The three human surfaces are text: the two checklist sections rendered by
`selection.py`, the `Model` column in `sessions list`, and the verdict table in
`the-loop models check` / `diagnose`. Each is specified above in the form it is read in.

## Data models

| Where | Key | Type | Default | Validated by |
|---|---|---|---|---|
| `cli-config.yaml` | `harnesses[]` (top level) | `{name, default?, args?}` | absent → inferred from `routing.defaultHarness` | `cli-config.schema.json` + `scripts/validate_config.py` |
| `cli-config.yaml` | `models[]` (top level) | `{harness, id, about?, args?}` | absent | as above; `args` only for a harness with no `model_flag` |
| `cli-config.yaml` | `effort[]` (top level) | `enum[]` — `low` \| `medium` \| `high` | absent | as above; no flags, the adapter maps each level |
| portable frozen record | `model`, `effort` | string | `""` | re-validated on read against the declared set |
| machine-local state | availability cache | `Verdict[]` | empty | re-validated against the declared set on read |
| session record | `model`, `effort` | string | omitted | — |
| session record | `harnessArgs` | string[] | omitted | — |

Schema constraints worth stating because they are the guard, not decoration: `id` matches
`^[A-Za-z0-9][A-Za-z0-9._:-]*$` (so an id can never be a flag, a path or a shell fragment), ids
are unique within a harness **and within a kind**, and `args` is an array of strings with **no
placeholder substitution of any kind** — unlike `critics[].args`, nothing here is templated, so
there is no `{…}` to expand.

## Error handling

| Situation | Behaviour | Surfaced as |
|---|---|---|
| a model row with `args` on a harness that has a model flag, or neither | config validation fails, naming the row | `validate_config.py` / `diagnose`, at startup — never at spawn (R2.5) |
| an effort level a harness cannot express | not offered for that harness | `models check` names the level as unsupported there (R2.6) |
| a `models[]` row naming a harness that is not declared | the row contributes nothing, named at validation | `validate_config.py` / `diagnose` |
| `harnessArgs.<harness>` already carries the same flag | validation warns, naming both | as above (R3.4) |
| a declared choice the harness refuses | not offered; if resolved anyway, spawn on `harnessArgs` + one comment naming it | `models check`, the checklist's absence, the comment (R7.3, R7.4) |
| the harness cannot be probed at all | `unknown` — offered, never blocking | `models check` / `diagnose` report it as unprobed (R7.6) |
| a section with several ticked rows | no choice for that section | named in the gate's confirmation comment (R1.5) |
| a reply naming an undeclared token | no choice for that section | debug log; the token never reaches argv (R2.3) |
| frozen record unreadable, or names an id no longer declared | the operator's arguments unchanged | one `warning`, same shape as `_tmux_for`'s (R4.5) |
| a session dead with a non-default choice and nothing to resume | re-probe that choice once, then respawn | `models check` cache update + the R7.4 comment if it is now refused |
| the checklist comment cannot be read at execute time | the operator's arguments unchanged | existing warning path, unchanged |

Every row resolves to *the operator's configuration unchanged*. There is no failure mode in
which the-loop runs a session on a model nobody declared, and none in which it retries a
refused one indefinitely.

## Security design

- **AuthN/AuthZ:** none added. Both rows are authorized by the reply that carries the execute
  keyword — `routing.authorizedUsers`, the same boundary the phase skips, the surface and
  `sessionPerPr` already answer to, with the-loop's own self-marked comments dropped before
  authorization is considered.
- **Input validation & injection surfaces:** the one untrusted ingress is the checklist body. It
  is matched by `_CHECK_LINE` — an existing regex whose token grammar admits no whitespace,
  quotes or metacharacters — and each token is then used as a **key into the operator's declared
  list**. What reaches argv is `DeclaredChoice.args`, built from `cli-config.yaml`. Command
  injection is therefore not mitigated but *absent*: there is no data path from comment text to
  a command line. Nothing is run through a shell (tmux and the probe are both exec'd with an
  argv), and no value is interpolated into a path, a prompt or a ref.
- **The probe's egress:** `modelprobe` is the one component that starts a process and talks to a
  vendor. It sends a fixed the-loop constant as its prompt and the declared args, never any
  repository or work-item text, and it runs off the delivery path. Its cache lives in the
  machine-local tree, so it is not agent-writable and does not travel in a repository.
- **Secrets handling:** none involved. A model id is not a credential, and this work item reads
  and writes no secret, token or environment variable. The probe inherits the daemon's
  environment exactly as a critic run does — it adds no variable of its own.
- **Least privilege:** a choice contributes only the arguments its declaration carries (R3.3).
  the-loop adds no permission flag of its own here, the same promise `harnessArgs` already makes
  and the reason `harnessTrust.acceptBypassPermissions` defaults to following the operator's own
  args rather than widening them.
- **Fail-closed behaviour:** every ambiguity resolves to `routing.harnessArgs.<harness>`
  unchanged — the operator's stated configuration, which is the closed direction here. The
  *narrowest* model would be a different and wrong reading of "closed": it would let a malformed
  reply silently downgrade a tier-5 work item.
- **Abuse-case coverage:**

  | Abuse case (requirements) | Mechanism | Negative test |
  |---|---|---|
  | A1 unauthorized user ticks and executes | existing `_authorized_comments` filter, upstream of any parse | `test_selection.py::unauthorized_reply_freezes_nothing` |
  | A2 reply names a flag / path / metacharacter | token grammar + lookup into the declared set | `test_modelchoice.py::undeclared_token_resolves_to_nothing` |
  | A3 a declared entry widens permissions | applied as declared, and only from the declaration | `test_modelchoice.py::args_come_only_from_config` |
  | A4 hand-edited portable record | re-validated on read against the declared set | `test_dispatcher_choice.py::forged_frozen_choice_is_ignored` |
  | A5 a label named after a model | no label is read anywhere in this path | `test_dispatcher_choice.py::label_does_not_select_a_model` |
  | A6 checklist comment unreadable | existing empty-body path resolves to no choice | `test_selection.py::unreadable_checklist_keeps_the_default` |
  | A7 forged availability verdict | resolution is against the declared set; a verdict can only withhold | `test_modelprobe.py::forged_verdict_cannot_introduce_a_choice` |

## Testing strategy

Unit tests carry the resolution rules (`modelchoice.py`: declaration parsing per kind, unknown
tokens, the `args`-vs-flag fork, the three-part merge order) and the schema validation
(`validate_config.py` rejecting a model row whose harness is undeclared, rejecting `args` on a
model row whose harness *has* a `model_flag`, rejecting an effort level outside the loop's enum,
warning on a duplicated flag and on a deprecated `routing.harnessArgs`). `modelprobe` tests use a stub adapter: `ok`,
`refused`, `unknown`, digest invalidation, and the withhold-not-introduce rule. Selection-hook
tests cover rendering (each section present only when offerable, capped, default in prose),
per-section parsing (one tick, no tick, two ticks, unknown token, an ambiguous model beside a
valid effort) and the two frozen keys. Dispatcher tests cover spawn, respawn, the safety-net re-launch and the
refused-at-resolution fallback with a fake registry and a stub tmux, plus every abuse case above
as a negative test. R8 gets its own set on the `on_arm`/`on_spawn` split: deferral at a
human-gate start node, no deferral for every existing `_guarded` skip path, no deferral once the
pointer has moved, the arming event still reaching the first gate (issue-199), and the announce
side effect moving with the spawn while conversations stay at arm time.

Three integration scenarios carry Gherkin docstrings under `cli/tests/test_*_integration.py`
per `testing.integrationTestGlobs`:

- `Scenario: a work item that chose a model and an effort is respawned on both` — freeze both,
  kill the session, deliver an event, assert the argv the runner was handed.
- `Scenario: an unauthorized reply cannot choose a model` — same setup, unauthorized author,
  assert the frozen record and the argv are untouched.
- `Scenario: a model the harness refuses is never spawned` — cache a `refused` verdict against a
  frozen choice, deliver an event, assert the argv is the operator's own and that one comment
  names the refusal.
- `Scenario: an armed work item gets no session until its gate is answered` — arm an item, assert
  the checklist was posted and no tmux session was created; then answer the gate as an authorized
  user and assert exactly one spawn, carrying the frozen choice (R8.1, R8.2).
- `Scenario: a mid-graph work item still respawns` — advance the pointer past the start node, kill
  the session, deliver an event, assert the respawn happened (R8.3 — the rule that keeps deferral
  from stranding anything).

Evidence: the argv assembled at each spawn (captured from the stubbed runner), the before/after
`sessions list` table, the `models check` verdict table, and the config-validation output for the
three rejected declarations. The executable detail — the full matrix, the verification
environment, the `n/a` rows and their reasons — belongs to `testing-plan.md`, which is not
authored yet because this design is not approved.

## Trade-offs & decisions

**The owner's questions, answered.**

1. *How does the-loop discover all possible models?* **It does not, by design.** No harness
   offers a stable machine-readable list of what a given account may run; the set moves with the
   vendor, the plan and the CLI version, and a list fetched over the network would be an ingress
   this daemon does not need. So the operator declares the few they use — the posture
   `repositories` took in decision-120 and `critics[]` in decision-123 — and the-loop
   **validates** that declaration against the harness (R7) instead of enumerating it. That also
   disposes of the UX half: the list is short because a human curated it, and the checklist caps
   and counts rather than paging.
2. *How does it work for claude vs cursor vs codex?* Through the adapter, which already owns this
   knowledge: `HarnessAdapter.model_flag` is `--model` for Claude Code and `-m` for Cursor, and
   `oneshot_argv(prompt, model)` already uses it for critics. A harness with no adapter, or no
   flag, is served by an entry's explicit `args`; a declaration that is neither is a config error
   rather than a runtime guess. Adding codex later is an adapter plus a `model_flag`, and this
   feature works for it with no further change.
3. *What happens when the chosen model is not available in the harness?* **R7**: probe each
   declared choice with the harness's own cheapest invocation, cache the verdict, withhold a
   `refused` choice from the checklist so a human cannot pick it, fall back visibly if one is
   resolved anyway, and re-probe once on a dead session so a stale `ok` cannot become a respawn
   loop. The failure surfaces at `models check` and `diagnose`, not in an unattended pane.
4. *Per harness or overall?* **One flat `models[]` list whose rows name a harness** — the owner's
   correction, and it is right. My objection was to the-loop having to *attribute* an id to a
   harness; a `harness:` field on the row removes the guess without nesting anything, and
   `critics[]` has had exactly this shape since issue-108. Revision 2's nested map is gone.
5. *Model and effort coupled?* **No — two inputs, two lists, two questions.** Revision 1 coupled
   them into one named argv, which would have made the operator declare the cross product. They
   are now independent all the way through: declaration, checklist section, frozen key, and
   concatenation order.
6. *Who owns the effort vocabulary?* **the-loop.** Revision 2 had the operator writing
   `["--thinking-effort", "high"]` per harness, which is worse than the coupling it replaced: it
   restates a flag in every config and lets two of them disagree about what "high" means. So the
   enum is fixed and the-loop's (`low | medium | high`), the translation is
   `adapter.effort_args(level)`, and a level a harness cannot express is not offered there. The
   per-harness mapping table is the **one fact this design cannot settle from the codebase** — no
   adapter has an effort flag today — so it is read from each harness CLI's own `--help` at
   implementation and validated by the same probe that validates a model. A spec does not invent
   a flag.
7. *Why were these under `routing`?* They should not have been. `routing` answers how an event
   reaches a session; the harnesses an instance has and what they can run is installed-tooling
   configuration, like `repositories` and `critics[]`. Three top-level sections now.
8. *Why does a session exist before the gate is answered?* It should not, and on your
   instruction the fix is **in this work item** (R8, § *Spawning after the gate, not before*): the
   graph is entered when the work item is armed, the spawn is deferred while the pointer is parked
   on a daemon-serviced start gate, and the first spawn therefore already carries the frozen
   choice. One claim of mine is struck in the process — the checkout is still needed at arm time,
   because the pointer lives in it, so what is saved is the tmux session and the harness process,
   not the clone.

**What this costs.**

- **A probe that runs the harness.** One cheap non-interactive call per declared choice per
  verdict lifetime, off the delivery path. It is the first time the-loop runs a harness to learn
  something rather than to do work, and it is why `modelprobe` is a module of its own.
- **A second place where argv is assembled.** `_adapter_for` joins `build_adapters` as a place
  the harness command line is decided. Contained by keeping the merge itself in
  `modelchoice.effective_args`, which both call.
- **Two new config keys**, with a shape a reader can hold in their head, on a file that already
  carries `harnessArgs`, `harnessTrust` and `harnessPlugins`.
- **R8's blast radius.** Deferring the spawn touches the arming path, `on_spawn`'s idempotency,
  the issue-199 comment hand-off, the announce/conversation-open side effects, and every test that
  assumes an armed work item has a session. It is the largest part of this work item and the
  reason it was first proposed as a ticket of its own; the deferral rule is deliberately narrow so
  that nothing mid-graph can be stranded by it.
- **A user-visible behaviour change**: an armed work item has no tmux session until its gate is
  answered, so it appears in `the-loop check` rather than `sessions list`.

**Rejected alternatives.**

| Alternative | Why not |
|---|---|
| `routing.harnessArgsByLabel` (the ticket's proposal) | a label rides GitHub's permission model, not `authorizedUsers`, and the payload does not attribute a label to a person — so it would let anyone with triage rights choose an unattended agent's argv. Same argument as issue-177's, with an argv at the end of it. |
| one coupled model+effort choice (revision 1) | the operator would declare the cross product; the owner's review rejected it, and it would grow multiplicatively. |
| a model list with **no** harness on the row | the-loop would have to attribute each id to a harness — a guess, and guesses are what decision-120 and decision-123 exist to refuse. A `harness:` field on a flat row is not that, and is what revision 3 does. |
| nesting `models` under `harnesses[]`, or under `routing` | the owner's review rejected both: `routing` is about event delivery, and nesting hides the one table an operator wants to read. |
| the operator declaring effort flags per harness (revision 2) | restates a flag in every config and lets two configs disagree about what "high" means. the-loop normalizes instead. |
| enumerating models from the harness or a vendor API | no stable machine-readable source; a network ingress this daemon does not need; and it would go stale between the fetch and the spawn anyway. R7 validates instead. |
| a `the-loop model: <id>` control keyword | works before a session exists, which is attractive — but it is a second surface for a per-work-item decision the gate already collects three of, and the control parser is deliberately argument-free except for `@login` (issue-307). The ordering fix removes the motivation. |
| free-form args in the reply (`the-loop execute --model X`) | comment text into argv. Refused outright. |
| a per-work-item key in the repository's harness config | the harness config is the *agent's* file and a pull request can edit it; decision-123 put executable configuration in the operator's file precisely so it cannot be. |
| changing the running session's model in place | no harness exposes it. |

**Durable decisions to record** (at implementation, as `docs/decisions/decision-124.md`): the
choice is a phase-selection question, not a label; the harnesses, models and effort levels an
instance offers are top-level installed-tooling configuration, not `routing`; a model row names
its harness rather than being nested under one; the effort vocabulary is the-loop's and the
per-harness translation is the adapter's; declarations are validated against the harness rather
than discovered from it; and a choice the harness refuses is withheld from the checklist rather
than failed at spawn.

## Open questions

1. ~~Is the prerequisite ordering ticket wanted?~~ **Answered by the owner: implement it in this
   PR.** R8 and § *Spawning after the gate, not before*.
2. **What lifetime should an availability verdict have?** Proposed 24 hours, plus invalidation on
   a changed declaration, plus the one re-probe of R7.5.
3. **Should the confirmation comment also say the argv?** It names the model and the effort level
   in this design. Naming the arguments would be more honest about what was resolved, and would
   also print `--dangerously-skip-permissions` onto a public ticket. Proposed: the ids only.
4. **Is `low | medium | high` the right effort enum?** Three levels is the smallest useful
   vocabulary and adding a level is easier than removing one. Say if you want `minimal` / `max`
   at the ends.
5. **Does the follow-up that folds `harnessTrust`, `harnessPlugins` and `defaultHarness` into
   `harnesses[]` get raised now?** This work item needs only `name`, `default` and `args`; the
   rest is a breaking config migration with its own tests.

## Review comments

### 2026-09-13 — @MadaraUchiha-314, review of PR #359

| Feedback | Where it landed |
|---|---|
| handle a model the harness does not have | R7 and § `modelprobe.py`; trade-off 3; the refused-at-resolution rows of § Error handling; scenario 3 and abuse case A7 |
| per harness or overall? | § *Per harness, not global*; trade-off 4; R2.2 |
| model and effort are coupled — keep them separate | § *Two lists, not their product*; the two checklist sections; the three-part merge order; trade-off 5 |
| "just models" | `models[]` (+ `effort[]`), and the module renamed `modelchoice.py` |
| why is a session started before phase selection? we ideally shouldn't | § *Spawning after the gate, not before* — agreed, and now **in scope as R8** on the owner's "implement in this same PR" |

### 2026-09-13 — @MadaraUchiha-314, second round on PR #359

| Feedback | Where it landed |
|---|---|
| "separate section for harnesses, a separate section for models, a separate list for efforts" | § *`harnesses`, `models`, `effort` — three top-level sections*; the data-models table |
| "the-loop should take care of normalizing" the effort enums | the enum is the-loop's (`low \| medium \| high`); `adapter.effort_args(level)` translates; a level a harness cannot express is not offered; the mapping table is probed, never invented — trade-off 6 |
| "putting it under routing key doesn't make any sense to me" | agreed — top level, beside `repositories` and `critics`; `routing` is event delivery. `harnesses[].args` is the new home for `routing.harnessArgs.<harness>`, with the warn-never-fail shim issue-156 and issue-348 used; the other three per-harness keys are a named follow-up — trade-off 7 |
| (implicit) the nested per-harness map | replaced by a flat `models[]` whose rows carry `harness:` — the shape `critics[]` already uses; trade-off 4 |
| "implement in this same PR" (the spawn-order change) | **R8** and § *Spawning after the gate, not before*: the `on_arm`/`on_spawn` split, the narrow deferral rule, the struck claim about the checkout, and the blast radius stated as the cost |
