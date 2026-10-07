---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Documentation: Jira as a first-class work-item source and update channel (issue-475)

Filled in one PR at a time. This record covers **PR 1 — identity** (tasks 1.1–1.5),
**PR 2 — control-plane integration** (tasks 2.1–2.7), **PR 3 — Jira as ledger and
channel** (tasks 3.1–3.7) and **PR 4 — ingress** (tasks 4.1–4.5).

## Capability docs

- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** documents work-item
  refs, so it gains three EARS criteria beside the existing `github:` ref grammar:
  - the Jira ref grammar `jira:<site>/<KEY>-<number>`, its slug and browse URL, and
    the per-provider scheme it parses through;
  - one spec-id derivation (`issue-<n>` / `jira-<key>-<n>`), the `derive_ref` inverse
    from the configured site, and the moved-key refusal;
  - `origin_repository`: a Jira project's mapped GitHub repository, the shared call
    sites that ask it, the fail-closed refusal of an unplaceable Jira ref, and the
    unqualified `pr-loops/pr-<n>/` layout for a Jira item's pull request in that
    repository.

  Plus a history row for issue-475.

## Documentation

- **Docstrings:** the "`jira:` prefix is reserved" note on `WorkItemRef`
  (`cli/the_loop/sessions/registry.py`) and the `provider`/`id` field notes in
  `cli/the_loop/lifecycle/contract.py` now describe the Jira scheme. The contract's
  `repository` field note says that for a Jira ticket it is the tracker path, not the
  origin repository.
- **Not changed yet, and why:**
  - `migrations._github_sources` and the `polling.sources[].provider` schema description
    still call `jira` reserved for polling. That stays true until PR 4 adds the Jira
    poll provider, and the schema is PR 2's.
  - `docs/config/` and the `integrations.jira` schema are PR 2's. PR 1 reads only
    `integrations.jira.site` and `integrations.jira.projects.<KEY>.repository`, by plain
    mapping access.
  - The skill, the commands and `/init` change in PR 5, when the verbs accept Jira refs.

## PR 2 — control-plane integration

### Capability docs

- **[`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md)**
  documents the integrations, under *Two call planes*. The task named
  `control-plane.md`, but that doc covers the service and has no integrations
  section, so the criteria went where the integrations are already described. They
  cover the Jira provider and its operations, the `create-label` no-op, `transition`
  with the Done category and the configured `closeTransition`, the refusal of
  unknown sites and projects before any request, `resolve("jira")` failing closed on
  a missing credential, and credentials kept out of errors and logs. Plus a history
  row for issue-475.

### Documentation

- **[`docs/decisions/decision-142.md`](../../../decisions/decision-142.md)** and its
  row in `decisions.md`: the pycontribs SDK, REST v3/ADF and v2/wiki, one site per
  deployment, the project → repository map. It supersedes decision-042 point 13.
- **[`docs/config/cli/integrations-options.md`](../../../config/cli/integrations-options.md)**:
  the Jira section is rewritten for the 0.12.0 block. It gains a deployment table, an
  example, one heading per key, the upgrade note for the stub, and the
  `doctor jira` pointer.
- **[`docs/cli/commands/migrate-config.md`](../../../cli/commands/migrate-config.md)**:
  the stub migration, and the current version is now `0.12.0` (the page still said
  `0.10.0`).
- **[`docs/cli/commands/doctor.md`](../../../cli/commands/doctor.md)**: a
  `doctor jira` section.
- **Docstrings:** `graph/integrations/__init__.py` and `resolve()` name the Jira
  provider. The `migrations` module docstring names the issue-475 migration.
- **Not changed yet, and why:**
  - The "jira is reserved" notes on `polling.sources[].provider` and
    `migrations._github_sources` are about polling. They change in PR 4.
  - `webhook.secretEnv` from the design's data model is not in the 0.12.0 schema yet.
    PR 4 adds it with the route it configures, so the key never sits unread.
  - The Markdown → ADF/wiki conversion and the Jira self-marker are PR 3's. Until then
    `JiraClient._body`/`_markdown` send a minimal ADF document (v3) or the text as
    given (v2).

## PR 3 — Jira as ledger and channel

### Capability docs

- **[`docs/capabilities/channels.md`](../../../capabilities/channels.md)** gains a
  *Jira* section under *Current behaviour*, with a diagram and EARS criteria for:
  - the provider-routed ledger (`RoutedLedger`): each event on its own work item's
    tracker, `work-item.create` on `channels.ledger`, nothing recorded back onto its
    source;
  - the shared body selection (`channels/bodies.py`) and the Jira ledger's marked,
    converted comments and `create_issue`, mirror-only projects refused;
  - the Markdown ⇄ ADF / wiki conversion, the task-item checklist and the restored
    sentinel markers;
  - the visible Jira self-marker backed by the `myself` author check;
  - hooks resolving the integration from the ref;
  - the Jira-safe label mapping table and the load-time refusal;
  - the output-only Jira channel, with the mirror-only setup as numbered steps.

  The ledger bullet now names `jira` as a value, the summary line names the Jira ticket
  as a ledger, and the *Design* list and *History* table gain issue-475 rows.

### Documentation

- **[`docs/config/cli/channels-options.md`](../../../config/cli/channels-options.md)**:
  `ledger` takes `github | jira` and says it decides only where `work-item.create`
  opens a ticket; a new *Jira* section with an example and one heading per key
  (`jira.enabled`, `jira.subscribe`, `jira.verbosity`). It changed in the same commits
  as the schema, as the docs-parity test requires.
- **[`docs/cli/commands/add-channel.md`](../../../cli/commands/add-channel.md)**: a
  `jira` row in the type table (an issue key, output only, the configured-project
  rule).
- **[`evidence/jira-bodies.md`](jira-bodies.md)** (T10): the checklist, request-review,
  ask and PR-briefing bodies as ADF and wiki markup, generated from the golden files
  T2 checks on every run.
- **Docstrings:** `jiraformat`, `jiralabels`, `channels/bodies.py` and
  `channels/jira.py` are new and carry their contracts; `jiraapi` (bodies through
  `jiraformat`, `is_self`), `authz` (the Jira marker), `channels/base.py`
  (`RoutedLedger`, `LEDGERS`, `ledger_name`), `channels/bus.py` (routed name,
  `addresses`), `workchannels` (the `jira` type) and `graph/integrations`
  (`integration_for`, the Jira provider's marker and labels) are updated.
- **Not changed yet, and why:**
  - `the-loop channels status` prints the Slack block only; a Jira block can follow
    when the channel has more than three keys to show.
  - The `ask`, `comment` and `add-channel` verbs still write their confirmation through
    GitHub-only paths (`core/sessions.py`, `core/workchannels.py`,
    `core/github_ops.py`, `channels/commands.py` and `channels/inbound.py` construct a
    `GitHubLedger` directly). Making the verbs dispatch by tracker is PR 5 (task 5.2),
    and the CLI capability doc changes with it.
  - The skill, the commands and `/init` change in PR 5.

## PR 4 — ingress

### Capability docs

- **[`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md)**
  gains a *Jira* section under *Current behaviour*, with a diagram and EARS criteria for:
  - the `jira` poll source: one quoted JQL query per project, every arming label in
    its Jira-safe form, mirror-only projects refused at the pre-flight;
  - comments against the poll ledger's cursor, a 429/5xx degrading one project and
    keeping the cursor, closure on the `done` status category;
  - the `/jira-webhook` doorbell: served only with a secret, 401 before parsing, three
    fields read and the issue and comment re-fetched, the event table;
  - one delivery id for both ingresses (`jira-comment-<site>-<id>`);
  - the allow-list by provider (`authorizedUsers[].jira`, no author is unauthorized,
    `jira:<id>` at the human gates, collaborator grants not applying);
  - whose comment it is, including the **relay addendum** below;
  - arming is a label, starting is a person; the unchanged untrusted frame;
  - the webhook setup as numbered steps (admin-registered, secret by variable name,
    events `comment_created` and `jira:issue_updated`).

  The summary line names Jira comments, and the *Design* line and *History* table gain
  issue-475 rows.
- **[`docs/capabilities/channels.md`](../../../capabilities/channels.md)**: the *Jira*
  section gains the relay criterion, and *History* a PR 4 row.

### Design addendum (recorded here and in both capability docs)

PR 3's `JiraLedger` marked every body it posted, relays included, and the Jira ledger
writes as the service account. A Slack-relayed gate answer or control command on a Jira
work item would therefore have been dropped by the Jira ingress as the-loop's own. On
GitHub a relay is posted unmarked under the operator's credentials and read back as the
operator's authorized words. PR 4 mirrors that trust model:

- `JiraLedger` posts a relay (`gate.feedback`, `control.command`) with the visible relay
  marker `[the-loop:relay]` instead of the self-marker, keywords kept
  (`channels/jira.jira_ledger_body`, `authz.mark_relayed_on_jira`).
- Both Jira ingresses accept a service-account comment that carries the relay marker and
  not the self-marker as authorized (`authz.jira_comment_origin`, `RELAY_KEY` on the
  event), and a human gate reads it as `jira-relay:operator`. Every other
  service-account comment is the-loop's own. On anyone else's comment the marker grants
  nothing (`test_relay_marker_from_other_user_grants_nothing`).
- `jiraformat` keeps `[the-loop:relay]` as literal text on read, as it keeps the
  self-marker.

### Documentation

- **[`docs/config/cli/routing-options.md`](../../../config/cli/routing-options.md)**:
  `authorizedUsers[].jira`, with the two rules that differ from GitHub.
- **[`docs/config/cli/polling-options.md`](../../../config/cli/polling-options.md)**:
  `sources[].provider` takes `github | jira`, and a new `sources[].projects` heading has
  an example, the JQL and the rate-limit behaviour.
- **[`docs/config/cli/integrations-options.md`](../../../config/cli/integrations-options.md)**:
  `jira.webhook.secretEnv`.
- Each config page changed in the same commit as its schema key, in both schema copies,
  as the docs-parity test requires.
- **Docstrings:** `poller/jira.py` and `webhook/jira.py` are new and carry their
  contracts. `authz` (relay marker, `is_authorized_on`, `jira_comment_origin`,
  `gate_authorized_users`), `webhook/router.py` (`PROVIDER_KEY`, `RELAY_KEY`,
  `event_provider`, `route(work_items=…)`), `webhook/server.py` (the Jira route),
  `poller/base.py` (`comment_origin`, `from_source(config=…)`), `graphlink.comments_from`,
  `channels/jira.py`, `jiraformat` and `migrations._github_sources` are updated.
- **Not changed yet, and why:**
  - The delivered prompt's header still reads `# GitHub webhook event for <ref>` with an
    empty `Repository:` line for a Jira event. The template is provider-blind, and
    making it provider-aware belongs with the verbs in PR 5.
  - `JiraProvider`'s `list-comments` still marks every service-account comment,
    relays included, as the-loop's own. No gate reads answers from `list-comments` (they
    arrive on the event), so it changes nothing today. Revisit it if a gate ever does.
  - The CLI graph path's own allow-list (`graph.bootstrap` with no
    `authorized_users`) still reads the GitHub logins only. The daemon passes the Jira
    gate list. The CLI's `the-loop graph` on a Jira ref is PR 5's.
  - `authorizedUsers[].jira` holds one id per person, not a list. One id per channel is
    how every other channel's id works (`identity.Principal`), and a second Jira account
    for the same person is a second entry.
  - The skill, the commands and `/init` change in PR 5.
