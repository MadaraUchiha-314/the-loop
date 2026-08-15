# Reports

Working notes and investigations that don't belong to a single work item's spec — deeper
dives, surveys, and reference write-ups produced along the way.

- [GitHub queries](/reports/gh-queries) — the GitHub API queries the poller / webhook
  ingress relies on, and where they live in the CLI.
- [Vendor SDKs vs. binaries](/reports/vendor-sdk-analysis) — whether the-loop should stop
  shelling out to `claude`, `cursor-agent` and `gh` in favour of the vendors' SDKs, and what
  each swap would actually cost.
- [Status labels & dashboards](/reports/labels-and-dashboards) — the label taxonomy
  the-loop defines, why the labels sit unused today, and how they feed a GitHub Projects
  kanban without a bespoke dashboard.
