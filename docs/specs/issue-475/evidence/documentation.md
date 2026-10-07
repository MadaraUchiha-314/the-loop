---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Documentation: Jira as a first-class work-item source and update channel (issue-475)

Filled in one PR at a time. This record covers **PR 1 — identity** (tasks 1.1–1.5)
and **PR 2 — control-plane integration** (tasks 2.1–2.7).

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
