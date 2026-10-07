---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Reviewer briefing: Jira as a first-class work-item source and update channel

Each PR in the stack has an R10 briefing, built from the-loop's `pr-briefing` template,
posted as a top comment before human review was requested:

| PR | Briefing | What it asks the reviewer to look at first |
|----|----------|--------------------------------------------|
| #476 | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/476#issuecomment-6042727153) | `RefScheme`, where `GitHubScheme` is the old code moved; disjoint spec-id prefixes; the `origin_repository` call sites |
| #477 | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/477#issuecomment-6042727721) | secret handling in `jiraapi.py`; the `configschema` keyword additions; the 0.12.0 migration; transition refusal |
| #478 | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/478#issuecomment-6042728392) | Jira markers (service-account-only, quoted markers neutralised); `RoutedLedger` and bus hooks; GitHub byte-identity of `bodies.py` |
| #479 | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/479#issuecomment-6042729226) | authorization by provider; the relay addendum (asks for confirmation); the doorbell; JQL quoting and pagination |
| #480 | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/480#issuecomment-6042729975) | every review fix, one commit each; `SOURCE_JIRA_KEY` linkage; `tracker_for`; the follow-up issue list (asks for agreement) |
