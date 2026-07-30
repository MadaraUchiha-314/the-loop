---
type: requirements
phase: requirements-definition
workItem: issue-117
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review (#118) — see execution-log
collaborators: [product-manager, technical-writer, engineer]
overrides: {}
---

# Requirements: the CLI documented as a product, and the docs restructured around it

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #117](https://github.com/MadaraUchiha-314/the-loop/issues/117) — *"CLI
documentation is kind of hidden and one long unstructured file"*. The ask, in the
reporter's words: treat the CLI **like a product** (onboarding guide, quick start), give
its documentation **proper structure**, make **every part of the ecosystem easy to
onboard**, and model the result on <https://vite.dev/config/>.

### The measured gap

| | Today |
|---|---|
| CLI docs surface | **one** page, `/cli`, reached from **one** nav entry |
| Length | **679 lines** in `cli/README.md`, copied verbatim to `docs/cli.md` by `docs/scripts/sync-content.mts` |
| Onboarding | none — no "what is this", no quickstart, no concepts page |
| Per-command pages | none — nine commands share one `## Commands` heading |
| Per-config-area pages | none — the whole CLI config is one `### CLI config reference` subtree |
| Config nav section | none — vite's top-level `Config` has no counterpart here |

The structural defect **causes** a content defect. A flat file has nowhere to *put* a new
command, so new commands got no entry, and the file has drifted from the code it
describes:

- **Three of nine commands are undocumented** — `check`, `graph` and `migrate-config`,
  all shipped by issue-109 (#110). `cli/README.md` documents six.
- **Whole config blocks are undocumented** — `integrations` (github/slack/jira transport
  selection), `webhooks.ghWebhook.routing.workspace` (per-work-item checkouts, issue-76),
  `webhooks.ghWebhook.routing.graph` (issue-113), `polling.maxRetries` (issue-80).
- **Documented config no longer exists** — `ghBinary` appears in **5** places in
  `cli/README.md` and **0** places in `.the-loop/cli-config.schema.json`; issue-109
  replaced it with `integrations.github.cli.binary`. An operator following the README
  today writes a key the CLI ignores.

So the restructure is not cosmetic: **the shape is why the content is wrong**, and
re-homing a page that misdescribes the product would leave the defect in place.

### Constraint that shapes the solution

`cli/README.md` cannot simply be deleted or split in place: it is the **PyPI package
readme** (`cli/pyproject.toml` → `readme = "README.md"`), so it must remain a valid,
useful standalone document rendered on the package page.

## Requirements

### Requirement 1 — the CLI has an onboarding path of its own

**User story:** As an operator who has just heard the-loop has a CLI, I want a *what it
is → install → first run → how it works* path, so that I can get from nothing to a
working daemon without reading a 679-line reference.

#### Acceptance criteria (EARS)

1. WHEN a reader opens the documentation site THEN the system SHALL present the CLI as a
   top-level navigation section, not a single page nested behind another section.
2. WHEN a reader enters the CLI section THEN the system SHALL offer, as distinct pages,
   an **overview** ("what is it, when do you need it"), an **installation** page, a
   **getting-started** quickstart, and a **concepts** page.
3. WHEN a reader follows the getting-started page from top to bottom THEN the system
   SHALL take them from an uninstalled CLI to a work item that an authorized comment can
   start, with every step given as a runnable command or a copyable config fragment.
4. WHEN the getting-started page instructs the reader to configure the CLI THEN the
   system SHALL state where the config file must live (all four resolution positions) and
   SHALL show a minimal working `cli-config.yaml`, not a partial fragment.
5. WHEN a reader finishes any onboarding page THEN the system SHALL link the next step
   explicitly, so the path is walkable without using the sidebar.

### Requirement 2 — every command is documented on its own page

**User story:** As an operator debugging a daemon at 2am, I want one page per command
with its synopsis, flags and behaviour, so that I can find and link the exact thing I
need instead of scrolling one document.

#### Acceptance criteria (EARS)

1. WHEN a command is registered in `the_loop.commands` THEN the system SHALL document it
   on a dedicated page under the CLI section.
2. WHEN the CLI section is opened THEN the system SHALL present a **commands overview**
   page listing every command in one table with a one-line summary and a link.
3. WHEN a command page is read THEN the system SHALL give its **synopsis** (usage block),
   its **options** with types and defaults, and the **behaviour** notes an operator needs
   (guards, hot-reload, exit codes, side effects) — each option's default matching the
   value the code or the schema actually uses.
4. WHEN a command reads configuration THEN its page SHALL link the config page that
   documents those keys.
5. IF a command's behaviour is currently undocumented (`check`, `graph`,
   `migrate-config`) THEN the system SHALL document it from the implementation, at the
   same depth as the pre-existing commands.

### Requirement 3 — configuration is a top-level reference, split by area

**User story:** As an operator writing `cli-config.yaml`, I want a configuration
reference split by area with a uniform per-option format, so that I can find one option
without reading the others — the way <https://vite.dev/config/> works.

#### Acceptance criteria (EARS)

1. WHEN the site is opened THEN the system SHALL present **Config** as a top-level
   navigation section whose landing page explains the two configuration files
   (`.the-loop/harness-config.yaml`, `cli-config.yaml`) and which one governs what.
2. WHEN the CLI configuration is documented THEN the system SHALL split it into pages by
   area — receiver, routing, polling, integrations, observability — rather than one page.
3. WHEN an individual option is documented THEN the system SHALL state its **type** and
   its **default**, uniformly, for every option on every configuration page.
4. WHEN an option's default is stated THEN it SHALL equal the default declared in
   `.the-loop/cli-config.schema.json` (or, where the schema declares none, the value the
   code applies).
5. WHEN the plugin (harness) configuration is documented THEN the system SHALL place it
   in the same top-level Config section as the CLI configuration, so a reader does not
   have to know which of the two they need before they can find either.

### Requirement 4 — the documentation matches the shipped code

**User story:** As an operator, I want the documented config keys and commands to be the
ones the CLI actually reads and exposes, so that following the documentation produces a
working setup.

#### Acceptance criteria (EARS)

1. WHEN the documentation names a CLI configuration key THEN that key SHALL exist in
   `.the-loop/cli-config.schema.json`.
2. WHEN a key has been removed from the schema THEN the documentation SHALL NOT describe
   it as current; specifically the system SHALL remove every `ghBinary` reference and
   document `integrations.github.cli.binary` in its place.
3. WHEN a configuration block exists in the schema THEN the documentation SHALL cover it;
   specifically `integrations`, `webhooks.ghWebhook.routing.workspace`,
   `webhooks.ghWebhook.routing.graph` and `polling.maxRetries` SHALL be documented.
4. WHEN the CLI registers a command THEN the documentation SHALL list it; specifically
   `check`, `graph` and `migrate-config` SHALL appear in the commands overview and have
   pages.
5. WHEN documentation-vs-code parity is asserted THEN the system SHALL provide an
   **automated** check that fails when a registered command has no documentation page or
   a documented CLI-config key is absent from the schema, so this class of drift is
   caught mechanically rather than by review attention.

### Requirement 5 — `cli/README.md` becomes the package landing page

**User story:** As someone landing on the PyPI page for `the-loopy-one`, I want a short,
accurate description with an install command and a link to the full documentation, so
that I can decide in thirty seconds whether this is what I want.

#### Acceptance criteria (EARS)

1. WHEN `cli/README.md` is rendered on PyPI THEN it SHALL stand alone as a valid
   description of the package — what it is, how to install it, one runnable example — and
   SHALL NOT depend on the surrounding repository for sense.
2. WHEN `cli/README.md` refers the reader onward THEN every link into the documentation
   site SHALL be **absolute** (`https://madarauchiha-314.github.io/the-loop/…`), because a
   relative link is broken on PyPI.
3. WHEN the documentation site is built THEN the system SHALL NOT copy `cli/README.md`
   into the site, since the CLI now has authored pages.
4. WHEN `cli/README.md` is reduced THEN no operator-relevant content it carried SHALL be
   lost — every section SHALL be traceable to the page that now carries it.

### Requirement 6 — the ecosystem's entry points agree

**User story:** As a newcomer arriving from any entry point — repo README, docs home,
guide, or a capability doc — I want to be routed to the right place for what I need, so
that "easy to onboard" holds for the whole ecosystem and not just for the page I landed
on.

#### Acceptance criteria (EARS)

1. WHEN a page links to CLI documentation THEN the link SHALL resolve to the new CLI
   pages, and no link SHALL point at the removed `/cli` single page.
2. WHEN the docs home page is opened THEN it SHALL offer the CLI as a first-class
   destination alongside the plugin guide.
3. WHEN the repository `README.md` describes the CLI THEN it SHALL link the CLI
   documentation section rather than only `cli/README.md`.
4. WHEN the site is built THEN the build SHALL succeed and the markdown lint gate SHALL
   pass over every new and changed file.
5. WHEN a reader uses site search THEN each CLI command and each configuration area SHALL
   be reachable as its own result, rather than as one result for the whole CLI.

## Non-functional requirements

- **No runtime behaviour change.** This work item changes documentation, navigation and
  one build script. No Python behaviour under `cli/the_loop/` changes, so the existing
  test suite SHALL remain green unchanged, aside from the new parity test of R4.5.
- **Authoring, not generation.** Pages are checked-in markdown, not generated at build
  time from the schema. The schema is the *authority* the parity test checks against, not
  a template engine — generated option tables would lose the prose that makes the current
  README worth reading.
- **Lint parity.** Every new file passes `markdownlint` under the repo's existing
  configuration, the same command CI runs.
- **Fidelity.** Where content moves, it moves; where it is rewritten, it is rewritten
  against the code or schema. No behaviour is described from memory of the old README.

## Security considerations

> Threat-model-lite (`security.threatModel.required`).

- **Actors & trust:** readers of a public documentation site and of the PyPI package
  page. All content is authored in-repo and reviewed on the PR; there is no user input,
  no form, no runtime, and no data collected. The documentation site is statically built
  and already published by `.github/workflows/docs.yml`.
- **Trust boundaries & data:** none crossed. The one build-script change removes a file
  copy; it adds no input, no network access and no new dependency. No secret, token or
  credential is stored or moved.
- **Documentation-as-a-security-surface (the real risk here):** documentation that
  understates a security control is a security defect, because operators configure from
  it. Three controls are load-bearing and MUST survive the restructure, stated at least
  as strongly as they are today:
  1. `routing.authorizedUsers` — REQUIRED, no plugin-config fallback, **fails closed**
     when empty (decision-023).
  2. The **self-comment marker** loop-prevention guard (decision-031).
  3. Secrets come from the **environment**, never from config — `secretEnv`,
     `integrations.slack.urlEnv`, `integrations.github.api.tokenEnv` hold *variable
     names*, never values.
- **Abuse cases (EARS):**
  1. WHEN the CLI configuration is documented THEN the system SHALL NOT show a real
     secret, token or webhook URL in any example, using env-var names or obvious
     placeholders instead.
  2. WHEN `authorizedUsers` is documented THEN the system SHALL state that an empty list
     fails closed and that there is no fallback to any repository's plugin config, so a
     reader cannot conclude the guard is optional or inherited.
  3. WHEN a copyable example configuration is given THEN it SHALL NOT widen exposure by
     default — `host` stays `127.0.0.1`, `webTerminal` stays disabled — so an operator
     pasting it does not publish a terminal to their network.
- **Fail closed:** unchanged and out of scope to alter. Where the documentation describes
  a fail-closed behaviour it describes the shipped one; this work item changes no gate.

## Out of scope

- Any change to CLI runtime behaviour, configuration schema, or defaults. If the
  restructure surfaces a genuine product defect, it is filed as its own issue, not fixed
  here.
- Generating configuration pages from the JSON schema at build time (see the
  authoring-not-generation note above).
- Restructuring the operating-model reference (`skills/the-loop/reference/*`), the
  capability docs taxonomy, the decision log, or the specs section. Their **links** are
  fixed where they point at moved pages; their organisation is not touched.
- Versioned documentation, i18n, or a documentation search provider change.

## Open questions

1. **Moving `/reference/configuration` to `/config/harness-config` breaks that URL.**
   VitePress ships no redirect mechanism and this site sets `markdown.html: false`, so a
   meta-refresh stub is not available either. Assumption taken (recorded on the ticket):
   the site is recent (#71), inbound links are unlikely, and the reporter explicitly asked
   for a vite-shaped structure in which `/config/` is top-level — so the clean move is
   taken. Reversible on request.
2. **`ghBinary` is documented but absent from the schema.** Treated as documentation drift
   from issue-109, not as a regression in the CLI — the code reads
   `integrations.github.cli.binary`. Raised on the ticket; if it is in fact a lost
   migration path, that is a separate work item.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
