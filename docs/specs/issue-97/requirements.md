---
type: requirements
phase: requirements-definition
workItem: "issue-97"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: PyYAML is a required runtime dependency of the CLI

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

[Issue #97](https://github.com/MadaraUchiha-314/the-loop/issues/97) asks that
`pyyaml`, today declared under `[project.optional-dependencies].config` in
`cli/pyproject.toml`, become a **required** dependency.

The extra dates from [decision-005](../../decisions/decision-005.md), which
established the CLI with a "zero runtime dependencies (stdlib only)" guarantee and
made PyYAML an optional extra "used only to read `.the-loop/config.yaml` defaults".
That framing has been overtaken by what the CLI became. Every YAML read is now
guarded by a `try: import yaml / except ImportError: return {}` fallback, and each
of those fallbacks silently degrades a load-bearing feature:

| Site | What silently degrades without PyYAML |
|---|---|
| `cli_config.load_cli_config` | The **entire CLI config** (`webhooks`, `polling`, `eventLog`) reads as `{}`. `poll` finds **no `polling.sources`** and exits 1; `gh-webhook` binds built-in host/port with no configured secret env, no routing, and an empty `routing.authorizedUsers`. |
| `eventlog.load_config` | `eventLog` reads as `{}`; the structured JSONL audit trail the `events` command queries falls back to defaults. |
| `commands/scenarios._load_config_globs` | `testing.integrationTestGlobs` reads as `[]`; `the-loop scenarios` scans built-in default globs instead of the project's. |

The **cause** is silent by construction — `cli_config` logs the missing import at
`debug`, `eventlog` does not log it at all — so what the operator gets is a
downstream message that actively misdirects:

```text
no polling sources configured — add entries under polling.sources
in the CLI config (~/.the-loop/cli-config.yaml, e.g. provider: github)
```

…printed against a file that is present and *does* list sources. Same for
`gh-webhook`: "no authorizedUsers configured — the receiver will act on NO
human-authored events until you set `webhooks.ghWebhook.routing.authorizedUsers`",
naming a key the operator has already set. Nothing anywhere names PyYAML.

The three long-running daemon commands (`gh-webhook`, `poll`, and the dispatch path
they share) are **unusable** without the config file, and the config file is YAML.
PyYAML is not optional in practice; it is only optional on paper.

`pip install the-loopy-one` (the documented install line, without `[config]`)
therefore installs a CLI whose primary commands cannot be configured. Making the
dependency required aligns the declared contract with the real one and lets the
three fallback branches — and the ambient "the CLI must work with zero runtime
deps" reasoning attached to them — be deleted rather than maintained.

This reverses one clause of decision-005 (and the "zero runtime dependencies"
restatement in [decision-030](../../decisions/decision-030.md) § Context). It does
**not** reverse the rest: Python stays the language, the core stays stdlib-only
apart from this one dependency, and no framework is adopted.

## Requirements

### Requirement 1 — PyYAML is declared as a required dependency

**User story:** As an operator running `pip install the-loopy-one`, I want the CLI
to be able to read its config out of the box, so that `poll` and `gh-webhook` work
without my discovering an undocumented extra.

#### Acceptance criteria

1. **1.1** WHEN the distribution's metadata is built THEN `pyyaml>=6` SHALL appear
   in `[project].dependencies` of `cli/pyproject.toml` and SHALL NOT be the content
   of any optional extra.
2. **1.2** WHEN a user installs `the-loopy-one[config]` (the previously documented
   line) THEN the install SHALL still succeed and resolve PyYAML — the `config`
   extra SHALL be **retained as an empty, deprecated alias** rather than removed,
   so an existing install command, script or Dockerfile does not start emitting
   pip's "does not provide the extra" warning.
3. **1.3** The version floor SHALL stay `>=6` with no upper bound, matching the
   pre-existing declaration; the repo's `uv.lock` SHALL be refreshed so the locked
   workspace resolves PyYAML for the `cli` member as a runtime dependency.
4. **1.4** The dependency SHALL remain compatible with the package's declared
   `requires-python = ">=3.9"`.

### Requirement 2 — the optional-import fallbacks are removed, not left dormant

**User story:** As a maintainer, I want exactly one way for YAML loading to behave,
so that no code path can silently return empty config.

#### Acceptance criteria

1. **2.1** WHEN any of the three YAML-reading sites runs (`cli_config.load_cli_config`,
   `eventlog.load_config`, `commands/scenarios._load_config_globs`) THEN it SHALL
   import `yaml` at module scope and SHALL NOT contain an `ImportError` fallback.
2. **2.2** The **non-import** leniency SHALL be preserved exactly as it is today: a
   missing file, and (with `strict=False`) an unparseable one, still degrade to
   `{}`/`[]` with the existing log line, so a broken hand-edit never breaks ingress.
3. **2.3** `load_cli_config(strict=True)` SHALL keep raising on a missing file and
   on a `YAMLError`, so `the_loop.reload.Reloader` keeps the previously loaded
   config across a transient broken save. Only the `ImportError` re-raise — which
   can no longer occur — SHALL go.
4. **2.4** No observable behaviour SHALL change for an environment that **has**
   PyYAML installed; the entire delta is the behaviour of an environment that does
   not, which is no longer a supported environment.

### Requirement 3 — the documented contract matches the code

**User story:** As a reader of the-loop's docs, I want the dependency story stated
once and correctly, so that "zero runtime dependencies" does not survive as a claim
the package no longer meets.

#### Acceptance criteria

1. **3.1** A **new decision record** SHALL be added recording the reversal, listing
   what forced it, what is retained from decision-005, and the alternatives
   rejected; it SHALL be indexed in `docs/decisions/decisions.md`.
2. **3.2** [decision-005](../../decisions/decision-005.md) and
   [decision-030](../../decisions/decision-030.md) SHALL carry a **superseded-in-part**
   pointer to the new record rather than being silently rewritten — the decision log
   is append-mostly, and the historical reasoning stays readable.
3. **3.3** Every prose claim of "zero runtime dependencies" / "stdlib-only" about
   the CLI SHALL be corrected to name the single dependency:
   `cli/pyproject.toml`, `cli/README.md`, root `README.md`,
   `docs/architecture/architecture.md`, `docs/capabilities/cli.md`,
   `skills/the-loop/reference/automation.md`, and the module docstrings that carry
   the reasoning (`cli_config.py`, `commands/gh_webhook.py`, `commands/scenarios.py`,
   `webhook/__init__.py`).
4. **3.4** `cli/README.md`'s two install lines SHALL stop advertising `[config]` as
   the way to get YAML support, while noting that the extra still resolves for
   anyone who has it in a script.
5. **3.5** The affected capability doc (`docs/capabilities/cli.md`) SHALL be updated
   in the same PR — its `SHALL have zero runtime dependencies` behaviour bullet is
   now false — with a history row pointing at this spec and the new decision.
6. **3.6** Statements that remain **true** SHALL NOT be churned: decision-016's
   "subprocessing the vendor CLIs keeps the zero-runtime-dependency guarantee" and
   decision-025's "both fit the zero-runtime-dependency rule (`sqlite3` …)" describe
   choices that were correct when made and are unaffected by adding PyYAML; they are
   covered by the supersede pointer, not edited.

### Requirement 4 — the change is covered by tests

1. **4.1** A test SHALL assert the **installed distribution metadata** requires
   PyYAML (`importlib.metadata.requires("the-loopy-one")`), so a future edit that
   demotes it back to an extra fails the suite rather than silently shipping.
2. **4.2** The existing YAML-reading tests (`test_cli_config.py`, `test_cli.py`,
   `test_eventlog.py`) SHALL stay green unchanged, evidencing R2.4.

## Security considerations (threat-model-lite)

- **New attack surface: one added dependency.** This is the substantive security
  fact of the change and is stated, not implied. PyYAML enters the *installed*
  dependency tree of the published package where before it was opt-in. Its own
  supply chain (a widely used, actively maintained library, pinned by `uv.lock` for
  this repo and floor-pinned `>=6` for consumers) is the risk accepted. No
  transitive dependencies are pulled in — PyYAML has none.
- **Parsing is unchanged and already safe.** Every call site uses
  `yaml.safe_load`, never `yaml.load`, so no constructor/`!!python/object` gadget
  is reachable. This change adds **no new call site** — it removes import guards
  around three existing ones. The `>=6` floor keeps the package above the
  CVE-2020-14343 (`full_load`/`FullLoader` RCE) line, which was fixed in 5.4.
- **Input trust is unchanged.** The files parsed are the operator's own local
  config (`~/.the-loop/cli-config.yaml`, the repo's `.the-loop/harness-config.yaml`)
  — never webhook payloads, ticket bodies, or any network-supplied bytes. No
  untrusted actor gains a parser they did not already reach.
- **The prompt-injection guard already fails closed, and stays that way.**
  `routing.authorizedUsers` (decision-023) lives in the CLI config, so a missing
  PyYAML currently hands the guard an empty allow-list — but `is_authorized`
  treats an empty allow-list as **deny-every-human-authored-action**, not
  allow-all, and `gh-webhook` warns about it at startup. So the pre-change
  behaviour was an availability failure, **not an open guard**, and this change
  does not close a hole. What it removes is the *misleading diagnostic*: the
  operator is no longer told to configure a key they have already configured.
  This is stated explicitly because the tempting version of this argument —
  "required PyYAML fixes a security bug" — is not true and should not be
  believed on the strength of the change.
- **Fail-loud is the intended trade.** A missing PyYAML now raises `ImportError` at
  import time instead of degrading to defaults. That is strictly preferable to the
  status quo for a daemon whose whole configuration is the file it could not read,
  and it cannot occur in a correctly installed environment (R1.1).
- **Risk tier 3** (`human-approves-pr`), below `security.review.humanSignOffMinTier: 4`
  — no named human security sign-off required. No file under
  `autonomy.sensitivePaths` is touched (no `*schema*`, no `.github/workflows/**`).

## Out of scope

- Adding any **other** runtime dependency. The ladder in
  `reference/minimalism.md` still applies to the next one, and this record is not a
  precedent for "dependencies are fine now".
- Replacing PyYAML with a different parser (e.g. `ruamel.yaml`, or a stdlib-only
  subset parser) — considered and rejected in the decision record.
- Vendoring PyYAML into the package.
- The **dev** dependency group in the root `pyproject.toml`, which already lists
  `pyyaml` for the repo's own tooling and is unaffected.
- Any change to *what* the CLI reads from YAML, or to the two-config split
  (decision-032).
