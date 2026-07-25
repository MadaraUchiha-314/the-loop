---
type: execution-log
workItem: "issue-97"
phase: needs-review
status: in-progress
---

# Execution Log: PyYAML is a required runtime dependency of the CLI

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-97/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-25 |  | Issue #97: make `pyyaml` a required dependency instead of the `[config]` extra. Investigation found the extra is optional only on paper — all three YAML sites degrade *silently* to empty config, which makes `poll` watch nothing and empties the `authorizedUsers` guard. |
| design | 2026-07-25 |  | Declaration → three fallbacks deleted → decision-038 + supersede pointers. `config` extra retained as an empty deprecated alias. |
| tasks-breakdown | 2026-07-25 |  | 11-task DAG |
| implementation | 2026-07-25 |  | Implemented on `claude/github-issue-97-sim8il` |
| needs-review | 2026-07-25 |  | PR opened with the reviewer briefing; `make check` green; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-25 — investigation + spec drafted

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Traced every `import yaml` in the CLI (three sites: `cli_config.load_cli_config`,
  `eventlog.load_config`, `commands/scenarios._load_config_globs`) and read what each
  fallback costs. The finding that shaped the spec: the degradation is **silent** —
  `cli_config` logs it at `debug`, `eventlog` not at all — so without PyYAML
  `the-loop poll` starts, reads `polling.sources` as `{}`, watches nothing, and says
  nothing about why; and `routing.authorizedUsers`, the input to decision-023's
  prompt-injection guard, arrives empty from the same silent path. The extra is
  therefore optional only on paper, and the change is a **removal** (three guards and
  the reasoning attached to them) rather than an addition. Decided to keep the
  `config` extra as an empty deprecated alias so pinned install lines keep working
  without pip's "does not provide the extra" warning, and to record the reversal as a
  new decision with superseded-in-part pointers on decision-005/decision-030 rather
  than rewriting their bodies.
- **Next:** implement T1–T9.
- **Blockers:** none. Tier 3 (`human-approves-pr`): spec + code approved together at
  the PR.

### 2026-07-25 — implemented (T1–T9)

- **Phase:** implementation → needs-review
- **Did:**
  - `cli/pyproject.toml`: `dependencies = ["pyyaml>=6"]`; the `config` extra kept as
    an empty deprecated no-op so a pinned
    `pip install "the-loopy-one[config]"` keeps resolving without pip's "does not
    provide the extra" warning. `uv.lock` refreshed.
  - `cli_config.py`, `eventlog.py`, `commands/scenarios.py`: `import yaml` moved to
    module scope, the three `try/except ImportError` guards deleted. The **file**
    leniency is untouched — missing file → `{}`/`[]`, lenient parse failure → `{}`
    with the existing `logger.warning`, and `strict=True` still raises
    `FileNotFoundError`/`YAMLError` so `Reloader` retains the last good config.
  - Docstrings that carried the retired guarantee rewritten in the same edit
    (`cli_config`, `gh_webhook` ×2, `scenarios` ×2, `webhook/__init__`).
  - `docs/decisions/decision-038.md` (new) + index row; superseded-in-part pointers
    on decision-005 and decision-030 — their bodies are left as written, since they
    record *why* the guarantee was made. decision-016/019/025 deliberately untouched
    (their conclusions are unaffected).
  - Prose: root `README.md`, `cli/README.md` (intro, both install blocks, and the
    three "when PyYAML is installed" clauses on `gh-webhook`/`poll`/`scenarios`),
    `docs/architecture/architecture.md`, `skills/the-loop/reference/automation.md`,
    `docs/capabilities/cli.md` (behaviour bullet + history row).
  - Test: `test_pyyaml_is_a_required_runtime_dependency` — the installed
    distribution metadata must carry a bare `pyyaml>=6` with **no `extra ==`
    marker**, and must still declare `Provides-Extra: config`.
- **Checkpoint/tests:** `make check` green — ruff, markdownlint (229 files),
  `ruff format --check`, pyright 0 errors, all six config files VALID, pytest
  **456 passed**. Additionally built the wheel and installed it into a clean venv
  (see evidence below).
- **Next:** open the PR with the reviewer briefing; request review.
- **Blockers:** none.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | self | the-loop (implementing agent) | One finding, fixed — an **accuracy** defect in my own spec. I had written that without PyYAML "`the-loop poll` starts, prints nothing, and never picks up a ticket". Reading `commands/poll.py` disproved it: `poll` *errors and exits 1* with "no polling sources configured — add entries under `polling.sources` in the CLI config (`<path>`)", and `gh-webhook` warns "no authorizedUsers configured". The cause is silent; the symptom is not — it **misdirects**, naming config the operator has already written. Corrected in `requirements.md`, `design.md`, `decision-038.md`, `capabilities/cli.md` and the test docstring. Also rewrapped an over-long `cli/README.md` bullet. | this PR |
| 2 | self (security lens, `security.review.mechanism: auto`) | the-loop (implementing agent) | One finding, fixed — I had claimed the change was "a security improvement, narrowly", on the grounds that a missing PyYAML emptied `routing.authorizedUsers` (decision-023's prompt-injection allow-list). Reading `authz.is_authorized` disproved it: an empty allow-list **denies every human-authored action** (fail-closed) and `gh-webhook` warns at startup. The guard was never open; the old behaviour was an availability failure. The claim is now stated as *not* a security fix, in requirements, design and decision-038 — an overstated security win is worse than none, because a reviewer may approve on the strength of it. Verified in the same pass: all three sites use `yaml.safe_load` (never `yaml.load`), the change adds **no** call site, `>=6` sits above the CVE-2020-14343 line, PyYAML has no transitives, and only operator-local files reach the parser (webhook payloads go through stdlib `json` on a different path). Risk tier 3 < `humanSignOffMinTier` (4): no named human security sign-off required. | this PR |
| 3 | self | the-loop (implementing agent) | No new findings. Went past the editable install's metadata for real end-to-end evidence: built the wheel and inspected `METADATA` (`Requires-Dist: pyyaml>=6` unconditional, `Provides-Extra: config` retained), then installed `<wheel>[config]` into a clean throwaway venv — resolved PyYAML 6.0.3 with no extra warning, `the-loop --version` ran. Also confirmed no import cycle from hoisting `import yaml` (`eventlog` → `yaml` → stdlib; `eventlog` → `cli_config` unchanged) and that `logger` remains used at both sites whose only other use was the deleted debug line. | this PR |
| 4 | self | the-loop (implementing agent) | No new findings — stopped per `reviews.stopOnNoNewFindings`. `reviews.critics` is empty in this repo's config, so no critic harness is configured to run. | this PR |

## Final validation evidence

Local gate (`make check`) green in full: ruff clean, markdownlint 0 errors over 229
files, `ruff format --check` clean, pyright 0 errors, all six config files VALID,
pytest **456 passed**.

Built-distribution evidence (beyond the editable install), from
`uv build --project cli` then a clean venv:

```text
the_loopy_one-0.20.0-py3-none-any.whl  →  METADATA
  Requires-Python: >=3.9
  Requires-Dist: pyyaml>=6              # unconditional — no `extra ==` marker
  Provides-Extra: config                # retained, contributes nothing
  Provides-Extra: dev
  Requires-Dist: commitizen>=3; extra == 'dev'
  Requires-Dist: pytest>=8; extra == 'dev'

$ uv pip install "<wheel>[config]"      # the pre-0.21 documented line
$ uv pip list | grep -i 'yaml\|loopy'
pyyaml         6.0.3
the-loopy-one  0.20.0
$ the-loop --version
the-loop 0.20.0
```

| AC | Evidence |
|----|----------|
| R1.1 | `test_pyyaml_is_a_required_runtime_dependency` (bare `pyyaml`, no `extra ==` marker) + the wheel's `Requires-Dist: pyyaml>=6` above |
| R1.2 | `Provides-Extra: config` in the wheel, asserted by the same test; the clean-venv `install "<wheel>[config]"` above succeeding with no pip extra warning |
| R1.3 | `>=6` asserted by the same test; `uv.lock` regenerated (`the-loopy-one` moves from `[package.optional-dependencies].config` to `dependencies`, and `requires-dist` drops the `extra == 'config'` marker) |
| R1.4 | `Requires-Python: >=3.9` unchanged in the built metadata; PyYAML 6 supports ≥3.6 |
| R2.1 | No `except ImportError` remains under `cli/the_loop/` (`grep`); `ruff` clean |
| R2.2, R2.3 | The pre-existing `test_missing_file_lenient_empty_strict_raises`, `test_unparseable_yaml_lenient_empty_strict_raises`, `test_valid_yaml_parses_full_document`, `test_load_config_globs_prefers_harness_config_with_config_yaml_fallback` and the `Reloader` tests stay green **unmodified** — that they needed no edit is the evidence |
| R2.4 | Full suite 456 passed, unchanged from the pre-change count plus the one new test |
| R3.1, R3.2 | `docs/decisions/decision-038.md`; index row in `decisions.md`; supersede pointers on decision-005 and decision-030 |
| R3.3 | `README.md`, `cli/README.md`, `docs/architecture/architecture.md`, `docs/capabilities/cli.md`, `skills/the-loop/reference/automation.md`, and the five docstrings — all in this PR |
| R3.4 | `cli/README.md` install blocks + the `[config]` compatibility note |
| R3.5 | `docs/capabilities/cli.md` behaviour bullet rewritten + issue-97 history row |
| R3.6 | decision-016 / decision-019 / decision-025 unedited by design (grep shows their wording intact) |
| R4.1 | `test_pyyaml_is_a_required_runtime_dependency` |
| R4.2 | The YAML-reading tests listed under R2.2 pass unmodified |
