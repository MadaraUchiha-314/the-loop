/**
 * The header bar: brand, the screens, and the daemon chips.
 *
 * The chips are the answer to "is anything actually watching GitHub right now?"
 * — a board full of stale rows and a stopped poller look identical without
 * them, which is why they sit in the chrome rather than on a page.
 */

import type { DaemonStatus } from "../api/types.ts";
import { hrefFor, type Route } from "../state/route.ts";
import { relativeTime } from "../api/model.ts";
import type { StreamState } from "../state/useStream.ts";

const TABS: { label: string; route: Route }[] = [
  { label: "Dashboard", route: { name: "dashboard" } },
  { label: "Sessions", route: { name: "sessions" } },
  { label: "Standing", route: { name: "standing" } },
  { label: "Attention", route: { name: "attention" } },
  { label: "Events", route: { name: "events" } },
  { label: "Settings", route: { name: "settings" } },
];

interface NavProps {
  route: Route;
  attentionCount: number;
  daemons: DaemonStatus[];
  stream: StreamState;
}

export function Nav({ route, attentionCount, daemons, stream }: NavProps) {
  return (
    <nav className="nav lp-nav">
      <div className="lp-nav-brand">
        the-loop <span>/ control plane</span>
      </div>
      <div className="lp-nav-tabs">
        {TABS.map((tab) => {
          // The detail page is a child of the dashboard, so the tab stays lit.
          const active = tab.route.name === route.name || (tab.route.name === "dashboard" && route.name === "detail");
          return (
            <a
              key={tab.label}
              className="lp-tab"
              href={hrefFor(tab.route)}
              aria-current={active ? "page" : undefined}
            >
              {tab.label}
              {tab.route.name === "attention" && attentionCount > 0 ? ` (${attentionCount})` : ""}
            </a>
          );
        })}
      </div>
      <div className="lp-daemons">
        <StreamChip state={stream} />
        {daemons.length === 0 ? <span className="lp-daemon">daemons · unknown</span> : null}
        {daemons.map((daemon) => (
          <span className="lp-daemon" key={daemon.daemon}>
            <span className={`lp-daemon-dot ${daemon.running ? "on" : "off"}`} aria-hidden="true" />
            {daemon.daemon} ·{" "}
            {daemon.running
              ? daemon.lastCycleAt
                ? `last cycle ${relativeTime(daemon.lastCycleAt)}`
                : "running"
              : "stopped"}
          </span>
        ))}
      </div>
    </nav>
  );
}

/**
 * Whether the screen is live, and if not, why (issue-239, R4.3).
 *
 * It sits with the daemon chips because it answers the same question they do —
 * "is anything actually keeping this page current?" — and it is **text plus a
 * dot**, never a dot alone, so the state survives being read by someone who
 * cannot see the colour. `aria-live="polite"` announces a change without
 * stealing focus from whatever the operator was doing.
 *
 * Nothing is rendered while the viewer chose polling or manual: a chip saying
 * "not streaming" on a page nobody asked to stream is noise.
 */
function StreamChip({ state }: { state: StreamState }) {
  if (state.name === "off") return null;
  const [tone, text] =
    state.name === "live"
      ? (["on", `live · connected ${relativeTime(new Date(state.since).toISOString())}`] as const)
      : state.name === "connecting"
        ? (["", "stream · connecting"] as const)
        : state.name === "reconnecting"
          ? (["off", `stream · reconnecting (${state.attempt})`] as const)
          : (["off", "stream unavailable · polling instead"] as const);

  return (
    <span className="lp-daemon" role="status" aria-live="polite" title={state.name === "fallback" ? state.advice : undefined}>
      <span className={`lp-daemon-dot ${tone}`} aria-hidden="true" />
      {text}
    </span>
  );
}
