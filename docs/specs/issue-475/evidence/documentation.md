---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Documentation: Jira as a first-class work-item source and update channel (issue-475)

Filled in one PR at a time. This record covers **PR 1 — identity** (tasks 1.1–1.5).

## Capability docs

- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** documents work-item
  refs, so it gains three EARS criteria beside the existing `github:` ref grammar:
  - the Jira ref grammar `jira:<site>/<KEY>-<number>`, its slug and browse URL, and
    the per-provider scheme it parses through;
  - one spec-id derivation (`issue-<n>` / `jira-<key>-<n>`), the `derive_ref` inverse
    from the configured site, and the moved-key refusal;
  - `origin_repository`: a Jira project's mapped GitHub repository, the shared call
    sites that ask it, and the fail-closed refusal of an unplaceable Jira ref.

  Plus a history row for issue-475.

## Documentation

- **Docstrings:** the "`jira:` prefix is reserved" note on `WorkItemRef`
  (`cli/the_loop/sessions/registry.py`) and the `provider`/`id` field notes in
  `cli/the_loop/lifecycle/contract.py` now describe the Jira scheme.
- **Not changed yet, and why:**
  - `migrations._github_sources` and the `polling.sources[].provider` schema description
    still call `jira` reserved for polling. That stays true until PR 4 adds the Jira
    poll provider, and the schema is PR 2's.
  - `docs/config/` and the `integrations.jira` schema are PR 2's. PR 1 reads only
    `integrations.jira.site` and `integrations.jira.projects.<KEY>.repository`, by plain
    mapping access.
  - The skill, the commands and `/init` change in PR 5, when the verbs accept Jira refs.
