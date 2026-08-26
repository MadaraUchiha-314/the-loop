/**
 * The health dot and its popover.
 *
 * The issue-298 redesign retired the top header bar: the Work screen's sidebar
 * is the navigation (brand block on top, Events and Settings links in the
 * footer), the way the signed-off design draws it. What survives from the old
 * chrome is the one dot that answers "is anything actually watching GitHub
 * right now?" (issue-283 B10) — it now sits in the sidebar footer, with the
 * same popover: the stream's state (from the one `useStream` the board owns,
 * so no second surface can disagree), each daemon's last cycle, and a manual
 * refresh.
 */

import type { DaemonStatus } from "../api/types.ts";
import { relativeTime } from "../api/model.ts";
import type { StreamState } from "../state/useStream.ts";

/** One word for the whole deployment's health, and the tone of the dot. */
function healthTone(daemons: DaemonStatus[], stream: StreamState): { tone: string; label: string } {
  const stopped = daemons.filter((daemon) => !daemon.running);
  if (stream.name === "fallback" || stopped.length > 0) {
    return { tone: "warn", label: "degraded" };
  }
  if (daemons.length === 0) return { tone: "unknown", label: "unknown" };
  return { tone: "ok", label: "healthy" };
}

function streamLine(stream: StreamState): string {
  switch (stream.name) {
    case "off":
      return "Stream: off — this browser polls or refreshes manually.";
    case "connecting":
      return "Stream: connecting…";
    case "live":
      return `Stream: live, connected ${relativeTime(new Date(stream.since).toISOString())}.`;
    case "reconnecting":
      return `Stream: reconnecting (attempt ${stream.attempt}).`;
    default:
      return "Stream: unavailable — polling instead.";
  }
}

/**
 * The dot and its popover (issue-283 B10, feature #8). A native `<details>`
 * rather than hover state: it opens from the keyboard, stays open while the
 * operator reads it, and needs no positioning code beyond CSS.
 */
export function HealthDot({
  daemons,
  stream,
  onRefresh,
}: {
  daemons: DaemonStatus[];
  stream: StreamState;
  onRefresh: () => void;
}) {
  const health = healthTone(daemons, stream);
  return (
    <details className="lp-health">
      <summary aria-label={`Service health: ${health.label}`}>
        <span className={`lp-health-dot ${health.tone}`} aria-hidden="true" />
        <span className="lp-health-word">{health.label}</span>
      </summary>
      <div className="lp-health-pop" role="status" aria-live="polite">
        <div className="lp-health-row">{streamLine(stream)}</div>
        {daemons.length === 0 ? <div className="lp-health-row">Daemons: unknown — nothing reported yet.</div> : null}
        {daemons.map((daemon) => (
          <div className="lp-health-row" key={daemon.daemon}>
            <span className={`lp-health-dot ${daemon.running ? "ok" : "warn"}`} aria-hidden="true" />
            {daemon.daemon}:{" "}
            {daemon.running
              ? daemon.lastCycleAt
                ? `running, last cycle ${relativeTime(daemon.lastCycleAt)}`
                : "running"
              : "stopped"}
          </div>
        ))}
        <button type="button" className="btn btn-secondary lp-health-refresh" onClick={onRefresh}>
          Refresh now
        </button>
      </div>
    </details>
  );
}
