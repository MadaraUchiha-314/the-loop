---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#540"
---

# Final validation: prompts in Markdown files, application strings in one JSON catalog

> Summarised from [`testing-plan.md`](../testing-plan.md) § Verification results and
> [`verification.md`](verification.md). The only code change after verification is a
> comment block in `webhook/dispatcher.py` (self-review F1); `ruff format --check` is
> clean at the same commit.

## Final validation evidence

| Acceptance criterion | How it was proved |
|----------------------|-------------------|
| R1.1 every agent-bound prompt is a `.md` file | 101 files under `cli/the_loop/prompts/` cover all 25 sites in the design inventory. The guard flags the six inline prompts on `origin/main` and none on this branch (`test_prompts_guard.py`). What stays inline is listed with reasons in requirements § Out of scope. |
| R1.2 one loader | every call site reads through `the_loop.prompts` (`load`/`render`) |
| R1.3 named placeholders, same semantics | the webhook templates are still `string.Template`, and everything else that used `str.format` still does (`design.md` § Components) |
| R1.4 byte-identical output | 6992 tests pass (they pin today's text), and 66,174 old-vs-new renders hash identically (`verification.md` V2) |
| R1.5 ships in wheel and sdist | the wheel lists 101 `.md` files and `en.json`, and a fresh-venv import renders them (V3). The sdist carries `cli/the_loop/**` by default. |
| R1.6 one source for the skill templates | `test_skill_templates_are_identical_to_the_packaged_prompts` |
| R1.7 a missing prompt raises naming the file | `test_missing_prompt_names_the_file` |
| R2.1 one catalog `strings/en.json` | 2,275 keys, shared with the UI build; `test_en_is_one_flat_object_of_strings_with_dotted_keys` |
| R2.2 one lookup `strings.t` | `test_t_formats_named_variables`; dictionaries are built through `strings.section` |
| R2.3 locale fallback | `test_a_locale_overrides_what_it_translates_and_falls_back_for_the_rest`, `test_set_locale_selects_explicitly`, `test_a_missing_locale_falls_back_to_en`, `test_an_invalid_locale_warns_and_falls_back` |
| R2.4 an unknown key raises | `test_a_missing_key_raises_naming_it` |
| R2.5 every human-facing string of the application from the catalog | 2,275 keys: comment, reply and notice bodies, CLI output, argparse help and `SystemExit` text, event-type descriptions, and the UI's 428 `ui.*` keys. The existing CLI (6998) and UI (379) suites pass unchanged (`verification.md` V5). |
| R2.6 catalog tests | `test_every_key_the_code_looks_up_exists_with_matching_placeholders`, `test_every_catalog_entry_is_used`, `test_placeholders_are_named_fields_only` |
| R3.1 guard | `test_no_module_defines_an_inline_multi_line_prompt`, `test_the_guard_fires_on_a_planted_prompt` |
| R3.2 conventions documented | `docs/capabilities/prompts-and-strings.md`, plus a paragraph in `CLAUDE.md` and in `AGENTS.md` |
| NFR no new dependency | `cli/pyproject.toml` is unchanged |
| Abuse cases 1–3, fail closed | see [`security-review.md`](security-review.md), items 5 and 7 |

**Full suite (scope extension):** 6998 passed at `14e5fd07`; the UI's 379 tests, typecheck, lint and build are clean (V5).

**Full suite (phase 1):** with the daemon's environment variables unset (as in CI), 6992 passed at
`d0470779`. With them set, 22 environment-dependent tests fail, identically on
`origin/main` (`verification.md` V2).

**Reviews:** self-review converged in 2 rounds, with 2 findings, both fixed. The critic
(codex) found nothing. The security review passed with no findings.
