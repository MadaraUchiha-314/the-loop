---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#340"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Design: `the-loop progress`

> Phase 2 of 4. Derived from [`requirements.md`](requirements.md). It follows the path
> `ask` laid ([issue-208](../issue-208/design.md), [issue-482](../issue-482/design.md)); the
> parts that are new are the label gate, the rate limit and one Slack rule.

## Overview

```mermaid
flowchart LR
  CLI["the-loop progress"] -->|service answers| R["POST /api/v1/sessions/progress"]
  CLI -->|no service| C
  R --> M["manager facade<br/>(proxies to the member)"] --> F["api facade"] --> C["core.progress.progress_session"]
  C --> L["label gate<br/>(the tracker)"]
  C --> T["rate limit<br/>(the event log)"]
  C --> B["bus.publish<br/>session.progress"]
  B --> S["Slack room<br/>one live line, edited in place"]
```

`core/progress.py` owns the verb; the CLI, the route, the manager facade and the SDK are thin
callers, as for every session verb. Core never prints: it returns `messages`, `exitCode` and
a `status`.

## Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | The verb is `progress`, a sibling of `ask`, and shares its routing | The same constraint holds: a spawned session has no token, and the label read and the room post need one |
| D2 | The opt-in is a **label read at call time**, not config | The issue asks for add-the-label-and-it-works: no edit, no restart, per issue |
| D3 | `status` is one of `sent`, `disabled`, `not-opted-in`, `rate-limited`, `label-unreadable`; the first four exit 0 | An agent can call the verb unconditionally without its exit code meaning "I failed" |
| D4 | The rate-limit clock is the **event log**: the newest `session.progress` for the item | The log is the source of truth for what was emitted (decision-025); a second store would be a second thing to drift |
| D5 | A too-soon report is **dropped, with the wait named**, not queued | A trailing flush needs a timer in a process the verb does not own; the agent's next call is the newest report anyway (see open question 1) |
| D6 | The event is **not recorded** on the ledger | The issue calls it "a signal, not a record"; the ticket already holds the detail |
| D7 | In an agentic room the line is **edited in place**, under its own key | `room_policy` already lists `session.progress` among its progress events; keyed by phase it would overwrite the runtime's message, so it is keyed `session.progress` |
| D8 | The text is defused in `SlackBotChannel.post`, before any rendering | Slack parses the plain-text fallback as well as the blocks, so defusing the blocks alone left a `<!channel>` live |
| D9 | The config is a top-level `progress` block; the config version is not bumped | The block is optional and adds a key rather than moving or removing one, as `selfDiagnosis` did |
| D10 | The feature is in no default subscription | An operator who has not asked for progress hears none, so existing deployments are unchanged |

## Components

- **`core/progress.py`** — `ProgressConfig`, `shorten`, `progress_session`. Reads the label
  through the tracker (`github_ops` client for GitHub, `JiraClient.labels` for Jira) and the
  rate-limit clock through `core.events.query_events(..., since=)`.
- **`commands/progress_cmd.py`** — the CLI, routed with `harness_routed` exactly as `ask` is.
- **API** — `SessionProgressBody`, `POST /sessions/progress`, `CoreFacade.progress_session`,
  `ManagerFacade.progress_session`, the OpenAPI contract.
- **`channels/events.py`, `eventlog.py`** — the catalog row and the event-log row.
- **`channels/room_policy.py`** — the key for the live line.
- **`channels/slack.py`** — the title, and the defusing at `post`.

## Error handling

| Situation | Result |
|-----------|--------|
| Empty text, malformed ref | `ValueError` before any read; CLI exit 2, route 400 |
| Label missing | `not-opted-in`, exit 0, nothing emitted |
| Feature off (`label: ""`) | `disabled`, exit 0, no tracker call |
| Tracker error reading labels | `label-unreadable`, exit 1, nothing emitted |
| Inside the interval | `rate-limited` with `retryAfterSeconds`, exit 0 |
| No channel subscribes | `sent`, with a note that nobody subscribes; the event is still logged |

## Security design

- *Untrusted text* — defused before rendering, plain-text fallback included (D8, R4.4); never
  written on the ticket (D6).
- *Flood* — three independent brakes: the label, the interval, the two-line cap; an unreadable
  label fails closed (R2.5).
- *Self-enabling* — the verb reads the label and never writes it.
- *Credential reach* — nothing new; the service holds the token, the session holds none.

## Open questions

1. **Keep the newest, or drop the late one?** The issue says reports faster than the interval
   should keep the newest. D5 drops the too-soon one and names the wait, which makes the
   agent's next call the newest. A true trailing flush needs a timer in the service. Which
   does the owner want?
2. **Edit in place, or reply in the thread?** An edit shows one current line and does not
   notify; a reply notifies and keeps history. D7 follows the room policy's existing intent.
3. **Where does the config live?** A top-level `progress` block is easiest to read. It could
   sit under `channels` or `routing` instead.
4. **Risk tier.** Declared 4 because a schema file changes; the owner may lower it.
