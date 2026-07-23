---
type: requirements
phase: requirements-definition
workItem: issue-70
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #70 body, 2026-07-23)"]
collaborators: [product-manager, architect, technical-writer]
overrides: {}
---

# Requirements: documentation site for the-loop

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Ticket:
> [issue #70](https://github.com/MadaraUchiha-314/the-loop/issues/70).
>
> **Note on sequencing:** this spec was authored **retroactively**, during PR #71's
> review, after the owner asked "where are the requirements.md/design.md for this
> work?". The-loop dogfoods its own 3-phase workflow; this backfills the paper trail so
> this work item conforms like any other. See `execution-log.md` for the honest
> timeline.

## Introduction

the-loop has accumulated substantial documentation (`README.md`, `cli/README.md`,
`docs/architecture/`, `docs/capabilities/`, `docs/decisions/`, `docs/specs/`, and
the operating-model reference under `skills/the-loop/reference/`), but no browsable
product-documentation **site** — a reader has to navigate the repo tree. This work item
stands up a static documentation site (installation, quickstart, reference, a CLI page,
and developer docs), deployed to GitHub Pages and rebuilt on merge to `main`.

Owner constraints from the issue, treated as hard requirements:

- Use a good static documentation site generator (VitePress named as the reference).
- Model the information architecture on https://vite.dev/guide/.
- Bare-minimum good-looking template — **no fancy animations or custom CSS**.
- **All content MUST be Markdown.**
- **Do not maintain two toolchains** (Python + JS) for authoring — if a JS-based tool
  is adopted, that is acceptable, but it must not fork the authoring workflow.
- **Existing docs MUST be reused/ported, not duplicated.** (Reinforced in PR #71
  review: "I don't want contents to be duplicated" — the site must consume the existing
  `docs/` tree, not copy it into a parallel folder.)

## Requirements

### Requirement 1 — a browsable documentation site

**User story:** As a prospective or current the-loop user, I want a browsable
documentation site with clear sections, so that I can learn and use the-loop without
reading the repository tree.

#### Acceptance criteria (EARS)

1. WHEN the site is built THEN it SHALL present distinct **Guide**, **Reference**,
   **CLI**, and **Developer** sections navigable from a top nav and a sidebar.
2. WHEN a reader opens the Guide THEN it SHALL cover, at minimum, what the-loop is,
   installation, a quickstart, and how it works.
3. WHEN a reader opens the Reference THEN it SHALL document the plugin commands and the
   configuration surface.
4. The information architecture SHALL follow the shape of https://vite.dev/guide/
   (landing page → guide → reference), per the issue.

### Requirement 2 — Markdown-only, single toolchain

**User story:** As a maintainer, I want all documentation authored in Markdown with a
single site toolchain, so that contributing docs stays trivial and the repo doesn't
carry two competing authoring stacks.

#### Acceptance criteria (EARS)

1. All site content pages SHALL be Markdown.
2. The site generator SHALL be a static-site generator (VitePress, per the issue).
3. WHEN the site toolchain is added THEN it SHALL be scoped to the documentation site
   only and SHALL NOT change the CLI's Python toolchain (`decision-030` keeps the CLI
   in Python).
4. The template SHALL use the generator's default theme with **no custom
   animations/CSS** beyond configuration.

### Requirement 3 — reuse existing docs, do not duplicate

**User story:** As the repository owner, I want the site to consume the docs that
already exist in `docs/`, so that there is one source of truth and no
duplicated-and-drifting copy.

#### Acceptance criteria (EARS)

1. The site's source directory SHALL be the existing `docs/` tree; `docs/architecture/`,
   `docs/capabilities/`, `docs/decisions/`, `docs/specs/` and `docs/reports/` SHALL be
   rendered **in place** as site pages, not copied to a second location.
2. WHEN a canonical doc must physically live outside `docs/` for a functional reason
   (`cli/README.md` is the CLI's PyPI package readme; `skills/the-loop/reference/*.md`
   is read at runtime by the harness from that path) THEN it MAY be synced into the
   site at **build time** from its canonical location, and the synced copy SHALL be
   git-ignored (the canonical file remains the single source of truth).
3. The site SHALL NOT introduce a parallel top-level folder that re-hosts a copy of the
   `docs/` content. (PR #71 review requirement.)
4. Per-work-item spec artifacts (`docs/specs/<id>/`) and reports (`docs/reports/`) SHALL
   be included in the built site with navigation; the `docs/specs/` sidebar SHALL be
   generated from the filesystem so new work items appear without manual nav upkeep.
   (PR #71 review: "why are we excluding docs and reports … we should keep it.")

### Requirement 4 — automated deployment to GitHub Pages

**User story:** As a maintainer, I want the site to publish itself on merge to `main`,
so that documentation stays current without a manual release step.

#### Acceptance criteria (EARS)

1. WHEN a commit is pushed to `main` that touches documentation sources THEN a GitHub
   Actions workflow SHALL build the site and deploy it to GitHub Pages.
2. The deployment SHALL use GitHub's first-party Pages actions
   (`configure-pages`/`upload-pages-artifact`/`deploy-pages`) with OIDC, no stored
   token.
3. WHILE a deploy is in progress a newer push SHALL supersede it (single-flight
   concurrency), so `main` and the published site do not diverge.
4. The workflow SHALL use **bun** (the-loop's declared TS package manager,
   `tooling.packageManager.ts`) to install and build, so the docs toolchain matches the
   repo's own TS tooling contract rather than introducing a separate one.

### Requirement 5 — no local-vs-CI drift, existing gates stay green

**User story:** As a maintainer, I want the site to fit the existing quality gates, so
that adding it doesn't weaken or bypass the checks the-loop already enforces.

#### Acceptance criteria (EARS)

1. WHEN `pre-commit run --all-files` runs THEN all existing gates (ruff, pyright,
   pytest, markdownlint, schema validation) SHALL pass with the site added.
2. Build-time synced/generated files SHALL be excluded from markdownlint (the canonical
   source is linted, not the copy) and from version control.
3. The site SHALL build cleanly (`bun run docs:build`) with no unresolved internal
   links to site pages.
4. The site's scripts SHALL be **TypeScript** (`.mts`), not JavaScript, run directly by
   bun (native type stripping — no compile step). (PR #71 review: "NO JS. Only TS.")

## Non-functional requirements

- **Minimal footprint:** the site is a self-contained bun project under `docs/`; it
  adds no runtime dependency to the CLI or plugin.
- **Reproducibility:** a committed `bun.lock` and `bun install --frozen-lockfile` in CI
  pin the build.
- **Accessibility/responsiveness:** inherited from VitePress's default theme (light/dark,
  responsive) — no bespoke work required by the issue.

## Security considerations

> Threat-model-lite (`security.threatModel.required`).

- **Actors & trust:** readers are anonymous consumers of a **public, static** site;
  there is no authenticated surface, no user input, no server. The build runs in CI
  from repository content only.
- **Trust boundaries & data:** the only privileged step is the Pages **deploy**, which
  uses GitHub Actions OIDC (`id-token: write`, `pages: write`) — no long-lived secret is
  stored or exposed. No secrets, tokens, or PII are read or emitted by the build.
- **Abuse cases (EARS):**
  1. WHEN the build runs THEN it SHALL consume only in-repo content and SHALL NOT fetch
     untrusted remote content at build time (self-contained pages).
- **Fail closed:** a failed build fails the workflow and publishes nothing (the previous
  deploy remains live).
- **New attack surface:** none beyond a public static site; enabling GitHub Pages is a
  one-time repository-settings act by the owner.

## Out of scope

- Custom theming, animations, or bespoke CSS (explicitly excluded by the issue).
- API reference generation from OpenAPI/GraphQL contracts (no such contracts exist yet;
  the `apiSpecs` config anticipates them — future work).
- Versioned/multi-version docs, i18n, search analytics.
- A custom domain (the default `github.io/the-loop/` base is used).
- Migrating or restructuring the canonical docs' content itself (only their
  presentation as a site).

## Open questions

- **Enabling GitHub Pages** (Settings → Pages → Source: GitHub Actions) is a
  repository-settings action the automation cannot perform; the owner must toggle it
  once for the deploy job to publish. Flagged on PR #71.
