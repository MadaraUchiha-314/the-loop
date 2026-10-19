---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T12 — the static set

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

```text
make lint
Linting: 1695 file(s)
Summary: 1 error(s)
docs/specs/issue-496/requirements.md:688 MD024/no-duplicate-heading Multiple headings with the same content [Context: "2026-10-18 — approved"]
make: *** [Makefile:19: lint] Error 1
make format-check
488 files already formatted
make typecheck
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`
make validate
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   skills/the-loop/templates/gateway-config.yaml
```

`ruff check`, `ruff format --check`, `pyright cli` (0 errors) and the config validation pass. `make lint` reported one markdownlint finding, `docs/specs/issue-496/requirements.md:688` MD024: the approval gate appended a second `### 2026-10-18 — approved` heading when the amended requirements were re-approved the same day. The record is the gate's and stays as written; a `markdownlint-disable-next-line` comment names the cause (commit e05debe) and [#500](https://github.com/MadaraUchiha-314/the-loop/issues/500) tracks the hook fix. With it, `make lint` is clean and CI's `checks` job re-ran on the push.
