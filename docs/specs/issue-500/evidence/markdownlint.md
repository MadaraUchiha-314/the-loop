# Real linter over a recorded artifact — T11

A scratch artifact was recorded into three times on one day by the real hook (`classify-feedback` then `record-feedback`, the gate's own chain), then linted with the pinned linter and the repository's `.markdownlint-cli2.jsonc`.

## The recorded artifact

```markdown
# R

## Review comments

### 2026-10-26 — approved

**@owner** wrote:

approved

### 2026-10-26 — approved (2)

**@owner** wrote:

approved

### 2026-10-26 — approved (3)

**@owner** wrote:

approved

```

## After the fix

```text
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: spec/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 1 file(s)
Summary: 0 error(s)
```

## The pre-fix shape (suffixes removed), for contrast

```text
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: spec/before.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 1 file(s)
Summary: 2 error(s)
spec/before.md:11 MD024/no-duplicate-heading Multiple headings with the same content [Context: "2026-10-26 — approved"]
spec/before.md:17 MD024/no-duplicate-heading Multiple headings with the same content [Context: "2026-10-26 — approved"]
```
