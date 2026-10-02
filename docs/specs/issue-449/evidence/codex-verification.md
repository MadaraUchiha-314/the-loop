# Codex remediation verification

Verification performed on 2026-10-02 against PR #450's locally cached branch
`claude/github-issue-449-codex`, starting from `4725a0903da57c944418a4185dbbdca09e966a45`.
The source of the remediation scope was the cached issue #449 comment containing
A1–A7 and B1–B4; live GitHub comments could not be refreshed in this session.

## Passing checks

- Targeted harness, transcript, installer, migration, dispatcher, critic, probe,
  poller, GitHub API, MCP, hook, documentation and version regressions:
  **783 passed**.
- Ruff 0.15.8 lint and formatting checks.
- Pyright 1.1.411: 404 files, zero errors or warnings.
- `scripts/validate_config.py`: all six repository and template configurations valid.
- `scripts/check_version_lockstep.py`: all six version files and `uv.lock` at 19.19.0.
- `uv lock --offline --check`: dependency lock current, 74 packages resolved.
- Markdown lint on changed instructions, capability docs and issue design.
- `git diff --check`.
- Checkout wheel and source distribution builds.
- Wheel rebuilt from an extracted source distribution.
- Both wheel archives contain the shared operating skill, work-on procedure and
  gate script. An isolated import from the extracted checkout wheel prepares
  instructions and a native hook and leaves a repeat preparation unchanged.

The installed Codex CLI was 0.160.0. Its interactive, exec, resume and plugin help
were inspected. Native hook and plugin protocol details were checked against
OpenAI documentation linked from `../design.md`.

## Full-suite comparison

The full suite was run both on the unchanged PR branch and on the remediation,
with the same cached dependencies and restricted execution environment.

| Checkout | Passed | Failed | Setup errors |
| --- | ---: | ---: | ---: |
| Original PR branch | 5,129 | 72 | 20 |
| Remediation | 5,160 | 69 | 20 |

Comparing failing test IDs found **no additional failures**. Three existing
documentation parity failures were resolved. The remaining original failures
include restricted socket/process integration checks and environment/package
metadata assumptions; this is not evidence of a fully green unrestricted suite.
The targeted run uses a normalized `PATH` and `/private/tmp` as `TMPDIR`, avoiding
installed optional binaries and macOS temporary-directory alias differences.

## Remaining operational verification

GitHub API access and remote push were unavailable during preparation. A fresh
live issue-to-PR run could not be performed here. The original PR's earlier live
trial is not presented as verification of this remediation.

Codex requires review of a newly installed non-managed hook definition through
`/hooks`; the loop reports that requirement. Operators must complete it before
expecting unattended Stop-gate continuation. Existing sandbox and approval
policies are preserved. Native plugin installation and a trusted interactive
Stop cycle still need a live Codex run in the deployment environment.
