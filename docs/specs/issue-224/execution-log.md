---
type: execution-log
workItem: issue-224
phase: needs-review
status: in-progress
---

# Execution Log: the learnings tree is a configured location, and it defaults into `docs/`

> Append-only log for issue-224. Ticket:
> [#224](https://github.com/MadaraUchiha-314/the-loop/issues/224).

## How this session ran the loop

One cloud session, one pass, no human at the other end — the same posture as
issue-208/209/211/217/220/222, with the same two consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started by the ticket
   itself; there was nobody to tick the checklist. Phases assumed: the full spec chain,
   implementation, verification, self-review. `brainstorming` was not taken (the ticket
   states the problem and the answer in two bullets) and neither was the opt-in
   `design-critic-review` — no second model was available to this session.
2. **The chain was authored before the code, but approved by nobody.** The artifacts are a
   proposal to ratify, not a locked chain; `status: draft` on all four says so. Risk tier
   **3** means this PR needs a human approval before it is complete, and — being below
   `security.review.humanSignOffMinTier` (4) — no separate named security sign-off. See
   `requirements.md` §Risk tier.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-14 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-14 | | [`requirements.md`](requirements.md) — 5 requirements, 5 NFRs, 3 abuse cases, risk tier **3** (two `sensitivePaths` files edited; no runtime code) |
| design | 2026-08-14 | | [`design.md`](design.md) — two design questions, thirteen touched files, no new code |
| test-planning | 2026-08-14 | | [`testing-plan.md`](testing-plan.md) — 11 rows in scope, 7 `n/a` with reasons |
| tasks-breakdown | 2026-08-14 | | [`tasks.md`](tasks.md) — 11 tasks |
| implementation | 2026-08-14 | | 11 tasks; one schema property, three config files, one `git mv`, nine documents |
| verification | 2026-08-14 | | Testing plan executed in full: 1965 passed + 1 skipped (unchanged from `main`), lint/format/types/markdownlint/config validation clean, docs site builds |
| needs-review | 2026-08-14 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-224-e96t9p` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-14 — orientation

Read the ticket, `CLAUDE.md`, the harness config, the skill and the issue-222 chain for
conventions, then inventoried what actually hardcodes the path. Six files carry the
literal `learnings/` as a *rule* (the skill, `reference/automation.md`, three commands, the
manifest); the rest of the ~40 matches are prose, historical records or the files
themselves. Two facts shaped the work:

- **There is no runtime to change.** `reference/automation.md` says the learnings lifecycle
  is implemented by the skill and that the CLI "can harden it later". Nothing under
  `cli/the_loop/` reads or writes the tree, and `harness_config.READS` — the CLI's complete,
  test-pinned read surface — has no entry for it. So this work item is a schema property, a
  default stated in three places, a `git mv`, and the documents that name the path.
- **The interesting decisions are not in the diff.** Which config block the key belongs to,
  and what happens to a project that already has `learnings/`, both had an obvious answer
  worth checking. Both are argued in `design.md` and recorded as
  [decision-082](../../decisions/decision-082.md).

### 2026-08-14 — the two decisions

**`workflow.learningsDir`, not `selfImprovement.learningsDir`.** `selfImprovement` holds
every other learnings knob, which is the argument for putting it there. Against it: the
question an operator is answering is a *layout* question they answer once for all three
knowledge trees, and `x-onboarding` puts `workflow` in the `confirm` group (shown, values
proposed) while `selfImprovement` sits in `advanced` (silent defaults, walked only on the
full tour). A key that decides where a project's documents live cannot be in the group
most adopters never see. `capabilitiesDir` is the precedent: it is no more a "workflow"
concept than learnings are, and it lives under `workflow` because that is where this schema
puts directory locations.

**Nothing relocates an existing tree on its own.** `manifest.deprecated` was the tempting
mechanism and is the wrong one — `/the-loop:upgrade-the-loop` *deletes* those paths, and
every entry there says so in its own `reason` ("SAFE TO DELETE, not a migration"). Learnings
are the operator's data. So the upgrade command gained a paragraph that presents both
outcomes (move the tree, or pin `workflow.learningsDir: learnings`) and takes neither
without confirmation. A runtime "use `learnings/` if it exists" fallback was rejected for
the reason issue-123 already taught this repository: one question with two answers,
resolved by whichever directory happens to exist.

### 2026-08-14 — building it

Order: schema first (everything else states its default), then the three configs, then the
move, then the documents that name the path. Two things came out of doing it rather than
planning it:

1. **The move puts the learnings inside the VitePress `srcDir`.** They had been outside
   `docs/` and therefore outside the site entirely; after the move they build as pages —
   unlisted, reachable only by URL. Leaving that would have been the worst of both: public
   but unfindable. They are now wired into the site's *authored* IA the way the decision log
   is — a `Learnings` group in the developer sidebar, an entry under the `Developer` nav
   menu, and `/learnings/` mapped to that sidebar. The site was built to confirm it.
2. **Publishing is now a consequence worth disclosing.** A project that publishes `docs/`
   publishes its learnings with it. That is the right default for a tree whose purpose is
   to be read by a human, and the key is the escape hatch — so the schema description, the
   automation reference and `docs/config/harness-config.md` each say it at the point an
   operator chooses.

### 2026-08-14 — verification

Every activity in the testing plan ran; results and commands are in
[`evidence/verification.md`](evidence/verification.md). Full suite 1965 passed + 1 skipped
— identical to the pre-change baseline — plus `make lint format-check typecheck validate`,
markdownlint over 637 files, the schema's own `check_schema`, a validation of the config
with `learningsDir` removed and again pinned to `learnings`, the rename check, the
reference sweep, and a docs-site build.

The sweep's surviving matches for the old path are all intended and are accounted for
individually in the evidence: prose that must name the old location to describe the move,
the historical record (`decision-012`, and `docs/specs/**` excluded for the same reason),
and the new path matching the pattern.

### 2026-08-14 — self-review

Three rounds, findings fixed in place rather than deferred:

1. **Round 1 — the site.** Caught the unlisted-pages consequence above; fixed by wiring the
   nav/sidebar and re-running the build. Also caught that `commands/init.md`'s YAML
   `description` still advertised scaffolding a root-level `learnings/`.
2. **Round 2 — the plan against what ran.** The testing plan predicted `make validate`
   against a modified copy for T9 and an "(empty) result" for T8's sweep; neither matched
   what was actually done. The plan is completed *as the record*, so the rows were corrected
   to the commands that ran rather than the evidence being written to match the plan.
3. **Round 3 — the scope of the key.** Confirmed the git-ignored write-gate queue
   (`.the-loop/learnings-pending/`) is deliberately **not** moved or configurable: it is
   harness scratch state, not checked-in knowledge, and it belongs beside the config for
   the same reason. Stated explicitly in `design.md` and in the schema description so the
   omission reads as a decision rather than an oversight.

No round produced a repeated finding, so nothing escalated.

## Capability docs

[`docs/capabilities/spec-workflow.md`](../../capabilities/spec-workflow.md) — the doc that
owns the `workflow.*` directory keys. Current behaviour gained a bullet making all three
knowledge directories project-placed (with the publishing caveat and the pending-queue
carve-out), the spec-dir bullet now names `<workflow.specDir>` instead of a literal, and a
history row records issue-224. No other capability doc describes the learnings tree.

## Documentation

- `docs/config/harness-config.md` — the `workflow` row names `learningsDir`; the
  `selfImprovement` row points at it and carries the published-`docs/` caveat.
- `docs/guide/how-it-works.md` — the repository-layout tree shows `docs/learnings/`, and a
  new sentence names the three project-placed directories.
- `docs/architecture/architecture.md` — §Knowledge & feedback follows the move.
- `docs/.vitepress/config.mts` — the authored nav/sidebar entries described above.
- `skills/the-loop/SKILL.md` and `skills/the-loop/reference/automation.md` — the published
  artifact names `<learningsDir>` and states the key and its default once.
- `commands/init.md`, `work-on.md`, `execute-tasks.md`, `upgrade-the-loop.md` — scaffold
  and write against the configured directory; the upgrade command gained the relocation
  paragraph.
- `README.md` needed no change: it does not describe the learnings tree.
