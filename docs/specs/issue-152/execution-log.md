---
type: execution-log
workItem: "issue-152"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: `the-loop install` / `the-loop upgrade`

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 | *pending* | `loop:requirements-definition` applied to [#152](https://github.com/MadaraUchiha-314/the-loop/issues/152); `requirements.md` written (risk tier 3 → `human-approves-pr`). |
| design | 2026-08-05 | *pending* | `design.md` derived: plan-of-steps, probe-don't-assume, two documented fallbacks. |
| tasks-breakdown | 2026-08-05 | *pending* | `tasks.md` DAG, 10 tasks. |
| implementation | 2026-08-05 | — | Tasks 1–10 complete; `make check` green. |
| needs-review | 2026-08-05 | *pending* | PR [#153](https://github.com/MadaraUchiha-314/the-loop/pull/153) opened with the reviewer briefing; the three spec artifacts are locked (`status: approved`, `approvedBy: []`) with human approval requested on the PR. |
| complete |  |  |  |

> **Spec phases were self-driven, not human-gated per phase.** This is a single
> autonomous session: requirements → design → tasks were written and *self*-locked in
> order, each derived from the one before it, and all three are presented for approval
> **together on the PR** (the same shape issue-143/issue-146/issue-148 used). Locked means
> `status: approved` with an empty `approvedBy` — the process graph treats an unlocked
> artifact as a **BLOCK** (agent-fixable, so CI fails on it) and the human approval node as
> a **WAIT** (the normal state of an open PR). Risk tier 3 (`human-approves-pr`) is what
> the gate rests on.

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#153](https://github.com/MadaraUchiha-314/the-loop/pull/153) | Whole work item: spec (tasks 1–10, task 6 descoped), `the_loop.install`, the two commands, tests, docs | open |

## Progress entries

### 2026-08-05 — spec chain written

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the issue and the current install surface (README, `docs/guide/installation.md`,
  `docs/cli/installation.md`, `harness_plugins.py`/`trust.py` from issue-143). Established
  what each harness actually supports by asking the binaries and the docs, rather than
  assuming: `claude plugin marketplace add|update`, `plugin install|update`, `--scope
  user|project|local` are real; Cursor's CLI plugin surface could **not** be verified from
  here, and Cursor documents no project-local plugin directory — recorded as a designed-for
  unknown (probe + documented fallback + honest skip) rather than a guess.
- **Checkpoint/tests:** n/a (artifacts only).
- **Next:** implement the task DAG.

### 2026-08-05 — implementation, and a defect the tests caught first

- **Phase:** implementation
- **Did:** Tasks 1–8. `cli/tests/test_install.py` written **before** `the_loop.install`
  (red: `ImportError: cannot import name 'install'`), then the module, then green.
- **Checkpoint/tests:** first green run was 41 passed / 3 failed, and the three failures
  were a **real defect, not test noise**: `execute()` fell back to `default_env()` when no
  env was passed, so steps planned for a fake machine executed on the real one — the run
  actually installed `the-loopy-one` into the container's system Python and wrote its
  `~/.claude/settings.json`. Fixed by binding each `Step` to the `Env` that planned it
  (`step.run`), which is also the honest invariant: a step is self-contained. The container
  side effects were reverted (`pip uninstall`, the two settings keys removed). 44 + 11
  tests green after the fix.
- **Next:** docs, capability docs, decision record.

### 2026-08-05 — docs, self-review, evidence

- **Phase:** implementation → needs-review
- **Did:** Task 9 (two command pages + sidebar + commands index, both installation guides,
  both READMEs, `docs/capabilities/{cli,distribution}.md` behaviour + history,
  `decision-057`). Self-review found three things, all fixed: (1) an empty configured
  `marketplaceRepo` — meaningful to the daemon, meaningless to an install — errored out
  instead of falling back to the shipped default; (2) an un-migrated CLI config would make
  `assert_current` refuse and block the very upgrade that fixes it, so the config read now
  degrades to `{}` with a warning; (3) the upgrade page did not say that an absent Cursor
  clone is created.
- **Checkpoint/tests:** `make check` → ruff · markdownlint (376 files) · ruff format ·
  pyright (0 errors) · schema validation · **1216 passed, 2 skipped**.
- **Next:** PR + reviewer briefing; await human approval of the three spec artifacts and
  the implementation.

### 2026-08-05 — CI gate: the artifacts had to be locked, not left `in-review`

- **Phase:** needs-review
- **Did:** The `gate` job failed on the-loop's own check —
  `issue-152: UNMET (at requirements-definition) · BLOCK · artifact is not locked —
  front-matter says status: in-review, expected status: approved`. Reproduced locally with
  `the-loop check issue-152 --recompute --fail-on block`. The workflow's own comment states
  the rule: a work item parked at a *human* approval node is a WAIT and does not fail, but
  an unlocked artifact is a BLOCK because it is something the agent can fix. Locked all
  three artifacts (`status: approved`, `approvedBy: []`, each noting that human approval is
  requested on the PR) — the same shape issue-143/issue-146 shipped with — and took the
  chance to correct R5.1, which claimed a stronger idempotence than the implementation
  delivers: the-loop reports `already` only for state it owns, and delegates to the
  harness's own idempotence otherwise (evidenced by the live re-run below).
- **Checkpoint/tests:** `the-loop check issue-152 --recompute --fail-on block` → exit 0
  (`WAIT requirements-approval · no authorized feedback yet`). `make check` re-run green.
- **Next:** await review.

### 2026-08-05 — reviewer asked for the web search; it found a defect

- **Phase:** needs-review
- **Did:** @MadaraUchiha-314 asked on PR #153 whether web search could settle the open
  question about Cursor's CLI surface. It could, further than the first attempt: Cursor's
  own docs and forum are HTTP 403 from this environment (WebFetch *and* curl through the
  proxy), but the indexed sources agree — as of Cursor 2.5 (17 Feb 2026) plugins install
  from the marketplace site or with `/add-plugin` in the editor;
  `cursor-agent plugin marketplace add` is reported to exist, while a forum thread titled
  *"Unable to find a CLI command to install a Cursor plugin after adding its marketplace
  repository"* is the state of the install half.
  That combination is a **defect in the probe**: it accepted a binary whose `plugin
  --help` merely named `marketplace`, so against Cursor the-loop would have run a
  `plugin install` that cannot work and reported `failed` instead of falling back. The
  probe now also requires `plugin install --help` to succeed — the command actually
  driven — and the docs/design/decision state the researched facts instead of hedging.
- **Checkpoint/tests:** new test
  `test_probe_needs_an_install_command_not_just_a_marketplace` (marketplace-only binary →
  no surface → local-clone fallback). `make check` green: **1217 passed, 2 skipped**.
- **Next:** await review.

### 2026-08-05 — review parked Cursor; the work item is Claude-only

- **Phase:** needs-review
- **Did:** @MadaraUchiha-314 on PR #153: *"Let's park cursor for now. For now let's only
  support claude. We will track the cursor installation as a separate issue."* Filed
  [issue #157](https://github.com/MadaraUchiha-314/the-loop/issues/157) carrying the whole
  research trail (what Cursor 2.5 documents, the probe commands to run first, and where the
  removed implementation lives in this PR's history), then removed the component: no
  `plan_cursor`, no `CURSOR_LOCAL_PLUGINS`, `COMPONENTS = ("cli", "claude")`, and `cursor`
  now rejected as an unknown component rather than half-supported. The **locked** artifacts
  were amended rather than rewritten — each carries the owner's words, the retirement of
  R1.2, and a pointer to issue-157 — because a locked artifact changing needs its authority
  on the record. decision-057 gains a *Cursor, parked* section stating why one harness done
  properly beat two half-done.
- **Kept from the descoped work:** the probe still requires a working `plugin install`
  rather than merely a `marketplace` command — the split that research found is real for
  any harness, not just Cursor.
- **Checkpoint/tests:** suite re-run after the removal; `make check` green.
- **Next:** await approval.

### 2026-08-05 — rebased onto main (v7.0.0); decision renumbered

- **Phase:** needs-review
- **Did:** @MadaraUchiha-314 asked for a rebase. `main` had moved to **7.0.0** with
  issue-156 (*"tmux is the only runner"*) merged — and that PR had taken **decision-056**,
  the number this work item also claimed. Replayed the branch onto the new `main` as one
  commit (that is how PRs land here — `main` carries one commit per PR), renumbered this
  work item's decision **056 → 057** across the decision file, both capability docs, both
  command pages and all four spec artifacts, and resolved the two content conflicts by
  keeping *both* sides: `decisions.md` and `docs/capabilities/cli.md` now carry issue-156's
  row and this one.
- **Checkpoint/tests:** `make check` on the rebased tree → green, **1222 passed, 2
  skipped** (the count rose with main's own tests). `the-loop check issue-152 --recompute
  --fail-on block` → exit 0. Nothing in issue-156's runner removal touches
  `the_loop.install`.
- **Note:** the `uv.lock` drive-by is now a 6.2.1 → 7.0.0 refresh — `main`'s release bump
  missed the lock again, and `uv sync` rewrites it.
- **Next:** await approval.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | 3 findings, all fixed (empty `marketplaceRepo`; un-migrated CLI config blocking upgrade; upgrade doc gap) | this log |
| 2 | self | the-loop | 1 finding, fixed: `execute()` resolved the real machine for steps planned against a fake one (see above) | this log |
| 3 | self | the-loop | zero new findings (converged) | this log |
| 4 | self (CI-prompted) | the-loop | 2 findings, fixed: artifacts left unlocked (BLOCK on the graph gate); R5.1 overstated idempotence for harness-owned state | [PR #153 gate](https://github.com/MadaraUchiha-314/the-loop/actions/runs/30963085265) |
| 5 | self (review-prompted) | the-loop | 1 finding, fixed: the probe accepted a marketplace-only plugin surface, so a Cursor-shaped binary would have failed instead of falling back | [PR #153 comment](https://github.com/MadaraUchiha-314/the-loop/pull/153) |
| 6 | human | @MadaraUchiha-314 | Descope: Cursor parked, Claude-only; split out as issue-157 | [PR #153 comment](https://github.com/MadaraUchiha-314/the-loop/pull/153) |
| — | critic | *unavailable* | `reviews.critics` is empty in this repo's harness config — no critic harness is configured, so no critic round ran | `.the-loop/harness-config.yaml` |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; the bundled
  security-review skill is not available in this session).
- **Outcome:** pass. Each boundary from `requirements.md` § Security considerations was
  checked against the implementation:
  - *Marketplace value is code execution* — validated by `harness_plugins._REPO_RE` in
    `_validated_repo()` **before** the plan is built; five hostile spellings are covered by
    a parametrized test and an integration test asserts that `--from "owner/repo; rm -rf /"`
    exits 2 with no command executed and no settings file written. The resolved repo prints
    in the plan header, including under `--dry-run`.
  - *Shell injection* — one process entry point (`install._run`), argv list, `shell=False`;
    a test asserts every planned step's argv is a list of strings.
  - *Writing the operator's config* — only via `trust.update_json` (merge, atomic replace,
    no write when the state holds, unparseable file reported not overwritten); idempotence
    proved by an mtime assertion.
  - *Scope confusion* — no branch widens a scope; the "cannot be expressed" paths are
    tested for Claude (no `--scope` in the binary's help) and Cursor (no documented
    project-local route), and assert that nothing is written at user scope instead.
  - *Privilege* — no `sudo`, no elevation; writes confined to the harness config dir, the
    named project, or `~/.cursor/plugins/local/`.
  - *Unbounded child process* — every subprocess carries a timeout (20 s probe, 900 s
    step); a `TimeoutExpired` becomes a `failed` step, covered by a test.
- **Human sign-off:** n/a — risk tier 3 is below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

Beyond the suite, the command was exercised against the **real** Claude Code CLI in an
isolated `CLAUDE_CONFIG_DIR`, which is what proves R5 (re-running is safe) on the actual
harness rather than on a fake:

```text
$ the-loop install claude                       # run 1
claude  applied  … marketplace add …   √ Successfully added marketplace: the-loop (declared in user settings)
claude  applied  … plugin install …    √ Successfully installed plugin: the-loop@the-loop (scope: user)

$ the-loop install claude                       # run 2 — same command, nothing broken
claude  applied  … marketplace add …   √ Marketplace 'the-loop' already on disk — declared in user settings
claude  applied  … plugin install …    √ Plugin "the-loop@the-loop" is already installed (scope: user)

$ the-loop upgrade claude
claude  applied  … marketplace update …  √ Successfully updated marketplace: the-loop
claude  applied  … plugin update …       √ the-loop is already at the latest version (6.2.0).

$ claude plugin list
  > the-loop@the-loop   Version: 6.2.0   Scope: user   Status: √ enabled
```

The isolated config directory was removed afterwards. Acceptance criteria coverage:
R1 (install per harness, detected defaults, independent components), R2 (upgrade paths,
method detection, source checkout skipped, marketplace refreshed first), R3 (user/project
scope, pass-through, never widened), R4 (argv printed, `--dry-run`, `--format json`),
R5 (outcomes and exit code), R6 (probe, documented fallbacks only), R7 (marketplace
resolution and validation) — each mapped to a test in
`cli/tests/test_install.py` / `test_install_integration.py`.
