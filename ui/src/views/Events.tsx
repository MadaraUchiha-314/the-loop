/**
 * The append-only decision trail — `/api/v1/events` over
 * `<state.root>/logs/events.jsonl`.
 *
 * Filtering is server-side: the route takes `level` as a **minimum**, so
 * choosing `warning` returns warnings and errors, which is what an operator
 * scanning for trouble wants and what `the-loop events` already does.
 */

import { useState } from "react";

import { describeEvent, eventRef, levelTag, shortRef, stampOf } from "../api/model.ts";
import { useApi } from "../state/ApiContext.tsx";
import { useAsync } from "../state/useAsync.ts";

const LEVELS = ["all", "info", "warning", "error"] as const;
type Level = (typeof LEVELS)[number];

export function Events() {
  const { api } = useApi();
  const [level, setLevel] = useState<Level>("all");

  const events = useAsync(
    (signal) => api.events(level === "all" ? { limit: 200 } : { level, limit: 200 }, signal),
    [api, level],
  );

  const rows = (events.data ?? []).toReversed();

  return (
    <>
      <h1 className="lp-h1">Event log</h1>
      <div className="lp-subtle lp-page-note">
        append-only decision trail · /api/v1/events over .the-loop/logs/events.jsonl · level is a minimum, so
        &ldquo;warning&rdquo; includes errors
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
      </div>

      {events.error ? (
        <div className="lp-skeleton">Could not read the event log: {events.error.message}</div>
      ) : events.loading && !events.data ? (
        <div className="lp-skeleton">Loading events…</div>
      ) : rows.length === 0 ? (
        <div className="lp-skeleton">No events at this level.</div>
      ) : (
        <table className="table lp-table">
          <thead>
            <tr>
              <th scope="col">ts</th>
              <th scope="col">level</th>
              <th scope="col">source</th>
              <th scope="col">event</th>
              <th scope="col">work item</th>
              <th scope="col">detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((event, index) => (
              <tr key={`${event.ts}-${index}`}>
                <td className="lp-td-dim lp-mono">{stampOf(event.ts)}</td>
                <td>
                  <span className={`tag ${levelTag(event.level)}`}>{event.level ?? "info"}</span>
                </td>
                <td className="lp-td-dim">{event.source ?? "—"}</td>
                <td className="lp-event-name lp-td-nowrap">{event.event}</td>
                <td className="lp-td-ref">{eventRef(event) ? shortRef(eventRef(event)) : "—"}</td>
                <td className="lp-event-detail">{describeEvent(event)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
