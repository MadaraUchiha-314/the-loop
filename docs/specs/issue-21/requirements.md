---
type: requirements
phase: requirements-definition
workItem: issue-21
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #21: Trusted Publisher pre-registered)"]
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: Publish the-loop to PyPI

> **Source of truth:** GitHub [issue #21](https://github.com/MadaraUchiha-314/the-loop/issues/21)
> is the canonical requirements input for this work item. This file distills it into
> reviewable, testable requirements. Design and the task DAG live in `design.md` and
> `tasks.md`.

## Introduction

Today the-loop's CLI is only installable by cloning the repo and running `uv sync`.
Issue #21 wants it distributable from PyPI so users can `pip install` it. The issue author
has
already **pre-registered a PyPI Trusted Publisher** (GitHub Actions OIDC), which fixes
several parameters that the implementation MUST match exactly, and raised two design
questions (what to publish; how to future-proof the package naming) that the design MUST
answer.

Pre-registered Trusted Publisher (authoritative — the workflow MUST conform):

| Field            | Value                       |
|------------------|-----------------------------|
| PyPI project     | `the-loopy-one`             |
| owner            | `MadaraUchiha-314`          |
| repository       | `the-loop`                  |
| workflow         | `release.yml`               |
| environment      | `pypi`                      |

## Requirements

### R1 — Publish the CLI to PyPI under the reserved name

**User story:** As a user, I want to `pip install` the-loop's CLI, so that I can use it
without cloning the repo or installing uv.

#### Acceptance criteria (EARS)

1. The published distribution's `[project] name` SHALL be exactly `the-loopy-one` (the
   reserved PyPI project the Trusted Publisher was registered against).
2. WHEN the distribution is installed THEN it SHALL expose the `the-loop` console script
   and the importable `the_loop` package (user-facing names unchanged).
3. The built artifacts SHALL include both an sdist (`.tar.gz`) and a wheel
   (`.whl`) for the member, and no other (root/workspace) distribution.

### R2 — Automated release via GitHub Actions Trusted Publishing (no stored token)

**User story:** As the maintainer, I want releases published automatically over OIDC, so
that no long-lived PyPI token is stored as a secret.

#### Acceptance criteria (EARS)

1. There SHALL be a workflow at `.github/workflows/release.yml` (matching the registered
   workflow name) that builds and publishes the distribution.
2. The publish job SHALL run in the `pypi` GitHub environment and request an OIDC
   `id-token` (Trusted Publishing); it SHALL NOT reference a stored PyPI API token.

### R3 — Semantic, automatic versioning on merge to main (owner request, PR #22)

**User story:** As the maintainer, I want versions and PyPI releases produced automatically
from Conventional Commit / PR-title types, so that I never hand-cut a release.

#### Acceptance criteria (EARS)

1. WHEN a commit lands on `main` THEN the workflow SHALL derive the next version from the
   Conventional Commits since the last tag (`feat → minor`, `fix → patch`,
   `BREAKING CHANGE`/`!` → major) using commitizen (`cz bump`).
2. WHEN a release is warranted THEN the workflow SHALL rewrite the version in `.cz.toml`
   and `cli/pyproject.toml`, tag `v<version>`, push the bump commit + tag to `main`, cut a
   GitHub Release, build the distribution, and publish it to PyPI.
3. IF no commit since the last tag warrants a bump THEN the workflow SHALL publish nothing
   (clean no-op), and the bump commit it pushes SHALL NOT recursively trigger a release.

### R4 — Reproducible build tooling (no local-vs-CI drift)

**User story:** As the maintainer, I want the release build to use the-loop's own package
manager, so that it stays consistent with local dev and CI (RULE: no tooling drift).

#### Acceptance criteria (EARS)

1. The release workflow SHALL build the distribution with `uv` (the declared package
   manager), and `uv.lock` SHALL be re-locked to match the renamed distribution.

### R5 — Design answers the packaging questions

**User story:** As the architect, I want the "what do we publish?" and "how do we
future-proof sub-packages?" questions answered and recorded, so that adding future
packages is an additive change, not a redesign.

#### Acceptance criteria (EARS)

1. The design SHALL state precisely which artifact is published today (scope) and record
   the durable choice under `docs/decisions/`.
2. The design SHALL document the convention for future packages/sub-packages (naming +
   Python namespacing) so it can be followed without rework.

## Non-functional requirements

- **Security / credential hygiene:** no long-lived PyPI credential stored in the repo;
  OIDC Trusted Publishing only. `.github/workflows/**` is a `sensitivePaths` entry
  (config `autonomy`), so the change ships behind human PR approval.
- **Zero runtime dependencies preserved** (decision-005): packaging changes MUST NOT add
  runtime dependencies to the core CLI.

## Out of scope

- Publishing to TestPyPI, or a separate staging environment.
- Splitting the import package into namespace sub-packages, or publishing more than the
  one `cli` distribution (only the convention is documented — see R5).
- Container image publishing (`ghcr`, per `tooling.release.containers`).

## Open questions

None outstanding — the Trusted Publisher parameters are fixed by the issue, and the
naming/future-proofing questions are resolved in `design.md` + `docs/decisions/decision-019.md`.
