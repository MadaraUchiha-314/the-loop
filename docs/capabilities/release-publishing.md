# Capability: release-publishing

> Automatic, semantic releases: merging to `main` versions, tags and publishes the CLI
> to PyPI with no stored credentials.

## What it is

The release pipeline for the CLI package — versioning derived from Conventional
Commits, publishing via GitHub Actions Trusted Publishing (OIDC).

## Current behaviour

- WHEN commits land on `main` THEN `.github/workflows/release.yml` SHALL derive the
  next version with `cz bump` (commitizen) from the Conventional Commits / PR titles
  since the last tag, tag it, and push the tag explicitly.
- The workflow SHALL build the package with `uv` and publish to PyPI using **Trusted
  Publishing (OIDC)** — no stored API token — gated by the `pypi` GitHub environment.
- The distribution SHALL be named **`the-loopy-one`** (base name taken) while the
  import package `the_loop` and the `the-loop` console script stay unchanged.
- WHEN no release-worthy commit exists THEN the workflow SHALL exit without publishing
  (first-release baseline handled via a local-only tag).

## Design

[`docs/specs/issue-21/design.md`](../specs/issue-21/design.md) ·
[architecture § CLI companion](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-21 | Introduced PyPI Trusted Publishing + automatic semantic releases (incl. tag-push and first-release fixes) | [spec](../specs/issue-21/), [decision-019](../decisions/decision-019.md) |
