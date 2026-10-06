---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#462"
---

# Self-review: CI monitoring and self-healing (issue-462)

> No critics are configured in this cloud checkout (`.the-loop/cli-config.yaml` declares
> none), so the critic rounds could not run. Round 6 (after the owner's poll-ingress ask) found
> nothing new, which meets the stop rule (3 self, 3 critic, stop on no new findings).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) Treating `cancelled` as a failure would wake the session for every run a newer push superseded, since `concurrency: cancel-in-progress` cancels them. The gate ignores `cancelled` and `stale`; `pr status` still counts `cancelled` as failing, unchanged. (b) A `rerequested` or `requested_action` check run re-sends the old run's completed state, so it would be counted again. Now ignored. (c) Delivering `check_suite` and `workflow_run` too would wake the session two or three times per failure. Only the per-job `check_run` is delivered. (d) PyGithub's streaming download cannot be exercised by the suite's replay double. The client reads `Location` and fetches it itself, which is as safe and testable. |
| 2 | self (diff read) | new findings | (e) `_download_tail` read a whole 64 KiB chunk even when the cap was smaller, so the cap was not exact and a cut log was not reported. It now reads `min(chunk, cap − read)`, and drops the last, partial line of a cut log. (f) The PR-scope lookup matched a work item by number only. It now also checks the event's repository. (g) The design named a `pull_request` string on `CiSignal`, but the code carries `pull_number` and resolves the ref against the router's refs, so the ref keeps its host. Design updated. (h) The settled-vocabulary test requires every new settled outcome to be listed there and in `poll.comment_settled`'s catalogue entry. Both added. |
| 3 | self (adversarial read) | new findings | (i) The spec said the gate reads at most 8 MiB of a log, but keeping the *tail* means reading to the end. The requirement now says the tail is kept in a 256 KiB window and reading stops at 32 MiB, with a marker line when the log is cut. (j) The security text said PyGithub strips the token on redirect; the implemented path never sends it at all. Reworded. |
| 4 | self (adversarial read) | zero (converged) | — |
| 5 | owner (PR #470) + self | new scope | The owner asked for CI on the poll ingress, on its own frequency. Added as R6 / design Part D / T13. Self-read of that diff: (k) reading CI for every listed PR would spend three requests on PRs nobody works; only a PR a live session owns is read. (l) Forwarding every completed result every CI cycle would rely on the in-memory dedup, which a restart empties; the `ciSeen` ledger makes it once across restarts. (m) A running check would be dropped by the gate anyway; the provider leaves it out. |
| 6 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Can the gate hide a real failure?** Only a failure of a check whose attempts are
  spent, and only after the session was told once to stop and escalate. Every withheld
  event is logged with its reason and check name.
- **What happens on a daemon restart?** The counts are lost, so each check can get
  `maxAttempts` more attempts. That is stated in the requirements, the schema
  description and the routing options page.
- **Does a custom `promptTemplate` lose the section?** No. It is appended after the
  rendered template and the attachments, the same way attachments are (test: the section
  coexists with the template's UNTRUSTED framing).
- **Does a non-CI event change?** No. `classify` returns `None`, the event is returned
  unchanged, `ci_note` stays empty, and the prompt is byte-identical (test).
- **Does `autofix: false` restore the old behaviour exactly?** Yes. The gate is not
  called at all (test: a passing and a failing run are both delivered, with no section).
- **Does a poll-only installation get the feature?** Yes, since round 5: `polling.ci`
  reads each live PR's checks every `intervalSeconds` (default 300) and hands each new
  result to the same gate (test: a polled failure reaches the session with the CI
  section; a polled pass does not).
- **Can a fork's PR be healed?** Its `check_run` names no pull request, so the budget
  is scoped to the work item, and the section asks for `pr checks <your pull request>`.
