/**
 * The shell (issue-327): the two notices above the columns, the theme, the
 * side panels' open state, and the one board the whole page reads from.
 *
 * Every hash lands on the Work surface — `#/standing` and `#/settings` swap
 * what the main column shows, and the legacy pre-283 routes and `#/events`
 * land on the work column as they did (issue-298). The theme is the stored
 * choice or the browser's preference (state/theme.ts); the side panels start
 * open on a wide viewport and closed on a narrow one, and can be toggled from
 * the header either way.
 */

import { useEffect, useMemo, useState } from "react";

import { ConnectionBanner, DemoBanner } from "./components/Banner.tsx";
import type { Chrome } from "./components/HeaderBar.tsx";
import { DEMO_TITLES } from "./demo/fixture.ts";
import { useApi } from "./state/ApiContext.tsx";
import { navigate, useRoute } from "./state/route.ts";
import { applyTheme, browserPrefersDark, otherTheme, resolveTheme } from "./state/theme.ts";
import { useControlPlane } from "./state/useControlPlane.ts";
import { Work, type Surface } from "./views/Work.tsx";

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
  const board = useControlPlane(api, { mode: settings.refreshMode, pollSeconds: settings.pollSeconds }, selectedRef);

  const surface: Surface = route.name === "settings" ? "settings" : route.name === "standing" ? "standing" : "work";

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

  const serviceLabel = api.isDemo ? "demo fixture · nothing leaves the browser" : `service · ${hostOf(api.baseUrl)}`;

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
        surface={surface}
        onChanged={board.refresh}
        transcriptTick={board.transcriptTick}
        daemons={board.daemons}
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
