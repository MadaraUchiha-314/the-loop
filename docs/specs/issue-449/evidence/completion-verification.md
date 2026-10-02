# PR #450 completion verification

The completion review found three gaps after `65985a8`: malformed rollout
directory metadata was accepted, packaged instructions lacked the required
writing skill, and installation pages omitted Codex. The fixes are verified
locally. Remote review, CI, approval and the requested fresh end-to-end run
remain unverified in the original restricted-session record below. The live
follow-up at the end records the subsequently restored access and fresh test.

## Environment

Commands ran on 2026-10-02 from the-loop's repository root, except the runtime
attempt, which ran from `/Users/rohithr31/workspace/github.com/MadaraUchiha-314/devbox`
as requested. Python dependencies came from the existing temporary environment
`/private/tmp/the-loop-pr450-codex/.venv`; tool binaries came from cached packages.
No credential values were displayed or copied into artifacts.

The normal `uv sync --offline --locked` path could not install Ruff from the
available cache. The isolated `uv build --offline` path lacked cached build
dependency resolution. Verification therefore used the cached Ruff 0.15.8,
Pyright 1.1.411, Markdownlint CLI2 0.18.1 and Hatchling backend directly.

## Directory recovery: red to green

```sh
PYTHONPATH=cli TMPDIR=/private/tmp PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /private/tmp/the-loop-pr450-codex/.venv/bin/python -m pytest \
  -c cli/pyproject.toml cli/tests/test_codex_support.py -k explicit_absolute -q
```

Before the fix:

```text
6 failed, 28 deselected in 0.28s
```

The six cases exercise absent, empty and relative metadata with both launch
markers and native IDs. Each failed because lookup returned a rollout instead
of refusing it. The implementation now requires an absolute string before
comparing directories. Existing wrong-directory, ambiguity, unsafe-ID and
escaping-symlink tests still pass.

## Focused regressions

```sh
PYTHONPATH=cli TMPDIR=/private/tmp PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /private/tmp/the-loop-pr450-codex/.venv/bin/python -m pytest \
  -c cli/pyproject.toml cli/tests/test_codex_adapter.py \
  cli/tests/test_codex_support.py cli/tests/test_dispatcher_harness.py \
  cli/tests/test_harness_gate.py cli/tests/test_mcp_integration.py \
  cli/tests/test_install.py cli/tests/test_version_lockstep.py -q
```

```text
140 passed in 1.50s
```

The documentation and installation follow-up additionally ran:

```sh
PYTHONPATH=cli TMPDIR=/private/tmp PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /private/tmp/the-loop-pr450-codex/.venv/bin/python -m pytest \
  -c cli/pyproject.toml cli/tests/test_docs_parity.py \
  cli/tests/test_writing_parity.py cli/tests/test_sdk_docs_parity.py \
  cli/tests/test_install.py cli/tests/test_install_integration.py -q
```

```text
71 passed in 1.78s
```

This is targeted verification. The earlier full-suite comparison and its
environment failures remain recorded in [codex-verification.md](codex-verification.md).

## Packaged instruction resources: red to green

The archive assertion first failed for both the unchanged checkout wheel and
source distribution: neither included `the_loop/resources/skills/writing/SKILL.md`.
After adding the sibling skill to both packaging paths, the checkout wheel,
source distribution and wheel rebuilt from that extracted distribution each
contained the six checked resources below.

The exact build backend procedure was:

```python
import os
from pathlib import Path
from hatchling.build import build_sdist, build_wheel

out = Path("/private/tmp/pr450-completion-build")
out.mkdir(exist_ok=True)
os.chdir("cli")
print(build_sdist(str(out)))
print(build_wheel(str(out)))
```

For each archive, the check asserted entries ending in
`the_loop/resources/` plus each of:

```text
skills/the-loop/SKILL.md
skills/the-loop/reference/workflow.md
skills/writing/SKILL.md
skills/writing/reference/tells.md
commands/work-on.md
hooks/the-loop-gate.py
```

The source distribution was extracted with `tarfile.extractall(filter="data")`;
`hatchling.build.build_wheel` then ran from its extracted root. The rebuilt wheel
was extracted into an isolated consumer directory, added to `sys.path`, and
`prepare_instructions` ran twice against temporary project and hook directories.
Assertions required successful preparation, readable writing references and
an unchanged second run.

```text
the_loopy_one-19.19.0.tar.gz: all 6 required resources present
the_loopy_one-19.19.0-py3-none-any.whl: all 6 required resources present
rebuilt the_loopy_one-19.19.0-py3-none-any.whl: all 6 required resources present
isolated wheel consumer: instructions and hook prepared; repeat unchanged; writing reference readable
```

## Static checks

| Check | Executed command | Result |
| --- | --- | --- |
| Ruff | Cached Ruff 0.15.8: `ruff check cli hooks` and `ruff format --check cli hooks` | All checks passed; 406 files formatted |
| Types | Cached Pyright 1.1.411: `pyright --typeshedpath <cached typeshed-fallback> --pythonpath /private/tmp/the-loop-pr450-codex/.venv/bin/python --outputjson cli` | 404 files; zero errors or warnings |
| Config | Cached Python: `scripts/validate_config.py` | All six configs valid |
| Versions | Cached Python: `scripts/check_version_lockstep.py` | All six version files and lock at 19.19.0 |
| Lock | `UV_CACHE_DIR=/private/tmp/the-loop-uv-cache uv lock --offline --check` | 74 packages resolved; current |
| Markdown | Cached Markdownlint CLI2 0.18.1: `markdownlint-cli2 '**/*.md'` | All repository Markdown checked |
| Whitespace | `git diff --check` | Passed |

## Source installation and devbox runtime attempt

The user requested source installation and a new issue in
`MadaraUchiha-314/the-loop-testing`, completed by Codex before merge.
The normal machine installation command was attempted:

```sh
UV_CACHE_DIR=/private/tmp/the-loop-uv-cache uv tool install --offline --force \
  /Users/rohithr31/workspace/github.com/MadaraUchiha-314/the-loop/cli
```

```text
error: Could not create temporary file
cause: Operation not permitted at /Users/rohithr31/.local/share/uv/tools/.tmp...
```

The existing machine installation was not replaced. The corrected checkout
wheel was successfully installed into a temporary target instead:

```sh
UV_CACHE_DIR=/private/tmp/the-loop-uv-cache uv pip install --offline --no-deps \
  --target /private/tmp/pr450-installed-source \
  /private/tmp/pr450-completion-build/the_loopy_one-19.19.0-py3-none-any.whl
```

Using that installed package and the cached dependency environment, from devbox:

```sh
PYTHONPATH=/private/tmp/pr450-installed-source \
  /private/tmp/the-loop-pr450-codex/.venv/bin/python -m the_loop --version
PYTHONPATH=/private/tmp/pr450-installed-source \
  /private/tmp/the-loop-pr450-codex/.venv/bin/python -m the_loop start
```

```text
the-loop 19.19.0
service: failed; did not become healthy
poller: failed; cannot open devbox/.the-loop/logs/poller.out: Operation not permitted
```

The devbox configuration enables polling and declares Codex as the default.
Its GitHub credential references are `GH_TOKEN` and `GITHUB_TOKEN`; neither is
available in this session, and the existing gh credential is also unavailable.
`the-loop ticket show` from devbox reports no GitHub token. Git cannot resolve
github.com. No new test issue was created and no live run is claimed.

## Remaining completion work

- Restore writable machine installation and devbox runtime state, authenticated
  GitHub access and network access.
- Refresh issue #449, PR #450, its CI and unresolved review threads; post the
  prepared findings and [reviewer briefing](reviewer-briefing.md).
- Install the corrected source as the machine CLI and start it from devbox.
- Create a fresh smoke issue in the-loop-testing through `the-loop ticket create`.
  Follow its authorized phase selections and Codex hook trust requirements;
  record its issue, PR, checks, trace and completion evidence here.
- Complete the selected gates and merge only after that live verification.

The main workspace's `.git` is read-only. The local completion commits are
prepared in `/private/tmp/pr450-completion-checkout`; no remote push or merge
has occurred.

## Live follow-up: source install and tracked instructions

On 2026-10-02, the current checkout was fast-forwarded from `65985a8` to
`5d2ca97`. The operator's local edits remain in a Git stash. Existing GitHub
credentials were supplied to the daemon by reference; their values were not
printed or written into evidence.

```sh
uv tool install --force /Users/rohithr31/workspace/github.com/MadaraUchiha-314/the-loop/cli
```

Installed distribution: `the-loopy-one==19.19.0`. Its `direct_url.json` points
at this checkout's `cli` directory. SHA-256 comparisons confirmed that installed
`codex_support.py` and `harness/codex_agent.py` matched the pulled source; the
writing skill was present in the installed resources.

From the operator's requested devbox cwd:

```sh
the-loop install codex --scope user
the-loop start
the-loop status
```

```text
service running — http://127.0.0.1:4114, healthy
poller running
```

The installed Stop gate was reviewed through Codex's native hook screen.
Only this gate was trusted; the resulting Stop row showed one installed and
one active hook. No hook-trust bypass flag or trust-file edit was used.

A real codex-cli 0.160.0 read-only probe ran from this repository:

```sh
codex --ask-for-approval never exec --sandbox read-only --json   'This is a read-only instruction-discovery probe for PR 450. Without using tools or editing files, identify the global instruction source and the project instruction source already supplied to this conversation. Quote one line from each that establishes the-loop operating instructions. Do not perform work on any ticket.'
```

The native conversation `01a0fe02-9e5c-7cc2-985c-8a5f61220c91` reported both the
global the-loop block and the project's “Working in the-loop” instructions.
The JSONL contained no tool calls, and the project stayed clean. This agrees
with [Codex's documented global/project instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

A8 regression: both tracked project instruction filenames failed preservation
before the fix. Spawn preparation now installs the managed block in Codex's
global instruction file when the effective project file is tracked. Four
combinations of project/global `AGENTS.md` and `AGENTS.override.md` verify
unchanged project bytes, a clean Git status, operator text preservation, and
idempotent preparation. Explicit project-scope installation is unchanged.

```sh
TMPDIR=/private/tmp uv run python -m pytest -q   cli/tests/test_codex_support.py cli/tests/test_codex_adapter.py   cli/tests/test_dispatcher_harness.py cli/tests/test_harness_gate.py   cli/tests/test_mcp_integration.py cli/tests/test_install.py   cli/tests/test_version_lockstep.py
```

```text
153 passed in 2.29s
```

Ruff lint and format checks, Pyright, six configuration validations, and
Markdownlint passed. The initial full-suite run on the pulled branch reported
5261 passed and four failures: two tests assumed Cursor was absent, one
compared macOS's temporary-directory alias without resolving it, and one
expected a numeric POSIX session ID from macOS `ps`. A rerun from `cli` with
canonical temp paths removed the first three conditions but omitted tmux from
PATH, causing eight ingress-test failures. Rerunning the two affected ingress
test files with Homebrew's tmux available reported 10 passed and one failure:
the same macOS session-ID assertion (`ps` reports `sess=0`). These environment
results are not a green suite.
The three GitHub checks on `5d2ca97` were successful.

Fresh smoke issue: [the-loop-testing#3](https://github.com/MadaraUchiha-314/the-loop-testing/issues/3).
It was created through `the-loop ticket create` and started through
`the-loop sessions start` from devbox. The service prepared its worktree,
posted the phase-selection checklist, and recorded `graph.parked` plus
`session.spawn_deferred` with reason `parked-at-human-start-gate`, selecting
Codex as the deployment default. The CLI's start command returned an error
because no session had spawned; the graph's events show it waiting correctly
at the human gate. No selection or approval was fabricated. End-to-end
execution and completion remain pending the operator's phase selection.

## Completed live Codex run and startup regression

The later operator instruction explicitly delegated phase selection to this Codex
session. The recorded selection chose Codex, implementation and verification,
with the other phases explicitly unchecked. No artifact approval was claimed.
The deployment launched the issue from the configured devbox cwd at
2026-10-02T19:27:52Z using the installed source at `fdf8261`.

[Smoke issue #3](https://github.com/MadaraUchiha-314/the-loop-testing/issues/3)
completed. [PR #4](https://github.com/MadaraUchiha-314/the-loop-testing/pull/4)
merged at 2026-10-02T19:33:32Z with merge commit
`5600637414df40a0ec6b3523f54c66cb300a647c`; the issue closed automatically.
The delivery added the requested `codex-smoke.md` sentence, linked it from README,
and committed the test work item's verification evidence. The original README
content was preserved. No managed machine instructions or session state were
committed. The native session reported a complete graph before normal cleanup
removed its worktree and local session state.

[The persistent smoke verification record](https://github.com/MadaraUchiha-314/the-loop-testing/blob/main/docs/specs/issue-3/evidence/verification.md)
and [the agent's main-PR report](https://github.com/MadaraUchiha-314/the-loop/pull/450#issuecomment-5959955607)
record the delivery. The native conversation was
`01a0fe16-5d14-7923-ba0f-650b743d759a`; the service's Harness trace returned that
same conversation and rendered user, assistant and tool events.

A separate real read-only Codex chat in the same worktree started after the
work-item session. It produced native ID
`01a0fe18-8108-7850-8cc7-b9ce435b7afd`. A fresh Python process using the installed
`CodexAdapter.resolve_session_id` and original launch marker
`e499f5ef-ac59-4ba0-a285-2be0ed7b08d1` still resolved the work-item conversation,
not the newer unrelated chat. Both native executions produced real JSONL files.
An interrupted TUI respawn and a blocking Stop continuation were not exercised;
the operator's native hook review and trust were exercised separately above.

The live start exposed one additional bug: CLI `sessions start` cleared its
accepted start request when the graph deliberately parked at phase selection.
[The finding was posted before the fix](https://github.com/MadaraUchiha-314/the-loop/pull/450#issuecomment-5959913727).
The dispatcher now records `parked-at-human-start-gate` in its existing bounded
settlement cache. The CLI returns success with effect `waiting` and preserves
the request when that precise outcome is present. Actual spawn failures still
return failure and clear the request; no human gate or authorization is bypassed.

The positive integration scenario failed before the production fix (`exit_code`
was 1 instead of 0). It now verifies that a subsequent authorized execute command
launches exactly one session. A separate real-spawn-failure scenario verifies
that a failed launch leaves no start request armed. The event catalogue and its
exact vocabulary test include the new outcome.

Latest relevant verification:

```text
672 passed in 9.77s
Ruff: all checks passed; 407 files already formatted
Pyright: 0 errors, 0 warnings
```

The test command covered spawn-gate, control CLI/integration, core sessions,
instance integration, reactions, polling, routing, work-channel integration,
Codex support and Codex adapter tests. This is targeted verification, not a
claim that the local full suite passed.

## Installed startup fix: live regression

Source commit `032ed5e` was pushed, installed with `uv tool install --force`,
and the service/poller restarted from devbox. SHA-256 comparisons of installed
`core/sessions.py`, `webhook/dispatcher.py`, `codex_support.py` and
`harness/codex_agent.py` matched the checkout.

[Startup-only issue #5](https://github.com/MadaraUchiha-314/the-loop-testing/issues/5)
was created through the-loop. From devbox, this command returned exit code 0:

```sh
the-loop sessions start --work-item github:MadaraUchiha-314/the-loop-testing#5
```

```text
started the loop for github:MadaraUchiha-314/the-loop-testing#5; waiting at its first human gate before launching a session
```

The installed `ControlStore` read the existing devbox portable state and asserted
`start_requested=True`. The work item was still at phase selection and no harness
launched. [The result was posted on the issue](https://github.com/MadaraUchiha-314/the-loop-testing/issues/5#issuecomment-5960575014).
This live probe verifies the previously broken CLI path without launching another
Codex conversation. The startup-only issue was closed through the operator's
authorized gh CLI because no harness session existed for lifecycle registration.
`the-loop sessions stop --no-comment` then cancelled its start request; a fresh
ControlStore assertion confirmed it was no longer armed.

A fresh artifact-only `the-loop check --recompute` also found missing required
spec/evidence sections in the retroactively authored files. The existing content
now names Architecture, Security design, Testing strategy, Security considerations,
Verification environment, Evidence plan, Verification results and Security review
(gate). Final-validation and pull-request gate records summarize the existing
proof; no approval or work-item state was fabricated. Recomputed agent-owned
artifact checks now pass; human approval checks still wait. The local graph state
is absent, so this recomputation does not claim to advance the live selected graph.
