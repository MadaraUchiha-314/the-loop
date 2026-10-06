---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#464"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 3                  # a CLI option that writes one file, plus onboarding text; no sensitive path touched
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: a Slack app from one click, named by its operator

> Phase 1 of 4 (requirements → design → testing plan → tasks). Tier 3
> (`human-approves-pr`): new options on `the-loop channels manifest`, and the init and
> upgrade walkthroughs that use them. No scope, event or credential changes.

## Introduction

[Issue #464](https://github.com/MadaraUchiha-314/the-loop/issues/464): "Ship a manifest
and a one-click link (lowest friction)."

**What is broken.** the-loop already ships its Slack app manifest
(`cli/the_loop/channels/slack-app-manifest.yaml`, printed by `the-loop channels
manifest`), but creating the app still takes four manual moves: print the YAML, open
api.slack.com, choose *From a manifest*, paste. Every app is also called `the-loop`. Each
operator creates their own app, because the app's tokens are what their daemon runs on,
so two operators in one workspace get two bots with the same name. Nothing records what
an operator imported, so when a release adds a scope, nobody can tell them what to change.

**What this changes.**

- `the-loop channels manifest --name <app name>` renames the app for its operator.
- `--link` prints Slack's prefilled create-app URL
  (`https://api.slack.com/apps?new_app=1&manifest_json=…`), so creating the app is one
  click, then pick a workspace and confirm.
- `--write` keeps the generated manifest as `slack-app-manifest.json` in the `.the-loop/`
  directory that holds the operator's CLI config. Run again, it regenerates the file from
  the shipped manifest under the same name and names the scopes and events that changed.
- `/the-loop:init` asks the app's name and walks the link. `/the-loop:upgrade-the-loop`
  regenerates the file.

**One reading of the issue to check.** The issue says the user "pastes the bot token
back". The loop's credential rule (`reference/onboarding.md` § The credential preflight)
is that a token never enters a config, a report or the conversation. So the walkthrough
has the user paste the token into their environment or the configured `env.file`, and
init reports only whether it is set. Nothing else in the flow needs a token.

## Requirements

### Requirement 1 — a manifest named for its operator

**User story:** As an operator setting up Slack, I want the app named as I choose, so my
bot is distinguishable from another operator's in the same workspace.

#### Acceptance criteria (EARS)

1.1 WHEN `the-loop channels manifest` is run with none of the new options THEN the
system SHALL print the packaged manifest verbatim, as it does today.

1.2 WHEN `--name NAME` is given THEN the manifest SHALL carry `NAME` as
`display_information.name` and NAME's handle as `features.bot_user.display_name`, and
every other key SHALL equal the packaged manifest's.

1.3 NAME's handle SHALL be NAME trimmed and lowercased, with each run of characters
outside `a-z`, `0-9`, `.`, `_` and `-` replaced by one `-`, and leading and trailing `-`
removed.

1.4 IF NAME is empty after trimming, is longer than 35 characters (Slack's limit for an
app name), contains a control character, or has an empty handle THEN the system SHALL
print the reason, write nothing, and exit 2.

1.5 WHEN `--format json` is given THEN the system SHALL print the manifest as JSON;
`--format yaml` (the default) SHALL print YAML.

### Requirement 2 — the one-click link

**User story:** As an operator, I want a link that opens Slack's create-app dialog with
the manifest already filled in, so I never copy and paste a manifest to create the app.

#### Acceptance criteria (EARS)

2.1 WHEN `--link` is given THEN the system SHALL print
`https://api.slack.com/apps?new_app=1&manifest_json=` followed by the percent-encoded,
compact JSON of the manifest Requirement 1 describes.

2.2 Building the link SHALL make no network request and SHALL need no token.

### Requirement 3 — the generated manifest kept beside the CLI config

**User story:** As an operator, I want the manifest I imported kept next to my CLI
config, so an upgrade can regenerate it with the same name and tell me what changed.

#### Acceptance criteria (EARS)

3.1 WHEN `--write` is given without a path THEN the system SHALL write the manifest as
JSON to `slack-app-manifest.json` in the directory of the resolved CLI config (`--config`,
`$THE_LOOP_CLI_CONFIG`, `./.the-loop/cli-config.yaml`, `~/.the-loop/cli-config.yaml`).
WHEN a path is given THEN it SHALL write there.

3.2 WHEN `--write` is given without `--name` AND the target file holds a manifest with a
`display_information.name` THEN the system SHALL reuse that name. WHEN the target file
does not exist THEN it SHALL use the packaged name.

3.3 IF the target file exists, `--name` is not given, and the file is not a JSON object
with a non-empty string `display_information.name` THEN the system SHALL leave the file
untouched, say to pass `--name`, and exit 2.

3.4 WHEN the generated manifest equals the file's content THEN the system SHALL not
rewrite the file and SHALL report it unchanged.

3.5 WHEN the write changes an existing manifest THEN the system SHALL name the bot
scopes and bot events added and removed, and say that an app created from the old
manifest needs its manifest replaced and, when scopes changed, a reinstall.

3.6 WHEN the file is written or found unchanged THEN the system SHALL print its path and
the one-click link for that manifest, and exit 0.

### Requirement 4 — onboarding walks the link

**User story:** As a new operator, I want `/the-loop:init` to take me from "yes, Slack"
to a created app in one click.

#### Acceptance criteria (EARS)

4.1 WHEN the user opts into Slack at `/the-loop:init` THEN init SHALL ask the app's name
(proposing `the-loop`, and saying each operator creates their own app), write the
manifest beside the CLI config with `--write`, and give the user the link to click.

4.2 Init SHALL NOT ask the user to paste a token into the conversation. The user puts
each token in their environment or the configured `env.file`, and the credential
preflight reports only whether it is set.

4.3 WHERE the CLI is not installed, init SHALL print the command for the user to run.

### Requirement 5 — upgrade regenerates it

**User story:** As an operator upgrading the-loop, I want my manifest regenerated when a
release changes the app's scopes or events, so I learn what to change in Slack.

#### Acceptance criteria (EARS)

5.1 WHEN `/the-loop:upgrade-the-loop` finds `slack-app-manifest.json` beside the CLI
config THEN it SHALL run `the-loop channels manifest --write` and report the outcome:
unchanged, or the delta with the replace-and-reinstall instruction.

5.2 WHEN Slack is enabled in the CLI config and no generated manifest exists THEN upgrade
SHALL ask the app's name and generate it (a `needs-user` line under `--dry-run`).

5.3 `.the-loop/manifest.yaml` SHALL list `.the-loop/slack-app-manifest.json` as a
managed, optional file.

## Security considerations

- **Untrusted actors.** Whoever runs the CLI on the operator's machine. The manifest is
  public by design; it names scopes and events, not secrets.
- **Trust boundaries.** None crossed. The command makes no network request and reads no
  token. The link goes to the operator's browser, and Slack's own dialog confirms the
  workspace and the scopes before anything is created.
- **Abuse cases.**
  - *A name that breaks out of the manifest.* NAME is a JSON string value, encoded by the
    JSON serializer and then percent-encoded. Control characters are refused (R1.4), and
    no other key takes NAME.
  - *A tampered generated file that widens the app's scopes.* Regeneration builds every
    key except the name from the packaged manifest, so it can only reset scopes to the
    shipped set. Only `display_information.name` is read from the old file.
  - *Overwriting a file the command did not write.* An unreadable or non-manifest file is
    left untouched unless `--name` is given (R3.3).
  - *A token pasted into the conversation.* The walkthrough sends tokens to the
    environment, never the chat (R4.2).
- **Fail-closed.** Every refusal writes nothing and exits 2.
- **No new scope, event or permission.** The shipped manifest's scopes and events are
  unchanged.
