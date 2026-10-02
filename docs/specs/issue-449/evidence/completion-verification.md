# PR #450 completion verification

The completion review found three gaps after `65985a8`: malformed rollout
directory metadata was accepted, packaged instructions lacked the required
writing skill, and installation pages omitted Codex. The fixes are verified
locally. Remote review, CI, approval and the requested fresh end-to-end run
remain unverified.

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
