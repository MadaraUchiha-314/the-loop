# Verification evidence — issue-224

The testing plan ([`../testing-plan.md`](../testing-plan.md)) executed, one section per
row. Every command was run from the repository root in this checkout on 2026-08-14. No
output below carries a token, a credential, a personal path or an internal hostname;
absolute paths are repository-relative.

## T1 — schema validation (`make validate`)

```console
$ make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

The edited schema is itself a valid draft 2020-12 schema, and the new property carries the
default the ticket asked for:

```console
$ uv run python -c '<check_schema + read the new property>'
schema default    : docs/learnings | type: string
config value      : docs/learnings
```

## T2, T4 — config parity and the CLI read surface

```console
$ uv run --project cli python -m pytest -q cli/tests/test_harness_config.py \
      cli/tests/test_manifest_schemas.py cli/tests/test_docs_parity.py
..................................................                       [100%]
50 passed in 0.55s
```

`test_harness_config.py` carries both the byte-parity assertion (T2) and H1–H4 (T4):
`READS` still resolves against the edited schema and did not grow, so the CLI gained no
read of `learningsDir` (NFR-2). The parity is also checked directly:

```console
$ cmp skills/the-loop/templates/harness-config.yaml cli/the_loop/harness-config.default.yaml
byte-identical
```

## T3 — manifest ↔ schema mapping

Covered by `cli/tests/test_manifest_schemas.py` in the run above: every shipped config
still resolves to its schema and validates against it after the `knowledge` paths moved.

## T5 — docs↔code parity

`cli/tests/test_docs_parity.py` in the run above: P1–P5 pass with the documentation edits
in place.

## T6 — full suite (`make test`)

```console
$ make test
uv run --project cli python -m pytest -q cli
........................................................................ [100%]
1965 passed, 1 skipped in 81.36s (0:01:21)
```

Same counts as the pre-change baseline on `main` (1965 passed, 1 skipped) — nothing in the
suite depended on the moved path or on the schema's shape.

## T7 — lint, format, types

```console
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 637 file(s)
Summary: 0 error(s)

$ make format-check typecheck
uv run ruff format --check cli hooks
206 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

markdownlint covers the moved learnings files and every new document in this spec chain.

## T8 — reference sweep for the pre-move path

```console
$ git grep -n "learnings/" -- . ':!docs/specs/' ':!docs/learnings/' \
    | grep -v "docs/learnings/" | grep -v "learnings-pending"
commands/init.md:2: … (updated: now names the docs trees, not a root-level learnings/)
commands/upgrade-the-loop.md:108,110: the relocation paragraph, which must name the old path
docs/capabilities/spec-workflow.md:145: the history row, which must name the old path
docs/decisions/decision-012.md:22: a 2026-07-01 decision record — the historical record
docs/guide/how-it-works.md:80: the docs/ tree listing, i.e. "docs/" + "  learnings/"
```

Every surviving occurrence is one of three intended kinds: prose that must name the old
location to describe the move (the upgrade paragraph, the capability history row), the
historical record (`docs/decisions/decision-012.md`, and `docs/specs/**` which is excluded
for the same reason), or the new path itself matching the pattern. No rule, scaffold step
or manifest entry still points at the pre-move location.

Links inside the moved tree resolve:

```console
$ for f in $(grep -o "learning-00[0-9].md" docs/learnings/learnings.md | sort -u); do
      test -f "docs/learnings/$f" && echo "OK  docs/learnings/$f"; done
OK  docs/learnings/learning-001.md   … through …   OK  docs/learnings/learning-007.md
```

## T9 — an already-adopted project is not broken

```console
$ uv run python -c '<load config, delete workflow.learningsDir, validate; then set "learnings">'
omitted-key config: VALID
pinned 'learnings': VALID
```

A config that never heard of the key stays valid (no migration, no version bump), and a
project that pins the old location with `workflow.learningsDir: learnings` validates too —
the two outcomes `/the-loop:upgrade-the-loop` now presents (R5.1). The command's text was
reviewed against R5.2: it presents both, moves nothing without confirmation, and states
why this is not a `manifest.deprecated` entry.

## T10 — the move preserved history

```console
$ git status --short | grep '^R'
R  learnings/learning-001.md   -> docs/learnings/learning-001.md
R  learnings/learning-002.md   -> docs/learnings/learning-002.md
R  learnings/learning-003.md   -> docs/learnings/learning-003.md
R  learnings/learning-004.md   -> docs/learnings/learning-004.md
R  learnings/learning-005.md   -> docs/learnings/learning-005.md
R  learnings/learning-006.md   -> docs/learnings/learning-006.md
R  learnings/learning-007.md   -> docs/learnings/learning-007.md
R  learnings/learnings.md      -> docs/learnings/learnings.md
RM learnings/topics/README.md  -> docs/learnings/topics/README.md
```

Nine renames, not nine deletes plus nine adds. `topics/README.md` is `RM` because its two
path references were rewritten to `<learningsDir>` in the same change.

## T15 — security review

Reviewed against [`../requirements.md`](../requirements.md) §Security considerations. The
claim "no new attack surface" is carried by an assertion rather than by assertion-in-prose:
H1–H4 in `test_harness_config.py` (T4) fail if `READS` grows, and `READS` is unchanged, so
no CLI code path resolves `learningsDir` and there is no new parser, writer or process
boundary. Abuse cases 1 and 2 rest on the committed-and-reviewed config boundary that
`specDir` and `capabilitiesDir` already sit behind; abuse case 3 (the default placing
learnings inside a published `docs/` tree) is disclosed in three places an operator reads
before adopting — the schema description, `reference/automation.md` §Self-improvement and
`docs/config/harness-config.md`.

## T18 — manual read-through

The moved tree was read as a reader would: `docs/learnings/learnings.md`, each of its
seven records, and `docs/learnings/topics/README.md`, whose two path references now name
`<learningsDir>` and point at the key that placed the directory.

The move puts the learnings inside the VitePress `srcDir`, so they are now **published**
pages. That is deliberate (decision-082) and is wired into the site's authored IA rather
than left unreachable — a `Learnings` group in the developer sidebar, a `Learnings` entry
under the `Developer` nav menu, and `/learnings/` mapped to the developer sidebar. The
site build was run to confirm:

```console
$ cd docs && bun install --frozen-lockfile && bun run docs:build
docs: synced skills/the-loop/reference/ -> docs/operating-model/reference/
vitepress v1.6.4
✓ building client + server bundles...
✓ rendering pages...
build complete in 41.80s.

$ ls docs/.vitepress/dist/learnings/
learning-001.html … learning-007.html  learnings.html  topics/
```

The generated spec sidebar is unaffected — it reads `docs/specs/` only.

## Rows not run

T11 (integration), T12 (e2e), T13 (UI/visual), T14 (performance), T16 (accessibility) and
T17 (snapshot) are marked `n/a` in the testing plan, each with its reason. Nothing in the
plan was skipped for want of an environment.
