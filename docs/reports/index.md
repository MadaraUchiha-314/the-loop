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
- [Is `harness-config.yaml` required?](/reports/harness-config-audit) — every reader of
  the per-repository harness config, how each key is enforced, why the file cannot be
  removed, and which keys belong in the CLI config or nowhere (issue-352).
- **The end-to-end Slack test series** — one work item driven from Slack against a live
  deployment, operator-simulated, each run validating the previous run's fixes and
  recording its own findings (redacted; the per-item follow-ups live in
  [`followups/`](/reports/followups/README)):
  - [2026-09-19](/reports/e2e-slack-test-2026-09-19) — the first run: 13 interventions
    and two hours; the findings became issue-393, #395, #396, #397.
  - [2026-09-20 (run 2)](/reports/e2e-slack-test-2026-09-20) — on 19.7.0: five messages
    and 50 minutes; the N1–N3, O7, O9 findings, fixed in PR #402.
  - [2026-09-20 run 3](/reports/e2e-slack-test-2026-09-20-run-3) — on 19.8.3 with zero
    setup deltas: the P1 (typed selection grammar) and P2 (close path vs. the session's
    endgame) findings, fixed in issue-405.
- [The architecture of the-loop (CLI)](/reports/cli-architecture-survey) — how the CLI is
  put together, the exact `the-loop start` / `the-loop execute` flows, which guardrails
  keep `design` behind `requirements-approval` (and which are code), and how the harness
  and the daemon talk — with component and sequence diagrams (issue-354).
