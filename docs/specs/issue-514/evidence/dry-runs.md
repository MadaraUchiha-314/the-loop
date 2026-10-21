---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#514"
---

# Dry runs: `/init`, `/init-cli`, `/init-gateway`

Each command run once with `--dry-run`, non-interactively, through the plugin loaded from
this branch (commit `fd89577a`), in a throwaway repository:

```bash
git init && git remote add origin git@github.com:example-org/widget.git   # plus README.md, tests/test_x.py
echo "/the-loop:<cmd> --dry-run" | env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_WORK_ITEM \
  claude -p --plugin-dir <this checkout> \
  --allowedTools Read Glob Grep "Bash(git status*)" "Bash(git remote*)" "Bash(ls*)" "Bash(cat*)" \
  --disallowedTools Write Edit NotebookEdit
```

`Write` and `Edit` were denied as a safety net. That denial alone proves nothing about
`--dry-run`, so the outcome was checked from the outside as well:

| Check | Result |
|---|---|
| `git status --short --ignored` in the throwaway repository after all three runs | empty |
| `ls -la ~/.the-loop` before vs after (the home-directory location both `/init-cli` and `/init-gateway` may target) | identical |
| Exit status of each run | 0 |

Each report is below, verbatim apart from tool-installer noise and a closing note about
unrelated claude.ai connectors. Secrets: the reports name environment variables and say
whether each is set. No value appears; nothing needed redacting.

## `/the-loop:init --dry-run`

````markdown
This was a dry run of `/the-loop:init`, so nothing was written. Nothing was created on GitHub and no hooks were installed.

**What's in the repo:** `README.md` and `tests/test_x.py`, with no `.the-loop/` or `docs/` folder yet. The remote is `example-org/widget`, which is a GitHub repository, so the phase labels would be GitHub issue labels. There are no convention docs (CONTRIBUTING, style guides), no API contracts, no hook manager and no CI.

## Created (would be)
| Path | Source / content |
|---|---|
| `.the-loop/harness-config.yaml` | Plugin template, schema line kept as the first line. `customInstructions.docs: []`, `testing.integrationTestGlobs: []`, the `apiSpecs`/`design` defaults, `version: "0.3.0"` |
| `.the-loop/manifest.yaml` | Copy of the plugin manifest |
| `.the-loop/collaborators.yaml` | Plugin template, `collaborators: []` (user-owned) |
| `docs/architecture/architecture.md` | Index stub |
| `docs/decisions/decisions.md` | Index stub |
| `docs/specs/` | Empty folder (`.gitkeep`) |
| `docs/capabilities/` | `capabilities.md` index |
| `docs/learnings/learnings.md` | Index stub |
| GitHub labels on `example-org/widget` | All 12: `loop:not-started`, `loop:phase-selection`, `loop:brainstorming`, `loop:requirements-definition`, `loop:design`, `loop:test-planning`, `loop:tasks-breakdown`, `loop:implementation`, `loop:verification`, `loop:needs-review`, `loop:complete`, `loop:cleanup` |
| Local pre-commit / pre-push hooks | Would run `pytest`; there is no linter or type checker to run |
| CI workflow | Would run the same root `pytest` command |

The plugin's schemas could be read, so both config files would be checked against them before being written. No templates or schema files would be copied into the project.

## Skipped (up to date)
Nothing. There are no the-loop files yet, and none of the daemon or gateway configs (`cli-config.yaml`, `slack-app-manifest.json`, `gateway-config.yaml`) are in the repo.

## Drifted (suggested)
Nothing.

## Needs user
1. **Collaborators (required).** `collaborators.yaml` would be written empty. Add at least one person holding the `approver` role, for example `handle: "@MadaraUchiha-314"`, `kind: individual`, `roles: [approver, engineer]`.
2. **Custom instruction docs.** No candidates were found, so this defaults to none (`# TODO: verify`). Add the paths of any convention docs the agent should read, including absolute paths that only exist on your machine.
3. **Integration-test globs.** The only test is `tests/test_x.py`, which looks like a unit test, so this is left empty and uses the CLI's built-in defaults (`# TODO: verify`). Confirm it, or give a glob such as `tests/integration/**/*.py`.
4. **Phase labels.** The GitHub API answered "Could not resolve to a Repository" for `example-org/widget`. Either the repository doesn't exist or this `gh` login can't see it. Fix the access or the remote before a real run, or label creation will fail.
5. **Hooks and CI.** There's no `pyproject.toml` or requirements file, so `pytest` as the test runner is a guess. Confirm it before the real run scaffolds hooks and CI around it.

## Not set up here
No CLI or gateway setup was done. If this is your **operator** repository (the one whose checkout runs the-loop's daemon, or you keep its config in `~/.the-loop/`), run `/the-loop:init-cli` once to set up the daemon in `cli-config.yaml`: where it runs, how much runs unattended, Slack, Jira, the arming labels and their credentials. If this machine hosts a the-loop gateway, run `/the-loop:init-gateway` (`gateway-config.yaml`). A repository that only uses the-loop needs neither.

## Next action
Run `/the-loop:init` without `--dry-run` to do the guided onboarding and write the files. Then start work with `/the-loop:work-on <ticket>` or `/the-loop:new-requirement`.
````

## `/the-loop:init-cli --dry-run`

````markdown
# the-loop: init-cli — dry run

Nothing was written: no config, no Slack manifest, no labels, no `.gitignore` line. Below is what the walkthrough would do, and the questions it would ask.

## What I detected

| Item | Found |
|---|---|
| Repository | `example-org/widget` (from `origin`). **`gh` can't resolve this repository**: either it doesn't exist or the authenticated account can't see it. |
| Deployment shape | **Not clear.** No container, cloud-shell or CI marker. It looks like a personal Linux machine, but I won't assume that. |
| Existing CLI config | None at `./.the-loop/cli-config.yaml` or `~/.the-loop/cli-config.yaml`. `$THE_LOOP_CLI_CONFIG` is unset. |
| An env file that already exists | `~/.the-loop/the-loop.env`. The current template doesn't name it, because `env.file` defaults to `""`. |
| Schema | Found and readable at `<plugin>/.the-loop/cli-config.schema.json`, so validation would run. |
| CLI | `the-loop 20.2.1` is on PATH, so verification can run locally. |

## Questions the walkthrough would ask

1. **Where will the daemon run?**
   - (a) This machine, which you close: proposes polling plus a `github` source for `example-org/widget`.
   - (b) An always-on host with an inbound route: proposes the webhook receiver plus `THE_LOOP_GH_WEBHOOK_SECRET`.
   - (c) Nowhere yet: routing stays off.
2. **How much runs unattended?** Pick one profile:
   - **`commands-only`**: no daemon, and nothing watches your repositories. *Still yours:* everything.
   - **`watch-and-ask`** ⭐ recommended: the daemon follows items you've labelled, but nothing spawns until someone authorized comments `the-loop start`. It never merges. *Still yours:* starting each item, merging every PR, and all the gates.
   - **`armed`**: the labels alone start the work, an approved PR merges itself, and self-diagnosis is on. *Still yours:* every gate.

   **No profile removes a human gate.** The phase-selection checklist, the `requirements.md` and `design.md` approvals, the PR approval and the risk-tier sign-offs are fixed rules. A profile decides who *starts* work and how events arrive, never who *approves* it.
3. **Where should the config live?** Either `./.the-loop/cli-config.yaml`, tracked in this repo, or `~/.the-loop/cli-config.yaml`.
4. **Three settings no profile fills in:**
   - `routing.authorizedUsers`: empty by default, so nobody can start, stop or approve anything from a comment until it names someone (e.g. `MadaraUchiha-314`?).
   - `routing.workspace.root`: empty by default, so a spawned session has nowhere to check out code (e.g. `~/.the-loop/workspace`).
   - `routing.autoExecuteLabels`: defaults to `["the-loop: auto-execute"]`. All of these labels must be on an item before it can spawn.
5. **Gateway or your own ingress?** The walkthrough asks whether this instance reads events from a the-loop gateway, or runs its own receiver, poller and Slack listener.
6. **Slack: yes or no?** If yes, it asks the app's name (default `the-loop`; ≤35 characters; use a distinct one in a shared workspace), then would run:
   ```bash
   the-loop channels manifest --name "<name>" --write <config dir>/slack-app-manifest.json
   ```
   After that come the bot token, the app-level token and the channel id. `publish` stays at `work-item.reply` only. Guide: https://madarauchiha-314.github.io/the-loop/guide/slack
7. **Jira:** only offered if your work items live there.

## Would create
- `cli-config.yaml` at the chosen path. It would come from the template, starting with the `# yaml-language-server: $schema=…` line, then a `# onboarding profile: <id>` comment.
- `slack-app-manifest.json` beside it, only if you want Slack.
- The label `the-loop: auto-execute` on `example-org/widget`, only if routing is enabled. **As things stand this step would fail**, because `gh` can't reach the repository.

## Skipped (up to date)
- Nothing yet: there's no existing CLI config.

## Drifted (suggested)
- None, since there's no existing config to compare with the template.

## Needs you
- **Deployment shape, autonomy profile and config location:** none of these has been answered.
- **`routing.authorizedUsers` and `routing.workspace.root`:** both are empty. Until they're set, the daemon can't be driven and has nowhere to work.
- **Repository access:** check that `example-org/widget` is correct and visible to your `gh` account. Otherwise the poller sees nothing and the arming label can't be created.
- **Credentials.** I checked whether each one is set, never its value:
  - `GH_TOKEN` / `GITHUB_TOKEN` (`integrations.github.api.tokenEnv`) is **not set** in this shell and not in `~/.the-loop/the-loop.env`. It's needed for polling, reactions and label work. Get one with `gh auth token`, or create a PAT under GitHub → Settings → Developer settings.
  - `THE_LOOP_GH_WEBHOOK_SECRET` is **not set**. It's only needed if you choose (b), the webhook receiver. It's the shared secret for the repository's webhook.
  - `THE_LOOP_SLACK_BOT_TOKEN` and `THE_LOOP_SLACK_APP_TOKEN` are only needed with Slack. They're **not set in this shell but present in `~/.the-loop/the-loop.env`**. The daemon only loads them if you set `env.file: the-loop.env` (relative to a config in `~/.the-loop/`). Until then they count as *unverified*.
- **Env-file safety:** if the config lives in this repo and points at an env file inside it, that file holds secrets and needs a `.gitignore` entry. This repo has no `.gitignore` yet.
- **Verification to run after a real init:** `the-loop channels status --probe` and `the-loop doctor slack` (with Slack), and `the-loop doctor jira` (with Jira).

## Autonomy profile
**None applied, so no automation is enabled.** The shipped defaults mean no daemon ingress, no routing and no Slack.

**Next step:** run `/the-loop:init-cli` without `--dry-run` to answer the questions above, then `the-loop start`.
````

## `/the-loop:init-gateway --dry-run`

````markdown
# `/the-loop:init-gateway --dry-run`: report

Nothing was written. No config, no `.gitignore` line, and no questions were asked.

## What I checked

- **Existing gateway config:** there isn't one. `./.the-loop/gateway-config.yaml` and `~/.the-loop/gateway-config.yaml` don't exist, and `$THE_LOOP_GATEWAY_CONFIG` is unset.
- **Existing CLI config:** there isn't one either, in this repo or in `~/.the-loop/`, so I have no reason to suggest one location over the other.
- **Schema:** the plugin's `.the-loop/gateway-config.schema.json` (`manifest.schemasDir: .the-loop`) is readable. I validated the template against it locally, without the network: **0 errors**, so writing the file wouldn't be blocked.
- **Dotenv file:** `~/.the-loop/the-loop.env` exists. It's a natural `env.file` candidate.
- **CLI:** `the-loop` is installed at `~/.local/bin/the-loop`.

## What the walkthrough would ask

1. **Location:** this repo (`.the-loop/gateway-config.yaml`) or your home directory (`~/.the-loop/gateway-config.yaml`)? It would not assume either.
2. **`listen`:** default `127.0.0.1:8790`, `exposed: false`. Any host other than loopback needs `exposed: true`. This release has no instance authentication, so the network is the only boundary (decision-146).
3. **`store` / `state`:** `retentionDays: 7`, `maxAttempts: 3`, `state.root: ~/.the-loop/gateway`.
4. **`repositories`:** the `owner/repo` list the gateway may start work items in. It's empty in the template and has no default. Events from repositories not on the list are dropped.
5. **Transports**, each one optional:
   - **`github`:** webhook off, poller off. Instances keep their own pollers unless you turn this on.
   - **`jira`:** webhook off, poller off. If enabled, it needs `site` and `projects`.
   - **`slack`:** Socket Mode on, HTTP off. Optional static `rooms`.
6. **Advanced blocks**, defaulted without asking and summarised with an offer to walk through them: `consume` (`maxBatch: 256`, `maxWaitSeconds: 30`, lease 10–300s), `instances: []`, `observability.eventLog` enabled, and `env.file`. For `env.file` it would propose `~/.the-loop/the-loop.env`.

## Credential preflight (names only)

I checked whether each variable is set, never its value. With the template defaults, only Slack Socket Mode is enabled, so only these two are needed:

| Variable | What it gates | Process env | `~/.the-loop/the-loop.env` |
|---|---|---|---|
| `THE_LOOP_SLACK_APP_TOKEN` | Socket Mode connection (`xapp-…`, Slack app → Basic Information → App-Level Tokens, scope `connections:write`) | unset | named |
| `THE_LOOP_SLACK_BOT_TOKEN` | Slack bot (`xoxb-…`, Slack app → OAuth & Permissions) | unset | named |

Both variables are listed in `the-loop.env`, so they would load once `env.file` points at it. The env file is under your home directory, not inside a repo, so there's no `.gitignore` to check.

The other variables only matter if you enable their transport:
- GitHub: `THE_LOOP_GH_WEBHOOK_SECRET` (webhook) and `GITHUB_TOKEN` (poller). Neither is set or in the env file.
- Jira: `THE_LOOP_JIRA_WEBHOOK_SECRET` (webhook; in the env file), plus `THE_LOOP_JIRA_EMAIL` and `THE_LOOP_JIRA_TOKEN` (poller; neither in the env file).
- Slack over HTTP: `SLACK_SIGNING_SECRET`.

## Summary

- **created:** nothing (dry run). A real run would create `gateway-config.yaml` at the location you choose, from the template, keeping its `$schema` first line.
- **skipped (up to date):** nothing; there's no existing file.
- **drifted (suggested):** nothing.
- **needs-user:**
  - Where the file goes: `.the-loop/` in this repo or `~/.the-loop/`.
  - `repositories`: at least one entry, e.g. `- owner/repo`.
  - `env.file`: e.g. `~/.the-loop/the-loop.env`.
  - `THE_LOOP_SLACK_APP_TOKEN` and `THE_LOOP_SLACK_BOT_TOKEN` aren't set in this shell. They're **unverified** rather than missing until the gateway loads `env.file`.
  - Slack checks I didn't run: `the-loop channels status --probe` and `the-loop doctor slack`.

## Next steps

1. Run `/the-loop:init-gateway` without `--dry-run` to write the file.
2. Start it with `the-loop gateway start`.
3. Every instance that reads from this gateway needs a `gateway` block in its CLI config. `/the-loop:init-cli` sets that up. If the instance has its Slack channel enabled, it also needs `channels.slack.read.mode: gateway` (issue-503).
````
