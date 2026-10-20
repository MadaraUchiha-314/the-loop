---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Documentation: `read.mode: gateway`

Every page that told an operator behind a gateway to use `read.mode: socket`, or said
that only `socket` receives a button press, now names `gateway`.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../../capabilities/channels.md) | A `read.mode: gateway` note under Current behaviour. The button and kickoff-picker rules are restated on reachability (`push_reachable`) instead of `socket` | issue-503 |
| [`gateway.md`](../../../capabilities/gateway.md) | The instance side names `read.mode: gateway` as the setting beside the block. Also covered: fail closed without the block, `channels listen` refused, and the 20.3.0 form migrated | issue-503 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/channels-options.md` | `slack.read.mode`: type `'poll' \| 'socket' \| 'gateway' \| 'off'`, a `gateway` paragraph and the 20.3.0 migration note. The grant table, kickoff picker and slash command say "socket or gateway" |
| `docs/config/cli/gateway-options.md` | A worked example: the `gateway` block beside `read.mode: gateway`, with why |
| `docs/guide/gateway.md` | Step 3 sets `read.mode: gateway`. Leaving the gateway now means removing the block **and** resetting the mode |
| `docs/guide/slack.md` | The manifest comment and the example config's `read.mode` comment name `gateway` |
| `skills/the-loop/reference/onboarding.md` | An instance reading from a gateway is onboarded with `read.mode: gateway`, never `socket` |
| `skills/the-loop/templates/cli-config.yaml` | `read.mode` comment: `poll \| socket \| gateway \| off`. The `appTokenEnv` and grant comments are updated to match |
| `cli/the_loop/schemas/cli-config.schema.json` (+ `.the-loop/` copy) | The enum gains `gateway`. The `read.mode`, `gateway`, `appTokenEnv` and `publish` descriptions are rewritten |
| `cli/the_loop/channels/slack-app-manifest.yaml` | The interactivity comment names `socket or gateway` |
| `README.md` | Not changed: it does not describe Slack read modes |
