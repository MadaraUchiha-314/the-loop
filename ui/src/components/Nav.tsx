/**
 * The header bar: brand, the three screens, and one health dot.
 *
 * The pre-283 header carried three all-caps daemon chips on every screen, and
 * the stream chip disagreed with Settings about the same connection (B10). Now
 * one dot answers "is anything actually watching GitHub right now?" and a
 * popover carries the detail — the stream's state (from the one `useStream`
 * the board owns, so no second surface can disagree), each daemon's last
 * cycle, and a manual refresh.
 */

import type { DaemonStatus } from "../api/types.ts";
import { hrefFor, type Route } from "../state/route.ts";
import { relativeTime } from "../api/model.ts";
import type { StreamState } from "../state/useStream.ts";

const TABS: { label: string; route: Route }[] = [
  { label: "Work", route: { name: "work" } },
  { label: "Events", route: { name: "events" } },
  { label: "Settings", route: { name: "settings" } },
];

interface NavProps {
  route: Route;
  /** Work items needing a human — the badge on the Work tab. */
  needsYouCount: number;
  daemons: DaemonStatus[];
  stream: StreamState;
  onRefresh: () => void;
}

export function Nav({ route, needsYouCount, daemons, stream, onRefresh }: NavProps) {
  return (
    <nav className="nav lp-nav">
      <div className="lp-nav-brand">
        the-loop <span>control plane</span>
      </div>
      <div className="lp-nav-tabs">
        {TABS.map((tab) => {
          const active =
            tab.route.name === route.name || (tab.route.name === "work" && route.name === "standing");
          return (
            <a key={tab.label} className="lp-tab" href={hrefFor(tab.route)} aria-current={active ? "page" : undefined}>
              {tab.label}
              {tab.route.name === "work" && needsYouCount > 0 ? (
                <span className="lp-tab-badge">{needsYouCount}</span>
              ) : null}
            </a>
          );
        })}
      </div>
      <HealthDot daemons={daemons} stream={stream} onRefresh={onRefresh} />
    </nav>
  );
}

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
function HealthDot({
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
