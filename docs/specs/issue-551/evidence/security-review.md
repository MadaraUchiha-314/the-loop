---
type: evidence
workItem: issue-551
---

# Security review: a session never goes idle unnoticed

> The `security-review` node's proof. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop's checklist, run by an independent reviewer
  (`[claude/fable-5.2]`) over `git diff 667acd46..HEAD`, after the two self-review
  rounds and the critic round. The reviewer read the diff and both security
  sections, ran the seven abuse-case test files, and probed the derivation, the stop
  check and the channel renderers with throwaway scripts.
- **Outcome:** findings fixed, two recorded, one decision open for the approver.
- **Risk tier:** 4. The change touches the config schema (`**/*schema*`,
  `.the-loop/**`) and the harness hooks.
- **Human sign-off:** pending. Requested on the pull request; this line is updated
  with the handle and the link when it is given.

## Checklist

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Trust boundaries enforced where the design says | pass, with one stated difference | The design says the service refuses a ref the caller is not bound to. As built, the service confirms the ref names a live registered session and authenticates no caller. See "The binding check". |
| 2 | Untrusted input validated; injection surfaces covered | pass after F3 | The nudge inserts only the node id, the node's command, the ref and the idle minutes; the node and command come from the operator's config or the bundled graphs, never the checkout. Subprocess calls use argument lists; a ref that starts with `-` is refused. Defaults, questions and conditions render inert on Slack, GitHub, the terminal and the UI. |
| 3 | Untrusted content cannot steer privileged behaviour | pass | An unauthorized author is dropped at the router. A collaborator with input-only rights closes no ask and resets no budget. The "default taken" comment carries the agent-comment marker and no gate reads it. |
| 4 | No secrets | pass | Defaults and conditions pass the existing scrubbing at the routes. The evidence directory holds no token, address, home path or Slack id. |
| 5 | Checks fail closed | pass after F1, with F2 open | A default with no readable time is never taken. A disabled or unwritable log means the watcher does nothing. Waits, forged background work and give-ups are each bounded and then covered by the watcher. |
| 6 | Least privilege | pass | No new scope. The routes are loopback-only unless the operator exposes the service, as before. |
| 7 | Each abuse case has a passing negative test | pass | [`security-tests.md`](security-tests.md): 324 tests selected, each abuse case mapped. |
| 8 | New dependencies | pass | None. |

## Findings

| # | Severity | Finding | Disposition |
|---|---|---|---|
| F1 | medium | A session that blanks its own pointer file stops as `inconclusive` and is never reported. | Fixed, `65eb9239`: a work item's own session in that state gets the one notice. A pull request's own session keeps its carve-out. |
| F2 | medium/low | "Working" has no time bound: repeated turn-start calls, or a turn that ends with no Stop hook, keep a session looking busy forever. | **Open, for the approver.** The approved requirements put a turn that hangs out of scope. |
| F3 | low | A default kept control characters and was pasted raw. | Fixed, `563d1349`: one shared policy drops them when the default is recorded and again when it is pasted. |
| F4 | low | `session.reply_sent` reset the nudge budget, and the unauthenticated reply endpoint writes it. | Fixed, `a7cfc905`: only a pointer move, `ask_answered`, an actor-named delivery or an authorized Slack reply resets a budget. |
| F5 | low | No negative test for an input-only collaborator's comment. | Fixed, `4d13ac0a`: test added; it passed at once, so the code was right. |
| F6 | low | No rate limit on `turn-start`, `wait` or `ask`; a question has no size cap; the event log never rotates. | Recorded as a limit. The log's growth is older than this change. |

## The binding check

The three new operations and `the-loop wait` are meant to act only on the session's
own work item. What enforces that:

- The CLI refuses a ref that differs from the session's work-item variable, and
  refuses a shell that carries the daemon's instance variable but names no work item.
- The service refuses a ref that names no live registered session.

What does not: the service authenticates no caller. A steered session that unsets its
variables, or calls the API directly, can name another registered work item. It
could end that session's stall, record a wait or a turn end for it, or open an ask on
it. The reviewer judged this no greater than what the reply operation already
allows, since that operation pastes arbitrary text into any session. The risk is low
on a single-user host and medium on a shared one. Closing it needs a per-session
credential, which is a work item of its own.

## Decisions asked of the approver

1. Sign off on this review, accepting the binding check as built.
2. F2: bound "working" now (a notice, never a nudge, after a long time in one
   turn), or keep it out of scope as the requirements say.
3. Accept F6 as a recorded limit.
