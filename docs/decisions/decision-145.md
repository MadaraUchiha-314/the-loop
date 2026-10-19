<!-- Written per the `the-loop:writing` skill. -->

# Decision 145: the gateway's queue contract — subjects, one queue per instance, store-before-ack, pull with commit, at-least-once to idempotent consumers; consumers resolved at ingest by claim, then actor

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-19
- **Deciders:** MadaraUchiha-314 (the ask; pull instead of stream and fan-out by claim on the ticket, 2026-10-19; the requirements and design gates), the-loop (design)
- **Work item:** [issue-496](https://github.com/MadaraUchiha-314/the-loop/issues/496)
- **Spec:** [`docs/specs/issue-496/requirements.md`](../specs/issue-496/requirements.md) R2–R5, R11; [`design.md`](../specs/issue-496/design.md) §`gateway/store.py`, §`gateway/routing.py`, §`gateway/consume.py`, §Trade-offs
- **Contract:** [`docs/api-specs/openapi/the-loop-gateway.v1.yaml`](../api-specs/openapi/the-loop-gateway.v1.yaml)

## Context

Several instances cannot share one Slack app or one webhook URL: each listener is a
second Socket Mode consumer and each receiver a second Request URL. The first design
gave the gateway a stream (SSE) that every instance subscribed to and filtered. The
author rejected it twice on the ticket: a fleet would hold a connection per instance,
and every instance would read the whole firehose to find its own events. The ask was
*"a Kafka-like architecture where all events are written into a queue and the instances
read from it"*, with each instance reaching only its own queue and the gateway
correlating event → work item → instance.

## Decision

1. **Subjects.** Every stored event is on the subject `loop-<slug>` of its work item —
   the tmux slug the instance already uses — or on `unassigned` while nothing consumes
   it. The envelope is exactly the ten fields of R6.2 with the provider's payload
   verbatim; the gateway interprets a payload only far enough to name the work item.
2. **Store before ack.** The event and its fan-out rows are written in one SQLite
   transaction before the provider is answered (`202` to GitHub and Jira, the Socket
   Mode ack to Slack). A store failure withholds the ack so the provider retries.
3. **One queue per instance, fan-out on write.** At ingest the gateway resolves the
   consumers — the claimants of the subject and of each subject linked through a
   binding (a pull request's ticket), else the one instance that registered the
   event's actor, else none — and appends one delivery row per consumer. No instance
   receives or filters another's events; an event with no consumer is held and routed
   when a claim, binding or registration later covers it.
4. **Pull with commit, no stream.** `POST /api/v1/gateway/fetch` refreshes the
   instance's lease, commits the previous batch's outcomes, reads the next deliveries
   of that queue after `max(cursor, committed)`, and long-polls while the queue is
   empty. `committed` advances contiguously; a `failed` outcome leaves the delivery
   pending and it returns with `attempt + 1`, dead-lettered at `store.maxAttempts`.
5. **At-least-once to idempotent consumers.** A crash between dispatch and commit
   redelivers; the instance's existing dedup layers (the router's deduper, the record's
   recent delivery ids, `control-deliveries.json`) drop the duplicate. The gateway
   never claims exactly-once.
6. **Claims and actors are what the instance already knows.** A registered session
   publishes a claim `{subject, instance, role}` — `driver` for a ticket, `reviewer`
   for a pull request under `review` — and releases it when it closes; an instance
   registers the actors it works for on start and after every outage; a bound Slack
   thread or a linked pull request publishes a binding. Each is a `UNIQUE` row the
   gateway lists (`gateway subjects|instances`), so a misdirected work item is visible.
7. **The store is the seam.** `Store` is the one interface a replica would replace;
   nothing but the long-poll `Condition` lives in process memory, so a restart loses no
   offset, claim or registration.

## Consequences

- The gateway's work per fetch is bounded by that instance's backlog (an index range on
  `deliveries(instance, seq)`), never by the fleet's size or traffic; it holds at most
  one open request per long-polling instance and none for a plain poller.
- Latency under plain polling is one poll interval; long-polling makes it one wake-up.
  The SSE grammar of decision-087 is not reused here.
- Write amplification is one row per consumer; events rarely have more than two (a
  driver and a reviewer).
- **Deferred, named here so the follow-ups start from the record:** a work-item lease
  over claims, so one user's subjects can be split across several instances with
  fencing (brainstorm option D); multi-replica gateways over a shared store (sharding
  Socket Mode connections and poll sources). Neither changes the envelope or the commit.

## Alternatives considered

- A stream (SSE) every instance filters — rejected by the author: connections grow with
  the fleet and every instance reads everything.
- A broker (Kafka, NATS, Redis streams) — a new runtime dependency and a second process
  to operate, for a queue whose readers number in the tens; SQLite from the standard
  library gives transactional offsets, a unique dedup index and a bounded delete, which
  the JSONL event log (decision-025) cannot.
- Routing on read (every fetch scans every event) — costs every instance the whole
  table; routing once on write is three small table reads.
- A lease and election for work-item ownership in the first landing — removed by the
  author on the ticket; claims and actors answer the routing question without a
  fencing token, and a lease can later guard both.
