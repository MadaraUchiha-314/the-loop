/**
 * The shell (issue-327): the two notices above the columns, the theme, the
 * side panels' open state, and the one board the whole page reads from.
 *
 * Every hash lands on the Work surface — `#/standing`, `#/settings`,
 * `#/instances` and `#/instances/<name>` swap what the main column shows, and
 * the legacy pre-283 routes and `#/events` land on the work column as they
 * did (issue-298). The theme is the stored choice or the browser's preference
 * (state/theme.ts); the side panels start open on a wide viewport and closed
 * on a narrow one, and can be toggled from the header either way.
 *
 * On a manager (issue-374) the board is the fleet's: the sidebar's instance
 * filter lives here so `#/?instance=<name>` — the Instances tab's **Open** —
 * can preset it, and the footer names the role and the fleet's size.
 */

import { useEffect, useMemo, useState } from "react";

import { ConnectionBanner, DemoBanner } from "./components/Banner.tsx";
import type { Chrome } from "./components/HeaderBar.tsx";
import { DEMO_TITLES } from "./demo/fixture.ts";
import { useApi } from "./state/ApiContext.tsx";
import { navigate, useRoute, type Surface } from "./state/route.ts";
import { applyTheme, browserPrefersDark, otherTheme, resolveTheme } from "./state/theme.ts";
import { useControlPlane } from "./state/useControlPlane.ts";
import { Work } from "./views/Work.tsx";

/** Whether the viewport is at least `px` wide; true where `matchMedia` is missing. */
function wideEnough(px: number): boolean {
  try {
    return typeof globalThis.matchMedia !== "function" || globalThis.matchMedia(`(min-width: ${px}px)`).matches;
  } catch {
    return true;
  }
}

export function App() {
  const { api, settings, updateSettings } = useApi();
  const route = useRoute();
  // One stream connection per tab (issue-239 R3.5), owned here rather than by
  // the detail column: the column comes and goes with the route. A legacy
  // `#/events/<ref>` permalink names a work item, so it lands on that item.
  const selectedRef = (route.name === "work" || route.name === "events") && route.ref ? route.ref : "";
  const selectedInstance = route.name === "work" && route.ref ? (route.instance ?? "") : "";
  const board = useControlPlane(api, { mode: settings.refreshMode, pollSeconds: settings.pollSeconds }, selectedRef);

  const surface: Surface =
    route.name === "settings" || route.name === "standing" || route.name === "instances" || route.name === "instance"
      ? route.name
      : "work";
  const instanceName = route.name === "instance" ? route.instance : "";

  // The sidebar's instance filter (issue-374, R5.2): the viewer's pick, which a
  // `#/?instance=<name>` hash presets — the Instances tab's Open lands here.
  const [instanceFilter, setInstanceFilter] = useState(() => (route.name === "work" ? (route.filter ?? "") : ""));
  const presetFilter = route.name === "work" ? route.filter : undefined;
  useEffect(() => {
    if (presetFilter !== undefined) setInstanceFilter(presetFilter);
  }, [presetFilter]);

  // The theme: the stored choice, else the browser's preference (issue-327 R2).
  const theme = resolveTheme(settings.theme, browserPrefersDark());
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // The side panels: open on a wide viewport, closed on a narrow one (R4.6).
  const [sidebarOpen, setSidebarOpen] = useState(() => wideEnough(768));
  const [asideOpen, setAsideOpen] = useState(() => wideEnough(1280));

  const chrome: Chrome = {
    theme,
    onToggleTheme: () => updateSettings({ theme: otherTheme(theme) }),
    sidebarOpen,
    onOpenSidebar: () => setSidebarOpen(true),
  };

  // The poller caches each ticket's title in the portable record (issue-283
  // B1), so a live service serves it; the demo fixture's titles fill the same
  // role for the bundled data.
  const titles = useMemo(() => {
    const map = new Map<string, string>();
    for (const view of board.views) {
      const title = view.record.poll?.title;
      if (title) map.set(view.ref, title);
    }
    return map;
  }, [board.views]);
  const titleFor = (ref: string) => titles.get(ref) ?? (api.isDemo ? DEMO_TITLES[ref] : undefined);

  const serviceLabel = api.isDemo
    ? "demo fixture · nothing leaves the browser"
    : board.instances.role === "manager"
      ? `manager · ${hostOf(api.baseUrl)} · ${board.instances.instances.length} instance${board.instances.instances.length === 1 ? "" : "s"}`
      : `service · ${hostOf(api.baseUrl)}`;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      {api.isDemo ? <DemoBanner onGoLive={() => updateSettings({ mode: "live" })} /> : null}
      {!api.isDemo && board.error ? (
        <ConnectionBanner
          error={board.error}
          baseUrl={api.baseUrl}
          onDemo={() => {
            updateSettings({ mode: "demo" });
            navigate({ name: "work" });
          }}
        />
      ) : null}

      <Work
        views={board.views}
        loading={board.loading}
        titleFor={titleFor}
        selectedRef={selectedRef}
        selectedInstance={selectedInstance}
        surface={surface}
        instanceName={instanceName}
        onChanged={board.refresh}
        transcriptTick={board.transcriptTick}
        daemons={board.daemons}
        instances={board.instances}
        instanceFilter={instanceFilter}
        onInstanceFilter={setInstanceFilter}
        stream={board.stream}
        chrome={chrome}
        panels={{ sidebarOpen, asideOpen, setSidebarOpen, setAsideOpen }}
        serviceLabel={serviceLabel}
      />
    </div>
  );
}

/** `http://127.0.0.1:8787` → `127.0.0.1:8787`, for the footer's one line. */
function hostOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl;
  }
}
