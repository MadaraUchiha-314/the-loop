/**
 * The header bar: brand, the four screens, and the daemon chips.
 *
 * The chips are the answer to "is anything actually watching GitHub right now?"
 * — a board full of stale rows and a stopped poller look identical without
 * them, which is why they sit in the chrome rather than on a page.
 */

import type { DaemonStatus } from "../api/types.ts";
import { hrefFor, type Route } from "../state/route.ts";
import { relativeTime } from "../api/model.ts";

const TABS: { label: string; route: Route }[] = [
  { label: "Dashboard", route: { name: "dashboard" } },
  { label: "Sessions", route: { name: "sessions" } },
  { label: "Attention", route: { name: "attention" } },
  { label: "Events", route: { name: "events" } },
  { label: "Settings", route: { name: "settings" } },
];

interface NavProps {
  route: Route;
  attentionCount: number;
  daemons: DaemonStatus[];
}

export function Nav({ route, attentionCount, daemons }: NavProps) {
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
