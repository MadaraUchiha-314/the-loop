/**
 * The append-only decision trail — `/api/v1/events` over
 * `<state.root>/logs/events.jsonl`.
 *
 * Level and work-item filtering are server-side (`level` is a minimum, so
 * `warning` includes errors). What the page adds (issue-283 B7, feature #4):
 * the UI's own `api.request` traffic is hidden unless asked for — a polling
 * dashboard otherwise fills the whole window with its own reads within
 * minutes — plus an event-namespace filter, a live-tail toggle, and a
 * permalink per work item's filtered view (`#/events/<ref>`).
 */

import { useEffect, useMemo, useState } from "react";

import { describeEvent, eventRef, levelTag, relativeTime, shortRef } from "../api/model.ts";
import type { EventRecord } from "../api/types.ts";
import { useApi } from "../state/ApiContext.tsx";
import { navigate } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";

const LEVELS = ["all", "info", "warning", "error"] as const;
type Level = (typeof LEVELS)[number];

/** The dot-namespaces the log carries — `poll.*`, `graph.*`, … */
const NAMESPACES = [
  "all",
  "control",
  "dispatch",
  "graph",
  "poll",
  "routing",
  "session",
  "standing",
  "channel",
  "webhook",
  "workspace",
  "stream",
  "service",
  "api",
] as const;
type Namespace = (typeof NAMESPACES)[number];

/** The UI's own read traffic — noise unless explicitly asked for (B7). */
const API_TRAFFIC = new Set(["api.request", "mcp.call"]);

/** How often the live tail re-reads the log. */
const TAIL_SECONDS = 5;

export function Events({ refFilter = "" }: { refFilter?: string }) {
  const { api } = useApi();
  const [level, setLevel] = useState<Level>("all");
  const [namespace, setNamespace] = useState<Namespace>("all");
  const [showApiTraffic, setShowApiTraffic] = useState(false);
  const [tail, setTail] = useState(false);
  const [tick, setTick] = useState(0);

  const events = useAsync(
    (signal) =>
      api.events(
        {
          ...(level === "all" ? {} : { level }),
          ...(refFilter ? { workItem: refFilter } : {}),
          ...(namespace === "all" ? {} : { type: [`${namespace}.*`] }),
          limit: 200,
        },
        signal,
      ),
    [api, level, refFilter, namespace, tick],
  );

  useEffect(() => {
    if (!tail) return undefined;
    const timer = setInterval(() => setTick((value) => value + 1), TAIL_SECONDS * 1000);
    return () => clearInterval(timer);
  }, [tail]);

  const rows = useMemo(() => {
    const all = (events.data ?? []).toReversed();
    return showApiTraffic ? all : all.filter((event) => !API_TRAFFIC.has(event.event));
  }, [events.data, showApiTraffic]);

  // The refs present in the loaded window, for the work-item filter select.
  const refs = useMemo(() => {
    const seen = new Set<string>();
    for (const event of events.data ?? []) {
      const ref = eventRef(event);
      if (ref) seen.add(ref);
    }
    if (refFilter) seen.add(refFilter);
    return [...seen].toSorted();
  }, [events.data, refFilter]);

  return (
    <>
      <div className="lp-page-head">
        <h1 className="lp-h1">Events</h1>
        <span className="lp-subtle">the decision trail — newest first</span>
      </div>

      <div className="lp-filters">
        {LEVELS.map((choice) => (
          <button
            key={choice}
            type="button"
            className="lp-tab"
            aria-current={level === choice ? "page" : undefined}
            onClick={() => setLevel(choice)}
          >
            {choice}
          </button>
        ))}
        <select
          className="input lp-filter-select"
          aria-label="Event type"
          value={namespace}
          onChange={(event) => setNamespace(NAMESPACES.find((n) => n === event.target.value) ?? "all")}
        >
          {NAMESPACES.map((choice) => (
            <option key={choice} value={choice}>
              {choice === "all" ? "every type" : `${choice}.*`}
            </option>
          ))}
        </select>
        <select
          className="input lp-filter-select"
          aria-label="Work item"
          value={refFilter}
          onChange={(event) => {
            const ref = event.target.value;
            navigate(ref ? { name: "events", ref } : { name: "events" });
          }}
        >
          <option value="">every work item</option>
          {refs.map((ref) => (
            <option key={ref} value={ref}>
              {shortRef(ref)}
            </option>
          ))}
        </select>
        <label className="lp-filter-check">
          <input
            type="checkbox"
            checked={showApiTraffic}
            onChange={(event) => setShowApiTraffic(event.target.checked)}
          />{" "}
          show API traffic
        </label>
        <label className="lp-filter-check">
          <input type="checkbox" checked={tail} onChange={(event) => setTail(event.target.checked)} /> live tail
        </label>
      </div>

      {events.error ? (
        <div className="lp-skeleton">Could not read the event log: {events.error.message}</div>
      ) : events.loading && !events.data ? (
        <div className="lp-skeleton">Loading events…</div>
      ) : rows.length === 0 ? (
        <div className="lp-skeleton">No events match these filters.</div>
      ) : (
        <table className="table lp-table">
          <thead>
            <tr>
              <th scope="col">when</th>
              <th scope="col">level</th>
              <th scope="col">source</th>
              <th scope="col">event</th>
              <th scope="col">work item</th>
              <th scope="col">detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((event, index) => (
              <EventRow key={`${event.ts}-${index}`} event={event} />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function EventRow({ event }: { event: EventRecord }) {
  const ref = eventRef(event);
  return (
    <tr>
      <td className="lp-td-dim lp-mono" title={event.ts}>
        {relativeTime(event.ts)}
      </td>
      <td>
        <span className={`tag ${levelTag(event.level)}`}>{event.level ?? "info"}</span>
      </td>
      <td className="lp-td-dim">{event.source ?? "—"}</td>
      <td className="lp-event-name lp-td-nowrap">{event.event}</td>
      <td className="lp-td-ref">
        {ref ? (
          <button type="button" className="lp-linklike" onClick={() => navigate({ name: "events", ref })}>
            {shortRef(ref)}
          </button>
        ) : (
          "—"
        )}
      </td>
      <td className="lp-event-detail">{describeEvent(event)}</td>
    </tr>
  );
}
