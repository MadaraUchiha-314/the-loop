---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#466"
---

# Self-review: arming a linked pull request (issue-466)

> No `cli-config.yaml` declares critics in this cloud checkout, so the critic rounds
> are unavailable. Round 3 found nothing new, which meets the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) Labelling in `core.sessions.link_pull_request` would put a GitHub call on a path many tests and the registry use without a client. Moved to a `github_ops.link_pull_request` wrapper that every entry point calls. (b) Re-labelling on every discovery run would cost a request per push and undo a person's removal. Now only a newly recorded link is labelled; `pr create` labels whenever its link succeeded. (c) A labelled PR whose link failed would be armed but untracked. Now labels follow a recorded link only (R3) |
| 2 | self (diff read) | new findings | (d) The `sdk/client.py` import was out of order. Moved. (e) The MCP tool descriptions, which agents read, did not mention the labels. Updated. (f) `execute-tasks.md` still pointed to the "execution log", which issue-365 retired. It now points to `evidence/pull-requests.md` |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Does a webhook-recorded link starve `link-pr` of labels?** For `pr create`, no: it
  labels whenever its link succeeded. For a PR opened by hand that a webhook recorded
  first, the webhook path already routes its events, so labels are not needed there.
- **Can a label request reach an unconfigured host?** No. `_trusted` runs before the
  client is built, and a test asserts that no call is made.
- **What does an empty `autoExecuteLabels` do?** It applies nothing and makes no request,
  which matches the poller: an empty list arms nothing.
- **Does `--discover` still report the same `linked` list?** Yes. The wrapper returns
  core's result unchanged, plus `labels` and the extra message.
