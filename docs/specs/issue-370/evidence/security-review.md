---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#370"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a pull request is tracked because the-loop recorded it

> The `security-review` node's proof. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (risk tier 3 — no auth, secret or credential path, no
  workflow or schema change; `hooks/**` and `.the-loop/**` are not the same tree)
- **Outcome:** pass — one finding, fixed before the gate
- **Human sign-off:** n/a (risk tier below 4)

## The threat model this change moves

**It closes more than it opens.** The removed behaviour was itself a small integrity
problem: anyone who could open a pull request against a watched repository could get it
filed against a work item's tracking — a durable entry in `portable/`, and a row in a
**committed** `work-item-state.json` — by naming a branch `issue-<n>` or writing
`fixes #<n>`. Neither required any authorization, and nothing removed the entry
afterwards. Tracking now records only what the-loop itself did.

Delivery inference stays, deliberately, and is unchanged: it decides which conversation
hears an event, it is re-derived every time, and the arming/authorization gates in front
of it are untouched by this work item.

## New attack surface: the `PostToolUse` hook

| Vector | Why it does not work |
|--------|----------------------|
| Command injection through the tool payload | Both subprocesses are argv lists; `shell=True` is absent and a test asserts it stays absent |
| A crafted pull-request URL in a tool's output | The number and coordinates come from `_PR_URL_RE`, whose name shapes are GitHub's own; anything else does not match, and the captured text is what reaches the argv |
| A crafted `THE_LOOP_WORK_ITEM` | Validated against `github:[host/]owner/repo#n` before use; an unparseable value falls through to the registry and then to silence, never to an argument (`test_an_injected_work_item_ref_is_refused`) |
| Adopting the wrong work item | Resolution is `THE_LOOP_WORK_ITEM` → registry by harness session id → registry by cwd, and stops. There is no branch-name guess — reintroducing one here is the thing this work item removes. A `closed` session record never claims a pull request |
| Hanging a session | Both calls carry `CLI_TIMEOUT_SECONDS`; every path exits 0, so a hook failure can never block a tool call |
| Recording a pull request that was never created | The number is read from the tool's **response**, so a failed, interrupted or dry-run creation links nothing |

**One finding, fixed:** `--dry-run` was matched as a substring of the command, so a title
containing that text would have suppressed a real recording. Availability, not
confidentiality, but it is the failure the hook exists to prevent. Now matched as a flag.

## The env var the runner now exports

`THE_LOOP_WORK_ITEM` carries a `WorkItemRef.ref` into `tmux new-session -e`. It is an argv
list, so the value cannot become a second argument, and tmux treats it as opaque. The ref
is composed from a webhook payload's repository coordinates, so the value is not
guaranteed to be well-formed — which is why every reader validates it rather than trusting
it, and why the hook answers "unknown" for a ref that does not parse. A standing session,
which has no work item, exports nothing.
