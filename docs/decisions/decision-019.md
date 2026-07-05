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
`.github/workflows/release.yml`, released **automatically on merge to `main`** with
**semantic versioning derived from Conventional Commits** (owner request, PR #22).

Three names are kept deliberately distinct:

| Name kind         | Value           | Where it shows up                 |
|-------------------|-----------------|-----------------------------------|
| distribution (PyPI) | `the-loopy-one` | `pip install the-loopy-one`       |
| import package    | `the_loop`      | `import the_loop`                 |
| console script    | `the-loop`      | `the-loop --help`                 |

Only the distribution name is affected by the PyPI collision; the import package and CLI
command keep the natural `the_loop`/`the-loop`, so user-facing ergonomics are unchanged.

### Release trigger — semantic, on merge to main (revised on PR #22)

The **first design** cut releases manually (publish a GitHub Release → build → publish).
The owner asked for **semantic-release** instead: version bumps derived from PR titles /
commit types, published automatically. Adopted model:

- **Engine: commitizen (`cz bump`)** — the tool the-loop already standardised on
  (decision-008), so no second release tool is introduced. It reads the Conventional
  Commits since the last tag and applies `feat → minor`, `fix → patch`,
  `BREAKING CHANGE`/`!` → major. With squash-merge the squash commit is the PR title, so
  this is exactly "versioned by PR titles".
- **Trigger: `push` to `main`.** On each merge, the `release` job runs `cz bump`, which
  rewrites the version in `.cz.toml` **and** `cli/pyproject.toml` (`version_files`),
  commits `bump: …`, tags `v<version>`, and generates the changelog. The job pushes the
  bump commit + tag back to `main`, cuts a GitHub Release (`gh release create
  --generate-notes`), and builds the distribution. The `publish-pypi` job — gated by the
  `pypi` environment with `id-token: write` — uploads via `pypa/gh-action-pypi-publish`.
- **No-op when nothing is releasable.** If no commit since the last tag warrants a bump,
  `cz bump` exits `21`/`3` (NoneIncrementExit / NoCommitsFoundError) and the run publishes
  nothing. The self-push of the `bump:` commit does not recurse: pushes authenticated with
  `GITHUB_TOKEN` don't re-trigger `on: push`, and an explicit `if: !startsWith(…, 'bump:')`
  guard makes that intent explicit.
- **Operational prerequisite:** the `release` job pushes to `main`, so if `main` is a
  protected branch the repo must allow `github-actions[bot]` to bypass the protection (or
  swap in a bot PAT). Trusted-Publishing identity is unaffected — the workflow filename
  (`release.yml`) and environment (`pypi`) are unchanged, so the registered publisher
  still matches.

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
- **Releases are automatic on merge to `main`.** Every merge whose commit type is
  `feat`/`fix`/breaking cuts a new version + PyPI release; docs/chore/refactor-only merges
  publish nothing.
- `.cz.toml` gains `version_files` (so a bump rewrites the package version) and a
  generated `CHANGELOG.md` appears at the repo root, committed by the release job.
- The release job pushes the bump commit + tag to `main`; in practice `github-actions[bot]`
  was able to push to `main` directly (no branch-protection bypass was needed).

### Post-merge fixup (issue #21 follow-up)

The first release run (on the issue-21 merge) **bumped `main` to `0.2.0` but published
nothing**: `git push --follow-tags` pushes only *annotated* tags, while commitizen creates
a *lightweight* one, so `v0.2.0` never reached the remote and `gh release create
--verify-tag` aborted. Two workflow fixes (this follow-up PR):

1. **Push the tag explicitly** — `git push origin HEAD:refs/heads/main refs/tags/v<version>`
   instead of `--follow-tags`.
2. **First-release baseline bootstrap** — when no `v*` tag exists, tag the version already
   in the repo on `HEAD^` before bumping, so `cz bump` computes the increment from the
   commits merged since (not the whole history). It runs exactly once.

Because `main` already sits at `0.2.0` (files) with a seeded `v0.2.0` baseline, the next
release is a **patch → `0.2.1`**, which is the first version actually uploaded to PyPI.
`0.1.0`/`0.2.0` remain un-uploaded baselines.

## Alternatives considered

- **Store a PyPI API token as a GitHub secret** — rejected: long-lived credential, exactly
  what Trusted Publishing (already registered) removes.
- **Publish the whole workspace / the virtual root** — not possible/meaningful: the root is
  a virtual workspace with no `[project]`; only members are distributions.
- **Rename the import package / CLI to `the-loopy-one`** — rejected: needlessly degrades
  ergonomics (`import the_loopy_one`, `the-loopy-one --help`) for a name collision that only
  needs to be resolved at the distribution layer.
- **Manual GitHub-Release-triggered publish (the first design)** — superseded on PR #22:
  the owner wanted zero-touch semantic releases from PR titles, not a manual Release step.
- **A dedicated semantic-release tool (`python-semantic-release`) or `release-please`** —
  rejected: commitizen is already adopted (decision-008) and does the same job; adding a
  second release tool would duplicate config and versioning authority. `release-please`'s
  release-PR model was considered (it avoids pushing to `main`) but not worth a new tool
  given the bot-bypass path is straightforward.
