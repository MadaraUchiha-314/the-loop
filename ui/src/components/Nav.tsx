/**
 * The health word and its popover (issue-283 B10, drawn per issue-327).
 *
 * The design's sidebar footer ends in a mono `● live`; that word is this
 * component — the one answer to "is anything actually watching GitHub right
 * now?": the stream's state (from the one `useStream` the board owns) folded
 * with each daemon's last cycle. A native `<details>` rather than hover
 * state: it opens from the keyboard, stays open while read, and positions
 * itself with CSS alone.
 *
 * On a manager the fleet folds in (issue-374, R5.5): a member that is not
 * `live` degrades the word, and the popover lists each instance with its
 * state beneath the daemon rows.
 */

import type { DaemonStatus, InstanceRow, InstancesDocument } from "../api/types.ts";
import { relativeTime } from "../api/model.ts";
import { t } from "../i18n.ts";
import type { StreamState } from "../state/useStream.ts";
import { RefreshIcon } from "./Icons.tsx";
import { ControlButton } from "./primitives.tsx";
import { StatusDot, type DotStatus } from "./StatusDot.tsx";

/**
 * One word for the whole deployment's health, and the dot's colour. The
 * daemons are the manager's **own** (a member's stopped daemon is that
 * member's problem, reported through its probe); the fleet is every row of
 * `GET /instances`, any of which not `live` degrades the word.
 */
export function healthTone(
  daemons: DaemonStatus[],
  stream: StreamState,
  instances: InstanceRow[] = [],
): { status: DotStatus; label: string } {
  const stopped = daemons.filter((daemon) => !daemon.running);
  const down = instances.filter((row) => row.state !== "live");
  if (stream.name === "fallback" || stopped.length > 0 || down.length > 0) return { status: "blocked", label: t("ui.health.degraded") };
  if (daemons.length === 0) return { status: "pending", label: t("ui.health.unknown") };
  if (stream.name === "live") return { status: "done", label: t("ui.health.live") };
  return { status: "done", label: t("ui.health.healthy") };
}

function streamLine(stream: StreamState): string {
  switch (stream.name) {
    case "off":
      return t("ui.health.stream.off");
    case "connecting":
      return t("ui.health.stream.connecting");
    case "live":
      return t("ui.health.stream.live", { since: relativeTime(new Date(stream.since).toISOString()) });
    case "reconnecting":
      return t("ui.health.stream.reconnecting", { attempt: stream.attempt });
    default:
      return t("ui.health.stream.fallback");
  }
}

/** One popover line per instance: `name · this instance · N managed`, or `name · state · version | detail`. */
export function instanceLine(row: InstanceRow, own: boolean): string {
  if (own) return t("ui.health.instance.own", { count: row.managedCount });
  if (row.state === "live") return row.version ? t("ui.health.instance.live-version", { version: row.version }) : t("ui.health.instance.live");
  return row.detail ? t("ui.health.instance.state-detail", { state: row.state, detail: row.detail }) : row.state;
}

export function HealthDot({
  daemons,
  stream,
  instances,
  onRefresh,
}: {
  daemons: DaemonStatus[];
  stream: StreamState;
  /** The fleet, when the service serves one; absent or empty folds nothing in. */
  instances?: InstancesDocument | undefined;
  onRefresh: () => void;
}) {
  const fleet = instances?.instances ?? [];
  // A manager's `GET /daemons` is the union, each row stamped: the word and the
  // rows are the manager's **own** (R5.5) — a member's daemons are that
  // member's, reported through its probe state beneath. A worker stamps
  // nothing, so every row is its own.
  const own = daemons.filter((daemon) => !daemon.instance || !instances?.name || daemon.instance === instances.name);
  const health = healthTone(own, stream, fleet);
  return (
    <details className="relative shrink-0">
      <summary
        aria-label={t("ui.health.aria", { label: health.label })}
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
        {own.length === 0 ? <div className="text-muted-foreground">{t("ui.health.daemons-unknown")}</div> : null}
        {own.map((daemon) => (
          <div className="flex items-center gap-2" key={`${daemon.instance ?? ""}:${daemon.daemon}`}>
            <StatusDot status={daemon.running ? "done" : "blocked"} />
            <span className="font-mono">{daemon.daemon}</span>
            <span className="text-muted-foreground">
              {daemon.running
                ? daemon.lastCycleAt
                  ? t("ui.health.daemon.running-cycle", { when: relativeTime(daemon.lastCycleAt) })
                  : t("ui.health.daemon.running")
                : t("ui.health.daemon.stopped")}
            </span>
          </div>
        ))}
        {/* The fleet, beneath the daemons (R5.5): each instance with its state
            in words, the own row first as the document orders it. Shown only
            when there is a fleet to show — a worker's single self row would
            say nothing the service line does not. */}
        {instances && (fleet.length > 1 || instances.role === "manager") ? (
          <div className="space-y-1 border-t border-border pt-1.5" data-fleet>
            {fleet.map((row) => (
              <div className="flex items-center gap-2" key={row.name}>
                <StatusDot status={row.state === "live" ? "done" : "blocked"} />
                <span className="font-mono">{row.name}</span>
                <span className="min-w-0 truncate text-muted-foreground" title={row.detail}>
                  {instanceLine(row, row.name === instances.name)}
                </span>
              </div>
            ))}
          </div>
        ) : null}
        <div className="pt-1">
          <ControlButton onClick={onRefresh} className="inline-flex items-center gap-1.5">
            <RefreshIcon className="h-3 w-3" />
            {t("ui.health.refresh")}
          </ControlButton>
        </div>
      </div>
    </details>
  );
}
