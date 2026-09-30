# Documentation (issue-442)

Capability docs updated in this PR — the organized view of the specs, never left to rot:

| Doc | What changed |
|-----|--------------|
| `docs/capabilities/cli.md` | the `ask`/`add-channel`/`add-collaborator` bullets say "a missing token or a failing post" instead of "a failing `gh`"; the host rule (issue-311) names the client's per-host base; a history row |
| `docs/capabilities/webhook-triggers.md` | the label filter, the existence check, the PR→issue linkage, the poller's network path, the give-up notice and the reactions bullets rewritten off `gh`; a history row |
| `docs/capabilities/interactive-sessions.md` | the announcement bullet; a history row |
| `docs/capabilities/sdk.md` | `REQUIREMENTS` no longer lists `gh`; a history row |
| `docs/capabilities/self-diagnosis.md` | a history row (the issue is opened through the shared writer) |
| `docs/capabilities/control-plane.md` | the `ask` bullet no longer names `gh` |

User-facing docs:

| Doc | What changed |
|-----|--------------|
| `docs/config/cli/integrations-options.md` | rewritten: one transport, one token; `github.transport` and `github.cli.binary` removed (an *Upgrading* box says what the migration does); `tokenEnv` default and scopes; `baseUrl` semantics; the host tiers no longer described as `gh`'s |
| `docs/config/cli/polling-options.md` | the label filter, the issues-disabled sentence, the per-PR request cost and the *Where the credential comes from* tip |
| `docs/config/cli/routing-options.md`, `self-diagnosis-options.md`, `repositories-options.md`, `channels-options.md` | reactions, announcement, self-diagnosis and the repository grammar described without `gh` |
| `docs/cli/installation.md` | the tools table loses `gh`; a sentence on the token |
| `docs/cli/getting-started.md` | prerequisites: a token, not `gh auth login` |
| `docs/guide/onboarding.md` | the `GH_TOKEN` row: what it gates and the scopes |
| `docs/cli/receiver.md`, `docs/cli/concepts.md` | the existence check and the host tiers |
| `docs/cli/commands/{ask,diagnose,channels,sessions,add-channel,add-collaborator,status}.md`, `docs/cli/state.md` | wording and example error strings |
| `docs/sdk/environment.md` | the contract table without `gh`; `git` as the renamed binary; the Dockerfile without the `gh` apt source; the *Credentials* section names the token, its variables and scopes |
| `docs/sdk/index.md` | the diagram and the "drives other programs" sentence |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | `integrations.github` without `transport`/`cli`, the token comment, version `0.11.0` |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the keys removed; descriptions of `integrations`, `host`, `tokenEnv`, `baseUrl`, the reactions/announce switches, `selfDiagnosis` and the kickoff `repo` rewritten |
| `docs/reports/gh-queries.md` | a superseded-by note (the report itself is point-in-time and unchanged) |
| `docs/decisions/decision-139.md`, `docs/decisions/decisions.md` | proposed |

Deliberately **not** changed: the skill's references (`skills/the-loop/reference/*.md`),
the slash commands and the plugin hooks, which tell the *agent* it may use `gh` in its
session — the harness's tooling, outside `integrations` (R8, decision-139 D7).

Parity: `test_docs_parity.py` (P1–P5), `test_sdk_docs_parity.py` and
`test_config_schema_parity.py` pass.
