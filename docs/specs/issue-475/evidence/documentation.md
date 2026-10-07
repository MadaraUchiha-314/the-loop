---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Documentation: Jira as a first-class work-item source and update channel (issue-475)

This record covers all five PRs of the stack: **PR 1 — identity** (tasks 1.1–1.5),
**PR 2 — control-plane integration** (2.1–2.7), **PR 3 — Jira as ledger and channel**
(3.1–3.7), **PR 4 — ingress** (4.1–4.5) and **PR 5 — edges** (5.1–5.4). Each PR updated
its capability docs in the same PR as the behaviour; the last section lists what a PR
deferred and where it closed.

## Capability docs

### PR 1 — identity

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

### PR 2 — control-plane integration

- **[`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md)**
  documents the integrations, under *Two call planes*. The task named
  `control-plane.md`, but that doc covers the service and has no integrations
  section, so the criteria went where the integrations are already described. They
  cover the Jira provider and its operations, the `create-label` no-op, `transition`
  with the Done category and the configured `closeTransition`, the refusal of
  unknown sites and projects before any request, `resolve("jira")` failing closed on
  a missing credential, and credentials kept out of errors and logs. Plus a history
  row for issue-475.

### PR 3 — Jira as ledger and channel

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

### PR 4 — ingress

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

### PR 5 — edges

- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** gains two EARS
  criteria: the ticket verbs dispatch by tracker (`core/tickets.tracker_for`), with
  each verb's Jira behaviour (`ticket show` in the GitHub shape, `ticket create
  --project`, `ticket close` transitioning into Done and refusing an ambiguous choice,
  `comment` and `ask` on the Jira ledger, `pr create` in the origin repository, the
  refusals before any request, announcements as relays); and the CLI graph path
  accepting the daemon's provider-aware gate identities. Plus a history row.
- **[`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md)**:
  the `jira-key` linkage source as an EARS criterion (branch and title only, the three
  checks, abuse case 7), and the provider-aware prompt header. Plus a history row.
- **[`docs/capabilities/channels.md`](../../../capabilities/channels.md)**: every verb
  records on the work item's own tracker, `list-comments` reads a relay as the
  operator's words, and the `channels status` Jira block. Plus a history row.

### Review fixes (on #480)

The fixes from the self-review, critic and security rounds added one-sentence notes to the
capability docs they changed:

- `docs/capabilities/channels.md`: GitHub bodies are unaffected by the visible marker (L1);
  wiki round-trip edges (L5); markers in mirrored content are broken before posting to Jira,
  and only a standalone opening paragraph from the service account is a gate record (C1).
- `docs/capabilities/webhook-triggers.md`: control comments run once across both ingresses
  (M1, R2-2); the doorbell refuses a moved ticket (L2) and is rebuilt on hot reload (L3);
  only the service account's comments carry gate markers (R2-4); the doorbell fetches its
  comment by id, and all comment pages are read (C2).
- `docs/capabilities/cli.md`: a PR in a Jira item's mapped repository is that item's own
  delivery (C3).
- `docs/capabilities/process-graph.md`: a migrated Jira stub that can't pass the schema is
  dropped with a note (R2-1).

## Documentation

### PR 1 — identity

- **Docstrings:** the "`jira:` prefix is reserved" note on `WorkItemRef`
  (`cli/the_loop/sessions/registry.py`) and the `provider`/`id` field notes in
  `cli/the_loop/lifecycle/contract.py` now describe the Jira scheme. The contract's
  `repository` field note says that for a Jira ticket it is the tracker path, not the
  origin repository.

### PR 2 — control-plane integration

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

### PR 3 — Jira as ledger and channel

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

### PR 4 — ingress

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

### PR 5 — edges

- **[`docs/cli/commands/ticket.md`](../../../cli/commands/ticket.md)**: the Jira
  examples, `ticket show`'s Jira shape, `--project` beside `--repository`, the
  transition rule for `ticket close`, and the exit-2 cases.
- **[`docs/cli/commands/comment.md`](../../../cli/commands/comment.md)**,
  **[`ask.md`](../../../cli/commands/ask.md)** and
  **[`pr.md`](../../../cli/commands/pr.md)**: a `jira:` ref in `--work-item`, and
  `pr create`'s origin-repository rule.
- **[`docs/cli/commands/channels.md`](../../../cli/commands/channels.md)**: the
  `status` Jira block.
- **[`docs/cli/lifecycle-hooks.md`](../../../cli/lifecycle-hooks.md)**: `provider` is
  `github | jira`, no longer "jira reserved".
- **[`docs/guide/quickstart.md`](../../../guide/quickstart.md)**: `/the-loop:work-on`
  takes a `jira:` ref when `integrations.jira` is configured.
- **README and docs site.** A search of `README.md` and `docs/` (outside `docs/specs/`)
  for Jira-via-MCP wording found none to change. The "Jira via MCP" lines were in the
  skill (`reference/collaboration.md`, `reference/workflow.md`) and the commands, and
  changed in task 5.3.
- **[`docs/api-specs/openapi/the-loop.v1.yaml`](../../../api-specs/openapi/the-loop.v1.yaml)**:
  `TicketCreateBody` gains `project`, and `repository` is no longer required (T12).
  The MCP `create_ticket` tool takes `project` too.
- **The skill and the commands (task 5.3):** `commands/work-on.md`,
  `create-ticket.md`, `finish-tasks.md`, `skills/the-loop/reference/automation.md`,
  `collaboration.md` and `workflow.md` run a Jira-ticketed item on its `jira:` ref, the
  Jira MCP tools only the fallback without the CLI. `commands/init.md` (step 5) and
  `reference/onboarding.md` § Jira onboarding add the Jira walk, and the credential
  preflight collects the Jira variable names.
- **Prompt templates:** `skills/the-loop/templates/webhook-event-prompt.md` and
  `webhook-autoexecute-prompt.md` take `$event_source` and `$event_origin`, in step with
  the dispatcher's built-in defaults.
- **Docstrings:** `core/tickets.py` is new and carries its contract; `webhook/router.py`
  (`SOURCE_JIRA_KEY`, `JiraLinkage`, `jira_linkage`), `core/github_ops.
  _pull_request_owner`, `channels/jira.ledger_for_ref`, `graph/integrations/jira.
  JiraProvider._as_read` and `graph/bootstrap` are updated.

### Review fixes (on #480)

- `docs/cli/state.md`: a `jira:` ref has a browse URL; the new
  `<state.root>/local/control-deliveries.json` store is documented (M1).

## Design addendum (PR 4, recorded here and in both capability docs)

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

PR 5 carries the same rule to the remaining readers: `JiraProvider`'s `list-comments`
reads a service-account relay as `jira-relay:operator`, and the CLI's own announcements
on a Jira ticket (a control command, an `add-channel` declaration) are posted as relays.

## Deferred items, and where they closed

| Deferred in | Item | Closed in |
|---|---|---|
| PR 1 | `polling.sources[].provider` and `migrations._github_sources` called `jira` reserved | PR 4 |
| PR 1 | `docs/config/` and the `integrations.jira` schema | PR 2 |
| PR 1, 2, 3, 4 | the skill, the commands and `/init` | PR 5 (task 5.3) |
| PR 2 | `webhook.secretEnv` absent from the 0.12.0 schema | PR 4 |
| PR 2 | Markdown → ADF / wiki conversion and the Jira self-marker | PR 3 |
| PR 3 | `channels status` printed no Jira block | PR 5 |
| PR 3 | `ask`, `comment` and `add-channel` wrote through GitHub-only paths | PR 5 (task 5.2) |
| PR 4 | the delivered prompt read `# GitHub webhook event` with an empty repository line | PR 5 |
| PR 4 | `list-comments` read a relay as the-loop's own | PR 5 |
| PR 4 | the CLI graph path accepted GitHub logins only at a gate | PR 5 |
| PR 4 | `authorizedUsers[].jira` holds one id per person | stays, by design: one id per channel, as every channel |
