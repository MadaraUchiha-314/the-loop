/**
 * The health word and its popover (issue-283 B10, drawn per issue-327).
 *
 * The design's sidebar footer ends in a mono `● live`; that word is this
 * component — the one answer to "is anything actually watching GitHub right
 * now?": the stream's state (from the one `useStream` the board owns) folded
 * with each daemon's last cycle. A native `<details>` rather than hover
 * state: it opens from the keyboard, stays open while read, and positions
 * itself with CSS alone.
 */

import type { DaemonStatus } from "../api/types.ts";
import { relativeTime } from "../api/model.ts";
import type { StreamState } from "../state/useStream.ts";
import { RefreshIcon } from "./Icons.tsx";
import { ControlButton } from "./primitives.tsx";
import { StatusDot, type DotStatus } from "./StatusDot.tsx";

/** One word for the whole deployment's health, and the dot's colour. */
export function healthTone(daemons: DaemonStatus[], stream: StreamState): { status: DotStatus; label: string } {
  const stopped = daemons.filter((daemon) => !daemon.running);
  if (stream.name === "fallback" || stopped.length > 0) return { status: "blocked", label: "degraded" };
  if (daemons.length === 0) return { status: "pending", label: "unknown" };
  if (stream.name === "live") return { status: "done", label: "live" };
  return { status: "done", label: "healthy" };
}

function streamLine(stream: StreamState): string {
  switch (stream.name) {
    case "off":
      return "Stream off — this browser polls or refreshes manually.";
    case "connecting":
      return "Stream connecting…";
    case "live":
      return `Stream live, connected ${relativeTime(new Date(stream.since).toISOString())}.`;
    case "reconnecting":
      return `Stream reconnecting (attempt ${stream.attempt}).`;
    default:
      return "Stream unavailable — polling instead.";
  }
}

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
    <details className="relative shrink-0">
      <summary
        aria-label={`Service health: ${health.label}`}
        className={`inline-flex items-center gap-1 rounded-md font-mono text-[0.65rem] ${
          health.status === "done" ? "text-state-done" : health.status === "blocked" ? "text-state-blocked" : "text-muted-foreground"
        }`}
      >
        <StatusDot status={health.status} />
        {health.label}
      </summary>
      <div
        role="status"
        aria-live="polite"
        className="absolute bottom-full right-0 z-10 mb-2 w-72 space-y-1.5 rounded-lg border border-border bg-surface px-3 py-2 text-xs text-foreground/90"
      >
        <div>{streamLine(stream)}</div>
        {daemons.length === 0 ? <div className="text-muted-foreground">Daemons unknown — nothing reported yet.</div> : null}
        {daemons.map((daemon) => (
          <div className="flex items-center gap-2" key={daemon.daemon}>
            <StatusDot status={daemon.running ? "done" : "blocked"} />
            <span className="font-mono">{daemon.daemon}</span>
            <span className="text-muted-foreground">
              {daemon.running
                ? daemon.lastCycleAt
                  ? `running · last cycle ${relativeTime(daemon.lastCycleAt)}`
                  : "running"
                : "stopped"}
            </span>
          </div>
        ))}
        <div className="pt-1">
          <ControlButton onClick={onRefresh} className="inline-flex items-center gap-1.5">
            <RefreshIcon className="h-3 w-3" />
            Refresh now
          </ControlButton>
        </div>
      </div>
    </details>
  );
}
