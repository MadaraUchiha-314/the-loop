---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Security review: outbound Slack through the gateway, and a loud failure when it cannot

> The `security-review` node's proof (`reference/security.md`). Risk tier **4**: the
> change adds two routes to the gateway's contract, moves where a credential is needed,
> and touches a schema under `.the-loop/`. A named human sign-off is required before the
> work item completes, distinct from the PR approval.

## Security review (gate)

- **Mechanism:** Claude Code's built-in `security-review` skill — a focused review of the
  branch's diff against `origin/main` by a sub-agent briefed with the threat model
  (decision-146: no instance authentication, the network is the boundary; the owner's
  design-review decision that any accepted instance may post wherever the bot can). It
  traced the token's path, the download route's host rule, method and parameter
  smuggling into the SDK, response pass-through, the instance's trust in the gateway's
  answers, and the construction-site changes.
- **Outcome:** findings fixed. One finding, below; everything else checked clean.
- **Findings:**

  | # | Severity | Finding | Disposition |
  |---|----------|---------|-------------|
  | 1 | Low (confidence 5/10 as a vulnerability, 9/10 that the code behaved so) | `slack_sdk`'s `api_call` pops a `token` key out of the JSON body and uses it in place of the client's token, so `SlackProxy.call`'s `api_call(method, json=params)` let a peer make the gateway call Slack with a credential the peer supplied, recorded as the gateway's own call. No privilege gained (the peer could call Slack directly with that token), but the design's invariant — the gateway posts with its own token or not at all — was not enforced | **Fixed** — `SlackProxy.call` refuses a `token` key with `422 param-not-allowed` before any web client is built, records `gateway.refused`, and the negative test `test_abuse_7_a_token_in_params_is_refused_before_the_sdk_sees_it` asserts nothing is sent and the value never reaches the log; the contract and the capability page name the refusal |

  Checked and clean (the reviewer's list): the bot token reaches only `WebClient(token=…)` and `fetch_url(credential=…)`, never a response body, header or `eventlog.emit` field; `download` refuses non-`https` and off-host URLs before any request and `fetch_url` re-checks every redirect hop with redirects disabled; `method` must be an exact member of the allow-list before anything is sent and `api_call`'s other keyword arguments are unreachable; only `Retry-After` is copied from Slack's headers; the instance's client caps and type-checks the gateway's answers; the gateway URL probed at `start` is the operator's own config; the construction-site changes add no entry point and change no actor authorization; `/health`'s new `slack.posting` discloses the same class of fact as `slack.socket`.
- **Abuse cases of the requirements:** 1 (method outside the allow-list), 4 (off-host or
  over-cap download), 5 (posting disabled, no token on the gateway) and the new 7 (a
  token in params) have negative tests under `-k abuse`; 6 (a non-loopback bind without
  `exposed`) is the existing gateway test; 2–3 were withdrawn by the owner at the design
  review, and the posture they would have narrowed is stated in the contract and the
  capability page instead.
- **Human sign-off:** _pending_ — requested from @MadaraUchiha-314 on PR #522 with the
  reviewer briefing (risk tier 4): a comment reading `security sign-off: approved` (or
  what must change). Recorded here when it lands.
