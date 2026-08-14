# Verification evidence — issue-220

Executed 2026-08-14 in the work item's own cloud session, against the branch
`claude/github-issue-220-3vc1hg`. Every command was run from the repository root, which is
where `make` and the configured tooling run (`repository.runScriptsFromRoot: true`).

Nothing captured here contains a secret: the commands run a test suite and linters over a
public repository, and no credential, token or environment variable is involved in this
work item at all.

## T1 — unit: adoption keeps the modeline first, and the default stays the template

```text
$ uv run pytest cli/tests/test_harness_config.py -q
......................................                                   [100%]
38 passed in 0.52s

$ uv run pytest cli/tests/test_harness_config.py::test_scaffold_keeps_the_schema_modeline_on_the_first_line -q
.                                                                        [100%]
1 passed in 0.27s
```

The red half of the red→green transition, captured before `_with_header` existed:

```text
>       assert lines[0].startswith("# yaml-language-server: $schema=")
E       AssertionError: assert False
E        +  where False = <built-in method startswith of str object …>('# yaml-language-server: $schema=')
E        +    where … = '# Written by the-loop: this repository carried no .the-loop/harness-config.yaml, so'.startswith
FAILED cli/tests/test_harness_config.py::test_scaffold_keeps_the_schema_modeline_on_the_first_line
```

And the file adoption now writes into an unconfigured repository — the modeline on line 1,
the provenance header directly beneath it:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/MadaraUchiha-314/the-loop/main/.the-loop/harness-config.schema.json
# Written by the-loop: this repository carried no .the-loop/harness-config.yaml, so
# the-loop adopted it with its BUILT-IN DEFAULTS (issue-193) rather than working it
# under nothing. This is the same baseline `/the-loop:init --defaults` writes — run
# `/the-loop:init` for the guided version, and edit this file freely; the-loop never
# rewrites a config that already exists.

# .the-loop/harness-config.yaml — HARNESS (plugin) configuration (per repo).
```

## T2 — repository parity: the manifest, the schemas and the modelines agree

```text
$ uv run pytest cli/tests/test_manifest_schemas.py -q
.......                                                                  [100%]
7 passed in 0.10s
```

Seven cases: `schemasDir` resolves and holds all three schemas · `meta` names no schema ·
all three copies are `deprecated` · and four parametrized cases, one per scaffolded config
(`templates/harness-config.yaml`, `templates/collaborators.yaml`,
`templates/cli-config.yaml`, `cli/the_loop/harness-config.default.yaml`), each asserting a
first-line modeline whose URL names a schema the plugin actually ships.

The same module against the **unchanged** repository, before task 1 and task 3 — the red
that motivated them:

```text
FAILED cli/tests/test_manifest_schemas.py::test_the_manifest_declares_where_the_schemas_live
FAILED cli/tests/test_manifest_schemas.py::test_no_schema_is_tracked_as_a_project_file
FAILED cli/tests/test_manifest_schemas.py::test_every_retired_schema_copy_is_deprecated
FAILED cli/tests/test_manifest_schemas.py::test_every_scaffolded_config_points_at_a_schema_that_exists[cli/the_loop/harness-config.default.yaml-harness-config.schema.json]
FAILED cli/tests/test_manifest_schemas.py::test_every_scaffolded_config_points_at_a_schema_that_exists[skills/the-loop/templates/cli-config.yaml-cli-config.schema.json]
FAILED cli/tests/test_manifest_schemas.py::test_every_scaffolded_config_points_at_a_schema_that_exists[skills/the-loop/templates/collaborators.yaml-collaborators.schema.json]
FAILED cli/tests/test_manifest_schemas.py::test_every_scaffolded_config_points_at_a_schema_that_exists[skills/the-loop/templates/harness-config.yaml-harness-config.schema.json]
7 failed in 0.09s
```

## T8 — security / abuse cases

Reviewed against `requirements.md` §Security considerations. No runner executes `/upgrade`,
so each mechanism is cited where it is written down:

| Abuse case | Mechanism, and where it now lives | Verdict |
|-----------|-----------------------------------|---------|
| 1 — deletion escapes the project's `.the-loop/` | `commands/upgrade-the-loop.md` step 3: "Only the exact paths the manifest names… a candidate that resolves outside the project's `.the-loop/` — a symlink, a `..` segment, an absolute path — is **refused and reported**". The candidate list is three literals in `manifest.deprecated`, asserted by T2 | met |
| 2 — a hand-edited copy is deleted silently | same step: "A schema copy that differs from the plugin's shipped schema is a signal. Diff it before removing and say so in the report"; a file that cannot be established as a the-loop copy is left and reported under **needs-user** | met |
| 3 — the loop needs the network | `init.md` step 5 and `upgrade-the-loop.md` step 4 both say "read them from there and validate locally; never fetch a schema over the network". T1/T2 ran with no network access to `raw.githubusercontent.com` and passed | met |
| 4 — a tampered modeline redirects validation | no code reads the modeline. `grep -rn "yaml-language-server" cli/` matches only `harness_config._MODELINE_PREFIX`, which is used to decide *where the provenance header goes* and never to resolve a schema | met |

No new attack surface beyond the one deliberately added — `/upgrade` may now delete three
named files from an operator's repository — and that one is bounded by a closed list, an
escape check and a fail-closed rule, all three written into the command.

## T10 — migration / upgrade

`commands/upgrade-the-loop.md` §3–4 read against R3.1–R3.5: the cleanup step names the
schemas explicitly (R3.2), carries the diff-before-delete rule (R3.3), step 4 migrates the
*config* while reading the plugin's schema and writes no schema into the project (R3.4),
and `--dry-run`'s "computes and prints the report above without writing anything" covers
the removals it would make (R3.5). The manifest's `reason` strings say "SAFE TO DELETE,
not a migration", which is the phrasing step 3 routes on (R3.1).

This repository is its own migration target — it carries all three configs — and they all
still validate after the change:

```text
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## T11 — read-through of the command and the user-facing docs

`commands/init.md` read end to end as the agent would execute it. No step writes a
`*.schema.json`: step 3's bullet list creates `harness-config.yaml`, `manifest.yaml`,
`collaborators.yaml` and (only on the opt-in answer) `cli-config.yaml`; step 5 validates
against `${CLAUDE_PLUGIN_ROOT}/.the-loop/` and says the absence of a project copy never
weakens the step; step 2's onboarding reads `x-onboarding` from the plugin's schema.

The sweep for surviving project-relative references:

```text
grep -rn "\.the-loop/[a-z-]*\.schema\.json" --include="*.md" --include="*.yaml" .
```

After the change every remaining hit is one of three legitimate kinds: a modeline or
comment inside a scaffolded config that names `${CLAUDE_PLUGIN_ROOT}`, this repository's
**own** `.the-loop/` files (where the path is accurate — this repo *is* the plugin root,
including `autonomy.sensitivePaths`), or a `manifest.deprecated` entry naming the copy to
delete. `docs/reports/labels-and-dashboards.md` was also fixed in passing: it linked
`.the-loop/config.schema.json`, a path retired by the issue-82 rename two releases ago.

## Regression — the whole gate

```text
$ make check
uv run ruff check cli hooks                    → All checks passed!
npx markdownlint-cli2 "**/*.md"                → 623 files linted, 0 errors
uv run ruff format --check cli hooks           → 198 files already formatted
uv run pyright cli                             → 0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py       → 7 files VALID
uv run --project cli python -m pytest -q cli   → 1895 passed, 1 skipped in 83.67s
```

1895 passed is +8 over the pre-change baseline: the 7 new cases in
`test_manifest_schemas.py` plus the one added to `test_harness_config.py`. No existing
test changed behaviour, and none was deleted.
