---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Final validation: outbound Slack through the gateway, and a loud failure when it cannot

> The `evidence` node's proof: the acceptance criteria of `requirements.md`, each mapped
> to how the executed `testing-plan.md` proved it. Summarised from the plan's
> Verification results, not re-derived. Raw output sits beside this file.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1 — `start` logs one warning naming the variable and the gateway's answer (or that it could not be asked), and still starts | T1 `start_all` cases; T2 scenario 5; T11 on real processes: the warning line, then `service started` | [unit.md](unit.md), [integration.md](integration.md), [manual.md](manual.md) |
| R1.2 — `status` and `channels status` name the variable beside the gateway row while nothing can post | T1 `gateway_line` and `channels status` cases; T11: the gateway-client row's suffix, the `posting:` line and `[!]` | [unit.md](unit.md), [manual.md](manual.md) |
| R1.3 — `doctor slack` is `unverifiable` with the same reason | T1 doctor cases (`_probe`, `check_declared_channels`, `_gateway_lines`); T11: the `[!]` gateway line | [unit.md](unit.md), [manual.md](manual.md) |
| R1.4 — `status` and `channels status` say `posting through the gateway` when that is the path | T1 suffix and `posting:` cases | [unit.md](unit.md) |
| R1.5 — Slack disabled prints and logs nothing | T1 `start_all` and `gateway_line` cases with Slack disabled | [unit.md](unit.md) |
| R1.6 — no refusal to start | T1 `start_all` returns `ok`; T2 scenario 5; T11 step 2 | [unit.md](unit.md), [integration.md](integration.md), [manual.md](manual.md) |
| R2.1, R2.2 — one route, the fourteen methods forwarded as a JSON body, Slack's answer verbatim, an unknown method refused with nothing sent | T1 proxy and route cases; T8 abuse case 1; T2 scenario 1 | [unit.md](unit.md), [integration.md](integration.md) |
| R2.3 — no token or no `slack` block on the gateway → `503`, nothing sent | T1 `available` cases; T8 (no token → `503 no-token`) | [unit.md](unit.md) |
| R2.4 — Slack's `ok: false`, a 429 with `Retry-After`, a transport failure come back as they are / as `502` | T1 proxy cases; T2 scenario 1 (the instance's client maps them) | [unit.md](unit.md), [integration.md](integration.md) |
| R2.5 — the contract carries both routes and the served schema matches | T3 | [contract.md](contract.md) |
| R2.6 — `gateway.slack_call` carries method, channel and outcome, never text or the token | T1 log case; T2 scenario 1 asserts the text is absent from the log | [unit.md](unit.md), [integration.md](integration.md) |
| R3.1, R3.2 — the download route under Slack's hosts and the cap; off-host and over-cap refused before any fetch | T1 download cases; T8 abuse case 4 | [unit.md](unit.md) |
| R3.3 — `fetch_attachments` downloads through the gateway and renders as with a local token | T1 attachments cases; T2 scenario 3 (a voice note's transcript) | [unit.md](unit.md), [integration.md](integration.md) |
| R4.1 — a local token is used first, gateway or not | T1 resolver cases; T10 (a 20.9.0 instance config); T2 scenario 4 | [unit.md](unit.md), [integration.md](integration.md) |
| R4.2 — without a token, every outbound site uses the gateway-backed client | T1 resolver, channel, directory, doctor and attachments cases; T2 scenarios 1–3 | [unit.md](unit.md), [integration.md](integration.md) |
| R4.3 — with neither, today's error plus the gateway hint | T1; T2 scenario 5 | [unit.md](unit.md), [integration.md](integration.md) |
| R4.4 — a gateway that is unreachable or refuses fails the post, never a local token | T1 client mapping cases; T2 scenario 6 | [unit.md](unit.md), [integration.md](integration.md) |
| R4.6 — the gateway document and health carry whether the gateway posts | T1 `document()` and health cases; T11: `slack posting:` in `gateway status`, the suffix in `status` | [unit.md](unit.md), [manual.md](manual.md) |
| R4.7 — a thread opened through the gateway is bound and a reply reaches the work item | T2 scenarios 1 and 2 | [integration.md](integration.md) |
| R5.3, R5.4 — the instances allow-list, the peer lease and the body bounds apply to the new routes | T1 route cases (`409`, `422` at the door) | [unit.md](unit.md) |
| R6.1–R6.3 — `slack.post.enabled`, default on, `503` when off, hot-reloaded, shown by `gateway status` | T1 config and route cases; T10; T11 step 3 (`disabled` within the reload cadence, no restart required) | [unit.md](unit.md), [manual.md](manual.md) |
| R6.4 — the onboarding question | T1 schema case (the description the walk asks from); `commands/init-gateway.md` | [unit.md](unit.md), [documentation.md](documentation.md) |
| R7 — the documents say what is true | T12 markdownlint over every touched page; the pages listed | [lint-and-typecheck.md](lint-and-typecheck.md), [documentation.md](documentation.md) |
| Abuse cases 1, 4, 5, 6 and the fail-closed set | T8 (1, 4, 5), the existing non-loopback test under T12 (6), T1 route and client cases (bounds, no token read) | [unit.md](unit.md), [lint-and-typecheck.md](lint-and-typecheck.md) |
| NFR compatibility — no change for an instance with a local token or without a gateway block | T10; T12 (the whole suite) | [unit.md](unit.md), [lint-and-typecheck.md](lint-and-typecheck.md) |

Not proved here, by the plan's decision: the live run against a real Slack workspace (T4
is `n/a` with its reason; offered to the author as a post-merge check on
`the-loop-testing`). Abuse cases 2–3 and R5.1–R5.2 were withdrawn by the owner at the
design review and have no test.
