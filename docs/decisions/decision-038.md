# Decision 038: PyYAML is a required runtime dependency of the CLI — the "zero runtime dependencies" guarantee is retired

- **Status:** proposed
- **Date:** 2026-07-25
- **Deciders:** @MadaraUchiha-314 (issue #97)
- **Work item:** issue-97
- **Spec:** `docs/specs/issue-97/`
- **Revisits:** [decision-005](decision-005.md) (zero runtime dependencies) and
  [decision-030](decision-030.md) § Context, which restated it — **superseded in
  part**: only the zero-dependency clause, not the Python choice or the
  stdlib-first posture.

## Context

Issue #97: *"pyyaml shouldn't be optional dependency — make it a required
dependency."*

decision-005 established the CLI in 2026-06-30 with **zero runtime dependencies
(stdlib only)**, PyYAML being an optional `[config]` extra "used only to read
`.the-loop/config.yaml` defaults". At the time that was accurate: the CLI was a
webhook receiver configured by flags, and the config file was a convenience.

What the CLI became is a different program. It now has three long-running daemon
commands (`gh-webhook`, `poll`, and the dispatch stack they share) whose entire
behaviour comes from a **YAML** file — `cli-config.yaml` for the daemons
(decision-032), `harness-config.yaml` for `scenarios`. Every read of that file is
behind a `try: import yaml / except ImportError: return {}` guard, and each guard
degrades a load-bearing feature **silently**:

| Site | What silently degrades without PyYAML |
|---|---|
| `cli_config.load_cli_config` | The whole CLI config reads as `{}`. `poll` finds **no `polling.sources`** and exits 1; `gh-webhook` gets no configured secret env, no routing, and an empty `routing.authorizedUsers` (decision-023's prompt-injection allow-list). |
| `eventlog.load_config` | `eventLog` reads as `{}`; the JSONL audit trail falls back to defaults. |
| `commands/scenarios._load_config_globs` | `testing.integrationTestGlobs` reads as `[]`; built-in globs are scanned instead of the project's. |

One of those logs the missing import at `debug`; the others not at all. What the
operator sees is a downstream message that **actively misdirects** — `poll` exits
with *"no polling sources configured — add entries under `polling.sources` in the
CLI config (`~/.the-loop/cli-config.yaml`)"* against a file that exists and lists
sources; `gh-webhook` warns *"no authorizedUsers configured"* about a key that is
set. Nothing names PyYAML.

So the documented install line (`pip install the-loopy-one`, without the extra)
produces a CLI whose primary commands cannot be configured and whose error messages
send the operator to fix config that is already correct. The "guarantee" is a
promise about a configuration nobody can usefully run.

## Decision

**Make `pyyaml>=6` a required runtime dependency of `the-loopy-one`, delete the
three optional-import fallbacks, and retire the zero-runtime-dependency
guarantee** — replacing it with a weaker, honest and still meaningful rule:

> The CLI has **exactly one** runtime dependency, PyYAML, because its entire
> configuration is YAML. Everything else is stdlib, and the minimalism ladder
> (`reference/minimalism.md`) governs any future addition as strictly as before.

Specifics:

- `[project].dependencies = ["pyyaml>=6"]`. The floor is the one already declared
  and sits above the CVE-2020-14343 (`FullLoader` RCE) line fixed in 5.4; PyYAML 6
  supports Python ≥3.6, so `requires-python = ">=3.9"` is unaffected. PyYAML has no
  transitive dependencies.
- The `config` extra is **kept as an empty, deprecated no-op**, so a pinned
  `pip install "the-loopy-one[config]"` in someone's script or Dockerfile keeps
  resolving instead of emitting pip's "does not provide the extra" warning. It can
  be dropped at a future major.
- The three `try/except ImportError` guards go; `import yaml` moves to module
  scope. The **non-import** leniency is untouched: a missing file, and (lenient
  path) an unparseable one, still degrade to `{}`/`[]` with the existing log line,
  and `strict=True` still raises so `Reloader` retains the last good config across
  a transient broken save.
- Docstrings and docs that asserted the old guarantee are corrected rather than
  left to rot.

## Consequences

- `pip install the-loopy-one` now yields a CLI that can actually read its config.
  The failure mode "configured daemon silently does nothing" is gone.
- **Not a security fix, and should not be cited as one.** `routing.authorizedUsers`
  could be emptied by the degradation, but an empty allow-list **denies** every
  human-authored action (`authz.is_authorized` fails closed) and `gh-webhook` warns
  at startup. The guard was never open. What this change removes is a misleading
  diagnostic, not an exposure.
- **No new parser surface.** All three sites already used `yaml.safe_load`, never
  `yaml.load`; this change adds no call site, it removes guards around existing
  ones. The bytes parsed are operator-local config files — never webhook payloads
  or ticket text, which go through stdlib `json`.
- One dependency enters the installed tree of the published package. Pinned exactly
  in the committed `uv.lock` for this repo and CI (decision-009's no-drift rule), so
  a supply-chain change is a reviewable lockfile diff.
- `import yaml` (~10–15 ms) is now paid on any invocation that touches config,
  inside the noise of CPython's ~120–250 ms cold start measured in decision-030 § 1.
  decision-030's lever 2 (lazy-import command modules) remains available.
- Decisions whose reasoning invoked the old rule but whose **conclusions are
  unaffected** are deliberately not edited: [decision-016](decision-016.md)
  (subprocessing the vendor CLIs), [decision-025](decision-025.md) (JSONL over
  SQLite) and [decision-019](decision-019.md)'s release-pipeline note all describe
  choices that were right under the rule in force and stay right without it. This
  record is the pointer that tells a reader the rule later moved.
- This is **not** a precedent for adding dependencies freely. The minimalism ladder
  still applies; the next dependency needs its own justification in a `design.md`.

## Alternatives considered

- **Delete the `config` extra outright** — rejected: every pinned
  `pip install "the-loopy-one[config]"` starts printing a pip warning, for no gain.
  An empty extra is one line and removable at a major.
- **Add the required dep but keep the fallbacks** — rejected: the dead branches and
  the docstrings asserting a retired guarantee are exactly the maintenance cost the
  issue is aimed at.
- **Stay optional; make the daemons fail loudly when PyYAML is missing** — rejected:
  keeps the branches, *adds* error-handling code, and still ships a package whose
  documented install line cannot be configured. More code, worse outcome.
- **Hand-roll a stdlib YAML subset parser** — rejected by the minimalism ladder
  itself, which ends at "existing dep" before "new abstraction". A hand-rolled YAML
  parser (anchors, merge keys, quoting, multiline scalars) is a correctness and
  security liability well beyond one well-known dependency.
- **Move the config format to JSON/TOML to preserve zero deps** (`tomllib` is stdlib
  from 3.11) — rejected: `requires-python` is `>=3.9`, so `tomllib` is not
  universally available, and it would break every `.the-loop/*.yaml` in the wild
  plus the schemas, templates and `/the-loop:init` — an enormous change to defend a
  guarantee that buys nothing.
- **`ruamel.yaml`** — rejected: heavier, and its round-trip comment preservation is
  irrelevant to a CLI that only reads.
- **Vendor PyYAML** — rejected: it carries a C extension, and vendoring forfeits the
  security updates that are the main reason to depend on a maintained parser.
