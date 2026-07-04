# Decision 019 — Publish the CLI to PyPI as `the-loopy-one` via Trusted Publishing

- **Status:** accepted (spec approved and implemented on this PR)
- **Date:** 2026-07-04
- **Deciders:** @MadaraUchiha-314 (product-manager, architect, approver)
- **Work item:** issue #21
- **Spec:** `docs/specs/issue-21/`

## Context

Issue #21 asks to publish the-loop to PyPI so users can `pip install` the CLI instead of
cloning the repo. The issue pre-registered a PyPI Trusted Publisher and posed two design
questions:

1. **What gets published?** Only the CLI, or more packages later?
2. **How do we future-proof** the package / sub-package naming?

Forces at play:

- **Name availability.** The natural distribution name `the-loop` (and close variants) was
  unavailable on PyPI, so the owner reserved **`the-loopy-one`** and configured the Trusted
  Publisher against it (owner `MadaraUchiha-314`, repo `the-loop`, workflow `release.yml`,
  environment `pypi`).
- **Zero-runtime-dependency guarantee** (decision-005): the core CLI is stdlib-only; the
  release tooling must not compromise that.
- **No local-vs-CI drift** (decision-006/009): the-loop dogfoods `uv`; the release build
  should use the same tool as local dev and CI.
- **Credential hygiene:** long-lived PyPI API tokens stored as repo secrets are a standing
  liability; the pre-registered Trusted Publisher lets us avoid them entirely.

## Decision

**Publish only the `cli` workspace member**, as the PyPI distribution **`the-loopy-one`**,
using **PyPI Trusted Publishing (GitHub Actions OIDC)** driven by a new
`.github/workflows/release.yml`.

Three names are kept deliberately distinct:

| Name kind         | Value           | Where it shows up                 |
|-------------------|-----------------|-----------------------------------|
| distribution (PyPI) | `the-loopy-one` | `pip install the-loopy-one`       |
| import package    | `the_loop`      | `import the_loop`                 |
| console script    | `the-loop`      | `the-loop --help`                 |

Only the distribution name is affected by the PyPI collision; the import package and CLI
command keep the natural `the_loop`/`the-loop`, so user-facing ergonomics are unchanged.

The workflow triggers on a **published GitHub Release** (tag `v<version>`, matching
`cli/pyproject.toml` and `.cz.toml`). A `build` job packages the member with
`uv build --package the-loopy-one` and guards that the release tag equals the packaged
version; a `publish-pypi` job — gated by the `pypi` environment and granted `id-token:
write` — uploads via `pypa/gh-action-pypi-publish`. Manual `workflow_dispatch` runs build
the artifacts (a safe dry run) but never publish.

## Future-proofing (answering issue #21's second question)

The repo is already a `uv` workspace whose **root is virtual (not a package)** and whose
publishable code lives in named members — today just `cli`. This is the Python-idiomatic
shape for a repo that may emit several distributions. The convention going forward:

- **One distribution per publishable workspace member**, each with its own `pyproject.toml`
  and `[project] name`, built with `uv build --package <name>` and added to the release
  matrix. Adding a package is: new member + its own Trusted Publisher registration + a
  matrix entry — no redesign.
- **Shared `the-loopy-one` prefix** for sibling distributions (e.g. a future
  `the-loopy-one-<component>`), so the family is discoverable on PyPI under one namespace.
- **PEP 420 implicit namespace packages** if/when the import surface is split, keeping
  imports coherent (`the_loop`, `the_loop.<component>`) without a redistribution.

Not adopted now (YAGNI): a monorepo release matrix, or splitting the import package — there
is exactly one distribution today. The workflow is written so a second package is an
additive change.

## Consequences

- `cli/pyproject.toml` `[project] name` becomes `the-loopy-one`; `uv.lock` is re-locked to
  match (the member renames `the-loop` → `the-loopy-one`).
- New `.github/workflows/release.yml`; a new protected `pypi` GitHub environment gates the
  publish job. `.github/workflows/**` is a `sensitivePaths` entry (config `autonomy`), so
  this ships behind human PR approval.
- No PyPI token secret is stored — OIDC only. If Trusted Publishing is ever unavailable,
  the fallback is an API token in the `pypi` environment's secrets; the workflow structure
  is unchanged.
- Releases are cut by publishing a GitHub Release; `cz bump` produces the matching
  `v<version>` tag (decision-008).

## Alternatives considered

- **Store a PyPI API token as a GitHub secret** — rejected: long-lived credential, exactly
  what Trusted Publishing (already registered) removes.
- **Publish the whole workspace / the virtual root** — not possible/meaningful: the root is
  a virtual workspace with no `[project]`; only members are distributions.
- **Rename the import package / CLI to `the-loopy-one`** — rejected: needlessly degrades
  ergonomics (`import the_loopy_one`, `the-loopy-one --help`) for a name collision that only
  needs to be resolved at the distribution layer.
- **Trigger on tag push (`v*`) instead of Release** — rejected: a published Release is an
  explicit human gate and pairs naturally with the `pypi` environment; the tag guard still
  enforces version/tag agreement.
