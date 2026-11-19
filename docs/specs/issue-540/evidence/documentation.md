---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#540"
---

# Documentation: prompts in Markdown files, application strings in one JSON catalog

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/prompts-and-strings.md` | **New.** The prompt loader and the string catalog: the normative rules, the areas and keys in use, what stays inline and why, and how to add a prompt, a message or a locale | issue-540 |
| `docs/capabilities/capabilities.md` | Index row for the new capability | — |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/.vitepress/config.mts` | "Prompts & strings" added to the capabilities sidebar |
| `CLAUDE.md`, `AGENTS.md` | One contributor paragraph each: prompts go in `cli/the_loop/prompts/`, messages in `cli/the_loop/strings/en.json` |
| `.markdownlint-cli2.jsonc` | `cli/the_loop/prompts/**` ignored: prompts are byte-for-byte contracts |

No behaviour an operator or a session sees changes. Every rendered prompt and message is
byte-identical (`evidence/verification.md` V2), so `docs/cli/`, `docs/config/` and the
skill references are unchanged. The `promptTemplate`/`spawnTemplate` schema descriptions
("falls back to a built-in default") are still accurate.
