---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#242"
phase: tasks-breakdown       # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the-loop diagnoses its own failures and files the bug itself

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner filing [#242](https://github.com/MadaraUchiha-314/the-loop/issues/242) and starting this cloud session on it. The ticket is unusually complete — it states the trigger case (#240), the opt-in default, the redaction MUST, the never-arm rule and the label — so `brainstorming` is skipped (the idea is not fuzzy); `design-critic-review` not selected (no critic configured in this repository). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-16 | pending — PR for this branch | `requirements.md`: six requirements; the two security-critical ones (redaction, never-armed) written in formal register. |
| design | 2026-08-16 | pending — PR for this branch | Reuse-first: `critics.run_critic` for the isolated agent, `comments.py`'s contract for the `gh` writer, `excerpt.py`'s allow-list argument for redaction. Six alternatives recorded as rejected. Risk tier 4 (schema touched). |
| test-planning | 2026-08-16 | pending — PR for this branch | 13 rows, 6 in scope; every `n/a` carries a reason; one manual activity (a human reads the dry-run output for redaction quality). |
| tasks-breakdown | 2026-08-16 | | 12 tasks, two independent red roots. |
| implementation | 2026-08-16 | | TDD: the red run captured and committed before the code. |
| verification | 2026-08-16 | | Every applicable activity ran, including a REAL agent dry run (T11 upgraded past its plan — see the progress entry). |
| needs-review | 2026-08-16 | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| this branch's PR | The whole work item — the spec chain and the feature. | pending |

## Progress entries

### 2026-08-16 — mapped the seams before designing

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the #240 trace as the archetype (`dispatch.failed` ×3 →
  `poll.comment_failed`, `will_retry: false`, and a human reconstructing the story from
  `events.jsonl` by hand), then mapped the code: the event log is the one central sink;
  `critics.run_critic` already is "one agent, one process, one envelope, no shell";
  nothing anywhere creates a GitHub issue today; nothing applies
  `routing.autoExecuteLabel` programmatically; and there is no redaction utility in
  code — only the `excerpt.py` allow-list precedent and prose obligations.
- **Found, and it decided the design:** #240-style defects do **not** surface as
  uncaught exceptions — the poll loop and the dispatch worker both swallow-and-continue
  by design. Detection therefore had to be a *policy over event-log records*
  (error-level + terminal give-ups), not an except-hook. That single fact shaped D2.
- **Also decided:** `parse_command` matches control keywords anywhere in a body
  (whole-token `re.search`), so agent prose mentioning `the-loop start` must be
  mechanically defanged, not just avoided (R6.2).

### 2026-08-16 — red first, then one choke point

- **Phase:** implementation
- **Did:** wrote the 49 guarding tests first and captured their failure as
  [`evidence/red.md`](evidence/red.md); then `redact.py`, `core/selfdiagnosis.py`, the
  `diagnose` command, the two daemon wiring points, the `selfDiagnosis` schema section
  (both copies), the dogfood config block, the event types, the state-layout entry and
  the docs pages.
- **Two findings from the self-review rounds, both fixed:**
  1. `eventlog.emit(event, ...)` collides with a field named `event` — the
     `diagnosis.*` records carry the triggering event type as `trigger` instead.
  2. The `diagnose` verb emitted into an unconfigured event log, so a posted issue
     would have left no `diagnosis.posted` trail — it now calls
     `configure_from_file("diagnose")` like every other emitting command.
  A third suspicion — the scan lock failing on a missing state root — was checked and
  dismissed: `RunLock.acquire` creates parent directories itself.
- **Checkpoint/tests:** 2274 passed, 1 skipped; `make lint`, `make format-check`,
  `make typecheck` clean. Evidence in [`evidence/`](evidence/).

### 2026-08-16 — the verification ran a real agent, deliberately

- **Phase:** verification
- **Did:** T11 was planned as "dry-run, human-read". The environment had a real
  `claude` binary, so the run was upgraded to the strongest available form: a seeded
  event log carrying the #240 trace **plus planted sensitive values** (a fake
  `GH_TOKEN`, a private-repo work item ref, absolute paths), fed through the *real*
  default agent path — synthetic critic, `claude -p` one-shot in a temp dir — with
  `--dry-run` so nothing posted. The printed report was then read for redaction
  quality: no planted value survived. Output in
  [`evidence/dry-run.md`](evidence/dry-run.md).

## Deviations from the standard gates

- **`phase-selection` was answered by direct instruction, not by the checklist
  comment.** This work started from the owner's cloud-session request on the ticket
  rather than from `the-loop start`, so no checklist was posted and no
  `the-loop execute` reply exists. The owner's filed ticket is the authorization; the
  spec chain exists in full rather than being skipped.
- **The artifacts are `in-review`, not `approved`.** Nothing here has been through a
  human gate yet; the pull request carries the whole chain for review in one place. No
  phase claims an approval it does not have.
- **Risk tier 4 without a pre-implementation spec approval.** `autonomy.tiers["4"]` is
  `human-approves-pr`, so the gate this work needs is the PR itself — but
  `security.review.humanSignOffMinTier: 4` also applies: the PR briefing explicitly
  requests a named human security sign-off on the redaction and never-arm contracts.
- **No `loop:<phase>` label on #242 from the harness** — the known #73 gap: a cloud
  session has no daemon. The phase state is this file.

## Capability docs

- **New:** [`docs/capabilities/self-diagnosis.md`](../../capabilities/self-diagnosis.md)
  — the capability's current-behaviour contract, indexed in
  [`capabilities.md`](../../capabilities/capabilities.md). Minted product-feature
  shaped: the behaviour is one coherent surface (detect → diagnose → redact → file),
  not a slice of an existing doc.
- **Decision:** [`decision-090`](../../decisions/decision-090.md), indexed in
  `decisions.md`.

## Documentation

- `docs/config/cli/self-diagnosis-options.md` — the `selfDiagnosis` block, every key
  with Type and Default (P3–P5 gated).
- `docs/cli/commands/diagnose.md` — the verb (P1/P2 gated), plus both vitepress nav
  lists and the `docs/config/cli/index.md` page table.
- `docs/cli/state.md` — the self-diagnosis ledger: classification row, its own
  section, and the `.gitignore` recipe line (mirrored into this repo's `.gitignore`,
  as the S4 parity test requires).
- **README:** unchanged, with reason — its CLI section is a deliberate highlights
  list, not a command reference; an opt-in diagnostic verb belongs in the full
  reference the section already links to.
- **Skill/reference docs:** unchanged, with reason — `reference/observability.md`
  points at the `EVENT_TYPES` catalog rather than duplicating it, and the new
  `diagnosis.*` types are registered there; no prose in the skill describes a surface
  this change altered.
