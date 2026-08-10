# Evidence — unit, abuse cases and the no-migration claim (issue-203)

Rows T1, T8 and T10 of [`../testing-plan.md`](../testing-plan.md). Nothing here reaches
the network: every URL is a `hooks.slack.example` fake, and the environment variable is
set and deleted by name through `monkeypatch`. No redaction was needed — no real
credential exists in this repository.

## T1 — precedence, both transports

Resolution is driven through `resolve("slack", config)`, not by constructing a provider:
the config key is what an operator writes, and the wiring is the half that was missing.

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py
.......................                                                  [100%]
23 passed in 0.11s
```

The four precedence cases (inline only · inline over env · env only · neither) run
parametrised over `webhook` and `sdk`, so a future change cannot make the transports
disagree about where a notification goes.

### Red before green

The same command, run before any source file was touched:

```console
FAILED cli/tests/test_graph_integrations.py::test_an_inline_url_is_used[webhook]
FAILED cli/tests/test_graph_integrations.py::test_an_inline_url_is_used[sdk]
FAILED cli/tests/test_graph_integrations.py::test_an_inline_url_wins_over_the_environment[webhook]
FAILED cli/tests/test_graph_integrations.py::test_an_inline_url_wins_over_the_environment[sdk]
FAILED cli/tests/test_graph_integrations.py::test_the_failure_names_both_remedies_and_not_the_url
FAILED cli/tests/test_graph_integrations.py::test_a_non_string_url_is_refused_by_the_schema
6 failed, 17 passed in 0.80s
```

`test_an_empty_inline_url_falls_back_to_the_environment` passed in both runs by
construction — before the change the key was ignored entirely. It is kept as the guard
that the fallback survives, and it earned its place: the first cut used
`str(section.get("url", ""))`, which lets a blank `url:` win over a working env var.

## T8 — the three abuse cases

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_integrations.py \
    -k "refused or empty or remedies"
.........                                                                [100%]
9 passed, 14 deselected in 0.07s
```

| Abuse case | Test |
|---|---|
| 1 — a non-string `url` | `test_a_non_string_url_is_refused_by_the_schema` — validates the real `.the-loop/cli-config.schema.json`, and asserts `additionalProperties: false` still holds so the surface widened by exactly one named key |
| 2 — a blank `url` | `test_an_empty_inline_url_falls_back_to_the_environment` |
| 3 — the URL leaking | `test_the_failure_names_both_remedies_and_not_the_url` — asserts both sources appear in the message and that `hooks.slack` does not |

The selector also picks up the pre-existing `*_is_refused` transport tests, which is why
9 rather than 3 run; all pass.

## T10 — a pre-change config still validates, and nothing needs migrating

```console
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Both CLI configs validate **without** an inline `url` — the property is optional, so a
config written before this change is still a valid config.

`migrations.CURRENT_CONFIG_VERSION` is `0.4.0` before and after, and the diff of
`.the-loop/cli-config.schema.json` touches no `version` field:

```console
$ git diff .the-loop/cli-config.schema.json | grep -c version
0
```

That is the whole no-migration claim: an optional additive property is a superset of the
old shape, and the version gate exists to refuse a shape the CLI no longer understands.

Documentation parity (issue-117's P1–P5), which is what forces the new schema leaf to be
documented with a `Type` and a `Default`:

```console
$ uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py
.....                                                                    [100%]
5 passed in 0.05s
```
