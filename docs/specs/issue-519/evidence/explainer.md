---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Explainer of the change: outbound Slack through the gateway, and a loud failure when it cannot

> Written by the `code-explainer` node (issue-488): where the explainer of the change and
> the code quiz were published, so the `code-quiz` gate can link the author to them and
> the reviewer briefing can start from them.

## Explainer

| Field | Value |
|---|---|
| Depth | deep |
| Location | https://claude.ai/artifact/BZYrYR1HmDNoniUN73HWaK |
| Published as | spec-chain artifact tab ("Explainer" and "Code quiz", beside the spec tabs) |
| Questions | 5 |

Depth `deep`: two new modules, two new routes on the gateway's contract, a credential that
moves. The page walks the change in execution order — the instance picks a client, the
gateway-backed client, the gateway makes the call, health and the wording, the two small
attachment changes — with `file:line` excerpts on PR #522's branch, and closes with Risks
and limits (the stated posture, the allow-list as a maintenance point, the one local
service call in `channels status`, the start-time probe, what was not done). The quiz
mixes code-level and spec-level questions, answer positions fixed and balanced.
