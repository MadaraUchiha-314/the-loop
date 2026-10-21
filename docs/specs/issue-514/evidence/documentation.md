---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#514"
---

# Documentation: split `/the-loop:init` into `/init`, `/init-cli` and `/init-gateway`

> The `capability-docs` node's proof, and it gates **both** sections (issue-174). A work
> item that genuinely changed nothing in either says so **with the reason** — "internal
> refactor, no described behaviour changed" is an answer; a blank is not. A row names a
> **document**, never a token, a credential or an internal hostname: this tree is as
> public as the repository.

## Capability docs

> The ORGANIZED VIEW OF SPECS — current behaviour per capability, for a reader who
> already uses the project. Updated in the **same PR** as the change.

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`distribution.md`](../../../capabilities/distribution.md) | New SHALL bullet: each config has its own init command; what `/init`, `/init-cli` and `/init-gateway` each own and must not touch; all three take `--dry-run` / `--defaults` | issue-514 |
| [`channels.md`](../../../capabilities/channels.md) | The Slack app's name and one-click link are asked by `/the-loop:init-cli` (was `/init`) | none (a pointer fix, not new behaviour) |

## Documentation

> The USER-FACING surface — README, the docs site, the operating-model skill — for a
> reader who does not yet. It rots the same way, so it is updated in the same PR.

| Document | What changed |
|----------|--------------|
| `skills/the-loop/SKILL.md` | § Commands lists `/init-cli`, `/init-gateway` (and the previously missing `/explain`); the onboarding reference line names all three |
| `skills/the-loop/reference/onboarding.md` | Three configs, three commands, one procedure; per-section "Run by" lines; modes, re-runs and the report per command; precedence reads the config being walked |
| `commands/init.md`, `commands/init-cli.md`, `commands/init-gateway.md` | The split itself |
| `commands/upgrade-the-loop.md` | The CLI-config location question and the Slack manifest point to `/init-cli` |
| `docs/reference/commands.md` | Rows for `/init-cli` and `/init-gateway`; `/init` says it sets up no daemon |
| `docs/guide/onboarding.md` | Rewritten around the three commands: who runs which, what each walks |
| `docs/guide/quickstart.md`, `docs/guide/installation.md` | `/init` in every repository; `/init-cli` once, in the operator repository |
| `docs/guide/gateway.md`, `docs/guide/slack.md` | Point to `/init-gateway` and `/init-cli` |
| `docs/config/index.md`, `docs/config/cli/index.md` | The CLI config is written by `/init-cli` |
| `docs/operating-model/index.md` | The onboarding row names the three commands |
| `docs/decisions/decision-149.md`, `docs/decisions/decisions.md` | The decision and its index row |
| `README.md` | Unchanged: it never described what `/init` asks |
