# Verification evidence — issue-222

Executed 2026-08-14 in the work item's own cloud session, on branch
`claude/gallant-hopper-c7su5v`. Every command was run from the repository root
(`repository.runScriptsFromRoot: true`), except the UI rows, which run in `ui/` on that
project's own toolchain.

Nothing captured here contains a secret. The tests run against temp directories; the
manual row (T16) runs the service against a **copy** of the shipped template in a scratch
directory, never against this repository's `.the-loop/cli-config.yaml` or any real
`~/.the-loop/cli-config.yaml`. Absolute paths in the captures are the sandbox's scratch
directory, not a personal home directory.

## T1 — unit: the file survives a save

```text
$ uv run pytest cli/tests/test_yamlpatch.py -q
....................                                                     [100%]
20 passed in 2.87s
```

The load-bearing assertions, on `skills/the-loop/templates/cli-config.yaml` (the ~270-line
file operators actually have):

- `test_a_save_keeps_every_comment_and_every_untouched_line` — after changing
  `routing.enabled`, the comment list is identical, the line count is identical, and
  **exactly one** line differs.
- `test_every_value_in_the_template_can_be_rewritten_in_place` — 71 leaves, each replaced
  in turn; every result re-parses to the intended document with every comment intact.
- `test_an_unverifiable_splice_raises_instead_of_returning_text` — with the renderer
  sabotaged, `apply()` refuses and names `root.other` rather than returning damaged text.

The eleven shapes covered by `test_every_shape_lands_the_intended_document`: existing
scalar, block sequence, flow sequence, empty container, flow-mapping insert, missing leaf,
missing parent chain, scalar-becomes-a-list, list-of-objects, delete a key, delete a
top-level key.

## T2 — unit: the validator, and the two tests that keep it honest

```text
$ uv run pytest cli/tests/test_configschema.py -q
....................                                                     [100%]
20 passed in 0.81s
```

- `test_the_schemas_use_no_keyword_the_validator_ignores` — every keyword in both packaged
  schemas is in `configschema.SUPPORTED`. A schema that grows one fails here.
- `test_this_validator_agrees_with_jsonschema` — 16 documents (the shipped template, 6
  valid, 9 invalid) judged by both implementations, verdicts identical.

## T3 — unit: the core surface, and what it refuses

```text
$ uv run pytest cli/tests/test_core_config.py -q
................                                                         [100%]
16 passed in 0.52s
```

Every refusal is asserted twice — the call raises **and** `path.read_bytes()` is unchanged:
unknown key, wrong type, the un-bootable CORS pair, a config below
`CURRENT_CONFIG_VERSION`, a patch that is not an object, and an unverifiable splice. Two
more properties are pinned here because they are easy to lose later: a **symlinked** config
is written through (the link stays a link) and an empty patch does not conjure a file on a
machine that has none.

## T4, T5, T10, T14 — integration: the three routes, hot reload, the audit trail

```text
$ uv run pytest cli/tests/test_api_config_integration.py -q
...........                                                              [100%]
11 passed in 2.21s
```

Covered here and worth naming: a `POST` is visible to the **next** request with no
restart; a `Reloader` baselined on the file — the object the poller and the receiver hold —
rebuilds after an API write and carries the new value (R4.1: **no poller or receiver was
started by hand in this session**, so this assertion is what carries that requirement, not
a manual run); a hand-edit of the file is picked up too; a file that becomes unparseable keeps
the previous config in force while `GET` reports 400; a body carrying a `path` writes the
resolved file and creates nothing elsewhere; the event-log record names
`routing.authorizedUsers` and the log contains no handle from the value.

## T6, T7 — contract and packaging parity

```text
$ uv run pytest cli/tests/test_api_contract_parity.py -q
.                                                                        [100%]
1 passed in 1.05s

$ uv run pytest cli/tests/test_config_schema_parity.py -q
...                                                                      [100%]
3 passed in 0.02s
```

## T8, T9, T11 — the UI

```text
$ cd ui && bun run test
 ✓ src/api/client.test.ts (7 tests)
 ✓ src/components/ConfigEditor.test.tsx (11 tests)
 ✓ src/api/model.test.ts (33 tests)
 ✓ src/api/configModel.test.ts (23 tests)
 ✓ src/state/settings.test.ts (7 tests)
 ✓ src/App.test.tsx (8 tests)

 Test Files  6 passed (6)
      Tests  89 passed (89)

$ cd ui && bun run lint      # oxlint --type-aware
$ cd ui && bun run build     # tsc --noEmit, then vite build
✓ built in 1.08s
```

Every control is found by its **key path** (`getByLabelText("routing.enabled")`), which is
T11's accessibility assertion as well as T9's render one. No axe run: this repository has
no accessibility harness, and adding one is its own work item — stated here rather than
implied by silence.

## T16 — manual: the real service, the real dashboard, the real file

The service was started against a **copy** of the shipped template in a scratch directory,
the built dashboard served from `bun run preview`, and the browser driven with Playwright:

```text
$ THE_LOOP_CLI_CONFIG=<scratch>/.the-loop/cli-config.yaml uv run python -m the_loop.api.serve &
$ curl -s http://127.0.0.1:4114/api/v1/health
{"status":"ok","version":"9.12.0"}

$ cd ui && bun run preview --port 4173 &
$ node shot.mjs        # navigate to #/settings, edit routing.maxConcurrentDispatches, save
sections: 11
report: Saved routing.maxConcurrentDispatches to <scratch>/.the-loop/cli-config.yaml. Live now.
```

Eleven cards: the header plus one per top-level property of the schema. The save landed,
and the file it landed in kept everything else:

```diff
--- skills/the-loop/templates/cli-config.yaml
+++ <scratch>/.the-loop/cli-config.yaml
@@ -142,7 +142,7 @@
     defaultHost: github.com     # host dir when the payload has no html_url (set to your GHE domain)
     keepCheckoutOnClose: false  # keep the work item's checkout after PR close (for post-mortem)
     gitBinary: git
-  maxConcurrentDispatches: 4
+  maxConcurrentDispatches: 7
   dedupCacheSize: 1024
```

```text
$ grep -c '#' skills/the-loop/templates/cli-config.yaml <scratch>/.the-loop/cli-config.yaml
skills/the-loop/templates/cli-config.yaml:249
<scratch>/.the-loop/cli-config.yaml:249
```

(The second hunk of that diff is the `service.cors.allowOrigins` entry added **by hand
before starting**, so the preview origin could read a loopback service — it is setup, not
something the save did.)

The rendered screen, captured after the save:

![The Settings tab's CLI config editor, showing the file path, the save report and the
first schema-derived section](settings-config.png)

Two console errors appear in the capture and belong to the sandbox, not the change: the
Google Fonts stylesheet is unreachable here (`ERR_CONNECTION_RESET`), and the favicon 404s
under the preview base path.

## Quality gates

```text
$ make test
1965 passed, 1 skipped in 79.10s

$ make validate
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ make lint          # ruff + markdownlint over 630 files
Summary: 0 error(s)

$ make format-check
206 files already formatted

$ make typecheck
0 errors, 0 warnings, 0 informations
```

Suite growth: 1893 → 1965 tests in Python (72 new), 55 → 89 in the UI (34 new).
