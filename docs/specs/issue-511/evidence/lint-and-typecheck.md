---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Lint, typecheck and markdown lint (T12, T13): de-cluttering the control plane UI

> Run at `verification` on 2026-10-20 on branch `issue-511-declutter-control-plane`.

## Lint

```text
cd ui && bun run lint
$ oxlint --type-aware
(no findings; exit 0)
```

## Typecheck

`tsc --noEmit` runs as the first half of `bun run build` — see [`build.md`](build.md);
it reported no error.

## Markdown

```text
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 1764 file(s)
Summary: 0 error(s)
```

Covers the spec chain under `docs/specs/issue-511/`, `docs/decisions/decision-148.md`,
`ui/README.md` and `docs/capabilities/control-plane.md`.
